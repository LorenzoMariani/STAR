"""Merge the NASA Small Spacecraft Technology State of the Art tables (audit/nasa_tables/*.csv, made by nasa_extract_tables.py)
into the catalogue, conservatively.

Tables merged: 3-8 (EPS/PMAD), 5-3 (reaction wheels), 5-7 (sun sensors). Every other table is only listed in
audit/nasa_candidates.csv (no catalogue category, required fields missing, or unreliable columns).

Rules (no value is estimated):
  * existing component (same vendor + product, token-wise name match): only fields that are null are filled, with the
    table value when it is a plain number; the fill is appended to `notes`;
  * new component: added only when mass_kg is a plain number (otherwise it is not selectable); fields the table does not
    give stay null; source = NASA report table, verified false;
  * a product whose name matches a component of ANOTHER vendor is not added (possible duplicate, reported);
  * reaction wheel momentum/torque are used only for vendors whose existing catalogue values agree with the table
    (the table mixes N m and mN m units);
  * 8-4 (OBC) rows are split over several lines in the PDF: candidates only.
Writes audit/nasa_updates.csv (what was added / filled) and audit/nasa_candidates.csv (everything else). Idempotent.

usage (base anaconda): python tools/add_nasa_components.py
"""
import csv
import json
import re
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent
CAT = PROJ / "data" / "catalog.json"
TABLES = PROJ / "audit" / "nasa_tables"
RET = "2026-10-23"
URL = "https://www.nasa.gov/smallsat-institute/sst-soa/"
TAG = "NASA SoA"
COUNTRIES = ("The Netherlands", "Netherlands", "Czech Republic", "South Africa", "South Aftri", "South Korea", "Germany", "GmBH Germany",
             "Italy", "Sweden", "Belgium", "USA", "Luxembourg", "Hungary", "Spain", "Turkey", "Istanbul", "Denmark", "Lithuania",
             "Poland", "Slovenia", "Bulgaria", "France", "Chile", "Quebec", "Argentina", "Australia", "Busan")
PLAIN = re.compile(r"^\s*(\d+(?:\.\d+)?(?:[eE]-?\d+)?)\s*$")
# deliberately null in the catalogue (the vendor datasheet gives only per-channel currents, tests/test_new_data.py)
KEEP_NULL = {(f"isis-iceps2-type-{x}", "output_power_w_max") for x in "abc"}
MERGED = {"3-8": "eps", "5-3": "reaction_wheel", "5-7": "sun_sensor"}


def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def tokens(s):
    return [t for t in re.split(r"[^a-z0-9]+", s.lower()) if t]


def plain(s):
    m = PLAIN.match(s or "")
    return float(m.group(1)) if m else None


VENDOR_FIX = (("Emxys", "Emxys"), ("C3S Electronics", "C3S Electronics Development"), ("Ecarver", "Ecarver"),
              ("Pumpkin Space Systems", "Pumpkin"), ("Redwire Space", "Redwire Space"))


def vendor_main(v):
    v = v.strip()
    for start, fixed in VENDOR_FIX:
        if v.startswith(start):
            return fixed
    for c in sorted(COUNTRIES, key=len, reverse=True):
        if v.endswith(" " + c):
            v = v[: -len(c)].strip()
    return v


def slug(s):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s.lower())).strip("-")


def token_match(nasa_name, cat_name):
    a, b = tokens(nasa_name), tokens(cat_name)
    return bool(a) and b[: len(a)] == a


def find(comps, cat, vendor, name):
    """-> (existing in the same vendor, name match in another vendor)"""
    same, other = None, None
    for c in comps:
        if c["category"] != cat or not token_match(name, c["name"]):
            continue
        if norm(c["vendor"].split("(")[0]) and norm(vendor).startswith(norm(c["vendor"].split("(")[0])):
            same = same or c
        else:
            other = other or c
    return same, other


def note_add(c, text):
    c["notes"] = (c.get("notes") or "").rstrip() + (" " if c.get("notes") else "") + text


def source(table, page):
    return {"url": URL, "document": f"NASA Small Spacecraft Technology State of the Art, Table {table} (PDF p. {page}, NASA platform soa-2026.pdf)",
            "retrieved": RET, "verified": False, "method": "trascritto da tabella NASA SoA; da controllare"}


def read(t):
    with open(TABLES / f"table_{t}.csv", encoding="utf-8", newline="") as f:
        r = list(csv.reader(f))
    return r[0], r[1:]


def parse_outputs(s):
    """fixed output voltages from strings like '3.3V; 5V; 12V' or '3.3/5/12/Batt' (Batt/Unreg ignored); None if nothing clean"""
    if not s or "*" in s:
        return None
    out = []
    for tok in re.split(r"[;/,]| and ", s):
        tok = tok.strip().rstrip("V").strip()
        v = plain(tok)
        if v is not None and v > 0:
            out.append([v, v])
    return out or None


def deg(s):
    """full angle in degrees from '110°', '±60° per axis', '128° x 128°'; None if not clean or < 5 deg"""
    if not s:
        return None
    m = re.match(r"^\s*(±)?\s*(\d+(?:\.\d+)?)\s*°(?:\s*(?:per axis|full cone|\(.*\)))?\s*$", s)
    if m:
        v = float(m.group(2)) * (2 if m.group(1) else 1)
        return [v] if v >= 5 else None
    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*°\s*[x×]\s*(\d+(?:\.\d+)?)\s*°\s*$", s)
    if m:
        return [float(m.group(1)), float(m.group(2))]
    return None


def acc_deg(s):
    m = re.match(r"^\s*(?:±)?\s*(\d+(?:\.\d+)?)\s*°\s*$", s or "")
    return float(m.group(1)) if m else None


def main():
    data = json.loads(CAT.read_text(encoding="utf-8"))
    comps = data["components"]
    ids = {c["id"] for c in comps}
    upd_path = PROJ / "audit" / "nasa_updates.csv"
    updates = []
    if upd_path.exists():  # keep the log of earlier runs (a rerun changes nothing)
        with open(upd_path, encoding="utf-8-sig", newline="") as f:
            updates = list(csv.reader(f))[1:]
    cands = []
    seen = set()

    def cand(t, sub, page, row, status, reason):
        cands.append([t, sub, page, status, reason, " | ".join(row)])

    def log(action, c, field, value, t, page):
        updates.append([action, c["id"], c["category"], field, value, f"Table {t} PDF p.{page}"])

    def fill(c, field, value, t, page, spec=False):
        tgt = c["specs"] if spec else c
        if value is None or tgt.get(field) is not None or (c["id"], field) in KEEP_NULL:
            return False
        tgt[field] = value
        log("fill", c, field, value, t, page)
        return True

    # reaction wheel unit trust, per vendor, from components already in the catalogue
    rw_trust = {}
    hdr, rows = read("5-3")
    for r in rows:
        vend, name = vendor_main(r[3]), r[4]
        same, _ = find(comps, "reaction_wheel", vend, name)
        if not same:
            continue
        for key, col, f in (("mom", 8, "momentum_mnms"), ("tor", 7, "max_torque_mnm")):
            nv, cv = plain(r[col]), same["specs"].get(f)
            if nv is None or cv is None:
                continue
            ok = abs(nv * 1000 - cv) <= 0.05 * cv
            rw_trust.setdefault((norm(vend), key), []).append(ok)
    trusted = {k: all(v) for k, v in rw_trust.items()}

    for t in sorted({p.stem[6:] for p in TABLES.glob("table_*.csv")}, key=lambda s: tuple(map(int, s.split("-")))):
        hdr, rows = read(t)
        cat = MERGED.get(t)
        for r in rows:
            sub, page = r[1], r[2]
            if cat is None:
                cand(t, sub, page, r[3:], "candidate",
                     "OBC rows span several lines in the PDF" if t == "8-4" else
                     "no merge rule: required catalogue fields missing or no matching category")
                continue
            if cat == "eps":
                vend, name, mass = vendor_main(r[3]), r[4], plain(r[5])
                pw, eff = plain(r[7]), plain(r[10])
                spec = {"output_power_w_max": pw, "efficiency": eff / 100 if eff and eff <= 100 else None,
                        "output_voltage_ranges_v": parse_outputs(r[9])}
                top = {"mass_kg": mass}
                extra = {}
            elif cat == "reaction_wheel":
                vend, name, mass = vendor_main(r[3]), r[4], plain(r[5])
                nv = norm(vend)
                mom = plain(r[8]) if trusted.get((nv, "mom")) else None
                tor = plain(r[7]) if trusted.get((nv, "tor")) else None
                spec = {"momentum_mnms": mom * 1000 if mom is not None else None,
                        "max_torque_mnm": tor * 1000 if tor is not None else None,
                        "power_w_peak": plain(r[6])}
                tid = plain(r[10])
                top = {"mass_kg": mass, "tid_krad": tid}
                if r[9].strip() not in ("1", "1/3/4 (Pyramid)"):
                    cand(t, sub, page, r[3:], "candidate", f"not a single wheel ('{r[9]}')")
                    continue
            else:  # sun_sensor
                vend, name, mass = vendor_main(r[3]), r[4], plain(r[6])
                stype = r[5].lower()
                kind = "fine" if "fine" in stype else "coarse" if "coarse" in stype else None
                fov = deg(r[9])
                spec = {"sensor_type": kind, "fov_deg": fov, "accuracy_deg": acc_deg(r[10]), "accuracy_basis": "3-sigma" if acc_deg(r[10]) is not None else None,
                        "data_interfaces": ["analogue"] if r[8].strip() == "Analog" else None}
                top = {"mass_kg": mass, "power_w": plain(r[7])}
            key = (cat, norm(vend), norm(name))
            if key in seen:
                cand(t, sub, page, r[3:], "candidate", "duplicate row in the table")
                continue
            seen.add(key)
            same, other = find(comps, cat, vend, name)
            if same:
                if cat == "sun_sensor" and same["specs"].get("accuracy_deg") is not None:
                    spec["accuracy_basis"] = None  # the basis belongs to the accuracy value already in the catalogue
                n = sum(fill(same, f, v, t, page) for f, v in top.items()) + sum(fill(same, f, v, t, page, True) for f, v in spec.items())
                if n:
                    note_add(same, f"{TAG} 2025 Table {t} (PDF p.{page}) filled {n} field(s) that were not declared; existing values kept.")
                else:
                    note_add(same, f"Also listed in {TAG} 2025 Table {t} (PDF p.{page}).") if f"Table {t} (PDF p.{page})" not in (same.get("notes") or "") else None
                continue
            if other:
                cand(t, sub, page, r[3:], "possible_duplicate", f"name matches {other['id']} of another vendor")
                continue
            if mass is None or mass <= 0:
                cand(t, sub, page, r[3:], "candidate", "no plain mass value: not selectable")
                continue
            cid = slug(vend) + "-" + slug(name)
            if cid in ids:
                cand(t, sub, page, r[3:], "candidate", f"id {cid} already used")
                continue
            ids.add(cid)
            base = {"id": cid, "category": cat, "vendor": vend, "name": name + (" reaction wheel" if cat == "reaction_wheel" else ""),
                    "mass_kg": mass, "source": source(t, page),
                    # no dimensions and no image: shape from the subsystem, as add_shapes.default_for
                    "shape": {"type": "cylinder" if cat == "reaction_wheel" else "box", "axis": None, "basis": "subsystem", "set": RET}}
            for f, v in top.items():
                if f != "mass_kg" and v is not None:
                    base[f] = v
            full = {f: None for f in {
                "eps": ["compatible_form_factors_u", "pv_channels", "pv_voltage_v", "pv_power_w_max", "battery_voltage_v", "battery_families",
                        "integrated_battery_wh", "integrated_battery_voltage_v", "output_voltage_ranges_v", "output_power_w_max", "data_interfaces",
                        "efficiency", "integrated_heater_w"],
                "reaction_wheel": ["momentum_mnms", "form_factor_range_u", "max_torque_mnm", "max_speed_rpm", "power_w_nominal", "power_w_peak",
                                   "supply_voltage_ranges_v", "data_interfaces"],
                "sun_sensor": ["sensor_type", "fov_deg", "accuracy_deg", "accuracy_basis", "update_rate_hz", "data_interfaces",
                               "supply_voltage_ranges_v"]}[cat]}
            full.update({k: v for k, v in spec.items() if v is not None})
            base["specs"] = full
            base["notes"] = (f"Transcribed from {TAG} 2025 Table {t} (PDF p.{page}); not checked against a vendor datasheet. "
                             "Fields the table does not give are null (not declared), not estimated.")
            comps.append(base)
            log("add", base, "-", f"{vend} {name}", t, page)

    CAT.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    with open(upd_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["action", "id", "category", "field", "value", "source"])
        w.writerows(updates)
    with open(PROJ / "audit" / "nasa_candidates.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["table", "subsystem", "pdf_page", "status", "reason", "row"])
        w.writerows(cands)
    adds = sum(1 for u in updates if u[0] == "add")
    fills = sum(1 for u in updates if u[0] == "fill")
    print(f"added {adds}, filled {fills} fields, candidates {len(cands)}; catalogue {len(comps)} components")


if __name__ == "__main__":
    main()

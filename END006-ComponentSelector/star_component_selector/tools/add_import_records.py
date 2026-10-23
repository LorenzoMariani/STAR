"""Merge the records extracted from the imported datasheets (audit/import_records/<category>.json) into the catalogue. Idempotent.

A record = one product in one PDF of datasheets/<folder>/:
  {"file": "magnetorquer/X.pdf", "action": "add" | "update" | "skip", "id": ..., "vendor": ..., "name": ..., "family": ..., "document": "title and date",
   "mass_kg", "power_w", "tid_krad", "temp_op_c", "trl", "flight_heritage", "dimensions_mm": [a, b, c], "notes": "...", "specs": {declared values only},
   "reason": "for skip"}
  * add: new component. Every spec key of the category is present (null = not declared); a missing required spec -> not added, listed in
    audit/import_skipped.csv. source = the vendor URL of the PDF (audit/import_stage.csv), verified false; datasheet = the PDF in its folder;
    shape from the category (subsystem default).
  * update: existing component `id`: only fields that are null are filled, conflicts (different declared value) are NOT applied and are listed in
    audit/import_updates.csv; the datasheet is linked when the component has none.
  * skip: nothing is written (documents without product data, duplicates of a document already used), reason in audit/import_skipped.csv.
Values are only the ones the datasheet declares, in the units of the schema; nothing is estimated.

usage (base anaconda): python tools/add_import_records.py [<category> ...]     (default: every file of audit/import_records/)
"""
import csv
import json
import sys
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJ))
from star_selector.models import AXIS_SHAPES, CATEGORIES, SPEC_FIELDS, validate_component  # noqa: E402

RET = "2026-10-23"
METHOD = "trascritto da datasheet del fornitore; da controllare manualmente"
COMMON = ("mass_kg", "power_w", "tid_krad", "temp_op_c", "trl", "flight_heritage")


def stage_urls():
    """final file name -> (url, origin)"""
    urls = {}
    with open(PROJ / "audit" / "import_stage.csv", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            urls[r["file"]] = (r["url"] or None, r["origin"])
    final = {}
    with open(PROJ / "audit" / "selezione_review.csv", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            old = r["from"].split("/", 1)[1]
            new = r["to"].split("/", 1)[1]
            if old in urls:
                final[new] = urls[old]
    for k, v in urls.items():
        final.setdefault(k, v)
    return final


def shape_for(category, rec, specs):
    if category == "structure":
        kind, axis = "frame", None
    elif category == "magnetorquer":
        kind, axis = ("rod", "long") if specs.get("magnetorquer_type") == "rod" else ("coil_board", "long")
    elif category == "reaction_wheel":
        kind, axis = "cylinder", "short"
    elif category in ("gps", "gnss_antenna"):
        kind, axis = ("board", None) if category == "gps" else ("box", None)
    else:
        kind, axis = "box", None
    idx = None
    dims = rec.get("dimensions_mm")
    if axis and dims and all(v is not None for v in dims):
        idx = max(range(3), key=lambda k: (dims[k], -k)) if axis == "long" else min(range(3), key=lambda k: (dims[k], k))
    return {"type": kind, "axis": idx, "basis": "subsystem", "set": RET}


def wheel_shape(dims):
    """published wheel size -> (type, axis): disc when much flatter than wide, else can; the rotation axis is the shortest size"""
    ordered = sorted(dims)
    return ("wheel_disc" if ordered[0] < 0.5 * ordered[1] else "wheel_can"), min(range(3), key=lambda k: (dims[k], k))


def load_csv(path):
    if path.exists():
        with open(path, encoding="utf-8-sig", newline="") as f:
            return list(csv.reader(f))[1:]
    return []


def save_csv(path, header, rows):
    seen, out = set(), []
    for r in rows:
        t = tuple(map(str, r))
        if t not in seen:
            seen.add(t)
            out.append(r)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(out)


def main():
    cats = sys.argv[1:] or sorted(p.stem for p in (PROJ / "audit" / "import_records").glob("*.json"))
    data = json.loads((PROJ / "data" / "catalog.json").read_text(encoding="utf-8"))
    comps = data["components"]
    by_id = {c["id"]: c for c in comps}
    urls = stage_urls()
    upd_path, skip_path = PROJ / "audit" / "import_updates.csv", PROJ / "audit" / "import_skipped.csv"
    upd, skipped = load_csv(upd_path), load_csv(skip_path)
    n_add = n_upd = n_skip = 0

    def pdf_info(rec):
        path = PROJ / "datasheets" / rec["file"]
        if not path.is_file():
            raise SystemExit(f"PDF not found: {path}")
        return path

    for cat_file in cats:
        for rec in json.loads((PROJ / "audit" / "import_records" / f"{cat_file}.json").read_text(encoding="utf-8")):
            act, fname = rec["action"], Path(rec["file"]).name
            if act == "skip":
                skipped.append([rec["file"], rec.get("name", ""), "skip", rec["reason"]])
                n_skip += 1
                continue
            path = pdf_info(rec)
            ds = {"file": f"datasheets/{rec['file']}", "document": rec["document"], "source_url": urls.get(fname, (None, None))[0],
                  "retrieved": RET, "bytes": path.stat().st_size}
            if act == "update":
                c = by_id[rec["id"]]
                for k in COMMON:
                    if rec.get(k) is not None:
                        if c.get(k) is None:
                            c[k] = rec[k]
                            upd.append([c["id"], k, "", rec[k], "filled", rec["file"]])
                        elif c[k] != rec[k]:
                            upd.append([c["id"], k, c[k], rec[k], "conflict (not applied)", rec["file"]])
                for k, v in (rec.get("specs") or {}).items():
                    if v is None:
                        continue
                    if c["specs"].get(k) is None:
                        c["specs"][k] = v
                        upd.append([c["id"], f"specs.{k}", "", v, "filled", rec["file"]])
                    elif c["specs"][k] != v:
                        upd.append([c["id"], f"specs.{k}", c["specs"][k], v, "conflict (not applied)", rec["file"]])
                if rec.get("dimensions_mm") and not c.get("dimensions"):
                    c["dimensions"] = {"mm": rec["dimensions_mm"], "basis": "declared", "note": f"{rec['document']}."}
                    upd.append([c["id"], "dimensions", "", rec["dimensions_mm"], "filled", rec["file"]])
                    sh = c.get("shape") or {}
                    if sh.get("type") in AXIS_SHAPES and sh.get("axis") is None and all(v is not None for v in rec["dimensions_mm"]):
                        d = rec["dimensions_mm"]       # rotation axis of a wheel = shortest size, the axis of the other shapes = longest
                        sh["axis"] = min(range(3), key=lambda k: (d[k], k)) if c["category"] == "reaction_wheel" else max(range(3), key=lambda k: (d[k], -k))
                        if c["category"] == "reaction_wheel":
                            sh["type"], sh["axis"] = wheel_shape(d)
                if not c.get("datasheet"):
                    if ds["source_url"] != c["source"]["url"]:      # reference document: not the page cited as source
                        ds = {**ds, "origin": urls.get(fname, (None, None))[1] or f"datasheets/{rec['file']}", "vendor_url": ds["source_url"], "source_url": None}
                    c["datasheet"] = ds
                    upd.append([c["id"], "datasheet", "", ds["file"], "linked", rec["file"]])
                if rec.get("notes") and rec["notes"] not in (c.get("notes") or ""):
                    c["notes"] = ((c.get("notes") or "") + " " + rec["notes"]).strip()
                n_upd += 1
                continue
            # add
            if rec["id"] in by_id:
                continue                                    # already merged (idempotent)
            cat = rec["category"]
            assert cat in CATEGORIES, cat
            specs = {k: None for k in SPEC_FIELDS[cat]}
            specs.update(rec.get("specs") or {})
            url, origin = urls.get(fname, (None, None))
            vendor_url = None
            if url and not url.startswith("https://"):      # the catalogue test wants https sources: keep the plain-http link as vendor_url
                vendor_url, url = url, None
                ds = {**ds, "origin": origin or f"datasheets/{rec['file']}", "vendor_url": ds["source_url"], "source_url": None}
            comp = {"id": rec["id"], "category": cat, "vendor": rec["vendor"], "name": rec["name"]}
            if rec.get("family"):
                comp["family"] = rec["family"]
            for k in COMMON:
                if rec.get(k) is not None:
                    comp[k] = rec[k]
            if rec.get("notes"):
                comp["notes"] = rec["notes"]
            comp["source"] = {"url": url, "document": rec["document"], "retrieved": RET, "verified": False, "method": METHOD}
            if url is None:
                comp["source"]["origin"] = origin or f"datasheets/{rec['file']}"
                if vendor_url:
                    comp["source"]["vendor_url"] = vendor_url
            comp["specs"] = specs
            if rec.get("dimensions_mm"):
                comp["dimensions"] = {"mm": rec["dimensions_mm"], "basis": "declared", "note": f"{rec['document']}."}
            comp["datasheet"] = ds
            comp["shape"] = shape_for(cat, rec, specs)
            if cat == "reaction_wheel" and rec.get("dimensions_mm") and all(v is not None for v in rec["dimensions_mm"]):
                comp["shape"]["type"], comp["shape"]["axis"] = wheel_shape(rec["dimensions_mm"])
            errs = validate_component(comp)
            if errs:
                skipped.append([rec["file"], rec["name"], "not added", "; ".join(e.split(": ", 1)[1] for e in errs)])
                continue
            comps.append(comp)
            by_id[comp["id"]] = comp
            upd.append([comp["id"], "-", "", rec["name"], "added", rec["file"]])
            n_add += 1
    (PROJ / "data" / "catalog.json").write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    save_csv(upd_path, ["id", "field", "old", "new", "action", "file"], upd)
    save_csv(skip_path, ["file", "name", "action", "reason"], skipped)
    print(f"added {n_add}, updated {n_upd}, skipped {n_skip}; catalogue {len(comps)} components")


if __name__ == "__main__":
    main()

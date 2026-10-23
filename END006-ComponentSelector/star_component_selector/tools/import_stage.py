"""Selection folders for the imported datasheets: the user keeps the wanted PDFs, deletes the others.

Moves the copies made by apply_datasheet_renames.py from datasheets/ to
Datasheet_CubeSat_1U-12U/_selezione/<category>/ by a keyword guess on the file name and the first two pages:
one folder per catalogue category, _incerti/ (no guess), _senza_testo/ (no text layer) and _fuori_ambito/
(deployers, whole platforms, ground segment, non-space vendors). The folder the user leaves a PDF in is its
category. The old datasheets of the catalogue stay in datasheets/; the old ones no component uses are COPIED
into the selection too. Idempotent: files already moved are skipped. Writes audit/import_stage.csv.

usage (star env, needs pypdf): python tools/import_stage.py
"""
import csv
import json
import logging
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

from pypdf import PdfReader

PROJ = Path(__file__).resolve().parent.parent
DS = PROJ / "datasheets"
STAGE = PROJ / "Datasheet_CubeSat_1U-12U" / "_selezione"
OUT = PROJ / "audit" / "import_stage.csv"
sys.path.insert(0, str(PROJ))
from star_selector.models import CATEGORIES  # noqa: E402

logging.getLogger("pypdf").setLevel(logging.ERROR)

# category -> keywords (regex, matched on lower-case text); title/file-name hits weigh 3, text hits 1 (max 3 each)
KEYWORDS = {
    "structure": [r"structure", r"chassis", r"cubesat kit", r"\brails?\b", r"\bframe\b"],
    "obc": [r"on-?board computer", r"\bobc\b", r"flight computer", r"payload processor", r"data handling", r"processor board"],
    "eps": [r"\beps\b", r"power system", r"electrical power", r"power distribution", r"\bpcdu\b", r"power conditioning", r"\bmppt\b"],
    "battery": [r"battery", r"batteries", r"li-?ion", r"lithium", r"battery pack"],
    "solar_panel": [r"solar panel", r"solar array", r"solar cell", r"solar wing"],
    "comms": [r"transceiver", r"transmitter", r"\bradio\b", r"\bmodem\b", r"s-band", r"x-band", r"\buhf\b", r"\bvhf\b", r"ka-band", r"ku-band"],
    "antenna": [r"antenna", r"\bpatch\b", r"helix", r"\bhorn\b", r"dipole", r"monopole", r"turnstile"],
    "adcs": [r"\badcs\b", r"attitude determination", r"attitude control"],
    "magnetorquer": [r"magnetorquer", r"torque ?rod", r"torquer", r"magnetic torq"],
    "reaction_wheel": [r"reaction wheel", r"momentum wheel"],
    "star_tracker": [r"star tracker", r"star sensor", r"startracker"],
    "sun_sensor": [r"sun sensor", r"fine sun", r"coarse sun"],
    "gps": [r"gnss receiver", r"gps receiver", r"\bgnss\b", r"\bgps\b"],
    "gnss_antenna": [r"gnss antenna", r"gps antenna", r"gps patch"],
    "propulsion": [r"thruster", r"propulsion", r"specific impulse", r"total impulse", r"propellant", r"\bisp\b"],
    "heater": [r"heater", r"thermofoil"],
    "payload": [r"camera", r"imager", r"multispectral", r"hyperspectral", r"telescope", r"\bsar\b", r"\bais\b", r"ads-b",
                r"optical terminal", r"laser comm", r"spectrometer", r"lidar"],
}
OUT_TITLE = {  # out of scope when the file name or the title says so
    "deployer / launch": r"deployer|dispenser|separation system|launch service|rideshare|canisteri[sz]ed|launch adapter|\bpod\b",
    "whole platform": r"satellite bus|spacecraft bus|satellite platform|spacecraft platform|\bplatform\b|mission services",
}
GROUND = r"ground station|ground segment|earth station|teleport|\bvsat\b|rack[- ]?mount|indoor unit|outdoor unit|block up-?converter|\bbuc\b|\blnb\b"
NON_SPACE_VENDORS = ("faulhaber", "bartington", "harmonicdrive", "work-microwave", "etlsystems", "enersys", "mrcy")
CUBESAT = re.compile(r"cubesat|nanosat|smallsat|small sat|\b(?:0\.5|1|1\.5|2|3|6|8|12|16|24)\s?u\b")


def first_pages(path, n=2):
    try:
        rd = PdfReader(str(path))
        return " ".join((rd.pages[i].extract_text() or "") for i in range(min(n, len(rd.pages))))
    except Exception:  # noqa: BLE001 - unreadable PDFs go to _senza_testo
        return ""


def guess(name, text):
    """(folder, reason) for one PDF."""
    head = re.sub(r"[_\-]+", " ", name.lower())
    body = re.sub(r"\s+", " ", text.lower())
    title = head + " " + body[:200]
    if len(body.strip()) < 50:
        return "_senza_testo", "no text layer (scanned or unreadable PDF)"
    cubesat = bool(CUBESAT.search(head + " " + body))
    for why, rx in OUT_TITLE.items():
        if re.search(rx, title):
            return "_fuori_ambito", why
    if any(v in name.lower() for v in NON_SPACE_VENDORS) and not cubesat:
        return "_fuori_ambito", "vendor without CubeSat products"
    if len(re.findall(GROUND, body)) >= 2 and not cubesat:
        return "_fuori_ambito", "ground segment"
    score = Counter()
    for cat, rxs in KEYWORDS.items():
        for rx in rxs:
            score[cat] += 3 * min(3, len(re.findall(rx, title))) + min(3, len(re.findall(rx, body)))
    if score["gnss_antenna"]:
        score["antenna"] = 0
    best = score.most_common(2)
    if not best or best[0][1] == 0:
        return "_incerti", "no category keyword"
    if len(best) > 1 and best[1][1] == best[0][1]:
        return "_incerti", f"tie {best[0][0]} / {best[1][0]}"
    return best[0][0], f"keywords (score {best[0][1]}{', mentions CubeSat' if cubesat else ''})"


def main():
    rows = list(csv.DictReader(open(PROJ / "audit" / "import_rename_map.csv", encoding="utf-8-sig")))
    inv = {r["file"]: r for r in csv.DictReader(open(PROJ / "audit" / "import_inventory.csv", encoding="utf-8-sig"))}
    items = [(r["new"], "move", r["site"] + "/" + r["old"], (inv.get(r["old"]) or {}).get("url", ""))
             for r in rows if r["datasheets"] == "copied"]
    catalog = json.loads((PROJ / "data" / "catalog.json").read_text(encoding="utf-8"))["components"]
    used = {c["datasheet"]["file"].split("/", 1)[1] for c in catalog if c.get("datasheet")}
    new = {i[0] for i in items}
    for p in sorted(DS.glob("*.pdf")):
        if p.name not in new and p.name not in used:
            items.append((p.name, "copy", "datasheets/" + p.name, ""))

    for folder in list(CATEGORIES) + ["_incerti", "_senza_testo", "_fuori_ambito"]:
        (STAGE / folder).mkdir(parents=True, exist_ok=True)
    staged = {p.name: p.parent.name for p in STAGE.glob("*/*.pdf")}
    out, count = [], Counter()
    for name, how, origin, url in items:
        if name in staged:
            folder, reason = staged[name], "already staged"
        else:
            src = DS / name
            if not src.exists():
                print(f"missing: {name}")
                continue
            folder, reason = guess(name, first_pages(src))
            dst = STAGE / folder / name
            shutil.move(src, dst) if how == "move" else shutil.copy2(src, dst)
        count[folder] += 1
        out.append({"file": name, "folder": folder, "reason": reason, "action": how, "origin": origin, "url": url})

    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["file", "folder", "reason", "action", "origin", "url"])
        w.writeheader()
        w.writerows(out)
    for k, v in sorted(count.items(), key=lambda kv: (kv[0].startswith("_"), -kv[1])):
        print(f"{k:16s} {v}")
    print(f"total {sum(count.values())} -> {STAGE}")


if __name__ == "__main__":
    main()

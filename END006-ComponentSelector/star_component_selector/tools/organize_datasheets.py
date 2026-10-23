"""Move the loose PDFs of datasheets/ into the category sub-folders and update every reference.

datasheets/<folder>/ now holds the PDFs by category (adcs, antenna, ..., imaging_cameras, satellite_components, ...). The PDFs still loose in
datasheets/ are the ones the catalogue already uses: each goes to the folder of the category of the component that cites it (imagers to
imaging_cameras). `datasheet.file` of the catalogue and the `file` column of datasheets/manifest.csv become `datasheets/<folder>/<name>.pdf`
and `<folder>/<name>.pdf`. A loose PDF that is byte-identical to one already in a folder is moved to datasheets/_duplicati/ and the catalogue
points to the copy in the folder. Loose PDFs no component cites go to the folder given in EXTRA. Idempotent. Writes audit/datasheet_move_log.csv.

usage: python tools/organize_datasheets.py
"""
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent
DS = PROJ / "datasheets"
CAT = PROJ / "data" / "catalog.json"
# PDFs the catalogue does not cite (checked by hand 2026-10-23)
EXTRA = {"FastBus CubeSat Platform - 3x2U v1.2.pdf": "cubesat_platform", "b-3-5-201805251613-allthorpe-mullis.pdf": "imaging_cameras",
         "satsearch_datasheet_x7lkd0_xcam_c3d.pdf": "imaging_cameras", "SatCatalog_-_XCAM_-_Nuscis_-_Datasheet.pdf": "imaging_cameras",
         "CUBECAT.pdf": "payload", "Blue-Canyon-Technologies__ACS-2019.pdf": "adcs"}


def folder_of(c):
    cat = c["category"]
    if cat == "payload":
        return "payload" if c["specs"].get("payload_type") == "optical_terminal" else "imaging_cameras"
    return cat


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    data = json.loads(CAT.read_text(encoding="utf-8"))
    comps = data["components"]
    cited = {}
    for c in comps:
        ds = c.get("datasheet")
        if ds:
            cited.setdefault(Path(ds["file"]).name, []).append(c)
    indexed = {}
    for p in DS.rglob("*.pdf"):
        if p.parent != DS:
            indexed.setdefault(sha(p), p)
    log = []
    new_path = {}
    for p in sorted(DS.glob("*.pdf")):
        users = cited.get(p.name)
        if users:
            folder = Counter(folder_of(c) for c in users).most_common(1)[0][0]
        elif p.name in EXTRA:
            folder = EXTRA[p.name]
        else:
            print("no folder for", p.name)
            continue
        twin = indexed.get(sha(p))
        if twin is not None:
            (DS / "_duplicati").mkdir(exist_ok=True)
            dst = DS / "_duplicati" / p.name
            p.rename(dst)
            new_path[p.name] = twin.relative_to(PROJ).as_posix() if users else None
            log.append([p.name, f"_duplicati/{p.name}", f"identical to {twin.relative_to(DS).as_posix()}"])
            continue
        (DS / folder).mkdir(exist_ok=True)
        dst = DS / folder / p.name
        if dst.exists():
            print("target exists:", dst)
            continue
        p.rename(dst)
        new_path[p.name] = dst.relative_to(PROJ).as_posix()
        log.append([p.name, f"{folder}/{p.name}", "category of the component that cites it" if users else "chosen by hand"])
    for c in comps:
        ds = c.get("datasheet")
        if ds and Path(ds["file"]).name in new_path and new_path[Path(ds["file"]).name]:
            ds["file"] = new_path[Path(ds["file"]).name]
    CAT.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    mf = DS / "manifest.csv"
    rows = list(csv.reader(mf.open(encoding="utf-8-sig", newline="")))
    for r in rows[1:]:
        r[0] = Path(new_path[r[0]]).relative_to("datasheets").as_posix() if new_path.get(r[0]) else r[0]
    with mf.open("w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows(rows)
    if log:
        with open(PROJ / "audit" / "datasheet_move_log.csv", "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["file", "to", "reason"])
            w.writerows(log)
    missing = [c["id"] for c in comps if c.get("datasheet") and not (PROJ / c["datasheet"]["file"]).is_file()]
    print(f"moved {len(log)} PDFs; components whose datasheet file is missing: {len(missing)} {missing[:5]}")


if __name__ == "__main__":
    main()

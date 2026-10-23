"""Applies audit/import_rename_proposal.csv: renames the PDFs inside Datasheet_CubeSat_1U-12U and copies the non-duplicate ones to datasheets/.

Writes audit/import_rename_map.csv (old -> new, copied) so the rename can be undone. Does not touch catalog.json or manifest.csv.
Idempotent: files already renamed are skipped. Nothing is deleted.

usage: python tools/apply_datasheet_renames.py
"""
import csv
import shutil
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent
SRC = PROJ / "Datasheet_CubeSat_1U-12U"
DS = PROJ / "datasheets"
PROP = PROJ / "audit" / "import_rename_proposal.csv"
MAP = PROJ / "audit" / "import_rename_map.csv"


def main():
    rows = list(csv.DictReader(open(PROP, encoding="utf-8-sig")))
    existing = {p.name.lower() for p in DS.glob("*.pdf")}
    targets = {}
    for r in rows:
        site = r["old"].split("/", 1)[0]
        targets.setdefault((site, r["new"].lower()), []).append(r["old"])
    assert all(len(v) == 1 for v in targets.values()), "duplicate target names inside one folder"
    out, renamed, copied = [], 0, 0
    for r in rows:
        site, old = r["old"].split("/", 1)
        src_old, src_new = SRC / site / old, SRC / site / r["new"]
        if src_old.exists() and src_old != src_new:
            assert not src_new.exists() or src_new.samefile(src_old), f"target exists: {src_new}"
            src_old.rename(src_new)
            renamed += 1
        dst = DS / r["new"]
        did_copy = ""
        if not r["duplicate"] and src_new.exists():
            if r["new"].lower() in existing and not dst.exists():
                did_copy = "skipped: name clash in datasheets/"
            elif not dst.exists():
                shutil.copy2(src_new, dst)
                existing.add(r["new"].lower())
                copied += 1
                did_copy = "copied"
            else:
                did_copy = "already there"
        elif r["duplicate"]:
            did_copy = "duplicate: " + r["duplicate"]
        out.append({"site": site, "old": old, "new": r["new"], "confidence": r["confidence"], "datasheets": did_copy})
    with open(MAP, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    print(f"renamed {renamed}, copied {copied} to datasheets/, map -> {MAP}")


if __name__ == "__main__":
    main()

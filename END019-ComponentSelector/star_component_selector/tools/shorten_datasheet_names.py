"""Accorcia i nomi dei file in datasheets/ oltre MAX_NAME caratteri e aggiorna catalogo, manifest e audit. Idempotente.

uso: python tools/shorten_datasheet_names.py
"""
import csv
import json
import sys
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from add_datasheets import MAX_NAME, short_name  # noqa: E402

DS = PROJ / "datasheets"
mapping = {}
for f in sorted(DS.glob("*.pdf")):
    new = short_name(f.name)
    if new != f.name:
        mapping[f.name] = new
targets = list(mapping.values())
assert len(set(targets)) == len(targets), "nomi accorciati duplicati"
assert not any((DS / t).exists() for t in targets), "il nome accorciato esiste gia'"
others = {f.name for f in DS.glob("*.pdf")} - set(mapping)
assert not (set(targets) & others), "collisione con un file esistente"
for old, new in mapping.items():
    (DS / old).rename(DS / new)

cat_path = PROJ / "data" / "catalog.json"
cat = json.loads(cat_path.read_text(encoding="utf-8"))
n = 0
for c in cat["components"]:
    ds = c.get("datasheet")
    if ds and Path(ds["file"]).name in mapping:
        ds["file"] = "datasheets/" + mapping[Path(ds["file"]).name]
        n += 1
cat_path.write_text(json.dumps(cat, indent=1, ensure_ascii=False), encoding="utf-8")


def rewrite_csv(path, column, prefix=""):
    if not path.is_file():
        return 0
    with path.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh))
    idx = rows[0].index(column)
    k = 0
    for r in rows[1:]:
        name = Path(r[idx]).name
        if name in mapping:
            r[idx] = prefix + mapping[name]
            k += 1
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        csv.writer(fh).writerows(rows)
    return k


m = rewrite_csv(DS / "manifest.csv", "file")
a = rewrite_csv(PROJ / "audit" / "audit_datasheets.csv", "datasheet", "datasheets/")
print(f"{len(mapping)} file rinominati; catalogo {n} componenti, manifest {m} righe, audit {a} righe")
longest = max(len(f.name) for f in DS.glob("*.pdf"))
print("nome piu' lungo:", longest)

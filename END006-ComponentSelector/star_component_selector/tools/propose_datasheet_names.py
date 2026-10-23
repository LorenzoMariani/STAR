"""Proposes Vendor__Product.pdf names from audit/import_inventory.csv (read-only on the PDFs).

Writes audit/import_rename_proposal.csv: old path, proposed name, confidence (high = descriptive file name, medium = PDF title,
low = first-page text only), vendor source, duplicate flag. Nothing is renamed here.

usage: python tools/propose_datasheet_names.py
"""
import csv
import json
import re
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent
INV = PROJ / "audit" / "import_inventory.csv"
OUT = PROJ / "audit" / "import_rename_proposal.csv"
AGGREGATORS = {"newspacemarket.com", "satbase.s3.amazonaws.com", "cdn.prod.website-files.com", "i3g2h5t3.delivery.rocketcdn.me"}
HASH = re.compile(r"^([0-9a-f]{40}|[0-9a-f]{5,8}_[0-9a-f]{32})$")
NOISE = re.compile(r"(?i)\b(data ?sheet|datasheet|brochure|web|final|rev[ _-]?[a-z0-9]+|v\d+(\.\d+)*|ver\d+|en|eng|pdf|print|low ?res)\b")
BAD_TITLE = re.compile(r"(?i)^(microsoft|untitled|adobe|document|slide|presentation|pdf|\s*$)|\.(html?|docx?|indd)$")
MAX_NAME = 50


def clean(s, words=None):
    s = re.sub(r"\.(pdf|html?)$", "", s, flags=re.I)
    s = NOISE.sub(" ", s)
    s = re.sub(r"[^A-Za-z0-9.+\-]+", " ", s).strip()
    toks = s.split()
    if words:
        toks = toks[:words]
    return "-".join(t.strip("-.") for t in toks if t.strip("-."))


def vendors():
    cat = json.load(open(PROJ / "data" / "catalog.json", encoding="utf-8"))["components"]
    names = {c["vendor"] for c in cat}
    names |= {n.split(" (")[0] for n in names}
    return sorted(names, key=len, reverse=True)


def detect_vendor(row, vend):
    hay = f"{row['file']} {row['text_start']} {row['pdf_title']}".lower()
    for v in vend:
        if v.lower() in hay:
            return re.sub(r"[^A-Za-z0-9]", "", v), "catalog"
    dom = row["domain"].lower().removeprefix("www.")
    if dom and dom not in AGGREGATORS:
        return clean(dom.rsplit(".", 1)[0].split(".")[-1], 1).capitalize() or "Unknown", "domain"
    m = re.match(r"(?i)^(?:satbase-)?([a-z]+)", row["file"])
    return "Unknown", "none"


def propose(row, vend):
    vendor, vsrc = detect_vendor(row, vend)
    stem = row["file"][:-4]
    if row["site"] == "SatBase":
        prod, conf = clean(re.sub(r"^satbase-|-datasheet$", "", stem, flags=re.I)), "high"
    elif not HASH.match(stem):
        prod, conf = clean(stem), "high"
    elif row["pdf_title"] and not BAD_TITLE.search(row["pdf_title"]):
        prod, conf = clean(row["pdf_title"], 6), "medium"
    else:
        prod, conf = clean(row["text_start"], 6), "low"
    if not prod:
        prod, conf = stem[:12], "low"
    if prod.lower().startswith(vendor.lower()):
        prod = prod[len(vendor):].lstrip("-_ ") or prod
    name = f"{vendor}__{prod}"
    room = MAX_NAME - 4
    if len(name) > room:
        name = name[:room].rstrip("-_.")
    return name + ".pdf", conf, vsrc


def main():
    vend = vendors()
    rows = list(csv.DictReader(open(INV, encoding="utf-8-sig")))
    out, used = [], {}
    for r in rows:
        new, conf, vsrc = propose(r, vend)
        key = new.lower()
        if key in used:
            used[key] += 1
            new = new[:-4] + f"-{used[key]}.pdf"
        else:
            used[key] = 1
        out.append({"old": f"{r['site']}/{r['file']}", "new": new, "confidence": conf, "vendor_source": vsrc,
                    "duplicate": r["duplicate"], "url": r["url"], "text_start": r["text_start"][:80]})
    with open(OUT, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    from collections import Counter
    print(len(out), dict(Counter(o["confidence"] for o in out)), dict(Counter(o["vendor_source"] for o in out)))


if __name__ == "__main__":
    main()

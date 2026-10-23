"""Inventory of Datasheet_CubeSat_1U-12U (read-only): hash, source URL, PDF title and first-page text for every PDF.

Writes audit/import_inventory.csv. Duplicates (same SHA-256 as an earlier file or as a PDF already in datasheets/) are flagged.

usage (star env, needs pypdf): python tools/import_datasheet_folder.py
"""
import csv
import hashlib
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

from pypdf import PdfReader

PROJ = Path(__file__).resolve().parent.parent
SRC = PROJ / "Datasheet_CubeSat_1U-12U"
DS = PROJ / "datasheets"
OUT = PROJ / "audit" / "import_inventory.csv"


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_index():
    url_by_name = {}
    with open(SRC / "indice_download.csv", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f, delimiter=";"):
            if r["Esito"] == "ok" and r["File locale"]:
                url_by_name[r["File locale"].replace("\\", "/").rsplit("/", 1)[-1]] = r["URL origine"]
    return url_by_name


def probe(p):
    try:
        rd = PdfReader(str(p))
        meta = (rd.metadata.title if rd.metadata and rd.metadata.title else "") or ""
        pages = len(rd.pages)
        text = ""
        for i in range(min(pages, 2)):
            text += (rd.pages[i].extract_text() or "") + " "
            if len(text) > 400:
                break
        text = re.sub(r"\s+", " ", text).strip()[:300]
        return meta.strip(), pages, text
    except Exception as e:  # noqa: BLE001
        return "", 0, f"ERROR {type(e).__name__}"


def main():
    urls = read_index()
    existing = {sha256(p): p.name for p in DS.glob("*.pdf")}
    seen = {}
    rows = []
    files = sorted(SRC.glob("*/*.pdf"))
    for n, p in enumerate(files, 1):
        h = sha256(p)
        meta, pages, text = probe(p)
        dup = existing.get(h) and f"in datasheets/: {existing[h]}" or (h in seen and f"dup of {seen[h]}") or ""
        seen.setdefault(h, f"{p.parent.name}/{p.name}")
        url = urls.get(p.name, "")
        rows.append({
            "site": p.parent.name, "file": p.name, "bytes": p.stat().st_size, "sha256": h, "pages": pages,
            "url": url, "domain": urlparse(url).netloc, "pdf_title": meta, "text_start": text, "duplicate": dup,
        })
        if n % 100 == 0:
            print(f"{n}/{len(files)}", file=sys.stderr)
    OUT.parent.mkdir(exist_ok=True)
    with open(OUT, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} PDFs, {sum(1 for r in rows if r['duplicate'])} duplicates -> {OUT}")


if __name__ == "__main__":
    main()

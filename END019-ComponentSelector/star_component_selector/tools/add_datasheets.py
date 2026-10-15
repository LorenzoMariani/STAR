"""Scarica in datasheets/ i PDF (datasheet e brochure) indicati come fonte dei componenti e registra `datasheet` nel catalogo.

Si scaricano SOLO gli URL gia' citati in `source.url` che puntano a un PDF; le pagine HTML dei fornitori non si salvano.
Un file e' accettato solo se inizia con %PDF. Nessun valore del catalogo viene modificato: si aggiunge solo il campo `datasheet`.
"""
import csv
import json
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path
from urllib.parse import unquote, urlparse

PROJ = Path(__file__).resolve().parent.parent
CAT = PROJ / "data" / "catalog.json"
OUT = PROJ / "datasheets"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
MAX_BYTES = 60 * 1024 * 1024
RET = date.today().isoformat()


def slug(s):
    return re.sub(r"[^A-Za-z0-9._-]+", "-", s).strip("-")


MAX_NAME = 50      # nomi corti: sotto i 260 caratteri di Windows anche con il pacchetto estratto in una cartella profonda


def short_name(name):
    """Accorcia il nome di un file (vendor__documento.pdf) a MAX_NAME caratteri tenendo la parte finale, che identifica il prodotto."""
    if len(name) <= MAX_NAME:
        return name
    stem = name[:-4] if name.lower().endswith(".pdf") else name
    vendor, _, doc = stem.partition("__")
    vendor = vendor[:14].strip("-_")
    doc = re.sub(r"^SatCatalog_-_", "", doc)
    doc = re.sub(r"_-_", "_", doc)
    room = MAX_NAME - len(vendor) - 2 - 4
    return f"{vendor}__{doc[-room:].lstrip('-_')}.pdf"


def is_pdf_url(u):
    return urlparse(u).path.lower().endswith(".pdf")


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=90) as r:
        data = r.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("file oltre 60 MB")
    if not data.startswith(b"%PDF"):
        raise ValueError("non e' un PDF")
    return data


def main():
    OUT.mkdir(exist_ok=True)
    cat = json.loads(CAT.read_text(encoding="utf-8"))
    comps = cat["components"]
    jobs = {}
    for c in comps:
        u = (c.get("source") or {}).get("url") or ""
        if is_pdf_url(u):
            jobs.setdefault(u, c)
    done, failed = {}, {}
    for url, first in sorted(jobs.items()):
        name = short_name(slug(f"{first['vendor']}__{unquote(Path(urlparse(url).path).name)}"))
        path = OUT / name
        try:
            if not path.exists():
                path.write_bytes(fetch(url))
            done[url] = (name, path.stat().st_size)
            print("ok  ", name, path.stat().st_size)
        except Exception as e:  # noqa: BLE001 - riportare ogni errore di rete/HTTP e proseguire
            failed[url] = str(e)
            print("FAIL", url, e)
    n = 0
    for c in comps:
        u = (c.get("source") or {}).get("url") or ""
        if not is_pdf_url(u) and (PROJ / (c.get("datasheet") or {}).get("file", "-")).is_file():
            continue        # PDF aggiunto a mano (fonte senza estensione .pdf, es. tools/add_solar_1u.py): non si tocca
        c.pop("datasheet", None)
        if u in done:
            name, size = done[u]
            c["datasheet"] = {"file": f"datasheets/{name}", "document": c["source"].get("document"), "source_url": u, "retrieved": RET, "bytes": size}
            n += 1
    CAT.write_text(json.dumps(cat, indent=1, ensure_ascii=False), encoding="utf-8")
    with (OUT / "manifest.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["file", "document", "source_url", "retrieved", "bytes", "components"])
        for u, (name, size) in sorted(done.items(), key=lambda kv: kv[1][0]):
            w.writerow([name, jobs[u]["source"].get("document"), u, RET, size, " ".join(c["id"] for c in comps if (c.get("source") or {}).get("url") == u)])
    print(f"{len(done)} PDF scaricati, {len(failed)} falliti, {n} componenti con datasheet")
    for u, e in failed.items():
        print("  non scaricato:", u, "-", e)
    return 0


if __name__ == "__main__":
    sys.exit(main())

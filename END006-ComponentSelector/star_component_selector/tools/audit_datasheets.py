"""Controlla i valori del catalogo contro il testo dei datasheet locali (datasheets/). Solo lettura: non modifica il catalogo.

Per ogni componente con `datasheet` cerca nel testo del PDF (nelle sole pagine che nominano il prodotto, se il documento ha piu' prodotti):
  - la massa (kg o g, tolleranza di arrotondamento);
  - le tre dimensioni dichiarate (mm; numeri presenti nel testo in qualunque ordine);
  - ogni specifica numerica del catalogo (numero presente nel testo, anche come mW/W, g/kg, km/m: vedi `variants`).
Esiti per voce: `found` (valore trovato), `missing` (non trovato: da guardare a mano), `skipped` (non cercabile: derivato, booleano, null).
`missing` NON significa errore: i PDF possono avere tabelle come immagini o unita' diverse. Scrive audit/audit_datasheets.csv e audit_summary.json.

uso: python tools/audit_datasheets.py [--only ID ...]
"""
import csv
import json
import re
import sys
from pathlib import Path

import pymupdf

PROJ = Path(__file__).resolve().parent.parent
OUT = PROJ / "audit"
NUM = re.compile(r"(?<![A-WYZa-wyz0-9.,])(\d{1,3}(?:[ ,]\d{3})+|\d+)(?:[.,](\d+))?(?!\d)")   # accetta l'unita' attaccata (304g, 113.5mm) e 100x100; esclude le sigle (RW210)


def pdf_pages(path, cache={}):
    if path not in cache:
        doc = pymupdf.open(path)
        cache[path] = [p.get_text("text") for p in doc]
        doc.close()
    return cache[path]


def numbers(text):
    """Tutti i numeri del testo come float (accetta virgola o punto decimale e separatori di migliaia)."""
    out = []
    for m in NUM.finditer(text.replace(" ", " ").replace("\xa0", " ")):
        whole, frac = m.group(1), m.group(2)
        whole = re.sub(r"[ ,]", "", whole)
        try:
            out.append(float(whole + ("." + frac if frac else "")))
        except ValueError:
            pass
    return out


def close(a, b):
    """Uguali entro lo 0.5 % (arrotondamento delle tabelle)."""
    return abs(a - b) <= max(abs(b) * 0.005, 0.0005)


def variants(v):
    """Rappresentazioni numeriche equivalenti di un valore del catalogo (cambi di unita' comuni)."""
    v = float(v)
    out = {v, v * 1000, v / 1000}
    return out


MASS = re.compile(r"(?<![A-Za-z0-9])(\d[\d.,]*|\.\d+)\s*(kg|g|gr|gram|grams)(?![A-Za-z])", re.I)


def masses_kg(text):
    """Masse scritte con unita' (g o kg) nel testo, in kg."""
    out = []
    for m in MASS.finditer(text.replace("\xa0", " ")):
        raw = m.group(1).rstrip(".,")
        try:
            val = float(raw.replace(",", ".")) if raw.count(",") + raw.count(".") <= 1 else float(re.sub(r"[,](?=\d{3}\b)", "", raw))
        except ValueError:
            continue
        out.append(val if m.group(2).lower() == "kg" else val / 1000)
    return out


def has(nums, v, factors=True):
    cands = variants(v) if factors else {float(v)}
    return any(close(n, c) for n in nums for c in cands)


def name_tokens(c):
    raw = c["name"].replace("(", " ").replace(")", " ")
    toks = [t for t in re.split(r"[\s/,]+", raw) if len(t) >= 2 and not re.fullmatch(r"\d+", t)]
    return [t.lower() for t in toks][:4]


def relevant_pages(c, pages):
    """Pagine che nominano il prodotto (tutti i token distintivi); se sono molte o nessuna, tutto il documento."""
    if len(pages) <= 10:      # documenti brevi: un solo prodotto, le sue specifiche possono stare su pagine che non ripetono il nome
        return list(range(len(pages))), "document"
    toks = [t for t in name_tokens(c) if not re.fullmatch(r"(cubesat|structure|solar|panel|u|kit|system|module|board|3u|6u|1u|12u)", t)]
    if toks:
        hit = [i for i, p in enumerate(pages) if all(t in p.lower() for t in toks[:2])]
        if hit and len(hit) <= max(6, len(pages) // 4):
            return hit, "pages with name"
    return list(range(len(pages))), "document"


def main(argv):
    only = set(argv[argv.index("--only") + 1:]) if "--only" in argv else None
    cat = json.loads((PROJ / "data" / "catalog.json").read_text(encoding="utf-8"))["components"]
    rows, summary = [], {"components": 0, "no_text": 0, "mass": {"found": 0, "missing": 0, "skipped": 0}, "dims": {"all": 0, "partial": 0, "none": 0, "skipped": 0}, "specs": {"found": 0, "missing": 0, "skipped": 0}}
    for c in cat:
        ds = c.get("datasheet")
        if not ds or (only and c["id"] not in only):
            continue
        summary["components"] += 1
        pages = pdf_pages(PROJ / ds["file"])
        text_len = sum(len(p) for p in pages)
        if text_len < 200 * max(1, len(pages) // 4):
            summary["no_text"] += 1
            rows.append([c["id"], ds["file"], "no text", "", "", "", "", "", "PDF senza testo estraibile (immagini): controllo a mano"])
            continue
        idx, scope = relevant_pages(c, pages)
        text = "\n".join(pages[i] for i in idx)
        nums = numbers(text)
        derived = "DERIVAT" in (c.get("notes") or "").upper() or "SOMMA" in (c.get("notes") or "").upper()
        # massa
        m = c.get("mass_kg")
        if m is None:
            mass_res = "skipped"
        elif any(close(v, m) for v in masses_kg(text)):
            mass_res = "found"                      # numero con unita' g o kg uguale alla massa del catalogo
        elif has(nums, m):
            mass_res = "number_only"                # lo stesso numero compare senza unita' accanto (tabelle): da confermare a mano
        else:
            mass_res = "missing"
        summary["mass"][mass_res] = summary["mass"].get(mass_res, 0) + 1
        # dimensioni
        dims = [x for x in ((c.get("dimensions") or {}).get("mm") or []) if x is not None]
        basis = (c.get("dimensions") or {}).get("basis")
        if not dims or basis == "derived":
            dim_res, dim_miss = "skipped", []
            summary["dims"]["skipped"] += 1
        else:
            dim_miss = [d for d in dims if not has(nums, d, factors=False) and not any(close(n, d / 10) for n in nums)]   # mm oppure cm
            dim_res = "all" if not dim_miss else ("partial" if len(dim_miss) < len(dims) else "none")
            summary["dims"][dim_res] += 1
        # specifiche numeriche
        found, missing = [], []
        for k, v in (c.get("specs") or {}).items():
            if isinstance(v, bool) or not isinstance(v, (int, float)) or k in ("form_factor_u", "max_total_mass_kg"):
                summary["specs"]["skipped"] += 1
                continue
            (found if has(nums, v) else missing).append(k)
        summary["specs"]["found"] += len(found)
        summary["specs"]["missing"] += len(missing)
        rows.append([c["id"], ds["file"], scope, f"mass:{mass_res}" + ("" if m is None else f" ({m} kg)"), f"dims:{dim_res}" + (f" missing {dim_miss}" if dim_miss else ""),
                     f"specs {len(found)}/{len(found) + len(missing)}", " ".join(missing), "derived-note" if derived else "", ""])
    OUT.mkdir(exist_ok=True)
    with (OUT / "audit_datasheets.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "datasheet", "search_scope", "mass", "dimensions", "numeric_specs_found", "specs_not_found", "flag", "note"])
        w.writerows(rows)
    (OUT / "audit_summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

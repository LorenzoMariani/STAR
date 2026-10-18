"""Assembla la cartella immagini con la fonte di ciascuna.
Priorita': override URL > estrazione da PDF > immagine web scelta. Salva PNG (max 1000 px) con la fonte nei metadati."""
import csv, json, sys
from pathlib import Path
from PIL import Image
from PIL.PngImagePlugin import PngInfo

sys.path.insert(0, str(Path(__file__).parent))
from naming import image_name  # noqa: E402

WORK, CAT, OUTDIR = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
OUTDIR.mkdir(parents=True, exist_ok=True)
RET = "2026-10-13"
comps = json.loads(CAT.read_text(encoding="utf-8"))["components"]
picked = json.loads((WORK / "picked.json").read_text(encoding="utf-8"))
pdfrep = json.loads((WORK / "pdf_report.json").read_text(encoding="utf-8"))
cand = json.loads((WORK / "candidates.json").read_text(encoding="utf-8"))
override = json.loads((WORK / "override.json").read_text(encoding="utf-8-sig")) if (WORK / "override.json").exists() else {}
skip = set(json.loads((WORK / "skip.json").read_text(encoding="utf-8-sig"))) if (WORK / "skip.json").exists() else set()

SIM = "https://simera-sense.com/earth-observation-cameras/"
OVERRIDE_PAGE = {  # pagina del fornitore da cui proviene l'immagine scelta a mano
    **{f"simera-{v}50": SIM + "xscape50/" for v in ("triscape", "multiscape", "hyperscape")},
    **{f"simera-{v}100": SIM + "xscape100/" for v in ("triscape", "multiscape", "hyperscape")},
    **{f"simera-{v}200": SIM + "xscape200-dual-use/" for v in ("monoscape", "triscape", "multiscape")},
    "aac-zaphod-6u": "https://www.aac-clyde.space/what-we-do/space-products-components/cubesat-structures",
    "satlantis-isim-90": "https://www.satlantis.com/space-cameras/", "satlantis-isim-90-swir": "https://www.satlantis.com/space-cameras/",
    "aac-quasar-strx": "https://www.aac-clyde.space/what-we-do/space-products-components/communications/quasar-strx",
    "endurosat-xband": "https://www.endurosat.com/products/x-band-transmitter",
}
NOTICE = ("Immagine di proprieta' del produttore, qui solo come riferimento visivo del prodotto; per usi diversi (pubblicazioni, "
          "presentazioni esterne) chiedere il permesso al produttore.")

names = [image_name(c) for c in comps]
assert len(set(names)) == len(names), [n for n in names if names.count(n) > 1]

info, rows = {}, []
for c, name in zip(comps, names):
    cid = c["id"]
    kind = img_url = page_url = None
    path = None
    if cid in skip:
        pass
    elif cid in override:
        kind, img_url, page_url, path = "web (scelta manuale)", override[cid], OVERRIDE_PAGE.get(cid), WORK / "pick" / f"{cid}.png"
    elif pdfrep.get(cid, "").startswith("OK"):
        pg = pdfrep[cid].split()[1].lstrip("p")
        kind, path = "estratta dal datasheet PDF", WORK / "pdf" / f"{cid}.png"
        # l'URL del PDF e' quello usato dallo script di estrazione, non sempre source.url
        sys.path.insert(0, str(WORK.parent))
        pdf_url = json.loads((WORK / "pdf_urls.json").read_text(encoding="utf-8"))[cid]
        img_url = f"{pdf_url}#page={pg}"
        page_url = pdf_url
    elif picked.get(cid, {}).get("url"):
        kind, img_url, path = "web", picked[cid]["url"], WORK / "pick" / f"{cid}.png"
        for pg in cand["plan"].get(cid, []):
            if any(i["url"] == img_url for i in cand["pages"].get(pg, {}).get("images", [])):
                page_url = pg
                break
    if path is not None and path.exists():
        im = Image.open(path)
        im = im.convert("RGBA") if im.mode in ("P", "LA", "RGBA") else im.convert("RGB")
        im.thumbnail((1000, 1000))
        meta = PngInfo()
        for k, v in (("Title", f"{c['vendor']} {c['name']}"), ("Author", c["vendor"]), ("Source", img_url or ""),
                     ("Description", f"Componente {cid}. Pagina/documento di origine: {page_url or 'n.d.'}. Scaricata il {RET}."),
                     ("Copyright", NOTICE)):
            meta.add_text(k, v)
        im.save(OUTDIR / name, optimize=True, pnginfo=meta)
        info[cid] = {"file": f"images/{name}", "image_url": img_url, "page_url": page_url, "type": kind, "retrieved": RET}
        rows.append([cid, c["vendor"], c["name"], name, kind, img_url, page_url or "", RET, f"{im.size[0]}x{im.size[1]}"])
    else:
        rows.append([cid, c["vendor"], c["name"], "", "nessuna immagine trovata", "", "", RET, ""])
    print(("OK  " if rows[-1][3] else "MISS"), cid, name)

# immagini condivise tra piu' componenti (stessa foto per famiglia o per varianti): lo si dichiara nella nota
from collections import defaultdict
groups = defaultdict(list)
for r in rows:
    if r[5]:
        groups[r[5]].append(r[0])
for r in rows:
    others = [x for x in groups.get(r[5], []) if x != r[0]] if r[5] else []
    r.append(("Foto condivisa con altre varianti/componenti della stessa famiglia: " + ", ".join(others)) if others else
             ("Nessuna immagine pubblica trovata per questo prodotto (solo per un'altra variante dello stesso fornitore)." if not r[3] else ""))
for cid, v in info.items():
    sh = [r for r in rows if r[0] == cid][0][-1]
    if sh:
        v["note"] = sh

with (OUTDIR / "manifest.csv").open("w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["id_componente", "venditore", "componente", "file", "tipo", "fonte_immagine", "pagina_o_documento_di_origine", "data_download", "dimensioni_px", "nota"])
    w.writerows(rows)
(OUTDIR / "info.json").write_text(json.dumps(info, indent=1, ensure_ascii=False), encoding="utf-8")



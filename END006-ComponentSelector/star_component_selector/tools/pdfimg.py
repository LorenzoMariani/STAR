"""Estrae l'immagine piu' grande (non di sfondo) da pagine indicate di datasheet PDF. Solo lettura di immagini."""
import hashlib, io, json, sys, urllib.request
from pathlib import Path
import pymupdf
from PIL import Image

WORK = Path(sys.argv[1])
(WORK / "pdf").mkdir(exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
ES = "https://endurosat.com/wp-content/uploads/2022/02/Endurosat_Product_Catalogue_02_22.pdf"
ISIS_S = "https://www.cubesatshop.com/wp-content/uploads/2016/06/ISIS-CubeSat-Structures-Brochure-v1.pdf"
ISIS_P = "https://www.cubesatshop.com/wp-content/uploads/2016/06/ISIS-Solar-Panels-Brochure-v1.pdf"
ISIS_T = "https://www.cubesatshop.com/wp-content/uploads/2016/06/VHF-UHF-Full-Duplex-Transceiver-Brochure-web-1.pdf"
CS = "https://www.cubesatshop.com/wp-content/uploads/2023/05/GEN-1-ADCS-Jan-2023-web.pdf"
PK = "https://www.cubesatkit.com/docs/datasheet/"
# id -> (pdf, pagine 1-based)
JOBS = {
    "endurosat-structure-3u": (ES, [19, 20]), "endurosat-structure-6u": (ES, [19, 20]),
    "endurosat-eps-i": (ES, [13, 14]), "endurosat-eps-ii": (ES, [13, 14]),
    "isis-structure-3u": (ISIS_S, [1, 2]), "isis-structure-6u": (ISIS_S, [1, 2]),
    "isis-solar-3u": (ISIS_P, [1, 2]), "isis-trxvu": (ISIS_T, [1]),
    "cubespace-cubeadcs-3axis-small": (CS, [3]), "cubespace-cubeadcs-ymomentum-small": (CS, [2]),
    "pumpkin-csk-mb-ppma1": (PK + "DS_CSK_MB_710-00484-E.pdf", [1]), "pumpkin-csk-mb-ppma2": (PK + "DS_CSK_MB_710-00484-E.pdf", [1]),
    "pumpkin-csk-mb-ppma3": (PK + "DS_CSK_MB_710-00484-E.pdf", [1]), "pumpkin-csk-mb-ppmb1": (PK + "DS_CSK_MB_710-00484-E.pdf", [1]),
    "pumpkin-csk-mb-ppmd1": (PK + "DS_CSK_MB_710-00484-E.pdf", [1]), "pumpkin-csk-mb-ppmd2": (PK + "DS_CSK_MB_710-00484-E.pdf", [1]),
    "pumpkin-fm430": (PK + "DS_CSK_FM430_710-00252-C.pdf", [1]),
    "pumpkin-linear-eps-11wh": (PK + "DS_CSK_Linear_EPS_711-00338-D.pdf", [1]), "pumpkin-linear-eps-22wh": (PK + "DS_CSK_Linear_EPS_711-00338-D.pdf", [1]),
    "pumpkin-bm1-40wh": (PK + "DS_CSK_BM_1_710-01006-A.pdf", [1]),
    "pumpkin-mai-100": (PK + "DS_CSK_ADACS_634-00412-A.pdf", [1]), "pumpkin-mai-200": (PK + "DS_CSK_ADACS_634-00458-A.pdf", [1]),
}


def fetch(url):
    f = WORK / "raw" / (hashlib.sha1(url.encode()).hexdigest()[:16] + ".pdf")
    if not f.exists():
        f.write_bytes(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read())
    return f


report = {}
for cid, (url, pages) in JOBS.items():
    try:
        doc = pymupdf.open(fetch(url))
        best = None
        for pn in pages:
            if pn > len(doc):
                continue
            page = doc[pn - 1]
            parea = page.rect.width * page.rect.height
            for xref, *_ in page.get_images(full=True):
                try:
                    pix = pymupdf.Pixmap(doc, xref)
                    if pix.alpha or pix.colorspace is None or pix.colorspace.n not in (1, 3, 4):
                        pix = pymupdf.Pixmap(pymupdf.csRGB, pix) if pix.colorspace is not None else None
                    if pix is None:
                        continue
                    if pix.colorspace.n == 4:
                        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
                    w, h = pix.width, pix.height
                except Exception:  # noqa: BLE001
                    continue
                if min(w, h) < 180 or not 0.25 < w / h < 4:
                    continue
                if w * h > 0.9 * parea * (150 / 72) ** 2 and w > 1500:  # probabile sfondo a tutta pagina
                    continue
                if best is None or w * h > best[0]:
                    best = (w * h, pix, pn, xref)
        if best:
            img = Image.open(io.BytesIO(best[1].tobytes("png")))
            img.save(WORK / "pdf" / f"{cid}.png")
            report[cid] = f"OK p{best[2]} {img.size}"
        else:
            report[cid] = "MISS"
    except Exception as e:  # noqa: BLE001
        report[cid] = f"ERR {type(e).__name__}: {e}"
    print(cid, report[cid])
(WORK / "pdf_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
(WORK / "pdf_urls.json").write_text(json.dumps({k: v[0] for k, v in JOBS.items()}, indent=1), encoding="utf-8")

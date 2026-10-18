"""Salva tutte le immagini >=120 px di alcune pagine di PDF gia' scaricati, per scegliere a mano."""
import hashlib, io, sys
from pathlib import Path
import pymupdf
from PIL import Image

WORK = Path(sys.argv[1])
out = WORK / "dump"
out.mkdir(exist_ok=True)
PK = "https://www.cubesatkit.com/docs/datasheet/"
JOBS = {
    "fm430": PK + "DS_CSK_FM430_710-00252-C.pdf", "leps": PK + "DS_CSK_Linear_EPS_711-00338-D.pdf",
    "mai100": PK + "DS_CSK_ADACS_634-00412-A.pdf", "mai200": PK + "DS_CSK_ADACS_634-00458-A.pdf",
    "isis_solar": "https://www.cubesatshop.com/wp-content/uploads/2016/06/ISIS-Solar-Panels-Brochure-v1.pdf",
    "es_cat": "https://endurosat.com/wp-content/uploads/2022/02/Endurosat_Product_Catalogue_02_22.pdf",
}
for name, url in JOBS.items():
    f = WORK / "raw" / (hashlib.sha1(url.encode()).hexdigest()[:16] + ".pdf")
    doc = pymupdf.open(f)
    for pn in range(1, min(len(doc), 25) + 1):
        for k, (xref, *_) in enumerate(doc[pn - 1].get_images(full=True)):
            try:
                pix = pymupdf.Pixmap(doc, xref)
                if pix.colorspace is None or pix.alpha or pix.colorspace.n != 3:
                    pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
                if min(pix.width, pix.height) < 120:
                    continue
                Image.open(io.BytesIO(pix.tobytes("png"))).save(out / f"{name}_p{pn}_{k}_{pix.width}x{pix.height}.png")
            except Exception:  # noqa: BLE001
                pass
print(len(list(out.glob("*.png"))))

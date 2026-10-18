import io, sys
from pathlib import Path
import pymupdf
from PIL import Image

W = Path(sys.argv[1])
for name in ("triumph", "renegade", "nebula"):
    doc = pymupdf.open(W / f"{name}.pdf")
    best = None
    for pn in (0, 1):
        for xref, *_ in doc[pn].get_images(full=True):
            try:
                pix = pymupdf.Pixmap(doc, xref)
                if pix.colorspace is None or pix.alpha or pix.colorspace.n != 3:
                    pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
            except Exception:  # noqa: BLE001
                continue
            if min(pix.width, pix.height) < 200:
                continue
            print(name, pn + 1, pix.width, pix.height)
            if best is None or pix.width * pix.height > best[0]:
                best = (pix.width * pix.height, pix, pn + 1)
    if best:
        Image.open(io.BytesIO(best[1].tobytes("png"))).save(W / f"{name}_img.png")
        print(name, "best page", best[2])

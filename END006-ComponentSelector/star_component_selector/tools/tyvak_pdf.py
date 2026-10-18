import sys, urllib.request
from pathlib import Path
import pymupdf

W = Path(sys.argv[1])
W.mkdir(exist_ok=True)
BASE = "https://assets.science.nasa.gov/content/dam/science/cds/spacecraft-development/rsdo/rapid-iv-catalog/"
for name, f in (("triumph", "TYVAK_TRIUMPH_PLATFORM_DATA_SHEET.pdf"), ("renegade", "TYVAK_RENEGADE_PLATFORM_DATA_SHEET.pdf"),
                ("nebula", "TYVAK_NEBULA%20_PLATFORM_DATA_SHEET.pdf")):
    try:
        data = urllib.request.urlopen(urllib.request.Request(BASE + f, headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read()
    except Exception as e:  # noqa: BLE001
        print(name, "ERR", e)
        continue
    (W / f"{name}.pdf").write_bytes(data)
    doc = pymupdf.open(W / f"{name}.pdf")
    print(name, len(doc), "pagine")
    for i in (0, 1):
        if i < len(doc):
            doc[i].get_pixmap(dpi=80).save(W / f"{name}_p{i + 1}.png")

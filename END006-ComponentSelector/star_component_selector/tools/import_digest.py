"""Short text digests of the datasheets in datasheets/<category>/ that no catalogue component cites yet.

For each PDF: audit/import_digest/<folder>/<file>.txt = title block plus the lines that carry a number with a unit or a keyword of the
category, with the page number (p.N), at most MAX chars (or the whole text when it is shorter than FULL, so that table labels stay next to their values). The model reads the digest, not the PDF, and opens more text only when mass, power
or the main field of the category are missing. Also prints, per PDF, the catalogue components of the same vendor (possible updates).

usage (base anaconda, pymupdf): python tools/import_digest.py <folder> [<folder> ...]
"""
import json
import re
import sys
from pathlib import Path

import pymupdf

PROJ = Path(__file__).resolve().parent.parent
DS = PROJ / "datasheets"
OUT = PROJ / "audit" / "import_digest"
MAX = 3600
UNIT = re.compile(r"\d\s*(?:kg|g|mg|W|mW|V|mV|A|mA|Ah|Wh|mm|cm|m|U|MHz|GHz|kHz|Hz|dBi|dB|dBm|krad|rad|Mbps|kbps|bps|Gbps|N|mN|Nm|mNm|Nms|mNms|s|ms|rpm|°|deg|arcsec|%|°C|K|ppm|bit|GB|MB|MP|nm|um|µm|Gb|kb)\b", re.I)
KEY = re.compile(r"mass|weight|power|voltage|dimension|size|volume|temperature|radiation|TID|interface|CAN|I2C|SPI|UART|RS-?4|accuracy|thrust|impulse|Isp|capacity|"
                 r"efficien|frequency|band|gain|polari|field of view|FOV|resolution|GSD|swath|pixel|focal|aperture|momentum|torque|dipole|heritage|TRL|lifetime", re.I)


FULL = 5500   # a datasheet whose whole text is shorter than this is given in full (labels stay next to their values)


def digest(pdf):
    d = pymupdf.open(pdf)
    whole = " ".join(f"p.{i} " + re.sub(r"\s+", " ", re.sub(r"[.…]{4,}", " ", pg.get_text())) for i, pg in enumerate(d, 1))
    if len(whole) <= FULL:
        return f"[{len(d)} pages, full text] " + whole
    parts = []
    first = re.sub(r"\s+", " ", d[0].get_text())[:450]
    parts.append(f"[{len(d)} pages] {first}")
    seen = set()
    n = len(parts[0])
    for pno, page in enumerate(d, 1):
        for line in page.get_text().splitlines():
            line = re.sub(r"\s+", " ", line).strip()
            if len(line) < 4 or line in seen:
                continue
            if UNIT.search(line) or (KEY.search(line) and re.search(r"\d", line)):
                seen.add(line)
                s = f"p.{pno} {line[:170]}"
                if n + len(s) > MAX:
                    return "\n".join(parts) + "\n[cut]"
                parts.append(s)
                n += len(s) + 1
    return "\n".join(parts)


def main():
    comps = json.loads((PROJ / "data" / "catalog.json").read_text(encoding="utf-8"))["components"]
    cited = {Path(c["datasheet"]["file"]).name for c in comps if c.get("datasheet")}
    for folder in sys.argv[1:]:
        (OUT / folder).mkdir(parents=True, exist_ok=True)
        for pdf in sorted((DS / folder).glob("*.pdf")):
            if pdf.name in cited:
                continue
            try:
                txt = digest(pdf)
            except Exception as e:  # noqa: BLE001
                txt = f"[unreadable: {e}]"
            (OUT / folder / (pdf.name + ".txt")).write_text(txt, encoding="utf-8")
            print(f"{folder}/{pdf.name}: {len(txt)} chars")


if __name__ == "__main__":
    main()

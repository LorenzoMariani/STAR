"""Adds product images to catalogue components that have a datasheet PDF but no image. Idempotent.

    python tools/import_images.py              extract images (pages 1-2, same logic as pdfimg.py) -> images/*.jpg,
                                               update data/catalog.json and images/manifest.csv
    python tools/import_images.py --mosaic DIR write one review mosaic per category (thumbnails + id) into DIR
    python tools/import_images.py --rejects    drop the images of the ids listed in audit/import_image_rejects.txt (image -> null)

Components listed in audit/import_image_rejects.txt are never given an image again."""
import csv
import io
import json
import sys
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw

PROJ = Path(__file__).resolve().parent.parent
CAT = PROJ / "data" / "catalog.json"
MANIFEST = PROJ / "images" / "manifest.csv"
REJECTS = PROJ / "audit" / "import_image_rejects.txt"
RET = "2026-10-23"
PAGES = (1, 2)
MIN_SIDE, MAX_SIDE, QUALITY = 200, 800, 85


def slug(s):
    return "".join(ch for ch in s.title() if ch.isalnum() or ch in "-")


def rejected():
    if not REJECTS.is_file():
        return set()
    return {ln.split("#")[0].strip() for ln in REJECTS.read_text(encoding="utf-8").splitlines() if ln.split("#")[0].strip()}


def doc_url(c):
    """Public URL of the datasheet when the catalogue has one, else the local copy (documents supplied by the user)."""
    ds = c["datasheet"]
    if c["source"]["url"] is None:
        return ds["file"]
    return ds.get("source_url") or ds.get("vendor_url") or ds["file"]


def best_image(pdf):
    """Largest non-background image of pages 1-2 with min side >= 200 px; returns (PIL image, page) or None."""
    doc = pymupdf.open(pdf)
    best = None
    for pn in PAGES:
        if pn > len(doc):
            continue
        page = doc[pn - 1]
        parea = page.rect.width * page.rect.height
        for xref, *_ in page.get_images(full=True):
            try:
                pix = pymupdf.Pixmap(doc, xref)
                if pix.colorspace is None:
                    continue
                if pix.alpha or pix.colorspace.n != 3:
                    pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
                w, h = pix.width, pix.height
            except Exception:  # noqa: BLE001
                continue
            if min(w, h) < MIN_SIDE or not 0.25 < w / h < 4:
                continue
            if w * h > 0.9 * parea * (150 / 72) ** 2 and w > 1500:  # full-page background
                continue
            if best is None or w * h > best[0]:
                best = (w * h, pix, pn)
    if best is None:
        return None
    im = Image.open(io.BytesIO(best[1].tobytes("png"))).convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    bg.alpha_composite(im)
    return bg.convert("RGB"), best[2]


def extract():
    cat = json.loads(CAT.read_text(encoding="utf-8"))
    skip = rejected()
    todo = [c for c in cat["components"] if not c.get("image") and (c.get("datasheet") or {}).get("file") and c["id"] not in skip]
    used = {c["image"]["file"] for c in cat["components"] if c.get("image")}
    rows, miss = [], []
    shared = {}
    for c in todo:
        shared.setdefault(c["datasheet"]["file"], []).append(c["id"])
    for c in todo:
        pdf = PROJ / c["datasheet"]["file"]
        try:
            res = best_image(pdf) if pdf.is_file() else None
        except Exception as e:  # noqa: BLE001
            print("ERR", c["id"], type(e).__name__, e)
            res = None
        if res is None:
            miss.append(c["id"])
            continue
        im, pn = res
        im.thumbnail((MAX_SIDE, MAX_SIDE))
        base = slug(c["vendor"].split(" (")[0].replace(" ", ""))
        name = f"{base}-{slug(c['name'].split(' (')[0].replace(' ', ''))}".replace("--", "-")
        file = f"images/{name}.jpg"
        if file in used:
            file = f"images/{name}-{slug(c['id'])}.jpg"
        used.add(file)
        im.save(PROJ / file, "JPEG", quality=QUALITY, optimize=True)
        ds = c["datasheet"]["file"]
        link = doc_url(c)
        note = f"Page {pn} of the datasheet {ds.split('/')[-1]}, largest product image (automatic import, to be checked)."
        others = [i for i in shared[ds] if i != c["id"]]
        if others:
            note += " Datasheet shared with: " + ", ".join(others) + "."
        c["image"] = {"file": file, "image_url": f"{link}#page={pn}", "page_url": link, "type": "estratta dal datasheet PDF",
                      "retrieved": RET, "note": note}
        rows.append([c["id"], c["vendor"], c["name"], file.split("/")[-1], "estratta dal datasheet PDF", f"{link}#page={pn}", link, RET,
                     f"{im.size[0]}x{im.size[1]}", note])
    CAT.write_text(json.dumps(cat, indent=1, ensure_ascii=False), encoding="utf-8")
    update_manifest(rows, {r[0] for r in rows})
    print(f"{len(rows)} images added, {len(miss)} without image: {miss}")


def update_manifest(rows, drop):
    with MANIFEST.open(encoding="utf-8-sig", newline="") as f:
        old = list(csv.reader(f))
    keep = [r for r in old if r and r[0] not in drop]
    with MANIFEST.open("w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows(keep + rows)


def apply_rejects():
    ids = rejected()
    cat = json.loads(CAT.read_text(encoding="utf-8"))
    n = 0
    for c in cat["components"]:
        if c["id"] in ids and c.get("image"):
            f = PROJ / c["image"]["file"]
            if c["image"].get("type") == "estratta dal datasheet PDF" and f.suffix == ".jpg" and f.is_file():
                f.unlink()
            del c["image"]
            n += 1
    CAT.write_text(json.dumps(cat, indent=1, ensure_ascii=False), encoding="utf-8")
    update_manifest([], ids)
    print(n, "images removed")


def mosaic(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    cat = json.loads(CAT.read_text(encoding="utf-8"))["components"]
    new = [c for c in cat if c.get("image") and c["image"].get("retrieved") == RET and str(c["image"]["file"]).endswith(".jpg")]
    cats = sorted({c["category"] for c in new})
    T, LAB, COLS = 220, 30, 5
    for k in cats:
        items = [c for c in new if c["category"] == k]
        for part in range(0, len(items), 20):
            chunk = items[part:part + 20]
            rows = (len(chunk) + COLS - 1) // COLS
            sheet = Image.new("RGB", (COLS * T, rows * (T + LAB)), "white")
            d = ImageDraw.Draw(sheet)
            for i, c in enumerate(chunk):
                x, y = (i % COLS) * T, (i // COLS) * (T + LAB)
                im = Image.open(PROJ / c["image"]["file"]).convert("RGB")
                im.thumbnail((T - 8, T - 8))
                sheet.paste(im, (x + (T - im.width) // 2, y + (T - im.height) // 2))
                d.text((x + 4, y + T + 2), c["id"][:36], fill="black")
                d.text((x + 4, y + T + 14), f"{c['id'][36:72]}", fill="black")
                d.rectangle([x, y, x + T - 1, y + T + LAB - 1], outline="#bbbbbb")
            f = out / f"{k}_{part // 20 + 1}.png"
            sheet.save(f)
            print(f, len(chunk))


if __name__ == "__main__":
    if "--mosaic" in sys.argv:
        mosaic(sys.argv[sys.argv.index("--mosaic") + 1])
    elif "--rejects" in sys.argv:
        apply_rejects()
    else:
        extract()

"""Aggiunge le immagini dei componenti delle categorie propulsion, antenna e gps: estratte dai datasheet PDF gia' scaricati oppure prese
dalla pagina del prodotto. Aggiorna anche images/manifest.csv. Idempotente.

    python tools/add_images_new_categories.py <cartella-del-progetto> <cartella-di-lavoro>

La cartella di lavoro contiene i PDF (sottocartelle prop/, ant/, gps/) scaricati con fetchdoc.py."""
import csv
import io
import json
import sys
import urllib.request
from pathlib import Path

import pymupdf
from PIL import Image
from PIL.PngImagePlugin import PngInfo

PROJ, WORK = Path(sys.argv[1]), Path(sys.argv[2])
RET = "2026-10-14"
NOTICE = ("Immagine di proprieta' del produttore, qui solo come riferimento visivo del prodotto; per usi diversi (pubblicazioni, "
          "presentazioni esterne) chiedere il permesso al produttore.")
ES_UHF = "https://www.endurosat.com/wp-content/uploads/2025/01/UHF-Antenna-2U.webp"
ES_SW = "https://www.endurosat.com/wp-content/uploads/2025/01/S-Band-Atenna-Wideband.webp"
SS = "https://cdn.satsearch.com/product-images/"

# id -> (tipo, riferimento, pagina_o_documento_di_origine, nota)
PDF = lambda doc, page, k: ("pdf", (doc, page, k))  # noqa: E731
IMAGES = {
    "enpulsion-nano-r3": (PDF("prop/enp_nano.pdf", 0, 1), "https://www.enpulsion.com/wp-content/uploads/DataSheet_Nano_20260319.pdf", ""),
    "thrustme-npt30-i2-1u": (PDF("prop/thrustme.pdf", 0, 1), "https://thrustme.fr/base/stock/ProductBannerFiles/2_thrustme-npt30-i2.pdf", ""),
    "thrustme-npt30-i2-1-5u": (PDF("prop/thrustme.pdf", 1, 2), "https://thrustme.fr/base/stock/ProductBannerFiles/2_thrustme-npt30-i2.pdf", ""),
    "busek-bgt-x5": (("web", "https://images.squarespace-cdn.com/content/v1/60df2bfb6db9752ed1d79d44/1628098575936-5TP3GUU9RPFWY595BT6O/BGT-X5+System+Trio.jpeg"),
                     "https://www.busek.com/bgtx5", ""),
    "busek-bit-3": (PDF("prop/bit3.pdf", 0, 1), "https://www.busek.com/s/BIT3_v10.pdf", ""),
    "aac-pm200": (PDF("prop/pm200.pdf", 0, 2), "https://www.aac-clyde.space/wp-content/uploads/2021/11/PM200.pdf", ""),
    "vacco-mips-0-5u": (PDF("prop/mips.pdf", 0, 1), "https://www.vacco.com/images/uploads/pdfs/MiPS_standard_0714.pdf", "Foto condivisa con altre varianti della stessa famiglia: vacco-mips-1u"),
    "vacco-mips-1u": (PDF("prop/mips.pdf", 0, 1), "https://www.vacco.com/images/uploads/pdfs/MiPS_standard_0714.pdf", "Foto condivisa con altre varianti della stessa famiglia: vacco-mips-0-5u"),
    "gomspace-nanoprop-cgp3": (PDF("prop/cgp3.pdf", 1, 2), "https://satcatalog.s3.amazonaws.com/components/1082/SatCatalog_-_GomSpace_-_NanoProp_CGP3_-_Datasheet.pdf",
                               "Foto del flyer GomSpace: puo' mostrare il sistema integrato e non il solo modulo; da verificare"),
    "l3harris-mps-120-1u": (PDF("prop/mps120.pdf", 0, 3), "https://satcatalog.s3.amazonaws.com/components/892/SatCatalog_-_Aerojet_Rocketdyne_-_MPS-120-1U_-_Datasheet.pdf",
                            "Foto condivisa con le altre varianti a serbatoio a pistone (MPS-120/130 1U e 2U)"),
    "l3harris-mps-120-2u": (PDF("prop/mps120.pdf", 0, 3), "https://satcatalog.s3.amazonaws.com/components/892/SatCatalog_-_Aerojet_Rocketdyne_-_MPS-120-1U_-_Datasheet.pdf",
                            "Foto condivisa con le altre varianti a serbatoio a pistone (MPS-120/130 1U e 2U)"),
    "l3harris-mps-130-1u": (PDF("prop/mps120.pdf", 0, 3), "https://satcatalog.s3.amazonaws.com/components/892/SatCatalog_-_Aerojet_Rocketdyne_-_MPS-120-1U_-_Datasheet.pdf",
                            "Foto condivisa con le altre varianti a serbatoio a pistone (MPS-120/130 1U e 2U)"),
    "l3harris-mps-130-2u": (PDF("prop/mps120.pdf", 0, 3), "https://satcatalog.s3.amazonaws.com/components/892/SatCatalog_-_Aerojet_Rocketdyne_-_MPS-120-1U_-_Datasheet.pdf",
                            "Foto condivisa con le altre varianti a serbatoio a pistone (MPS-120/130 1U e 2U)"),
    "l3harris-mps-135-4u": (PDF("prop/mps120.pdf", 0, 4), "https://satcatalog.s3.amazonaws.com/components/892/SatCatalog_-_Aerojet_Rocketdyne_-_MPS-120-1U_-_Datasheet.pdf",
                            "Immagine della famiglia a pompa (serbatoio cilindrico)"),
    "cuaerospace-chips-180": (PDF("prop/chips.pdf", 0, 0), "https://cuaerospace.com/Portals/0/SiteContent/assets/PDF/CHIPS-Data-Sheet-230724-180.pdf", "Immagine con didascalie del CHIPS-180, condivisa con CHIPS-500 e CHIPS-1000"),
    "cuaerospace-chips-500": (PDF("prop/chips.pdf", 0, 0), "https://cuaerospace.com/Portals/0/SiteContent/assets/PDF/CHIPS-Data-Sheet-230724-180.pdf", "Immagine del CHIPS-180, condivisa con la stessa famiglia"),
    "cuaerospace-chips-1000": (PDF("prop/chips.pdf", 0, 0), "https://cuaerospace.com/Portals/0/SiteContent/assets/PDF/CHIPS-Data-Sheet-230724-180.pdf", "Immagine del CHIPS-180, condivisa con la stessa famiglia"),
    "isis-ants-1u3u": (PDF("ant/isisbro.pdf", 0, 4), "https://www.cubesatshop.com/wp-content/uploads/2016/06/ISIS-Antenna-systems-Brochure-v1.pdf", ""),
    "endurosat-uhf-antenna-iii": (("web", ES_UHF), "https://www.endurosat.com/products/uhf-antenna-iii", ""),
    "gomspace-nanocom-ant430": (PDF("ant/ant430.pdf", 0, 2), "https://satcatalog.s3.amazonaws.com/components/667/SatCatalog_-_GomSpace_-_NanoCom_ANT430_-_Datasheet.PDF", ""),
    "isis-s-band-patch": (PDF("ant/isis_s.pdf", 0, 1), "https://satcatalog.s3.amazonaws.com/components/555/SatCatalog_-_Innovative_Solutions_In_Space_-_S-Band_Patch_Antenna_-_Datasheet.pdf", ""),
    "iq-spacecom-x-band-patch": (PDF("ant/iq_xband.pdf", 0, 4), "https://www.cubesatshop.com/wp-content/uploads/2023/04/X-Band-Antenna-Datasheet-09.2022.pdf", ""),
    "endurosat-x-band-patch": (("web", SS + "image-endurosat-single-x-band-patch-antenna-rucvyr.jpg"), "https://satsearch.co/products/endurosat-x-band-single-patch-antenna", ""),
    "endurosat-x-band-2x2": (("web", SS + "image-endurosat-x-band-2x2-patch-antenna-array-ypzgfa.jpg"), "https://satsearch.co/products/endurosat-x-band-2x2-patch-array-antenna", ""),
    "endurosat-x-band-4x4": (("web", SS + "image-endurosat-x-band-4x4-patch-antenna-array-1h05wz.jpg"), "https://satsearch.co/products/endurosat-x-band-4x4-patch-array-antenna", ""),
    "endurosat-x-band-8x12": (("web", SS + "image-endurosat-x-band-8x12-patch-array-antenna-2o1sue.jpg"), "https://satsearch.co/products/endurosat-x-band-8x12-patch-array-antenna", ""),
    "endurosat-s-band-commercial": (("web", SS + "image-endurosat-s-band-antenna-commercial-i0t8nk.jpg"), "https://satsearch.co/products/endurosat-s-band-patch-antenna-type-ii", ""),
    "endurosat-s-band-wideband": (("web", ES_SW), "https://endurosat.com/products/s-band-antenna-wideband", ""),
    "newspace-ngps-03-422": (PDF("gps/newspace.pdf", 0, 4), "https://www.cubesatshop.com/wp-content/uploads/2020/11/NewSpace-GPS-Receiver_2020-10a.pdf", "Foto del datasheet: la scheda mostrata puo' essere un modello diverso della famiglia NGPS"),
    "newspace-ngps-01-422": (PDF("gps/newspace.pdf", 0, 2), "https://www.cubesatshop.com/wp-content/uploads/2020/11/NewSpace-GPS-Receiver_2020-10a.pdf", "Foto del datasheet: puo' mostrare un altro modello della famiglia NGPS"),
    "skyfox-pinav-ng": (PDF("gps/pinav.pdf", 1, 0), "https://satcatalog.s3.amazonaws.com/components/58/SatCatalog_-_SkyFox_Labs_-_piNAV-NG_-_Datasheet.pdf", ""),
    "hyperion-gnss200": (PDF("gps/gnss200.pdf", 0, 1), "https://satcatalog.s3.amazonaws.com/components/39/SatCatalog_-_Hyperion_Technologies_-_GNSS200_-_Datasheet.pdf", ""),
    "sstl-sgr-ligo": (PDF("gps/sgr.pdf", 0, 4), "https://satcatalog.s3.amazonaws.com/components/68/SatCatalog_-_Surrey_Satellite_Technology_-_SGR-Ligo_-_Datasheet.pdf", ""),
}


def fetch(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=90).read()


def get_image(kind, ref):
    if kind == "web":
        return Image.open(io.BytesIO(fetch(ref)))
    doc, page, k = ref
    d = pymupdf.open(WORK / doc)
    xref = d[page].get_images(full=True)[k][0]
    pix = pymupdf.Pixmap(d, xref)
    if pix.colorspace is None or pix.alpha or pix.colorspace.n != 3:
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    return Image.open(io.BytesIO(pix.tobytes("png")))


def slug(s):
    return "".join(ch for ch in s.title() if ch.isalnum() or ch in "-")


cat_path = PROJ / "data" / "catalog.json"
cat = json.loads(cat_path.read_text(encoding="utf-8"))
by_id = {c["id"]: c for c in cat["components"]}
rows = []
for cid, ((kind, ref), page, note) in IMAGES.items():
    c = by_id[cid]
    im = get_image(kind, ref).convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    bg.alpha_composite(im)
    im = bg.convert("RGB")
    im.thumbnail((1000, 1000))
    base = c["vendor"].split(" (")[0].replace(" ", "")
    file = f"{slug(base)}-{slug(c['name'].split(' (')[0].replace(' ', ''))}.png".replace("--", "-")
    img_url = ref if kind == "web" else (str(ref[0]).split("/")[-1] and (page + f"#page={ref[1] + 1}"))
    meta = PngInfo()
    for k, v in (("Title", f"{c['vendor']} {c['name']}"), ("Author", c["vendor"]), ("Source", img_url),
                 ("Description", f"Componente {cid}. Pagina/documento di origine: {page}. Scaricata il {RET}."), ("Copyright", NOTICE)):
        meta.add_text(k, v)
    im.save(PROJ / "images" / file, optimize=True, pnginfo=meta)
    typ = "web" if kind == "web" else "estratta dal datasheet PDF"
    c["image"] = {"file": f"images/{file}", "image_url": img_url, "page_url": page, "type": typ, "retrieved": RET}
    rows.append([cid, c["vendor"], c["name"], file, typ, img_url, page, RET, f"{im.size[0]}x{im.size[1]}", note])
    print(cid, file, im.size)
cat_path.write_text(json.dumps(cat, indent=1, ensure_ascii=False), encoding="utf-8")
mf = PROJ / "images" / "manifest.csv"
with mf.open(encoding="utf-8-sig", newline="") as f:
    old = list(csv.reader(f))
NO_IMAGE = {"spacemanic-celeste": "Nessuna immagine: la pagina del fornitore non era raggiungibile dal programma di raccolta (HTTP 466); da aggiungere a mano."}
for cid, note in NO_IMAGE.items():
    c = by_id[cid]
    c.pop("image", None)
    rows.append([cid, c["vendor"], c["name"], "", "nessuna immagine trovata", "", "", RET, "", note])
cat_path.write_text(json.dumps(cat, indent=1, ensure_ascii=False), encoding="utf-8")
keep = [r for r in old if r and r[0] not in IMAGES and r[0] not in NO_IMAGE]
with mf.open("w", encoding="utf-8-sig", newline="") as f:
    csv.writer(f).writerows(keep + rows)
print(len(rows), "immagini;", len(keep) + len(rows) - 1, "righe nel manifest")

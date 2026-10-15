"""Aggiunge le strutture 12U (GomSpace, AAC Zaphod, Spacemind SM12) al catalogo con immagini e fonti."""
import csv, io, json, sys, urllib.request
from pathlib import Path
from PIL import Image
from PIL.PngImagePlugin import PngInfo

PROJ = Path(sys.argv[1])
RET = "2026-10-13"
CDS = ("max_total_mass_kg dalla CubeSat Design Specification Rev. 14.1, Table 1 "
       "(https://www.nasa.gov/wp-content/uploads/2018/01/cubesatdesignspecificationrev14_12022-02-09.pdf), non dal fornitore. "
       "panel_faces derivato dalla geometria della struttura, non dal fornitore: le quattro facce lunghe del 12U misurano 226.3 x 366 mm, "
       "come la faccia larga del 6U (pannelli con face '6U'). ")
NOTICE = ("Immagine di proprieta' del produttore, qui solo come riferimento visivo del prodotto; per usi diversi (pubblicazioni, "
          "presentazioni esterne) chiedere il permesso al produttore.")
SPECS = {"form_factor_u": 12, "max_total_mass_kg": 24.0, "internal_volume_u": None, "panel_faces": {"6U": 4}}
METHOD = "trascritto da documento pubblico del fornitore; da controllare manualmente"
NEW = [
    dict(id="gomspace-nanostruct-12u", vendor="GomSpace", name="Nanostruct 12U", mass_kg=1.496, file="GomSpace-Nanostruct12U.png",
         img="https://gomspace.com/wp-content/uploads/2025/10/NanoStructure-12U.png", page="https://gomspace.com/product/nanostruct-12u/",
         src=dict(url="https://gomspace.com/wp-content/uploads/2025/09/gs-ds-NanoStructure_12U_Platform_DataSheet_DS_-_1043916_-_1_-_10_-_1.pdf",
                  document="GomSpace NanoStructure 12U Platform DataSheet DS 1043916 rev. 1.0 (29 novembre 2022) + pagina prodotto Nanostruct 12U"),
         notes=CDS + "Massa 1496 g = struttura di default con 2 kit di struttura secondaria (struttura principale 1010 g, 230 g ciascun kit secondario). "
                "Ingombro 340.5 x 226.3 x 226.3 mm, Al 7075-T7351, 4 killswitch retrattili, fino a 9U per il payload. Qualificata ECSS/NASA GEVS "
                "(14.1 grms) con un EQM da 20 kg: sopra i 20 kg il datasheet non da' evidenza di qualifica. Il datasheet porta un avviso di "
                "confidenzialita' GomSpace: non ridistribuire senza consenso.", extra={}),
    dict(id="aac-zaphod-12u", vendor="AAC Clyde Space", name="ZAPHOD 12U structure", mass_kg=1.386, file="AACClydeSpace-ZAPHOD-12U.png",
         img="https://cdn.satsearch.com/product-images/satsearch_product-image_8pwa1s_aac-clyde_zaphod-12u-structure.jpg",
         page="https://satsearch.co/products/aac-clyde-zaphod-12u-structure",
         src=dict(url="https://satsearch.co/products/aac-clyde-zaphod-12u-structure",
                  document="Scheda prodotto AAC Clyde Space ZAPHOD 12U Structure sul marketplace satsearch (il datasheet ZAPHOD sul sito AAC copre solo 1U-6U)"),
         notes=CDS + "Massa 1386 g, 340.5 x 226.3 x 226.3 mm, -40..+80 C. Materiale e massa massima qualificata non dichiarati nella scheda; "
                "i dati vengono da una scheda su un marketplace di terzi, non da un documento sul sito AAC: da verificare.",
         extra={"temp_op_c": [-40, 80], "family": "aac-zaphod"}),
    dict(id="spacemind-sm12", vendor="NPC Spacemind", name="SM12 CubeSat structure 12U", mass_kg=None, file="Spacemind-SM12.png",
         img="https://www.npcspacemind.com/wp-content/uploads/2025/08/struttura-12u.png", page="https://www.npcspacemind.com/product/sm12/",
         src=dict(url="https://www.npcspacemind.com/product/sm12/", document="Pagina prodotto NPC Spacemind 'SM12'"),
         notes=CDS + "Massa, materiale e volume utile NON dichiarati; prezzo solo su richiesta (serve --mass-override spacemind-sm12=KG). "
                "Ingombro 340.5 x 226.3 x 226.3 mm (senza kill switch), fino a 8 interruttori di rilascio, compatibile PC104 e PC104 PLUS.", extra={}),
]
cat_path = PROJ / "data" / "catalog.json"
cat = json.loads(cat_path.read_text(encoding="utf-8"))
cat["components"] = [c for c in cat["components"] if c["id"] not in {n["id"] for n in NEW}]
rows = []
for n in NEW:
    raw = urllib.request.urlopen(urllib.request.Request(n["img"], headers={"User-Agent": "Mozilla/5.0"}), timeout=90).read()
    im = Image.open(io.BytesIO(raw)).convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    bg.alpha_composite(im)
    im = bg.convert("RGB")
    im.thumbnail((1000, 1000))
    meta = PngInfo()
    for k, v in (("Title", f"{n['vendor']} {n['name']}"), ("Author", n["vendor"]), ("Source", n["img"]),
                 ("Description", f"Componente {n['id']}. Pagina/documento di origine: {n['page']}. Scaricata il {RET}."), ("Copyright", NOTICE)):
        meta.add_text(k, v)
    im.save(PROJ / "images" / n["file"], optimize=True, pnginfo=meta)
    rows.append([n["id"], n["vendor"], n["name"], n["file"], "web", n["img"], n["page"], RET, f"{im.size[0]}x{im.size[1]}", ""])
    c = {"id": n["id"], "category": "structure", "vendor": n["vendor"], "name": n["name"], "mass_kg": n["mass_kg"], **n["extra"], "notes": n["notes"],
         "source": {**n["src"], "retrieved": RET, "verified": False, "method": METHOD}, "specs": dict(SPECS),
         "image": {"file": f"images/{n['file']}", "image_url": n["img"], "page_url": n["page"], "type": "web", "retrieved": RET}}
    cat["components"].append(c)
    print(n["id"], im.size)
cat_path.write_text(json.dumps(cat, indent=1, ensure_ascii=False), encoding="utf-8")
mf = PROJ / "images" / "manifest.csv"
with mf.open("a", newline="", encoding="utf-8-sig") as f:
    csv.writer(f).writerows(rows)

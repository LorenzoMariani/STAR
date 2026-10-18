"""Aggiunge al catalogo quattro pannelli solari 1U da documenti pubblici dei fornitori (il catalogo non aveva nessun pannello per 1U).

  isis-solar-1u         ISISpace Solar Panels Brochure v1 (gia' in datasheets/): 1U 2.3 W, 50 g
  endurosat-solar-1u    EnduroSat Product Catalogue 02/2022 (gia' in datasheets/), pag. 17: 1U 2.4 W; massa e quote non pubblicate
  dhv-1u-xy, dhv-1u-z   DHV Technology "CubeSat Products overview" (brochure, 24 pag.), pag. 4-5: tabella elettrica e disegno meccanico

uso: python tools/add_solar_1u.py <cartella con dhv_a.pdf gia' scaricato>      (il PDF DHV: https://cdn-assets.inwink.com/dc9072b4-cd94-4669-ba98-1adcec9979bf/61a4eb6f-9616-46a6-96b4-ab411b285959)
Idempotente. Nessun valore e' stimato: massa e spessore non pubblicati restano null.
"""
import csv
import json
import shutil
import sys
from pathlib import Path

import pymupdf
from PIL import Image
from PIL.PngImagePlugin import PngInfo

PROJ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from add_datasheets import short_name  # noqa: E402

RET = "2026-10-15"
VERIFIED = {"verified": False, "method": "trascritto da documento pubblico del fornitore; da controllare manualmente"}
NOTICE = ("Immagine di proprieta' del produttore, qui solo come riferimento visivo del prodotto; per usi diversi (pubblicazioni, "
          "presentazioni esterne) chiedere il permesso al produttore.")
DHV_URL = "https://cdn-assets.inwink.com/dc9072b4-cd94-4669-ba98-1adcec9979bf/61a4eb6f-9616-46a6-96b4-ab411b285959"
DHV_DOC = "DHV Technology CubeSat Products overview (brochure, 24 pagine)"
ES_URL = "https://endurosat.com/wp-content/uploads/2022/02/Endurosat_Product_Catalogue_02_22.pdf"
SHAPE = {"type": "panel", "axis": None, "basis": "image", "set": RET}


def save_png(im, name, vendor, title, source, page):
    meta = PngInfo()
    for k, v in (("Title", f"{vendor} {title}"), ("Author", vendor), ("Source", source), ("Description", f"Pannello solare 1U. Pagina/documento di origine: {page}. Scaricata il {RET}."), ("Copyright", NOTICE)):
        meta.add_text(k, v)
    im.save(PROJ / "images" / name, optimize=True, pnginfo=meta)
    return f"{im.size[0]}x{im.size[1]}"


def main():
    work = Path(sys.argv[1])
    cat_path = PROJ / "data" / "catalog.json"
    cat = json.loads(cat_path.read_text(encoding="utf-8"))
    comps = cat["components"]
    by_id = {c["id"]: c for c in comps}
    isis3, es3 = by_id["isis-solar-3u"], by_id["endurosat-structure-3u"]

    # --- DHV: PDF e immagine (pagina 4)
    dhv_file = "datasheets/" + short_name("DHV-Technology__CubeSat-Products-Overview.pdf")
    shutil.copyfile(work / "dhv_a.pdf", PROJ / dhv_file)
    dhv_doc = pymupdf.open(PROJ / dhv_file)
    pix = dhv_doc[3].get_pixmap(dpi=200)
    full = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    k = 200 / 70
    dhv_im = full.crop((int(28 * k), int(168 * k), int(236 * k), int(392 * k)))
    dhv_px = save_png(dhv_im, "DHV-1USolarPanel.png", "DHV Technology", "1U solar panel (DHV-1U Series)", DHV_URL + "#page=4", DHV_URL)
    # --- EnduroSat: immagine del pannello 1U dalla pagina 16 del catalogo
    es_doc = pymupdf.open(PROJ / "datasheets" / "EnduroSat__Endurosat_Product_Catalogue_02_22.pdf")
    img = pymupdf.Pixmap(es_doc, 417)
    es_im = Image.frombytes("RGB" if img.n < 4 else "RGBA", (img.width, img.height), img.samples).convert("RGB")
    es_im = es_im.crop((290, 62, 585, 412))        # senza il bordo nero della diapositiva
    es_px = save_png(es_im, "EnduroSat-1USolarPanel.png", "EnduroSat", "1U Solar Panel", ES_URL + "#page=16", ES_URL)

    dhv_ds = {"file": dhv_file, "document": DHV_DOC, "source_url": DHV_URL, "retrieved": RET, "bytes": (PROJ / dhv_file).stat().st_size}
    dhv_img = {"file": "images/DHV-1USolarPanel.png", "image_url": DHV_URL + "#page=4", "page_url": DHV_URL, "type": "estratta dal datasheet PDF", "retrieved": RET}
    dhv_notes = ("Brochure DHV 'CubeSat Products overview' pag. 4-5. 2 celle AzurSpace 3G30A con vetro di copertura da 100 um (2S1P), 2 diodi di blocco in parallelo, diodi di bypass, "
                 "sensore di temperatura digitale/analogico, fotodiodo, magnetorquer opzionale; TRL 9; almeno 3 anni in LEO tra -50 e +125 C. Parametri elettrici (tabella): Pmp BOL 2.47 W a -50 C, "
                 "2.07 W a 28 C, 1.52 W a 125 C; EOL 2.33 / 1.93 / 1.38 W; Voc BOL 6.35 / 5.38 / 4.18 V. peak_power_w = 2.47 W (massimo della tabella, BOL, -50 C) e "
                 "open_circuit_voltage_v = 6.35 V (massimo, -50 C). Massa e spessore non sono pubblicati nel brochure (il datasheet e' un documento separato, non scaricato). "
                 "Le due varianti (XY laterale e Z superiore/inferiore) hanno gli stessi parametri elettrici.")
    new = [
        {"id": "isis-solar-1u", "category": "solar_panel", "vendor": "ISISpace", "name": "Solar Panel 1U", "mass_kg": 0.05, "temp_op_c": [-40, 125],
         "notes": ("Celle GaAs AZUR Space, efficienza 30%. Potenza di picco 1U: 2.3 W; tensione 3 V standard (5 V e 8 V su richiesta). Massa dichiarata '1U: 50 g, dipende dalla "
                   "configurazione'. Spessore: pannello laterale 2.5 mm, superiore e inferiore 1.8 mm. Tolleranza alle radiazioni: 'minimo 2 anni in LEO' (nessun valore di TID). "
                   "Stessa brochure, stessa foto e stesso documento di isis-solar-3u."),
         "source": {"url": isis3["source"]["url"], "document": isis3["source"]["document"], "retrieved": RET, **VERIFIED},
         "specs": {"face": "1U", "peak_power_w": 2.3, "voltage_options_v": [3, 5, 8], "open_circuit_voltage_v": None, "degradation_per_year": None},
         "dimensions": {"mm": [100, 113.5, 2.5], "basis": "derived", "note": "Brochure ISIS: pannello laterale 1U, spessore 2.5 mm (superiore e inferiore 1.8 mm); taglia di faccia nominale CDS 1U (100 x 113.5 mm)."},
         "image": {**isis3["image"], "note": "Foto condivisa con altre varianti/componenti della stessa famiglia: isis-solar-3u"},
         "datasheet": dict(isis3["datasheet"]), "shape": dict(SHAPE)},
        {"id": "endurosat-solar-1u", "category": "solar_panel", "vendor": "EnduroSat", "name": "1U Solar Panel", "mass_kg": None,
         "notes": ("Catalogo EnduroSat 02/2022 pag. 17: 2 celle AZUR Space 3G30A in 2S1P, efficienza fino al 30%, potenza massima in LEO 2.4 W; sensori di sole e temperatura, giroscopio e "
                   "magnetorquer opzionali, interfaccia SPI. Massa, dimensioni e tensioni non sono pubblicate nel catalogo; le pagine prodotto del sito non sono piu' raggiungibili "
                   "(l'indirizzo '1u-solar-panel-x-y' rimanda all'elenco dei pannelli) e i valori degli aggregatori non sono stati usati."),
         "source": {"url": ES_URL, "document": "EnduroSat Product Catalogue 02/2022", "retrieved": RET, **VERIFIED},
         "specs": {"face": "1U", "peak_power_w": 2.4, "voltage_options_v": None, "open_circuit_voltage_v": None, "degradation_per_year": None},
         "image": {"file": "images/EnduroSat-1USolarPanel.png", "image_url": ES_URL + "#page=16", "page_url": ES_URL, "type": "estratta dal datasheet PDF", "retrieved": RET},
         "datasheet": dict(es3["datasheet"]), "shape": dict(SHAPE)},
        {"id": "dhv-1u-xy", "category": "solar_panel", "vendor": "DHV Technology", "name": "DHV-1U-XY solar panel (1U, lateral)", "mass_kg": None, "temp_op_c": [-50, 125],
         "notes": dhv_notes + " Dimensioni dal disegno 'Mechanical interface' (pag. 5): ingombro 82.80 x 97.80 mm.",
         "source": {"url": DHV_URL, "document": DHV_DOC, "retrieved": RET, **VERIFIED},
         "specs": {"face": "1U", "peak_power_w": 2.47, "voltage_options_v": None, "open_circuit_voltage_v": 6.35, "degradation_per_year": None},
         "dimensions": {"mm": [82.8, 97.8, None], "basis": "declared", "note": "Disegno 'Mechanical interface' del brochure DHV (pag. 5): 82.80 x 97.80 mm; spessore non indicato."},
         "image": dict(dhv_img), "datasheet": dict(dhv_ds), "shape": dict(SHAPE)},
        {"id": "dhv-1u-z", "category": "solar_panel", "vendor": "DHV Technology", "name": "DHV-1U-Z solar panel (1U, top/bottom)", "mass_kg": None, "temp_op_c": [-50, 125],
         "notes": dhv_notes + " Dimensioni dal disegno 'Mechanical interface' (pag. 5): ingombro 97.80 x 97.80 mm.",
         "source": {"url": DHV_URL, "document": DHV_DOC, "retrieved": RET, **VERIFIED},
         "specs": {"face": "1U Z", "peak_power_w": 2.47, "voltage_options_v": None, "open_circuit_voltage_v": 6.35, "degradation_per_year": None},
         "dimensions": {"mm": [97.8, 97.8, None], "basis": "declared", "note": "Disegno 'Mechanical interface' del brochure DHV (pag. 5): 97.80 x 97.80 mm; spessore non indicato."},
         "image": {**dhv_img, "note": "Foto condivisa con altre varianti/componenti della stessa famiglia: dhv-1u-xy"}, "datasheet": dict(dhv_ds), "shape": dict(SHAPE)},
    ]
    # non duplicare: si sostituisce una voce con lo stesso id; le nuove vanno dopo l'ultimo pannello solare
    ids = {c["id"] for c in new}
    comps[:] = [c for c in comps if c["id"] not in ids]
    last = max(i for i, c in enumerate(comps) if c["category"] == "solar_panel")
    comps[last + 1:last + 1] = new
    cat_path.write_text(json.dumps(cat, indent=1, ensure_ascii=False), encoding="utf-8")

    # --- manifest delle immagini e dei datasheet
    mf = PROJ / "images" / "manifest.csv"
    with mf.open(encoding="utf-8-sig", newline="") as fh:
        rows = [r for r in csv.reader(fh) if r and r[0] not in ids]
    px = {"DHV-1USolarPanel.png": dhv_px, "EnduroSat-1USolarPanel.png": es_px}
    for c in new:
        im = c["image"]
        fname = Path(im["file"]).name
        rows.append([c["id"], c["vendor"], c["name"], fname, im["type"], im["image_url"], im["page_url"], im["retrieved"], px.get(fname, "510x298"), im.get("note", "")])
    with mf.open("w", encoding="utf-8-sig", newline="") as fh:
        csv.writer(fh).writerows(rows)
    dm = PROJ / "datasheets" / "manifest.csv"
    with dm.open(encoding="utf-8-sig", newline="") as fh:
        drows = list(csv.reader(fh))
    for r in drows[1:]:
        ids_in = [x for x in r[5].split() if x not in ids]
        if r[0] == Path(isis3["datasheet"]["file"]).name:
            ids_in.append("isis-solar-1u")
        if r[0] == Path(es3["datasheet"]["file"]).name:
            ids_in.append("endurosat-solar-1u")
        r[5] = " ".join(ids_in)
    drows = [r for r in drows if r[0] != Path(dhv_file).name]
    drows.append([Path(dhv_file).name, DHV_DOC, DHV_URL, RET, str(dhv_ds["bytes"]), "dhv-1u-xy dhv-1u-z"])
    with dm.open("w", encoding="utf-8-sig", newline="") as fh:
        csv.writer(fh).writerows(drows)
    print(f"{len(new)} pannelli 1U aggiunti; catalogo: {len(comps)} componenti")


if __name__ == "__main__":
    main()

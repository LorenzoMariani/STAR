"""Aggiunge la categoria `sun_sensor` (sensori solari) con cinque componenti da documenti pubblici dei fornitori.

  newspace-ncss-sa05, newspace-nfss-411   NewSpace Systems, datasheet "Sun Sensor" 2020-10a (cubesatshop.com)
  solarmems-ssoc-a60                      Solar MEMS, "SSOC-A60 Technical Specification, Interfaces & Operation" v1.14 (nov 2015)
  solarmems-nanossoc-d60                  brochure nanoSSOC-D60 di SpaceQuest (distributore di Solar MEMS), NSD60-07-MAN-102
  cubespace-cubesense-sun                 pagina prodotto CubeSatShop "Fine Sun Sensor - CubeSense Sun" (CubeSpace): nessun PDF

uso: python tools/add_sun_sensors.py <cartella con nss_2020.pdf, ssoca60.pdf, aac_nsd.pdf, cubesense_orig.png gia' scaricati>
Idempotente. Nessun valore e' stimato: i valori derivati (potenza = corrente x tensione, campo di vista pieno da +-60 gradi) sono marcati nelle note.
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
NSS_URL = "https://www.cubesatshop.com/wp-content/uploads/2020/11/NewSpace-Sun-Sensor_2020-10a.pdf"
SSOC_URL = "https://www.cubesatshop.com/wp-content/uploads/2016/06/SSOCA60-Technical-Specifications.pdf"
NSD_URL = "https://www.aac-clyde.space/wp-content/uploads/2021/11/NSD_60_07_MAN_102_Brochure_SQ_20160525_4036cc7b30.pdf"
CS_URL = "https://www.cubesatshop.com/product/fine-sun-sensor-cubesense-sun/"
CS_IMG = "https://www.cubesatshop.com/wp-content/uploads/2023/06/Cubesense-Sun.png"
SHAPE = {"type": "box", "axis": None, "basis": "image", "set": RET}


def save_png(im, name, vendor, title, source, page):
    meta = PngInfo()
    for k, v in (("Title", f"{vendor} {title}"), ("Author", vendor), ("Source", source), ("Description", f"Sensore solare. Pagina/documento di origine: {page}. Scaricata il {RET}."), ("Copyright", NOTICE)):
        meta.add_text(k, v)
    im.save(PROJ / "images" / name, optimize=True, pnginfo=meta)
    return f"{im.size[0]}x{im.size[1]}"


def render(pdf, page, dpi):
    p = pymupdf.open(pdf)[page].get_pixmap(dpi=dpi)
    return Image.frombytes("RGB", (p.width, p.height), p.samples)


def trim(im, margin=0.12, thr=24):
    """Ritaglia lo sfondo nero di un'immagine."""
    g = im.convert("L").point(lambda v: 255 if v > thr else 0)
    box = g.getbbox()
    if not box:
        return im
    w, h = box[2] - box[0], box[3] - box[1]
    mx, my = int(w * margin), int(h * margin)
    return im.crop((max(0, box[0] - mx), max(0, box[1] - my), min(im.width, box[2] + mx), min(im.height, box[3] + my)))


def main():
    work = Path(sys.argv[1])
    cat_path = PROJ / "data" / "catalog.json"
    cat = json.loads(cat_path.read_text(encoding="utf-8"))
    comps = cat["components"]

    docs = {"nss": ("NewSpace-Systems__NewSpace-Sun-Sensor_2020-10a.pdf", "nss_2020.pdf", NSS_URL, "NewSpace Systems Sun Sensor datasheet (NCSS-SA05 e NFSS-411), 2020-10a"),
            "ssoc": ("Solar-MEMS__SSOC-A60-Technical-Specifications.pdf", "ssoca60.pdf", SSOC_URL, "Solar MEMS SSOC-A60 Technical Specification, Interfaces & Operation v1.14 (novembre 2015)"),
            "nsd": ("Solar-MEMS__nanoSSOC-D60-Brochure.pdf", "aac_nsd.pdf", NSD_URL, "SpaceQuest (distributore Solar MEMS): brochure nanoSSOC-D60 (NSD60-07-MAN-102)")}
    ds = {}
    for key, (name, src, url, doc) in docs.items():
        f = "datasheets/" + short_name(name)
        shutil.copyfile(work / src, PROJ / f)
        ds[key] = {"file": f, "document": doc, "source_url": url, "retrieved": RET, "bytes": (PROJ / f).stat().st_size}

    # immagini (ritagli dei documenti; CubeSense dalla pagina prodotto)
    k = 250 / 75
    nss = render(work / "nss_2020.pdf", 0, 250)
    px = {}
    px["NewSpace-NCSS-SA05.png"] = save_png(nss.crop((int(245 * k), int(225 * k), int(360 * k), int(305 * k))), "NewSpace-NCSS-SA05.png", "NewSpace Systems", "NCSS-SA05", NSS_URL + "#page=1", NSS_URL)
    px["NewSpace-NFSS-411.png"] = save_png(nss.crop((int(425 * k), int(150 * k), int(568 * k), int(298 * k))), "NewSpace-NFSS-411.png", "NewSpace Systems", "NFSS-411", NSS_URL + "#page=1", NSS_URL)
    k2 = 200 / 75
    px["SolarMEMS-nanoSSOC-D60.png"] = save_png(render(work / "aac_nsd.pdf", 0, 200).crop((int(305 * k2), int(222 * k2), int(558 * k2), int(305 * k2))), "SolarMEMS-nanoSSOC-D60.png", "Solar MEMS", "nanoSSOC-D60", NSD_URL + "#page=1", NSD_URL)
    k3 = 200 / 60
    px["SolarMEMS-SSOC-A60.png"] = save_png(render(work / "ssoca60.pdf", 0, 200).crop((int(90 * k3), int(95 * k3), int(290 * k3), int(215 * k3))), "SolarMEMS-SSOC-A60.png", "Solar MEMS", "SSOC-A60", SSOC_URL + "#page=1", SSOC_URL)
    cs = trim(Image.open(work / "cubesense_orig.png").convert("RGB"))
    px["CubeSpace-CubeSenseSun.png"] = save_png(cs, "CubeSpace-CubeSenseSun.png", "CubeSpace", "CubeSense Sun", CS_IMG, CS_URL)

    def img(file, url, page_url, typ="estratta dal datasheet PDF", note=None):
        d = {"file": "images/" + file, "image_url": url, "page_url": page_url, "type": typ, "retrieved": RET}
        if note:
            d["note"] = note
        return d

    new = [
        {"id": "newspace-ncss-sa05", "category": "sun_sensor", "vendor": "NewSpace Systems", "name": "NCSS-SA05 coarse sun sensor", "mass_kg": 0.005, "temp_op_c": [-25, 70], "power_w": 0.05,
         "notes": ("Datasheet 2020-10a: campo di vista 114 gradi, frequenza di aggiornamento '>10 Hz (limitata dall'ADC del cliente)' (si riporta 10), accuratezza '<0.01 gradi di errore RMS sul campo di vista' "
                   "come stampata nel datasheet. Massa '<5 g' (limite superiore). Corrente '<10 mA a 5 V': potenza 0.05 W DERIVATA (5 V x 10 mA), non dichiarata in W. Interfaccia: 5 canali analogici, "
                   "connettore Nano-D a 9 vie femmina, 3 fori filettati M2. Radiazioni: n.d. Una scheda di un aggregatore dichiara per lo stesso sensore un'accuratezza migliore di 0.5 gradi: "
                   "non e' coerente con il datasheet e non e' stata usata."),
         "source": {"url": NSS_URL, "document": docs["nss"][3], "retrieved": RET, **VERIFIED},
         "specs": {"sensor_type": "coarse", "fov_deg": [114], "accuracy_deg": 0.01, "accuracy_basis": "RMS", "update_rate_hz": 10, "data_interfaces": ["analogue"], "supply_voltage_ranges_v": [[5, 5]]},
         "dimensions": {"mm": [33, 11, 6], "basis": "declared", "note": "Datasheet NewSpace Systems 2020-10a."},
         "image": img("NewSpace-NCSS-SA05.png", NSS_URL + "#page=1", NSS_URL), "datasheet": dict(ds["nss"]), "shape": dict(SHAPE)},
        {"id": "newspace-nfss-411", "category": "sun_sensor", "vendor": "NewSpace Systems", "name": "NFSS-411 fine sun sensor", "mass_kg": 0.035, "temp_op_c": [-25, 70], "power_w": 0.15, "tid_krad": 20,
         "notes": ("Datasheet 2020-10a: campo di vista 140 gradi; accuratezza '<=0.1 gradi di errore RMS su 120 gradi di campo di vista'; aggiornamento 5 Hz tipico. Massa '<35 g' (limite superiore). "
                   "Potenza: in attesa <3 mA [15 mW], modo bootloader <8 mA [40 mW], modo applicazione attivo <30 mA [150 mW] (si riporta 0.15 W). Alimentazione da 5 V a 50 V (5 V nominale); "
                   "interfaccia RS-485 UART; connettore Micro-D a 9 vie; 4 fori passanti M2. Radiazioni: 20 krad a livello di componente. Davanti ha una finestra di zaffiro sintetico con fessure incise."),
         "source": {"url": NSS_URL, "document": docs["nss"][3], "retrieved": RET, **VERIFIED},
         "specs": {"sensor_type": "fine", "fov_deg": [140], "accuracy_deg": 0.1, "accuracy_basis": "RMS", "update_rate_hz": 5, "data_interfaces": ["RS-485 UART"], "supply_voltage_ranges_v": [[5, 50]]},
         "dimensions": {"mm": [34, 40, 20], "basis": "declared", "note": "Datasheet NewSpace Systems 2020-10a (una scheda precedente, versione 6a, secondo un aggregatore riportava 34 x 32 x 20 mm: non verificato)."},
         "image": img("NewSpace-NFSS-411.png", NSS_URL + "#page=1", NSS_URL, note="Foto dal datasheet: la stessa pagina mostra NCSS-SA05 e NFSS-411"), "datasheet": dict(ds["nss"]), "shape": {**SHAPE, "type": "cylinder", "axis": 2}},     # disco con la finestra in alto: l'asse e' la quota di 20 mm
        {"id": "solarmems-ssoc-a60", "category": "sun_sensor", "vendor": "Solar MEMS Technologies", "name": "SSOC-A60 sun sensor on a chip (analog)", "mass_kg": 0.025, "temp_op_c": [-45, 85], "power_w": 0.036, "tid_krad": 100,
         "notes": ("Documento Solar MEMS v1.14 (novembre 2015): due assi ortogonali, campo di vista +-60 gradi (120 gradi pieno, DERIVATO dal +-60), accuratezza '<0.3 gradi', precisione '<0.05 gradi' "
                   "(la base statistica non e' dichiarata), alimentazione 5.00 V, consumo '<36 mW', dimensioni ridotte 30 x 30 x 12 mm, peso 25 g, temperatura -45..85 C, radiazioni 'TID >100 krad' "
                   "(limite inferiore), LET 6 MeV/mg/cm2, shock 3000 g, vibrazioni 14 g; sensore di temperatura incluso. Uscita analogica. Il fornitore non lo classifica fine o coarse."),
         "source": {"url": SSOC_URL, "document": docs["ssoc"][3], "retrieved": RET, **VERIFIED},
         "specs": {"sensor_type": None, "fov_deg": [120], "accuracy_deg": 0.3, "accuracy_basis": None, "update_rate_hz": None, "data_interfaces": ["analogue"], "supply_voltage_ranges_v": [[5, 5]]},
         "dimensions": {"mm": [30, 30, 12], "basis": "declared", "note": "Documento Solar MEMS: 'Reduced size: 30 x 30 x 12 mm'."},
         "image": img("SolarMEMS-SSOC-A60.png", SSOC_URL + "#page=1", SSOC_URL), "datasheet": dict(ds["ssoc"]), "shape": dict(SHAPE)},
        {"id": "solarmems-nanossoc-d60", "category": "sun_sensor", "vendor": "Solar MEMS Technologies", "name": "nanoSSOC-D60 sun sensor (digital)", "mass_kg": 0.0065, "temp_op_c": [-30, 85], "power_w": 0.115, "tid_krad": 30,
         "notes": ("Brochure SpaceQuest (distributore): due assi ortogonali, campo di vista +-60 gradi (120 gradi pieno, DERIVATO dal +-60), accuratezza '<0.5 gradi (3 sigma)', precisione '<0.1 gradi', "
                   "interfaccia UART, I2C o SPI (connettore a 10 pin), alimentazione 3.3 V o 5 V, consumo '<23 mA': potenza 0.115 W DERIVATA (5 V x 23 mA), non dichiarata in W. Involucro in alluminio 6082 "
                   "anodizzato nero; temperatura -30..85 C; radiazioni 30 krad (gamma); piu' di 50 modelli di volo consegnati per piu' di 15 missioni. Il fornitore non lo classifica fine o coarse."),
         "source": {"url": NSD_URL, "document": docs["nsd"][3], "retrieved": RET, **VERIFIED},
         "specs": {"sensor_type": None, "fov_deg": [120], "accuracy_deg": 0.5, "accuracy_basis": "3-sigma", "update_rate_hz": None, "data_interfaces": ["UART", "I2C", "SPI"], "supply_voltage_ranges_v": [[3.3, 3.3], [5, 5]]},
         "dimensions": {"mm": [43, 14, 5.9], "basis": "declared", "note": "Brochure SpaceQuest/Solar MEMS: 43 x 14 x 5.9 mm."},
         "image": img("SolarMEMS-nanoSSOC-D60.png", NSD_URL + "#page=1", NSD_URL), "datasheet": dict(ds["nsd"]), "shape": dict(SHAPE)},
        {"id": "cubespace-cubesense-sun", "category": "sun_sensor", "vendor": "CubeSpace", "name": "CubeSense Sun fine sun sensor", "mass_kg": 0.015, "temp_op_c": [-20, 80], "power_w": 0.174, "tid_krad": 24,
         "notes": ("Pagina prodotto CubeSatShop (informazioni del fornitore CubeSpace): sensore CMOS con modello di distorsione precalibrato, accuratezza 0.2 gradi (rollio ed elevazione, 2 sigma), "
                   "velocita' angolare massima 70 gradi/s, campo di vista di rilevazione 166 gradi (orizzontale e verticale) e 176 gradi in diagonale, aggiornamento fino a 2 Hz, alimentazione 3.3 V, "
                   "potenza di picco 174 mW e media 100 mW (si riporta il picco), bus CAN/UART/RS-485 (I2C su richiesta), connettore Molex Pico-Lock Plus, dimensioni 35 x 22 x 24 mm (L x A x P), "
                   "radiazioni 24 krad, vibrazioni 14.16 g rms, vuoto termico -20..80 C, vita 5+ anni. Nessun PDF: la pagina e' la sola fonte."),
         "source": {"url": CS_URL, "document": "Pagina prodotto CubeSatShop 'Fine Sun Sensor - CubeSense Sun' (CubeSpace)", "retrieved": RET, **VERIFIED},
         "specs": {"sensor_type": "fine", "fov_deg": [166], "accuracy_deg": 0.2, "accuracy_basis": "2-sigma", "update_rate_hz": 2, "data_interfaces": ["CAN", "UART", "RS-485"], "supply_voltage_ranges_v": [[3.3, 3.3]]},
         "dimensions": {"mm": [35, 22, 24], "basis": "declared", "note": "Pagina prodotto: 'Dimensions [WxHxL] 35x22x24 mm'."},
         "image": img("CubeSpace-CubeSenseSun.png", CS_IMG, CS_URL, typ="web"), "shape": dict(SHAPE)},
    ]
    ids = {c["id"] for c in new}
    comps[:] = [c for c in comps if c["id"] not in ids]
    last = max(i for i, c in enumerate(comps) if c["category"] == "star_tracker")
    comps[last + 1:last + 1] = new
    cat_path.write_text(json.dumps(cat, indent=1, ensure_ascii=False), encoding="utf-8")

    mf = PROJ / "images" / "manifest.csv"
    with mf.open(encoding="utf-8-sig", newline="") as fh:
        rows = [r for r in csv.reader(fh) if r and r[0] not in ids]
    for c in new:
        im = c["image"]
        fname = Path(im["file"]).name
        rows.append([c["id"], c["vendor"], c["name"], fname, im["type"], im["image_url"], im["page_url"], im["retrieved"], px[fname], im.get("note", "")])
    with mf.open("w", encoding="utf-8-sig", newline="") as fh:
        csv.writer(fh).writerows(rows)

    dm = PROJ / "datasheets" / "manifest.csv"
    with dm.open(encoding="utf-8-sig", newline="") as fh:
        drows = [r for r in csv.reader(fh)]
    new_files = {Path(d["file"]).name for d in ds.values()}
    drows = [r for r in drows if r[0] not in new_files]
    members = {"nss": "newspace-ncss-sa05 newspace-nfss-411", "ssoc": "solarmems-ssoc-a60", "nsd": "solarmems-nanossoc-d60"}
    for key, d in ds.items():
        drows.append([Path(d["file"]).name, d["document"], d["source_url"], RET, str(d["bytes"]), members[key]])
    with dm.open("w", encoding="utf-8-sig", newline="") as fh:
        csv.writer(fh).writerows(drows)
    print(f"{len(new)} sensori solari aggiunti; catalogo: {len(comps)} componenti")


if __name__ == "__main__":
    main()

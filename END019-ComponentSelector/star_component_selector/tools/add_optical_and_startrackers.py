"""Aggiunge al catalogo i star tracker (nuova categoria `star_tracker`) e i terminali di comunicazione ottica (payload_type
'optical_terminal') con immagini e fonti; aggiorna i payload esistenti ai nuovi campi.

    python tools/add_optical_and_startrackers.py <cartella-del-progetto> <cartella-di-lavoro>

La cartella di lavoro contiene i PDF scaricati (cubecat.pdf, st200_1.pdf, rl_st.pdf): vedi fetch_pdfs.py.
Idempotente: rieseguirlo sostituisce le voci con gli stessi id."""
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
RET = "2026-10-13"
METHOD = "trascritto da documento pubblico del fornitore; da controllare manualmente"
NOTICE = ("Immagine di proprieta' del produttore, qui solo come riferimento visivo del prodotto; per usi diversi (pubblicazioni, "
          "presentazioni esterne) chiedere il permesso al produttore.")
NEW_PAYLOAD_KEYS = ["payload_type", "link_type", "link_data_rate_mbps", "uplink_data_rate_kbps", "max_range_km", "wavelength_nm", "host_pointing_deg"]
ACCURACY_NOTE = ("accuracy_cross_arcsec / accuracy_roll_arcsec sono riportati come dichiarati dal fornitore: la base statistica e' in accuracy_basis "
                 "(il selettore confronta 3-sigma/3 con 1-sigma e tratta RMS come 1-sigma). ")


def fetch(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=90).read()


def pdf_image(pdf, page_numbers=(0,), min_px=200):
    doc = pymupdf.open(WORK / pdf)
    best = None
    for pn in page_numbers:
        for xref, *_ in doc[pn].get_images(full=True):
            try:
                pix = pymupdf.Pixmap(doc, xref)
                if pix.colorspace is None or pix.alpha or pix.colorspace.n != 3:
                    pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
            except Exception:  # noqa: BLE001
                continue
            if min(pix.width, pix.height) >= min_px and (best is None or pix.width * pix.height > best[0]):
                best = (pix.width * pix.height, pix, pn)
    return Image.open(io.BytesIO(best[1].tobytes("png"))), best[2]


def nul(**kw):
    return kw


# ---------------------------------------------------------------- star tracker
ST = [
    dict(id="hyperion-st200", vendor="Hyperion Technologies (AAC Hyperion)", name="ST200 star tracker", file="Hyperion-ST200.png", mass=0.042, power=0.7,
         volume=0.032, trl=None, heritage=20, tid=9, temp=[-20, 40], family="hyperion-st",
         src=dict(url="https://www.aac-clyde.space/wp-content/uploads/2021/11/ST200-1.pdf", document="AAC Hyperion ST200 Star Tracker datasheet (release 22 Feb 2023)"),
         page="https://www.aac-clyde.space/?p=1532", img=("pdf", "st200_1.pdf", "https://www.aac-clyde.space/wp-content/uploads/2021/11/ST200-1.pdf#page=1"),
         notes=ACCURACY_NOTE + "Massa 42 g (senza baffle), 29 x 29 x 38.1 mm, potenza 370 mW minima / 700 mW tipica / 1 W massima (usata la tipica), 3.6-34 V, "
               "UART TTL di serie (RS-422, RS-485, I2C opzionali), -20..+40 C, tolleranza alle radiazioni 9 krad (Si), 5 Hz, velocita' massima 0.3 deg/s (tip/tilt) "
               "e 0.6 deg/s (roll). In volo dal 2015 su oltre 20 missioni (usato 20). Baffle opzionali da 30 e 45 gradi di esclusione solare (non inclusi nella massa). "
               "Campo di vista non dichiarato nel datasheet. Prezzo non pubblicato.",
         specs=dict(accuracy_cross_arcsec=30.0, accuracy_roll_arcsec=200.0, accuracy_basis="3-sigma", update_rate_hz=5.0, fov_deg=None,
                    data_interfaces=["UART"], supply_voltage_ranges_v=[[3.6, 34.0]])),
    dict(id="cubespace-cubestar", vendor="CubeSpace", name="CubeStar star tracker", file="CubeSpace-CubeStar.png", mass=0.047, power=0.165, volume=0.041, trl=None,
         heritage=None, tid=24, temp=[-20, 80], family="cubespace-cubestar",
         src=dict(url="https://www.cubesatshop.com/product/star-tracker-cubestar/", document="Pagina prodotto CubeSat Shop 'Star Tracker - CubeStar' (CubeSpace)"),
         page="https://www.cubesatshop.com/product/star-tracker-cubestar/", img=("web", "https://www.cubesatshop.com/wp-content/uploads/2023/06/CubeStar.png"),
         notes=ACCURACY_NOTE + "Massa 47 g, 35 x 49 x 24 mm, potenza 165 mW media e 271 mW di picco a 3.3 V, accuratezza 0.02 gradi (72 arcsec) trasversale e 0.06 gradi "
               "(216 arcsec) in roll, 3-sigma, fino a 1 Hz, campo di vista 42 x 42 gradi (59.4 diagonale), CAN, UART, RS-485 (I2C su richiesta), 24 krad (la pagina la "
               "chiama 'radiation tolerance'), -20..+80 C in vuoto termico (avvio a freddo e a caldo -35..+70 C), velocita' massima 0.3 gradi/s, vita 5+ anni. "
               "La pagina rimanda a 'Option Sheet e ICD' su richiesta: nessun datasheet pubblico. Prezzo su richiesta.",
         specs=dict(accuracy_cross_arcsec=72.0, accuracy_roll_arcsec=216.0, accuracy_basis="3-sigma", update_rate_hz=1.0, fov_deg=[42.0, 42.0],
                    data_interfaces=["CAN", "UART", "RS-485"], supply_voltage_ranges_v=[[3.3, 3.3]])),
    dict(id="rocketlab-st16rt2", vendor="Rocket Lab (Sinclair Interplanetary)", name="ST-16RT2 star tracker", file="RocketLab-ST16RT2.png", mass=0.158, power=0.5, volume=0.132,
         trl=None, heritage=None, tid=None, temp=[-40, 50], family="rocketlab-st16",
         price=dict(amount=120000, currency="USD", as_of="scheda non datata (letta il 2026-10-13)"),
         src=dict(url="https://rocketlabcorp.com/assets/Uploads/Star-trackers-product-sheet.pdf", document="Rocket Lab Second Generation Star Tracker (ST-16RT2) product sheet"),
         page="https://rocketlabcorp.com/assets/Uploads/Star-trackers-product-sheet.pdf", img=("pdf", "rl_st.pdf", "https://rocketlabcorp.com/assets/Uploads/Star-trackers-product-sheet.pdf#page=1"),
         notes=ACCURACY_NOTE + "Versione senza baffle: 158 g, 62 x 56 x 38 mm, US$120000 (con baffle corto 185 g, 62 x 56 x 68 mm, US$140000; baffle grande 235 g, 99 x 120 mm, "
               "US$140000). Accuratezza 5 arcsec trasversale e 55 arcsec attorno alla boresight (RMS, dimostrata in orbita, effetti termici inclusi), 2 Hz, "
               "velocita' massima 3 gradi/s, tempo di acquisizione zero (lost-in-space a ogni frame), 9-34 V, potenza media <0.5 W (usato 0.5) e picco 1 W, due RS-485 half-duplex "
               "(RS-422 o CAN come opzione di part number), -40..+50 C in funzione, vita 13 anni in LEO (800 km), campo di vista 7.5 x 10 gradi di semiampiezza (15 x 20 pieno), "
               "esclusione solare 34 gradi con baffle corto e 22 con baffle grande. Eredita': 30 unita' in orbita senza baffle (13 e 10 con i due baffle), prima unita' "
               "2013 (prima generazione) e 2016 (seconda). Tolleranza alle radiazioni: alloggiamento schermato, valore non dichiarato.",
         specs=dict(accuracy_cross_arcsec=5.0, accuracy_roll_arcsec=55.0, accuracy_basis="RMS", update_rate_hz=2.0, fov_deg=[15.0, 20.0],
                    data_interfaces=["RS-485", "RS-422"], supply_voltage_ranges_v=[[9.0, 34.0]])),
]
NST_COMMON = dict(vendor="Blue Canyon Technologies", trl=None, heritage=None, tid=None, temp=[-20, 50], family="bct-nst",
                  src=dict(url="https://www.bluecanyontech.com/wp-content/uploads/NST-May-2026.pdf", document="Blue Canyon Technologies Nano Star Trackers datasheet (REV 1/2026) + pagina componenti"),
                  page="https://www.bluecanyontech.com/?p=4117")
NST_NOTE = ("Scheda informativa REV 1/2026 ('data for information only and subject to change'). Potenza di picco <1.5 W a 5 V o <3.5 W a 28 V (usato 1.5), alimentazione "
            "5 V o 28 V, RS-422 o RS-485, campo di vista 10 x 12 gradi, 5 Hz, velocita' massima >2 gradi/s, temperatura operativa -20..+50 C (sopravvivenza -30..+70 C), "
            "magnitudine limite 7.5, catalogo di bordo oltre 20000 stelle, baffle interni (esterni su Mid e Full Extension). Il datasheet distingue 'Gen 2' (6 e 40 arcsec "
            "trasversale e boresight) da 'Gen 3' (1 e 10 arcsec): qui la Standard NST usa i valori Gen 2 e le due Extension i valori Gen 3 come sulla pagina del fornitore, "
            "senza indicazione esplicita di quale generazione sia ciascuna; basi statistiche 1-sigma. TID non dichiarata. ")
for suffix, nm, mass, dims, vol, cross, roll, imgurl, fn in (
        ("standard", "Standard NST", 0.35, "10 x 5.5 x 5 cm", 0.275, 6.0, 40.0, "component-model-standard_nst.png", "BlueCanyon-NST-Standard.png"),
        ("mid", "Mid-Extension NST", 0.45, "17 x 8.5 x 7 cm", 1.01, 1.0, 10.0, "component-model-mid_extension_nst.png", "BlueCanyon-NST-MidExtension.png"),
        ("full", "Full-Extension NST", 0.85, "25 x 10 x 10 cm", 2.5, 1.0, 10.0, "component-model-full_extension_nst-rev.png", "BlueCanyon-NST-FullExtension.png")):
    ST.append(dict(NST_COMMON, id=f"bct-nst-{suffix}", name=f"{nm} star tracker", file=fn, mass=mass, power=1.5, volume=vol,
                   img=("web", f"https://www.bluecanyontech.com/wp-content/uploads/{imgurl}"),
                   notes=ACCURACY_NOTE + f"Massa {mass * 1000:g} g, {dims}. " + NST_NOTE + "Prezzo non pubblicato.",
                   specs=dict(accuracy_cross_arcsec=cross, accuracy_roll_arcsec=roll, accuracy_basis="1-sigma", update_rate_hz=5.0, fov_deg=[10.0, 12.0],
                              data_interfaces=["RS-422", "RS-485"], supply_voltage_ranges_v=[[5.0, 5.0], [28.0, 28.0]])))

# ---------------------------------------------------------------- terminali ottici
OPT_NONE = dict(spectral_bands=None, reference_altitude_km=None, gsd_m_at_ref=None, swath_km_at_ref=None, focal_length_mm=None, aperture_mm=None, pixel_pitch_um=None,
                across_track_pixels=None, min_form_factor_u=None, data_interfaces=None, supply_voltage_ranges_v=None, storage_gb=None)
OPT = [
    dict(id="tesat-cubelct", vendor="Tesat-Spacecom", name="CubeLCT 100M optical terminal", file="Tesat-CubeLCT.png", mass=0.397, power=10.0, volume=0.3, trl=None, heritage=1,
         tid=None, temp=None, family="tesat-cubelct",
         src=dict(url="https://satcatalog.s3.amazonaws.com/components/568/SatCatalog_-_Tesat-Spacecom_-_CubeLCT_100M_-_Datasheet.pdf",
                  document="Tesat-Spacecom CubeLCT datasheet, versione 2019-09 (copia ospitata da SatCatalog; la versione 2019-08 su tesat.de riporta 360 g e 8 W)"),
         page="https://tesat.de/images/downloads/DataSheet_CubeLCT.pdf", img=("web", "https://tesat.de/images/media/blog/190803_cubelct_web.jpg"),
         notes="Collegamento LEO-terra: NON e' un terminale inter-satellite (il datasheet lo dichiara solo come 'roadmap': espandibile a 1 Gbps in downlink e a "
               "100 Mbps per collegamenti ottici inter-satellite). 100 Mbps LEO-terra, canale TC 1 Mbps terra-LEO, 1550 nm in downlink e 1590/1610 nm in uplink, "
               "potenza di trasmissione 100 mW, 397 g, 9 x 9.5 x 3.5 cm (circa 0.3U), 10 W di picco (la versione 2019-08: 8 W), campo di regard +/-1 gradi con "
               "specchio di puntamento fine (richiede il puntamento del corpo del satellite entro circa 1 grado, usato come requisito per l'ADCS), LVDS per i dati e UART per TM/TC, "
               "vita 5 anni in LEO, tecnologia IM/DD, CCSDS O3K, ottimizzato per stazioni ottiche da 60 cm. Prima missione PIXL-1 (lancio 24 gennaio 2021, collegamento "
               "completo dimostrato); unita' di volo disponibili. Eredita': 1 missione. Prezzo non pubblicato.",
         specs=dict(payload_type="optical_terminal", link_type="space_to_ground", link_data_rate_mbps=100.0, uplink_data_rate_kbps=1000.0, max_range_km=None, wavelength_nm=1550.0,
                    host_pointing_deg=1.0, **{**OPT_NONE, "data_interfaces": ["LVDS", "UART"]})),
    dict(id="aac-cubecat", vendor="AAC Clyde Space", name="CubeCAT laser communication terminal", file="AACClydeSpace-CubeCAT.png", mass=1.33, power=15.0, volume=0.88, trl=None,
         heritage=None, tid=None, temp=[-20, 40], family="aac-cubecat",
         src=dict(url="https://www.aac-clyde.space/wp-content/uploads/2021/10/CUBECAT.pdf", document="AAC Clyde Space / TNO CubeCAT datasheet (release 15 Nov 2021)"),
         page="https://www.aac-clyde.space/what-we-do/space-products-components/communications/cubecat",
         img=("pdf", "cubecat.pdf", "https://www.aac-clyde.space/wp-content/uploads/2021/10/CUBECAT.pdf#page=1"),
         notes="Collegamento bidirezionale spazio-terra con una stazione ottica a terra (non inter-satellite). Downlink 100/300/1000 Mbps (raw), uplink 200 kbps, distanza "
               "massima in slant range 1000 km, buffer di bordo oltre 64 GB, ITAR-free, nessuna licenza radio. 96 x 96 x 96 mm (<1U), massa <1.33 kg (usato 1.33), potenza "
               "di picco circa 15 W e media orbitale <1 W (usato il picco), -20..+40 C. Requisiti sulla piattaforma ospite: accuratezza di puntamento <0.5 gradi (3-sigma), "
               "errore di conoscenza del puntamento <17.2 mdeg, jitter (>20 Hz) <0.86 mdeg: usato 0.5 gradi come requisito per l'ADCS. Alimentazione 5 V digitale (4.75-5.25 V) e "
               "Vbat 9.6-21 V; interfacce USB 3.0 e I2C. Lunghezza d'onda non dichiarata. Prezzo non pubblicato.",
         specs=dict(payload_type="optical_terminal", link_type="space_to_ground", link_data_rate_mbps=1000.0, uplink_data_rate_kbps=200.0, max_range_km=1000.0, wavelength_nm=None,
                    host_pointing_deg=0.5, **{**OPT_NONE, "data_interfaces": ["USB", "I2C"], "supply_voltage_ranges_v": [[4.75, 5.25], [9.6, 21.0]]})),
    dict(id="tesat-scot20", vendor="Tesat-Spacecom", name="SCOT20 smallsat optical communication terminal", file="Tesat-SCOT20.png", mass=1.6, power=None, volume=1.0, trl=None,
         heritage=1, tid=None, temp=None, family="tesat-scot",
         src=dict(url="https://satsearch.co/products/tesat-scot20-smallsat-optical-communication-terminal",
                  document="Scheda prodotto SCOT20 su satsearch (massa e taglia) + grafico delle prestazioni nei datasheet Tesat SCOT30 (2026-08) e SCOT80 (2025-03)"),
         page="https://satsearch.co/products/tesat-scot20-smallsat-optical-communication-terminal",
         img=("web", "https://cdn.satsearch.com/product-images/image-tesat-spacecom-gmbh-co-kg-scot20-smallsat-optical-communication-terminal-cxshi7.jpg"),
         notes="Terminale per collegamenti LEO-LEO e LEO-terra: 1 Gbps fino a 2000 km (dal grafico dei datasheet Tesat), 1.6 kg e taglia 1U dalla scheda satsearch, "
               "che cita il fornitore. Il datasheet del SCOT20 non era scaricabile (403): potenza, interfacce, lunghezza d'onda, requisiti di puntamento e alimentazione "
               "NON dichiarati nelle fonti lette (il consumo ipotizzato dal selettore compare negli avvisi). Il comunicato Tesat del 23 marzo 2026 riporta il lancio su "
               "OptiSat (6U, Planetek Hellas) con Transporter-16, quindi un volo su un 6U; eredita' 1 missione, non confermata da un documento tecnico. Conforme a SDA ed ESTOL "
               "secondo il comunicato. Prezzo non pubblicato.",
         specs=dict(payload_type="optical_terminal", link_type="both", link_data_rate_mbps=1000.0, uplink_data_rate_kbps=None, max_range_km=2000.0, wavelength_nm=None,
                    host_pointing_deg=None, **OPT_NONE)),
    dict(id="tesat-scot30", vendor="Tesat-Spacecom", name="SCOT30 smallsat optical communication terminal", file="Tesat-SCOT30.png", mass=6.0, power=60.0, volume=12.88, trl=None,
         heritage=None, tid=None, temp=None, family="tesat-scot",
         src=dict(url="https://www.tesat.de/images/tesat/products/260803_DataSheet_SCOT30_A4.pdf", document="Tesat-Spacecom SCOT30 datasheet, versione 2026-08"),
         page="https://www.tesat.de/products", img=("web", "https://www.tesat.de/images/tesat/products/2026_01_22_SCOT-30web.jpg"),
         notes="Collegamenti inter-satellite LEO e direct-to-Earth: asimmetrico fino a 2.5 Gbps in trasmissione e 1.25 Gbps in ricezione (simmetrico fino a 1.25 Gbps), distanza "
               "fino a 3500 km, campo di regard iper-emisferico, conforme allo standard SDA OCT 3.1.0, massa <6 kg (usato 6), 230 x 280 x 200 mm, potenza <60 W di picco, "
               "Ethernet per dati e TM/TC, vita 5 anni in LEO. NON ancora disponibile: TRL6 previsto per il secondo trimestre 2027 e TRL8 per il primo 2028, disponibilita' 2028. "
               "min_form_factor_u = 16 e' DERIVATO, non dichiarato: la sezione 230 x 280 mm non entra in un 12U (226.3 x 226.3 mm), quindi il selettore (3U, 6U, 12U) non "
               "puo' sceglierlo. Alimentazione e requisiti di puntamento non dichiarati. Prezzo non pubblicato.",
         specs=dict(payload_type="optical_terminal", link_type="both", link_data_rate_mbps=2500.0, uplink_data_rate_kbps=None, max_range_km=3500.0, wavelength_nm=None,
                    host_pointing_deg=None, **{**OPT_NONE, "min_form_factor_u": 16, "data_interfaces": ["Ethernet"]})),
    dict(id="tesat-scot80", vendor="Tesat-Spacecom", name="SCOT80 optical communication terminal", file="Tesat-SCOT80.png", mass=11.9, power=80.0, volume=54.0, trl=None,
         heritage=None, tid=None, temp=None, family="tesat-scot",
         src=dict(url="https://www.tesat.de/images/tesat/products/250820_DataSheet_SCOT80_A4.pdf", document="Tesat-Spacecom SCOT80 datasheet, versione 2025-03"),
         page="https://www.tesat.de/products", img=("web", "https://www.tesat.de/images/tesat/products/250320_SCOT80_2560px.jpg"),
         notes="Collegamenti ottici inter-satellite per costellazioni LEO: 2.5 o 10 Gbps bidirezionali (scalabile da 100 Mbps a 100 Gbps), distanza fino a 8000 km, "
               "11.9 kg per canale ottico, testa ottica 31 x 29 x 47 cm piu' elettronica 26 x 19 x 24 cm, 60-80 W secondo la velocita' (usato 80), 28 V, Ethernet per dati e "
               "TM/TC, conforme SDA, oltre 1000 terminali contrattualizzati. Terminale per satelliti di classe superiore ai CubeSat: min_form_factor_u = 27 e' DERIVATO "
               "(volume di testa ed elettronica circa 54 L), non dichiarato; il selettore (3U, 6U, 12U) non puo' sceglierlo. Prezzo non pubblicato.",
         specs=dict(payload_type="optical_terminal", link_type="inter_satellite", link_data_rate_mbps=10000.0, uplink_data_rate_kbps=None, max_range_km=8000.0, wavelength_nm=None,
                    host_pointing_deg=None, **{**OPT_NONE, "min_form_factor_u": 27, "data_interfaces": ["Ethernet"], "supply_voltage_ranges_v": [[28.0, 28.0]]})),
]


def build(entry, category):
    if entry["img"][0] == "web":
        im, img_url = Image.open(io.BytesIO(fetch(entry["img"][1]))), entry["img"][1]
        typ = "web"
    else:
        im, _ = pdf_image(entry["img"][1])
        img_url, typ = entry["img"][2], "estratta dal datasheet PDF"
    im = im.convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    bg.alpha_composite(im)
    im = bg.convert("RGB")
    im.thumbnail((1000, 1000))
    meta = PngInfo()
    for k, v in (("Title", f"{entry['vendor']} {entry['name']}"), ("Author", entry["vendor"]), ("Source", img_url),
                 ("Description", f"Componente {entry['id']}. Pagina/documento di origine: {entry['page']}. Scaricata il {RET}."), ("Copyright", NOTICE)):
        meta.add_text(k, v)
    im.save(PROJ / "images" / entry["file"], optimize=True, pnginfo=meta)
    rec = {"id": entry["id"], "category": category, "vendor": entry["vendor"], "name": entry["name"], "family": entry.get("family"), "mass_kg": entry["mass"],
           "power_w": entry["power"], "volume_u": entry["volume"], "price": entry.get("price"), "trl": entry["trl"], "flight_heritage": entry["heritage"],
           "tid_krad": entry["tid"], "temp_op_c": entry["temp"], "notes": entry["notes"],
           "source": {**entry["src"], "retrieved": RET, "verified": False, "method": METHOD}, "specs": entry["specs"],
           "image": {"file": f"images/{entry['file']}", "image_url": img_url, "page_url": entry["page"], "type": typ, "retrieved": RET}}
    rec = {k: v for k, v in rec.items() if v is not None or k in ("mass_kg", "power_w")}
    manifest = [entry["id"], entry["vendor"], entry["name"], entry["file"], typ, img_url, entry["page"], RET, f"{im.size[0]}x{im.size[1]}", ""]
    return rec, manifest


cat_path = PROJ / "data" / "catalog.json"
cat = json.loads(cat_path.read_text(encoding="utf-8"))
new_ids = {e["id"] for e in ST + OPT}
cat["components"] = [c for c in cat["components"] if c["id"] not in new_ids]
for c in cat["components"]:   # payload esistenti: tutti sono camere/telescopi
    if c["category"] == "payload":
        c["specs"].setdefault("payload_type", "imager")
        for k in NEW_PAYLOAD_KEYS[1:]:
            c["specs"].setdefault(k, None)
rows = []
for entry in ST:
    rec, row = build(entry, "star_tracker")
    cat["components"].append(rec)
    rows.append(row)
    print("star_tracker", rec["id"])
for entry in OPT:
    rec, row = build(entry, "payload")
    cat["components"].append(rec)
    rows.append(row)
    print("optical", rec["id"])
cat_path.write_text(json.dumps(cat, indent=1, ensure_ascii=False), encoding="utf-8")
mf = PROJ / "images" / "manifest.csv"
with mf.open(encoding="utf-8-sig", newline="") as f:
    old = list(csv.reader(f))
keep = [r for r in old if r and r[0] not in new_ids]
with mf.open("w", encoding="utf-8-sig", newline="") as f:
    csv.writer(f).writerows(keep + rows)
print(len(cat["components"]), "componenti;", len(keep) + len(rows) - 1, "righe nel manifest")

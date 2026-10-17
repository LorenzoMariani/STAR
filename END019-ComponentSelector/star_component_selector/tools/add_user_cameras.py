"""Datasheet aggiunti dall'utente in datasheets/ il 2026-10-17 (nomi dei file lasciati come li ha salvati l'utente).

  skyfox-picam           nuovo: SkyFox Labs piCAM Product Datasheet Rev. A/2025 - camera VGA (640 x 480, JPEG) da 40 g, 315 mW, UART,
                         ottica S-mount ~60 gradi (diagonale), -30..+85 C; GSD e swath non dichiarati (null: un requisito di GSD non e'
                         soddisfatto da un valore mancante), i valori derivati dal campo di vista sono solo nelle note.
  xcam-c3d               nuovo: XCAM C3D CubeSat Camera MKPU-XCAM-MS-00011vC (PDF del 2022 distribuito da SatCatalog; la copia satsearch del
                         2018 e' la stessa scheda con eredita' di 3 anni invece di 8) - 1.3 MP, 360 m a 650 km, 85 g, 845 mW, I2C/SPI, TRL 9.
                         Swath DERIVATO come 1280 pixel x GSD e apertura DERIVATA come focale / F (come lo swath della NanoCam).
  cavu-raveneye5         nuovo: CAVU Aerospace RavenEye5 (s.LDU345, 5 MP, 2U) datasheet dell'agosto 2026 - 4.25 m e 10.4 km a 500 km,
                         EFL 400 mm, apertura 60 mm, 1.1 kg, 12 V, 30 krad; consumo e temperature non dichiarati.
  simera-multiscape100   datasheet 036665 rev. 5 (2020-11-19) collegato come documento di riferimento: i valori restano quelli della
                         pagina prodotto attuale (piu' recente), quelli del 2020 sono nelle note.

Non entrano nel catalogo (righe nel manifest con il motivo): CCAM (presentazione UKATC/RAL Space 2018: prototipo di ricerca; regola
dell'utente "niente prototipi"), XCAM Nuscis (scheda di controllo senza ottica, modello di volo previsto per il Q1 2025 alla data della
scheda), NearSpace Launch FastBus 6U (piattaforma completa: struttura, EPS, radio, ADCS e pannelli insieme, mentre il catalogo sceglie i
sottosistemi uno per uno), CUBECAT.pdf (copia identica di AAC-Clyde-Space__CUBECAT.pdf, gia' collegata ad aac-cubecat).

I PDF non hanno un URL pubblico: source.url = null e origin dice da dove vengono (vedi tools/add_satbase_datasheets.py); un datasheet con
origin puo' essere un documento di riferimento diverso dalla fonte (simera-multiscape100). Le foto sono i JPEG incorporati nei PDF (stream
DCTDecode estratti senza ricodifica e salvati nella cartella di lavoro): piCAM pagina 2 (Fig. 1, modello di volo), C3D pagina 1,
RavenEye5 pagina 1 (modello di volo).

uso: python tools/add_user_cameras.py <cartella con picam_p2.jpg, c3d_p1.jpg, raveneye5_p1.jpg>
Idempotente."""
import csv
import json
import sys
from pathlib import Path

from PIL import Image
from PIL.PngImagePlugin import PngInfo

PROJ = Path(__file__).resolve().parent.parent
RET = "2026-10-17"
ORIGIN = "PDF aggiunto dall'utente in datasheets/ il 2026-10-17, senza URL pubblico"
METHOD = "trascritto dal datasheet del fornitore aggiunto dall'utente (copia in datasheets/); da controllare manualmente"
NOTICE = ("Immagine di proprieta' del produttore, qui solo come riferimento visivo del prodotto; per usi diversi (pubblicazioni, "
          "presentazioni esterne) chiedere il permesso al produttore.")
NULL_TERMINAL = {"link_type": None, "link_data_rate_mbps": None, "uplink_data_rate_kbps": None, "max_range_km": None, "wavelength_nm": None,
                 "host_pointing_deg": None}

DOCS = {
    "picam": ("piCAM_Datasheet_rev_A_2025.pdf", "SkyFox Labs piCAM Product Datasheet Rev. A/2025"),
    "c3d": ("SatCatalog_-_XCAM_-_C3D_CubeSat_Camera_-_Datasheet.pdf", "XCAM C3D CubeSat Camera product sheet MKPU-XCAM-MS-00011vC (2022, distribuito da SatCatalog)"),
    "raven": ("CAVU-Camera-RavenEye5-Datasheet.pdf", "CAVU Aerospace RavenEye5 datasheet (agosto 2026)"),
    "ms100": ("SatCatalog_-_Simera_Sense_-_MultiScape100_CIS_-_Datasheet.pdf", "Simera Sense MultiScape100 CIS datasheet 036665 rev. 5 (2020-11-19, distribuito da SatCatalog)"),
}
# file nella cartella di lavoro, nome dell'immagine, titolo, documento
IMAGES = {"skyfox-picam": ("picam_p2.jpg", "SkyFoxLabs-piCAM.png", "SkyFox Labs piCAM", "picam", 2),
          "xcam-c3d": ("c3d_p1.jpg", "XCAM-C3D.png", "XCAM C3D CubeSat Camera", "c3d", 1),
          "cavu-raveneye5": ("raveneye5_p1.jpg", "CAVUAerospace-RavenEye5.png", "CAVU Aerospace RavenEye5", "raven", 1)}
UNLINKED = {
    "satsearch_datasheet_x7lkd0_xcam_c3d.pdf": "XCAM C3D product sheet (2018, distribuito da satsearch): stessa scheda della versione 2022 collegata a xcam-c3d, con eredita' di 3 anni invece di 8",
    "CUBECAT.pdf": "copia identica di AAC-Clyde-Space__CUBECAT.pdf, gia' collegata ad aac-cubecat",
    "SatCatalog_-_XCAM_-_Nuscis_-_Datasheet.pdf": "XCAM Nuscis Imager Controller Board MKPU-XCAM-MS-00047vD (novembre 2024): scheda senza ottica, modello di volo previsto per il Q1 2025 alla data della scheda; non nel catalogo",
    "FastBus CubeSat Platform - 3x2U v1.2.pdf": "NearSpace Launch FastBus CubeSat Platform 6U (3x2U) v1.2 (2019): piattaforma completa (struttura, EPS, radio, ADCS, pannelli), il catalogo sceglie i sottosistemi uno per uno; non nel catalogo",
    "b-3-5-201805251613-allthorpe-mullis.pdf": "UKATC/RAL Space, CCAM CubeSat Camera (presentazione, maggio 2018): prototipo di ricerca, non nel catalogo (regola dell'utente: niente prototipi)",
}

PICAM_NOTES = (
    "Datasheet piCAM Rev. A/2025 (SkyFox Labs, Praga): camera digitale a colori VGA 640 x 480 con uscita JPEG (cattura in 5 s), comandi a un "
    "byte su UART 115200-8-N-1 (1200-921600 bit/s, livelli CMOS 3.3 V), uscita a collettore aperto per un flash LED esterno, telemetria di "
    "tensioni e correnti. Alimentazione 2.7-3.6 V (3.3 V nominali), 315 mW tipici (95 mA); 40 g; corpo 33 x 33 x 19 mm piu' l'ottica (lunghezza "
    "variabile, non dichiarata), staffa 48 x 33 mm con 4 fori M2.5; connettore Molex PicoBlade a 6 poli; -30..+85 C operativi. Ottica S-mount a "
    "fuoco fisso (infinito), campo di vista ~60 gradi diagonale con filtro IR-cut (116 e 170 gradi a richiesta); immagini di esempio da un "
    "CubeSat in orbita eliosincrona a 530 km. GSD e swath non dichiarati: con 60 gradi in diagonale su 800 pixel a 530 km verrebbero circa "
    "765 m e 490 km (solo indicativi, non usati). Versioni EM e FM elettricamente identiche; parti commerciali non resistenti alle radiazioni; "
    "esportazione soggetta a licenza del Ministero dell'Industria ceco (30-60 giorni). Uso tipico: monitoraggio di dispiegamenti e immagini "
    "a bassa risoluzione.")
C3D_NOTES = (
    "Scheda XCAM C3D MKPU-XCAM-MS-00011vC (2022, distribuita da SatCatalog; la copia satsearch del 2018 e' identica salvo 'eredita' di volo "
    "3 anni' invece di 8): TRL 9, in volo dal 2014 su UKube-1 (UK Space Agency) e AlSat Nano; fino a tre teste per scheda (stereo o ottiche "
    "diverse), sensore CMOS 1.3 MP 1280 x 1024 da 5.3 um a colori (RGB) o bianco e nero, 400-650 nm, obiettivo commerciale 9.6 mm F/3.0, "
    "GSD 360 m a 650 km con questo obiettivo (altre varianti disponibili). Swath DERIVATO come 1280 pixel x GSD (non dichiarato) e apertura "
    "DERIVATA come 9.6 mm / 3.0. Dati: grezzi a 8 bit e miniature 1:10, compressione JPEG-LS senza perdite (50%), 16 MB SDRAM e 8 MB flash, "
    "interfacce I2C o SPI. Scheda 9.5 x 9.1 x 2.7 cm; 85 g con una testa WFI; picco 845 mW; -25..+65 C operativi, -35..+75 C di "
    "sopravvivenza (provati). Per CubeSat da 1U in su. Tensione di alimentazione non dichiarata.")
RAVEN_NOTES = (
    "Datasheet CAVU Aerospace RavenEye5 (agosto 2026): camera s.LDU345 da 5 MP (2448 x 2048, pixel 3.4 um), apertura 60 mm, focale 400 mm, "
    "GSD 4.25 m e swath 10.4 km a 500 km; immagini RAW Bayer a 12 bit senza compressione e JPEG, ritaglio centrale in hardware; FPGA "
    "Microchip PolarFire SoC con NVIDIA Jetson Xavier NX via MIPI CSI-2 a 4 linee (streaming). Modello di volo 1.1 kg, 200 x 96 x 96 mm (2U); "
    "alimentazione 12 V (consumo non dichiarato); connettori Samtec e Nano-D; dati LVDS + RS-422 + Ethernet, trasmissione UART RS-485; "
    "radiazione 30 krad (60 MeV), progetto immune agli SEU; EMC, vibrazioni e TVAC a livello di qualifica. Dichiarata 'flight proven' senza "
    "numero di missioni. Varianti 2U, 3U e 12U da 5, 16 e 51 MP non modellate (solo la 2U da 5 MP ha i dati). Temperature non dichiarate. "
    "Sensore ad area (camera a immagine, non push-broom).")
MS100_NOTE_2020 = (
    " Datasheet 036665 rev. 5 (2020-11-19; PDF aggiunto dall'utente il 2026-10-17, copia locale collegata come riferimento): 1.1 kg +-5%, "
    "2.5 W a riposo o in lettura e 5.8 W in acquisizione, 7 bande VNIR, 98 x 98 x 176 mm, campo 2.22 gradi across-track e 1.66 along-track, "
    "5 V +-250 mV, -10..+50 C, almeno 15 krad (provato fino a 25 krad senza schermo, Co-60), per CubeSat 3U o piu' grandi, striscia continua "
    "fino a 4500 km a 500 km. Si tengono i valori della pagina prodotto (piu' recente). Il datasheet porta una nota di copyright Simera Sense "
    "(uso limitato allo scopo per cui e' fornito): il PDF resta fuori da git.")


def ds_record(key: str) -> dict:
    name, doc = DOCS[key]
    path = PROJ / "datasheets" / name
    return {"file": f"datasheets/{name}", "document": doc, "source_url": None, "origin": ORIGIN, "retrieved": RET, "bytes": path.stat().st_size}


def user_source(key: str) -> dict:
    return {"url": None, "origin": ORIGIN, "document": DOCS[key][1], "retrieved": RET, "verified": False, "method": METHOD}


def image_record(cid: str, key: str, page: int) -> dict:
    f = f"datasheets/{DOCS[key][0]}"
    return {"file": f"images/{IMAGES[cid][1]}", "image_url": f"{f}#page={page}", "page_url": f, "type": "estratta dal datasheet PDF",
            "retrieved": RET, "note": f"Pagina {page} del datasheet {DOCS[key][1]} ({ORIGIN})."}


def imager_specs(**kw) -> dict:
    s = {"payload_type": "imager", "spectral_bands": None, "reference_altitude_km": None, "gsd_m_at_ref": None, "swath_km_at_ref": None,
         "focal_length_mm": None, "aperture_mm": None, "pixel_pitch_um": None, "across_track_pixels": None, "min_form_factor_u": None,
         "data_interfaces": None, "supply_voltage_ranges_v": None, "storage_gb": None, **NULL_TERMINAL}
    s.update(kw)
    return s


def main() -> None:
    work = Path(sys.argv[1])
    cat_path = PROJ / "data" / "catalog.json"
    cat = json.loads(cat_path.read_text(encoding="utf-8"))
    comps = cat["components"]

    px = {}
    for cid, (src, name, title, key, page) in IMAGES.items():
        im = Image.open(work / src).convert("RGB")
        meta = PngInfo()
        for k, v in (("Title", title), ("Author", title.split(" ")[0]), ("Source", f"datasheets/{DOCS[key][0]}#page={page}"),
                     ("Description", f"Pagina/documento di origine: datasheets/{DOCS[key][0]} ({ORIGIN})."), ("Copyright", NOTICE)):
            meta.add_text(k, v)
        im.save(PROJ / "images" / name, optimize=True, pnginfo=meta)
        px[cid] = f"{im.size[0]}x{im.size[1]}"

    new = [
        {"id": "skyfox-picam", "category": "payload", "vendor": "SkyFox Labs", "name": "piCAM (VGA, 60 deg)", "mass_kg": 0.04, "power_w": 0.315,
         "temp_op_c": [-30, 85], "notes": PICAM_NOTES, "source": user_source("picam"),
         "specs": imager_specs(spectral_bands=["RGB"], across_track_pixels=640, data_interfaces=["UART"], supply_voltage_ranges_v=[[2.7, 3.6]]),
         "dimensions": {"mm": [48.0, 33.0, None], "basis": "declared",
                        "note": "Datasheet piCAM: staffa 48 x 33 mm; corpo 33 x 33 x 19 mm piu' l'ottica, la cui lunghezza non e' dichiarata."},
         "image": image_record("skyfox-picam", "picam", 2), "datasheet": ds_record("picam"),
         "shape": {"type": "board_lens", "axis": 2, "basis": "image", "set": RET}},
        {"id": "xcam-c3d", "category": "payload", "vendor": "XCAM", "name": "C3D CubeSat Camera (1.3 MP, 9.6 mm)", "mass_kg": 0.085, "power_w": 0.845,
         "trl": 9, "flight_heritage": 2, "temp_op_c": [-25, 65], "notes": C3D_NOTES, "source": user_source("c3d"),
         "specs": imager_specs(spectral_bands=["RGB", "MONO"], reference_altitude_km=650.0, gsd_m_at_ref=360.0, swath_km_at_ref=460.8,
                               focal_length_mm=9.6, aperture_mm=3.2, pixel_pitch_um=5.3, across_track_pixels=1280, min_form_factor_u=1,
                               data_interfaces=["I2C", "SPI"], storage_gb=0.008),
         "dimensions": {"mm": [95.0, 91.0, 27.0], "basis": "declared", "note": "Scheda XCAM C3D: 9.5 x 9.1 x 2.7 cm."},
         "image": image_record("xcam-c3d", "c3d", 1), "datasheet": ds_record("c3d"),
         "shape": {"type": "board_lens", "axis": 2, "basis": "image", "set": RET}},
        {"id": "cavu-raveneye5", "category": "payload", "vendor": "CAVU Aerospace", "name": "RavenEye5 (s.LDU345, 5 MP, 2U)", "mass_kg": 1.1,
         "power_w": None, "volume_u": 2.0, "tid_krad": 30.0, "notes": RAVEN_NOTES, "source": user_source("raven"),
         "specs": imager_specs(spectral_bands=["RGB"], reference_altitude_km=500.0, gsd_m_at_ref=4.25, swath_km_at_ref=10.4, focal_length_mm=400.0,
                               aperture_mm=60.0, pixel_pitch_um=3.4, across_track_pixels=2448,
                               data_interfaces=["LVDS", "RS-422", "Ethernet", "RS-485"], supply_voltage_ranges_v=[[12.0, 12.0]]),
         "dimensions": {"mm": [200.0, 96.0, 96.0], "basis": "declared", "note": "Datasheet RavenEye5, modello di volo: 200 x 96 x 96 mm."},
         "image": image_record("cavu-raveneye5", "raven", 1), "datasheet": ds_record("raven"),
         "shape": {"type": "lens_box", "axis": 0, "basis": "image", "set": RET}},
    ]
    ids = {c["id"] for c in new}
    comps[:] = [c for c in comps if c["id"] not in ids]
    for c in new:
        last = max(i for i, x in enumerate(comps) if x["category"] == c["category"])
        comps.insert(last + 1, c)

    ms = next(c for c in comps if c["id"] == "simera-multiscape100")
    ms["notes"] = ms["notes"].split(" Datasheet 036665")[0] + MS100_NOTE_2020
    ms["datasheet"] = ds_record("ms100")
    cat_path.write_text(json.dumps(cat, indent=1, ensure_ascii=False), encoding="utf-8")

    mf = PROJ / "images" / "manifest.csv"
    with mf.open(encoding="utf-8-sig", newline="") as fh:
        rows = [r for r in csv.reader(fh) if r and r[0] not in ids]
    for c in new:
        im = c["image"]
        rows.append([c["id"], c["vendor"], c["name"], Path(im["file"]).name, im["type"], im["image_url"], im["page_url"], RET, px[c["id"]], im["note"]])
    with mf.open("w", encoding="utf-8-sig", newline="") as fh:
        csv.writer(fh).writerows(rows)

    dm = PROJ / "datasheets" / "manifest.csv"
    with dm.open(encoding="utf-8-sig", newline="") as fh:
        drows = [r for r in csv.reader(fh) if r]
    linked = {"picam": "skyfox-picam", "c3d": "xcam-c3d", "raven": "cavu-raveneye5", "ms100": "simera-multiscape100"}
    names = {DOCS[k][0] for k in linked} | set(UNLINKED)
    drows = [r for r in drows if r[0] not in names]
    for key, cid in linked.items():
        d = ds_record(key)
        drows.append([DOCS[key][0], f"{d['document']} ({ORIGIN})", "", RET, str(d["bytes"]), cid])
    for name, why in UNLINKED.items():
        drows.append([name, f"{why} ({ORIGIN})", "", RET, str((PROJ / "datasheets" / name).stat().st_size), ""])
    with dm.open("w", encoding="utf-8-sig", newline="") as fh:
        csv.writer(fh).writerows(drows)
    print(f"{len(new)} camere aggiunte, datasheet MultiScape100 collegato; catalogo: {len(comps)} componenti")


if __name__ == "__main__":
    main()

"""Aggiunge due componenti ISISpace da brochure pubbliche del fornitore.

  isis-iobc    ISIS On-Board Computer (iOBC), brochure v1 (cubesatshop.com, 2016-2017)
  isis-trxuv   ISIS TRXUV VHF/UHF Transceiver, brochure v.12.5 (cubesatshop.com)

Il TRXUV (trasmettitore VHF 130-160 MHz, ricevitore UHF 400-450 MHz) e' un prodotto diverso dal TRXVU gia' in catalogo (uplink VHF, downlink UHF).
Le URL ISIS dei datasheet piu' recenti dell'iOBC non sono piu' raggiungibili (404): si usa solo la brochure scaricata.
uso: python tools/add_isis_obc_trxuv.py <cartella con iobc_c.pdf e trxuv.pdf gia' scaricati>
Idempotente. Nessun valore e' stimato: le discrepanze tra documenti sono scritte nelle note.
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
IOBC_URL = "https://www.cubesatshop.com/wp-content/uploads/2016/06/iOBC-Brochure-v1.pdf"
IOBC_PAGE = "https://www.cubesatshop.com/product/isis-on-board-computer/"
TRX_URL = "https://www.cubesatshop.com/wp-content/uploads/2016/06/ISIS_TRXUV_Transceiver_Brochure_v.12.5.pdf"
SHAPE = {"type": "board", "axis": None, "basis": "image", "set": RET}


def pdf_image(pdf, xref):
    d = pymupdf.open(pdf)
    pix = pymupdf.Pixmap(d, xref)
    if pix.n > 3:
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def main():
    work = Path(sys.argv[1])
    cat_path = PROJ / "data" / "catalog.json"
    cat = json.loads(cat_path.read_text(encoding="utf-8"))
    comps = cat["components"]

    docs = {"iobc": ("iobc_c.pdf", "ISISpace__iOBC-Brochure-v1.pdf", "ISIS On Board Computer (iOBC) brochure v1", IOBC_URL),
            "trx": ("trxuv.pdf", "ISISpace__TRXUV-Brochure-v12.5.pdf", "ISIS TRXUV VHF/UHF Transceiver brochure v.12.5", TRX_URL)}
    ds = {}
    for key, (src, name, doc, url) in docs.items():
        f = "datasheets/" + short_name(name)
        shutil.copyfile(work / src, PROJ / f)
        ds[key] = {"file": f, "document": doc, "source_url": url, "retrieved": RET, "bytes": (PROJ / f).stat().st_size}
    imgs = {"ISISpace-iOBC.png": ("iobc", 54, "iOBC", IOBC_URL, IOBC_PAGE), "ISISpace-TRXUV.png": ("trx", 33, "TRXUV VHF/UHF Transceiver", TRX_URL, TRX_URL)}
    px = {}
    for name, (key, xref, title, url, page) in imgs.items():
        im = pdf_image(work / docs[key][0], xref)
        meta = PngInfo()
        for k, v in (("Title", f"ISISpace {title}"), ("Author", "ISISpace"), ("Source", url), ("Description", f"Pagina/documento di origine: {url}. Scaricata il {RET}."), ("Copyright", NOTICE)):
            meta.add_text(k, v)
        im.save(PROJ / "images" / name, optimize=True, pnginfo=meta)
        px[name] = f"{im.size[0]}x{im.size[1]}"

    def src(key):
        return {"url": docs[key][3], "document": docs[key][2], "retrieved": RET, **VERIFIED}

    new = [
        {"id": "isis-iobc", "category": "obc", "vendor": "ISISpace", "name": "On-Board Computer (iOBC)", "mass_kg": 0.1, "temp_op_c": [-25, 65], "power_w": 0.4,
         "notes": ("Brochure iOBC v1 (cubesatshop.com, con KubOS 'in arrivo nel 2017': documento datato, verificare la disponibilita' attuale): processore ARM9 a 32 bit 400 MHz, 64 MB SDRAM, 1 MB NOR flash, "
                   "256 kB FRAM per i dati critici, 2 schede SD da 2 GB (fino a 32 GB su richiesta) per i dati di massa; FreeRTOS, watchdog esterno, controllo di alimentazione e orologio in tempo reale; "
                   "telemetria di tensioni, correnti e temperatura; architettura a scheda figlia (EM per lo sviluppo, FM compatta, personalizzabile). "
                   "Interfacce: I2C (master o slave), SPI master (fino a 8 slave), 2 UART (RS232 + RS232/RS485/RS422), GPIO, ADC 10 bit a 8 canali, PWM, JTAG, USB host e device, interfaccia per sensore d'immagine. "
                   "Alimentazione 3.3 V, consumo medio 400 mW. Massa: 76 g con la sola scheda principale e 100 g con la scheda figlia EM; la massa con la scheda figlia FM (la configurazione delle dimensioni) "
                   "non e' dichiarata: si usa il valore dichiarato piu' alto (100 g). Dimensioni 96 x 90 x 12.4 mm 'incl. FM daughter board'. Eredita' di volo dichiarata dal 2014. "
                   "Le pagine ISIS riportano 94 g per la scheda principale e 512 kB di FRAM: valori diversi dalla brochure scaricata, che e' l'unica usata qui."),
         "source": src("iobc"),
         "specs": {"data_interfaces": ["I2C", "SPI", "UART", "RS-232", "RS-485", "RS-422", "GPIO", "ADC", "PWM", "JTAG", "USB", "image sensor interface"], "supply_voltage_ranges_v": [[3.3, 3.3]]},
         "dimensions": {"mm": [96, 90, 12.4], "basis": "declared", "note": "Brochure iOBC: 96 x 90 x 12.4 mm incl. FM daughter board."},
         "image": {"file": "images/ISISpace-iOBC.png", "image_url": IOBC_URL, "page_url": IOBC_PAGE, "type": "estratta dal datasheet PDF", "retrieved": RET},
         "datasheet": dict(ds["iobc"]), "shape": dict(SHAPE)},
        {"id": "isis-trxuv", "category": "comms", "vendor": "ISISpace", "name": "VHF/UHF Transceiver (TRXUV)", "mass_kg": 0.085, "temp_op_c": [-10, 45], "power_w": None,
         "notes": ("Brochure TRXUV v.12.5 (cubesatshop.com; prodotto di generazione precedente, progetto basato sull'eredita' Delfi-C3 2008): trasmettitore VHF a frequenza singola (a cristallo) nell'intervallo 130-160 MHz, "
                   "22 dBm medi, modulazione BPSK a coseno rialzato, 1200/2400/4800/9600 bps; ricevitore UHF a frequenza singola 400-450 MHz, sensibilita' -104 dBm per BER 1e-5, AFSK o FSK Manchester; AX.25, "
                   "decodifica dei comandi a bordo, beacon CW, modo loopback. Alimentazione 6.5-12.5 V DC (il connettore a 104 pin porta anche 6-30 V oppure 5 V/3.3 V); consumo <1.55 W in trasmissione e <0.2 W "
                   "in sola ricezione (usati come limiti superiori). Massa 'circa 85 g a seconda della configurazione' e dimensioni 96 x 90 x 15 mm. Interfaccia I2C, RF SMA femmina 50 ohm. "
                   "E' un prodotto diverso dal TRXVU gia' in catalogo (uplink VHF e downlink UHF). La tabella di qualifica riporta i test (inclusa la dose totale) senza valori di dose."),
         "source": src("trx"),
         "specs": {"band": "VHF/UHF", "has_receiver": True, "data_rate_kbps_max": 9.6, "power_w_idle": 0.2, "power_w_tx": 1.55, "data_interfaces": ["I2C"], "supply_voltage_ranges_v": [[6.5, 12.5]]},
         "dimensions": {"mm": [96, 90, 15], "basis": "declared", "note": "Brochure TRXUV v.12.5: 96 x 90 x 15 mm."},
         "image": {"file": "images/ISISpace-TRXUV.png", "image_url": TRX_URL, "page_url": TRX_URL, "type": "estratta dal datasheet PDF", "retrieved": RET},
         "datasheet": dict(ds["trx"]), "shape": dict(SHAPE)},
    ]
    ids = {c["id"] for c in new}
    comps[:] = [c for c in comps if c["id"] not in ids]
    for c in new:
        last = max(i for i, x in enumerate(comps) if x["category"] == c["category"])
        comps.insert(last + 1, c)
    cat_path.write_text(json.dumps(cat, indent=1, ensure_ascii=False), encoding="utf-8")

    mf = PROJ / "images" / "manifest.csv"
    with mf.open(encoding="utf-8-sig", newline="") as fh:
        rows = [r for r in csv.reader(fh) if r and r[0] not in ids]
    for c in new:
        im = c["image"]
        fname = Path(im["file"]).name
        rows.append([c["id"], c["vendor"], c["name"], fname, im["type"], im["image_url"], im["page_url"], im["retrieved"], px[fname], ""])
    with mf.open("w", encoding="utf-8-sig", newline="") as fh:
        csv.writer(fh).writerows(rows)

    dm = PROJ / "datasheets" / "manifest.csv"
    with dm.open(encoding="utf-8-sig", newline="") as fh:
        drows = [r for r in csv.reader(fh) if r]
    new_files = {Path(d["file"]).name for d in ds.values()}
    drows = [r for r in drows if r[0] not in new_files]
    for key, d in ds.items():
        members = " ".join(c["id"] for c in new if c["datasheet"]["file"] == d["file"])
        drows.append([Path(d["file"]).name, d["document"], d["source_url"], RET, str(d["bytes"]), members])
    with dm.open("w", encoding="utf-8-sig", newline="") as fh:
        csv.writer(fh).writerows(drows)
    print(f"{len(new)} componenti ISIS aggiunti; catalogo: {len(comps)} componenti")


if __name__ == "__main__":
    main()

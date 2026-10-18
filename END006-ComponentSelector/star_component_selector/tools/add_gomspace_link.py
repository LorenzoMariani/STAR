"""Aggiunge tre componenti `comms` GomSpace basati sulla NanoCom SDR MK3, dal datasheet pubblico NanoCom Link S, X and SX.

  gomspace-nanocom-link-s    NanoCom Link S  (SDR MK3 con un TR600 + front end S-band ANT2150-DUP, RX e TX)
  gomspace-nanocom-link-x    NanoCom Link X  (SDR MK3 con un TR600 + front end X-band ANT8250, solo TX)
  gomspace-nanocom-link-sx   NanoCom Link SX (SDR MK3 con due TR600 + ANT2150-DUP + ANT8250)

Fonte: GomSpace DS 1076242 revisione 13.0 (22 maggio 2026). La NanoCom SDR MK3 da sola non ha un datasheet pubblico (la pagina prodotto chiede l'accesso
e i vecchi PDF della SDR/flyer non sono piu' online): si usano le varianti Link, che la contengono. Non aggiunto: NanoCom Link IS1 (datasheet preliminare
con avviso di confidenzialita').
uso: python tools/add_gomspace_link.py <cartella con link13.pdf gia' scaricato>
Idempotente. Le somme (massa del prodotto, potenze) sono DERIVATE e marcate nelle note; nessun valore e' stimato.
"""
import csv
import io
import json
import shutil
import sys
from pathlib import Path

import pymupdf
from PIL import Image, ImageChops
from PIL.PngImagePlugin import PngInfo

PROJ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from add_datasheets import short_name  # noqa: E402

RET = "2026-10-15"
VERIFIED = {"verified": False, "method": "trascritto da documento pubblico del fornitore; da controllare manualmente"}
NOTICE = ("Immagine di proprieta' del produttore, qui solo come riferimento visivo del prodotto; per usi diversi (pubblicazioni, "
          "presentazioni esterne) chiedere il permesso al produttore.")
URL = "https://gomspace.com/wp-content/uploads/2025/09/gs-ds-nanocom-link-s-x-and-sx-communication-products-13.0.pdf"
DOC = "GomSpace NanoCom Link S, X and SX Communication Products datasheet DS 1076242 rev. 13.0 (22 maggio 2026)"
XREF = {"s": 752, "x": 753, "sx": 754}          # Figura 4.2 (pag. 20): viste prospettiche della SDR MK3 per Link S, X, SX
SHAPE = {"type": "box", "axis": None, "basis": "image", "set": RET}


def pdf_image(pdf, xref):
    d = pymupdf.open(pdf)
    info = d.extract_image(xref)
    im = Image.open(io.BytesIO(info["image"])).convert("RGB")
    if info.get("smask"):
        mask = Image.open(io.BytesIO(d.extract_image(info["smask"])["image"])).convert("L")
        white = Image.new("RGB", im.size, "white")
        im = Image.composite(im, white, mask)
    bg = Image.new("RGB", im.size, "white")
    box = ImageChops.difference(im, bg).getbbox()
    if box:
        m = 20
        im = im.crop((max(0, box[0] - m), max(0, box[1] - m), min(im.width, box[2] + m), min(im.height, box[3] + m)))
    return im


COMMON = ("Datasheet GomSpace DS 1076242 rev. 13.0 (22 maggio 2026). La NanoCom SDR MK3 (SoC Zynq con TR600) non ha un datasheet pubblico a se': qui si cataloga la variante Link che la contiene. "
          "Il prodotto e' fornito con SDR, front end d'antenna, cavi coassiali e cablaggi gia' configurati; controllo e telemetria via CSP su CAN, RS-422 (full duplex) e 3 interfacce SpaceWire LVDS per i dati, "
          "cifratura autenticata allineata a CCSDS 355.0-B-2, qualificato per piu' di 5 anni in orbita secondo il programma di qualifica GomSpace (hardware TRL9). "
          "Temperatura: il datasheet dichiara la qualifica per una temperatura operativa dell'interfaccia termica da -40 a +53 C (SDR; massimo assoluto -35..+53 C per l'SDR e -35..+57 C per i front end), usata in temp_op_c. "
          "Alimentazione: SDR 12-32 V (massimo assoluto 36 V), circa 1 A. Il front end d'antenna e' un'unita' esterna da montare su una faccia del satellite (nadir) con piastre di montaggio a scelta: "
          "la massa del prodotto e' la SOMMA DERIVATA di SDR + front end (configurazione di montaggio piu' pesante dichiarata) + kit cavi (Tabella 12.5, esclusi il kit filtri DSN opzionale da 221 g e i cavi di debug). "
          "Le dimensioni sono quelle dell'SDR MK3 (95 x 95 mm h7, spessore dal disegno della Figura 11.x); i front end d'antenna non sono inclusi nelle dimensioni. "
          "Le potenze in standby e in attivita' sono SOMME DERIVATE dei valori massimi (caso peggiore) dei moduli della Tabella 5.x; i valori tipici sono riportati sotto. ")


def main():
    work = Path(sys.argv[1])
    cat_path = PROJ / "data" / "catalog.json"
    cat = json.loads(cat_path.read_text(encoding="utf-8"))
    comps = cat["components"]

    f = "datasheets/" + short_name("GomSpace__NanoCom-Link-S-X-SX-Datasheet-13.pdf")
    shutil.copyfile(work / "link13.pdf", PROJ / f)
    ds = {"file": f, "document": DOC, "source_url": URL, "retrieved": RET, "bytes": (PROJ / f).stat().st_size}
    names = {"s": "GomSpace-NanoCom-Link-S.png", "x": "GomSpace-NanoCom-Link-X.png", "sx": "GomSpace-NanoCom-Link-SX.png"}
    px = {}
    for k, xref in XREF.items():
        im = pdf_image(work / "link13.pdf", xref)
        meta = PngInfo()
        for kk, v in (("Title", f"GomSpace NanoCom Link {k.upper()}"), ("Author", "GomSpace"), ("Source", URL + "#page=20"),
                      ("Description", f"Comunicazioni CubeSat. Documento di origine: {URL}, Figura 4.2 (pag. 20). Scaricata il {RET}."), ("Copyright", NOTICE)):
            meta.add_text(kk, v)
        im.save(PROJ / "images" / names[k], optimize=True, pnginfo=meta)
        px[names[k]] = f"{im.size[0]}x{im.size[1]}"

    def image(k):
        return {"file": "images/" + names[k], "image_url": URL + "#page=20", "page_url": URL, "type": "estratta dal datasheet PDF", "retrieved": RET,
                "note": "Vista prospettiva della SDR MK3 (Figura 4.2 del datasheet); i front end d'antenna non sono rappresentati."}

    src = {"url": URL, "document": DOC, "retrieved": RET, **VERIFIED}
    new = [
        {"id": "gomspace-nanocom-link-s", "category": "comms", "vendor": "GomSpace", "name": "NanoCom Link S (SDR MK3 + ANT2150-DUP, S-band)", "family": "gomspace-nanocom-link", "mass_kg": 0.418,
         "temp_op_c": [-40, 53], "power_w": None,
         "notes": (COMMON + "LINK S: S-band CCSDS 131.0-B-3 in full duplex continuo (BPSK/QPSK, 0.5-7.5 MBd/s, convoluzionale 1/2 + Reed-Solomon (255,223)), trasmissione 2200-2290 MHz fino a 32 dBm, ricezione 2025-2110 MHz, "
                   "fino a 7.5 Mbit/s. Massa: SDR 272 g + ANT2150-DUP 123 g (Type C; Type A 112 g) + cavi 23 g (6+6+6+4+1) = 418 g DERIVATA. "
                   "Potenza: standby SDR 3.5/5.0/7.0 W (min/tip/max) + ANT2150 0.1/0.1/0.3 W; attiva SDR 5.0/6.3/9.0 W + ANT2150 da 2.0 a 15.0 W secondo il livello di potenza (Tabella 5.6): "
                   "idle 7.3 W = 7.0 + 0.3 e trasmissione 24.0 W = 9.0 + 15.0 DERIVATE (massimi)."),
         "source": dict(src),
         "specs": {"band": "S", "has_receiver": True, "data_rate_kbps_max": 7500.0, "power_w_idle": 7.3, "power_w_tx": 24.0, "data_interfaces": ["CAN", "RS-422", "SpaceWire"],
                   "supply_voltage_ranges_v": [[12, 32], [8, 18]]},
         "dimensions": {"mm": [95, 95, 23.85], "basis": "declared", "note": "Datasheet GomSpace, Figura 11.3: SDR MK3 NanoCom Link S, 95 x 95 mm (h7) e spessore 23.85 mm; front end d'antenna esclusi."},
         "image": image("s"), "datasheet": dict(ds), "shape": dict(SHAPE)},
        {"id": "gomspace-nanocom-link-x", "category": "comms", "vendor": "GomSpace", "name": "NanoCom Link X (SDR MK3 + ANT8250, X-band, solo TX)", "family": "gomspace-nanocom-link", "mass_kg": 0.448,
         "temp_op_c": [-40, 53], "power_w": None,
         "notes": (COMMON + "LINK X: X-band DVB-S2 (MODCOD 1-28, roll-off 0.2, 2-50 MBd/s in configurazione standard, VCM e CCM), solo trasmissione 8000-8400 MHz (con il kit filtri DSN opzionale 8020-8280 MHz) fino a 33 dBm "
                   "(31 dBm con il kit), velocita' di 50, 150 o 225 Mbit/s scelte all'ordine (usata la massima, 225); nessuna ricezione in X-band. "
                   "Massa: SDR 272 g + ANT8250 150 g (lato Y; X 144 g, Z 131 g) + cavi 26 g (6+6+6+2+5+1) = 448 g DERIVATA. "
                   "Potenza: standby SDR 3.5/5.4/7.0 W + VCOM 5 V 0.3/0.7/1.0 W; attiva SDR 4.5/5.9/8.0 W + ANT8250 da 5.0 a 20.0 W (Tabelle 5.8-5.10) + VCOM 2.0/2.4/3.0 W: "
                   "idle 8.0 W = 7.0 + 1.0 e trasmissione 31.0 W = 8.0 + 20.0 + 3.0 DERIVATE (massimi). Progettato per almeno 20 minuti di trasmissione continua; l'ANT8250 richiede una buona interfaccia termica con la struttura."),
         "source": dict(src),
         "specs": {"band": "X", "has_receiver": False, "data_rate_kbps_max": 225000.0, "power_w_idle": 8.0, "power_w_tx": 31.0, "data_interfaces": ["CAN", "RS-422", "SpaceWire"],
                   "supply_voltage_ranges_v": [[12, 32], [4.9, 5.1]]},
         "dimensions": {"mm": [95, 95, 31.65], "basis": "declared", "note": "Datasheet GomSpace, Figura 11.2: SDR MK3 NanoCom Link X, 95 x 95 mm (h7) e spessore 31.65 mm; front end d'antenna esclusi."},
         "image": image("x"), "datasheet": dict(ds), "shape": dict(SHAPE)},
        {"id": "gomspace-nanocom-link-sx", "category": "comms", "vendor": "GomSpace", "name": "NanoCom Link SX (SDR MK3 + ANT2150-DUP + ANT8250, S+X-band)", "family": "gomspace-nanocom-link", "mass_kg": 0.629,
         "temp_op_c": [-40, 53], "power_w": None,
         "notes": (COMMON + "LINK SX: due TR600 sulla stessa SDR, con le funzioni di S (full duplex, fino a 7.5 Mbit/s) e di X (solo TX, fino a 225 Mbit/s); supporta un solo downlink dati attivo alla volta, con passaggio rapido tra S e X. "
                   "Massa: SDR 315 g + ANT2150-DUP 123 g + ANT8250 150 g + cavi 41 g (6+6+6+6+6+2+4+5) = 629 g DERIVATA. "
                   "Potenza: standby SDR 4.5/6.1/7.5 W + ANT2150 0.1/0.1/0.3 W + ANT8250 0.0 W + VCOM 0.3/0.7/1.0 W; attiva SDR 5.0/8.1/10.2 W + ANT2150 2.0-16.0 W + ANT8250 5.0-20.0 W + VCOM 2.0/2.4/3.0 W: "
                   "idle 8.8 W = 7.5 + 0.3 + 0.0 + 1.0 e trasmissione 49.2 W = 10.2 + 16.0 + 20.0 + 3.0 DERIVATE (somma dei massimi dei moduli; con un solo downlink attivo il caso reale e' inferiore, ma il datasheet "
                   "non lo quantifica)."),
         "source": dict(src),
         "specs": {"band": "S/X", "has_receiver": True, "data_rate_kbps_max": 225000.0, "power_w_idle": 8.8, "power_w_tx": 49.2, "data_interfaces": ["CAN", "RS-422", "SpaceWire"],
                   "supply_voltage_ranges_v": [[12, 32], [8, 18], [4.9, 5.1]]},
         "dimensions": {"mm": [95, 95, 31.65], "basis": "declared", "note": "Datasheet GomSpace, Figura 11.4: SDR MK3 NanoCom Link SX, 95 x 95 mm (h7) e spessore 31.65 mm; front end d'antenna esclusi."},
         "image": image("sx"), "datasheet": dict(ds), "shape": dict(SHAPE)},
    ]
    ids = {c["id"] for c in new}
    comps[:] = [c for c in comps if c["id"] not in ids]
    last = max(i for i, c in enumerate(comps) if c["category"] == "comms")
    comps[last + 1:last + 1] = new
    cat_path.write_text(json.dumps(cat, indent=1, ensure_ascii=False), encoding="utf-8")

    mf = PROJ / "images" / "manifest.csv"
    with mf.open(encoding="utf-8-sig", newline="") as fh:
        rows = [r for r in csv.reader(fh) if r and r[0] not in ids]
    for c in new:
        im = c["image"]
        fname = Path(im["file"]).name
        rows.append([c["id"], c["vendor"], c["name"], fname, im["type"], im["image_url"], im["page_url"], im["retrieved"], px[fname], im["note"]])
    with mf.open("w", encoding="utf-8-sig", newline="") as fh:
        csv.writer(fh).writerows(rows)

    dm = PROJ / "datasheets" / "manifest.csv"
    with dm.open(encoding="utf-8-sig", newline="") as fh:
        drows = [r for r in csv.reader(fh) if r and r[0] != Path(ds["file"]).name]
    drows.append([Path(ds["file"]).name, ds["document"], ds["source_url"], RET, str(ds["bytes"]), " ".join(sorted(ids))])
    with dm.open("w", encoding="utf-8-sig", newline="") as fh:
        csv.writer(fh).writerows(drows)
    print(f"{len(new)} NanoCom Link aggiunti; catalogo: {len(comps)} componenti")


if __name__ == "__main__":
    main()

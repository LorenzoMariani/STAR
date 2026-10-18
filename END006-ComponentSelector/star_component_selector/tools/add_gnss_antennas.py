"""Aggiunge la categoria `gnss_antenna` (antenne di ricezione GNSS) con tre componenti da documenti pubblici dei fornitori.

  isis-gapa          ISISpace GNSS Active Patch Antenna, datasheet ISIS-GAPA-DSH-0001 issue 2.2 (2022-11-09), da cubesatshop.com
  exa-gca01          EXA (Ecuadorian Space Agency) GCA01 Compact GNSS Active Patch Antenna, datasheet (cubesatshop.com)
  newspace-nant-ptcl1  NewSpace Systems NANT-PTCL1: nel datasheet GPS Receiver 2020-10a gia' in datasheets/ (pagina 1)

Non aggiunti: Spacemanic Zenith e SkyFox piPATCH (datasheet non raggiungibile o solo schede di aggregatori), EnduroSat (nessun documento trovato).
uso: python tools/add_gnss_antennas.py <cartella con gapa.pdf, gca01.pdf e GPS-Antenna-web.jpg gia' scaricati>
Idempotente. Nessun valore e' stimato: i valori derivati (potenza = corrente x tensione, intervallo di frequenza da centro e banda) sono marcati nelle note.
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
GAPA_URL = "https://www.cubesatshop.com/wp-content/uploads/2023/04/ISIS-GAPA-DSH-0001-GNSS_Antenna_Datasheet-02_02.pdf"
GAPA_PAGE = "https://www.cubesatshop.com/product/isis-gps-patch-antenna/"
GAPA_IMG = "https://www.cubesatshop.com/wp-content/uploads/2019/12/GPS-Antenna-web.jpg"
GCA_URL = "https://www.cubesatshop.com/wp-content/uploads/2021/03/EXA-GCA01-COMPACT-GNSS-ACTIVE-PATCH-ANTENNA-Datasheet.pdf"
SHAPE = {"type": "patch", "axis": None, "basis": "image", "set": RET}


def save_png(im, name, vendor, title, source, page):
    meta = PngInfo()
    for k, v in (("Title", f"{vendor} {title}"), ("Author", vendor), ("Source", source), ("Description", f"Antenna GNSS. Pagina/documento di origine: {page}. Scaricata il {RET}."), ("Copyright", NOTICE)):
        meta.add_text(k, v)
    im.save(PROJ / "images" / name, optimize=True, pnginfo=meta)
    return f"{im.size[0]}x{im.size[1]}"


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
    ns = next(c for c in comps if c["id"] == "newspace-ngps-01-422")

    ds = {}
    for key, (name, src, url, doc) in {
            "gapa": ("ISISpace__ISIS-GAPA-GNSS-Antenna-Datasheet-2_2.pdf", "gapa.pdf", GAPA_URL, "ISISpace GNSS Active Patch Antenna datasheet ISIS-GAPA-DSH-0001 issue 2.2 (2022-11-09)"),
            "gca": ("EXA__GCA01-Compact-GNSS-Active-Patch-Antenna.pdf", "gca01.pdf", GCA_URL, "EXA GCA01 Compact GNSS Active Patch Antenna datasheet (bozza con refusi)")}.items():
        f = "datasheets/" + short_name(name)
        shutil.copyfile(work / src, PROJ / f)
        ds[key] = {"file": f, "document": doc, "source_url": url, "retrieved": RET, "bytes": (PROJ / f).stat().st_size}
    px = {}
    px["ISISpace-GAPA.png"] = save_png(Image.open(work / "GPS-Antenna-web.jpg").convert("RGB"), "ISISpace-GAPA.png", "ISISpace", "GNSS Active Patch Antenna", GAPA_IMG, GAPA_PAGE)
    px["EXA-GCA01.png"] = save_png(pdf_image(work / "gca01.pdf", 388), "EXA-GCA01.png", "EXA", "GCA01", GCA_URL + "#page=1", GCA_URL)
    px["NewSpace-NANT-PTCL1.png"] = save_png(pdf_image(PROJ / ns["datasheet"]["file"], 1464), "NewSpace-NANT-PTCL1.png", "NewSpace Systems", "NANT-PTCL1", ns["source"]["url"] + "#page=1", ns["source"]["url"])

    new = [
        {"id": "isis-gapa", "category": "gnss_antenna", "vendor": "ISISpace", "name": "GNSS Active Patch Antenna (GAPA)", "mass_kg": 0.018, "temp_op_c": [-30, 70], "power_w": 0.05,
         "notes": ("Datasheet ISIS-GAPA-DSH-0001 issue 2.2 (2022-11-09): antenna attiva su patch ceramico per GPS L1 / Galileo E1, frequenza 1572-1578 MHz (banda 6 MHz), polarizzazione RHCP, "
                   "rapporto assiale <3 dB, return loss >15 dB, guadagno del circuito attivo 34.5 dB, filtri SAW, connettore MMCX unico per RF e alimentazione, alimentazione 3-5 V, "
                   "assorbimento '<10 mA a 5 V': potenza 0.05 W DERIVATA (5 V x 10 mA), non dichiarata in W. Massa 18 g in tabella ('<20 g' nelle caratteristiche), 70 x 70 x 9.7 mm, "
                   "con piastra di montaggio per CubeSat. Qualificata termicamente da -30 a +70 C e per 15 g quasi-statici. Il guadagno di picco del patch e' scritto 5.5 dBi nelle "
                   "caratteristiche e 5.2 dBi a 1575 MHz nella tabella: valori in contraddizione, lasciato non dichiarato (passive_gain_dbi null). La pagina CubeSatShop riporta una "
                   "versione precedente (<16 g, 3.5 V a 9 mA): non usata."),
         "source": {"url": GAPA_URL, "document": ds["gapa"]["document"], "retrieved": RET, **VERIFIED},
         "specs": {"bands": ["GPS L1", "Galileo E1"], "frequency_ranges_mhz": [[1572, 1578]], "active": True, "passive_gain_dbi": None, "lna_gain_db": 34.5, "total_gain_dbi": None,
                   "noise_figure_db": None, "beamwidth_deg": None, "polarization": "RHCP", "supply_voltage_ranges_v": [[3, 5]]},
         "dimensions": {"mm": [70, 70, 9.7], "basis": "declared", "note": "Datasheet ISIS GAPA issue 2.2: 70 x 70 x 9.7 mm (A x L x P)."},
         "image": {"file": "images/ISISpace-GAPA.png", "image_url": GAPA_IMG, "page_url": GAPA_PAGE, "type": "web", "retrieved": RET},
         "datasheet": dict(ds["gapa"]), "shape": dict(SHAPE)},
        {"id": "exa-gca01", "category": "gnss_antenna", "vendor": "EXA (Ecuadorian Space Agency)", "name": "GCA01 compact GNSS active patch antenna", "mass_kg": 0.01138, "temp_op_c": [-40, 85], "power_w": 0.1265,
         "notes": ("Datasheet EXA (bozza con refusi): patch ceramico a doppia risonanza con LNA a uno stadio e filtro SAW, GPS L1 (1575.42 +-1.023 MHz), Galileo, GLONASS (1602 +-5 MHz), "
                   "BeiDou (1561.098 +-2.046 MHz), banda complessiva 1561-1606 MHz, RHCP, 50 ohm, VSWR in uscita <=2.0. Guadagno del solo patch allo zenit: -2.5 dBi (GPS/Galileo), "
                   "-1.5 (GLONASS), -1 (BeiDou); guadagno complessivo allo zenit (antenna + SAW + LNA + cavo + connettore): 15.5 +-3 dBi (GPS/Galileo), 16.5 +-3 (GLONASS), 17 +-3 (BeiDou). "
                   "LNA: 12 / 18 / 22 dB min / tipico / max a 1.8 / 3.0 / 5.5 V, assorbimento 5 / 10 / 23 mA, cifra di rumore 3.0 / 2.8 / 3.0 dB. Potenza 0.1265 W DERIVATA (5.5 V x 23 mA, "
                   "massimo), non dichiarata in W. Campo di vista 112 gradi (non e' la larghezza di fascio a -3 dB). Il datasheet scrive 'Galileo 1575.42 +-4GHz': refuso, non usato. "
                   "Dimensioni: ceramica 25.1 x 25.1 x 4.7 mm; con la custodia di schermo 25.1 x 25.1 x 7.9 mm (riportata); cavo coassiale 60 mm; massa 11.38 g; radiazioni 'minimo 4 anni in LEO'; "
                   "eredita' di volo dal 2018."),
         "source": {"url": GCA_URL, "document": ds["gca"]["document"], "retrieved": RET, **VERIFIED},
         "specs": {"bands": ["GPS L1", "Galileo E1", "GLONASS G1", "BeiDou B1"], "frequency_ranges_mhz": [[1561, 1606]], "active": True, "passive_gain_dbi": -2.5, "lna_gain_db": 18.0,
                   "total_gain_dbi": 15.5, "noise_figure_db": 2.8, "beamwidth_deg": None, "polarization": "RHCP", "supply_voltage_ranges_v": [[1.8, 5.5]]},
         "dimensions": {"mm": [25.1, 25.1, 7.9], "basis": "declared", "note": "Datasheet EXA: 25.1 x 25.1 x 7.9 mm con la custodia di schermo (ceramica 25.1 x 25.1 x 4.7 mm)."},
         "image": {"file": "images/EXA-GCA01.png", "image_url": GCA_URL + "#page=1", "page_url": GCA_URL, "type": "estratta dal datasheet PDF", "retrieved": RET},
         "datasheet": dict(ds["gca"]), "shape": dict(SHAPE)},
        {"id": "newspace-nant-ptcl1", "category": "gnss_antenna", "vendor": "NewSpace Systems", "name": "NANT-PTCL1 active GPS antenna", "mass_kg": 0.08, "temp_op_c": [-25, 55], "power_w": 0.08, "tid_krad": 10,
         "notes": ("Datasheet NewSpace Systems GPS Receiver 2020-10a (pag. 1): antenna attiva GPS L1 a 1575.42 MHz con banda 20 MHz (intervallo 1565.42-1585.42 MHz DERIVATO da centro e banda), "
                   "larghezza di fascio a -3 dB >=100 gradi, polarizzazione RHCP, guadagno attivo >=16 dBiC allo zenit (limite inferiore), cifra di rumore <2 dB (limite superiore), "
                   "rapporto assiale <10 dB, return loss <=-5 dB, 50 ohm; massa '<80 g' (limite superiore), potenza '<80 mW', alimentazione 5 V, connettore SMA femmina, 4 fori M3 passanti; "
                   "temperatura operativa -25..+55 C (non operativa -30..+60 C); vibrazioni 14 g rms; radiazioni 10 krad a livello di componente."),
         "source": {"url": ns["source"]["url"], "document": ns["source"]["document"], "retrieved": RET, **VERIFIED},
         "specs": {"bands": ["GPS L1"], "frequency_ranges_mhz": [[1565.42, 1585.42]], "active": True, "passive_gain_dbi": None, "lna_gain_db": None, "total_gain_dbi": 16.0,
                   "noise_figure_db": 2.0, "beamwidth_deg": 100.0, "polarization": "RHCP", "supply_voltage_ranges_v": [[5, 5]]},
         "dimensions": {"mm": [54, 54, 14.1], "basis": "declared", "note": "Datasheet NewSpace Systems 2020-10a."},
         "image": {"file": "images/NewSpace-NANT-PTCL1.png", "image_url": ns["source"]["url"] + "#page=1", "page_url": ns["source"]["url"], "type": "estratta dal datasheet PDF", "retrieved": RET},
         "datasheet": dict(ns["datasheet"]), "shape": {**SHAPE, "type": "box"}},
    ]
    ids = {c["id"] for c in new}
    comps[:] = [c for c in comps if c["id"] not in ids]
    last = max(i for i, c in enumerate(comps) if c["category"] == "gps")
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
        drows = list(csv.reader(fh))
    new_files = {Path(d["file"]).name for d in ds.values()}
    drows = [r for r in drows if r[0] not in new_files]
    for r in drows[1:]:
        r[5] = " ".join(x for x in r[5].split() if x != "newspace-nant-ptcl1")
        if r[0] == Path(ns["datasheet"]["file"]).name:
            r[5] = (r[5] + " newspace-nant-ptcl1").strip()
    members = {"gapa": "isis-gapa", "gca": "exa-gca01"}
    for key, d in ds.items():
        drows.append([Path(d["file"]).name, d["document"], d["source_url"], RET, str(d["bytes"]), members[key]])
    with dm.open("w", encoding="utf-8-sig", newline="") as fh:
        csv.writer(fh).writerows(drows)
    print(f"{len(new)} antenne GNSS aggiunte; catalogo: {len(comps)} componenti")


if __name__ == "__main__":
    main()

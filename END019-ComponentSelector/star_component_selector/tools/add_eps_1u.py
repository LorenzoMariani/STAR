"""Aggiunge tre componenti `eps` utilizzabili in un CubeSat 1U da un documento pubblico del fornitore.

  isis-iceps2-type-a  ISISpace ICEPS2 Type A (PIU + batteria PBP-2S1P)
  isis-iceps2-type-b  ISISpace ICEPS2 Type B (PIU + batteria PBP-4S1P)
  isis-iceps2-type-c  ISISpace ICEPS2 Type C (PIU + PBP-4S1P + DaughterBoard)

Fonte: datasheet ISIS-ICEPS2-DSH-0001 issue 1.2 (2024-07-26). L'EPS e' di formato PC104, "1U-3U".
Non aggiunti (nessun documento raggiungibile con valori): GomSpace NanoPower P31u e BP4 (datasheet non piu' online), ISIS iEPS/IMEPS2,
EXA BA0x/TITAN-1 (pagine prodotto senza valori), DHV PicoEPS (solo scheda di un aggregatore).
uso: python tools/add_eps_1u.py <cartella con iceps2.pdf gia' scaricato>
Idempotente. I valori derivati (altezza con batteria di tipo B e C, potenza statica in W) sono marcati nelle note.
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
URL = "https://www.isispace.nl/wp-content/uploads/2025/01/ISIS-ICEPS2-DSH-0001-ICEPS2_Datasheet-01_02.pdf"
DOC = "ISISpace ICEPS2 datasheet ISIS-ICEPS2-DSH-0001 issue 1.2 (2024-07-26)"
PAGE = "https://www.isispace.nl/product/compact-electrical-power-system/"
XREF = {"a": 833, "b": 827, "c": 823}          # render della Tabella 1 (pagina 6) con la configurazione del tipo
SHAPE = {"type": "board", "axis": None, "basis": "image", "set": RET}


def pdf_image(pdf, xref):
    d = pymupdf.open(pdf)
    pix = pymupdf.Pixmap(d, xref)
    if pix.n > 3:
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def save_png(im, name, title):
    meta = PngInfo()
    for k, v in (("Title", f"ISISpace {title}"), ("Author", "ISISpace"), ("Source", URL + "#page=6"),
                 ("Description", f"EPS CubeSat. Pagina/documento di origine: {URL}, Tabella 1 (pag. 6). Scaricata il {RET}."), ("Copyright", NOTICE)):
        meta.add_text(k, v)
    im.save(PROJ / "images" / name, optimize=True, pnginfo=meta)
    return f"{im.size[0]}x{im.size[1]}"


COMMON = ("Datasheet ISIS-ICEPS2-DSH-0001 issue 1.2 (2024-07-26): EPS PC104 per piattaforme 1U-3U in LEO ('fino a 3U XL'), MPPT in hardware, riscaldatore automatico di batteria, "
          "interfaccia I2C (slave, 7 bit, 100/400 kbit/s). Potenza statica 0.093 W (93 mW dichiarati, a riposo). Rail VD0 = tensione di batteria non regolata, VD1 = 5 V (4.91-5.07 V a vuoto), "
          "VD2 = 3.3 V (3.26-3.41 V a vuoto), 4 canali per dominio, 3.01 A tipici per canale e 4 A totali per dominio. "
          "Temperatura 'con batteria' (usata in temp_op_c): scarica da -20 a +60 C, carica da +10 a +45 C (da 0 a +45 C fino a 800 mA), riscaldatori disabilitati; "
          "'senza batteria' -40..+85 C (stima da valutazione di progetto). Qualificazione termica -40..+80 C, carico statico +10.8 g. "
          "Energia: il testo dichiara 28.8 Wh (2S1P, 7.2 V) e 57.6 Wh (4S1P, 14.4 V), la copertina 'da 28.2 Wh a 57.6 Wh' e la tabella celle 3.2 Ah nominali (3.2 Ah x 7.2 V = 23 Wh): "
          "valori in contraddizione tra loro, si riportano i Wh dichiarati nel testo; capacita' in Ah non usata. ")


def main():
    work = Path(sys.argv[1])
    cat_path = PROJ / "data" / "catalog.json"
    cat = json.loads(cat_path.read_text(encoding="utf-8"))
    comps = cat["components"]

    f = "datasheets/" + short_name("ISISpace__ICEPS2-Datasheet-1_2.pdf")
    shutil.copyfile(work / "iceps2.pdf", PROJ / f)
    ds = {"file": f, "document": DOC, "source_url": URL, "retrieved": RET, "bytes": (PROJ / f).stat().st_size}
    names = {"a": "ISISpace-ICEPS2-TypeA.png", "b": "ISISpace-ICEPS2-TypeB.png", "c": "ISISpace-ICEPS2-TypeC.png"}
    titles = {"a": "ICEPS2 Type A", "b": "ICEPS2 Type B", "c": "ICEPS2 Type C"}
    px = {names[k]: save_png(pdf_image(work / "iceps2.pdf", XREF[k]), names[k], titles[k]) for k in XREF}

    def image(k):
        return {"file": "images/" + names[k], "image_url": URL + "#page=6", "page_url": URL, "type": "estratta dal datasheet PDF", "retrieved": RET,
                "note": "Render della Tabella 1 (pag. 6) 'ICEPS Types': il tipo e' quello della cella della tabella."}

    new = [
        {"id": "isis-iceps2-type-a", "category": "eps", "vendor": "ISISpace", "name": "ICEPS2 Type A (PIU + PBP-2S1P, 28.8 Wh)", "mass_kg": 0.184, "temp_op_c": [-20, 60], "power_w": 0.093,
         "notes": (COMMON + "TYPE A: scheda principale PIU con la batteria PBP-2S1P (2 celle in serie, 7.2 V, 28.8 Wh dichiarati nel testo) montata direttamente sopra; non combinabile con la DaughterBoard. "
                   "3 ingressi MPPT, tensione funzionale 3.5-7.5 V (massimo assoluto 15 V), 2 A per canale. Massa 184 g (179-189 g), 96 x 92 x 26.5 mm (PIU + batteria). "
                   "Soglia software di spegnimento 6.0 V."),
         "source": {"url": URL, "document": DOC, "retrieved": RET, **VERIFIED},
         "specs": {"compatible_form_factors_u": [1, 2, 3], "pv_channels": 3, "pv_voltage_v": [3.5, 7.5], "pv_power_w_max": None, "battery_voltage_v": None, "battery_families": None,
                   "integrated_battery_wh": 28.8, "integrated_battery_voltage_v": 7.2, "output_voltage_ranges_v": [[3.3, 3.3], [5, 5]], "output_power_w_max": None,
                   "data_interfaces": ["I2C"], "efficiency": None},
         "dimensions": {"mm": [96, 92, 26.5], "basis": "declared", "note": "Datasheet ISIS ICEPS2 issue 1.2, 'Volume' Type A: 96 x 92 x 26.5 mm (PIU + batteria a 2 celle); esclusi i connettori del kit (CSKB)."},
         "image": image("a"), "datasheet": dict(ds), "shape": dict(SHAPE)},
        {"id": "isis-iceps2-type-b", "category": "eps", "vendor": "ISISpace", "name": "ICEPS2 Type B (PIU + PBP-4S1P, 57.6 Wh)", "mass_kg": 0.310, "temp_op_c": [-20, 60], "power_w": 0.093,
         "notes": (COMMON + "TYPE B: scheda principale PIU + batteria PBP-4S1P (4 celle in serie, 14.4 V, 57.6 Wh dichiarati nel testo), la batteria si monta in un punto qualsiasi dello stack. "
                   "3 ingressi MPPT, tensione funzionale 3.5-13 V (massimo assoluto 15 V), 2 A per canale. Massa 310 g (305-315 g) nella tabella 'Physical characteristics', "
                   "senza indicare esplicitamente se comprende la batteria. Dimensioni: il datasheet da' PIU 96 x 92 x 11.3 mm e batteria a 4 celle 94 x 89 x 21.0 mm come volumi separati: "
                   "altezza 32.3 mm DERIVATA come somma 11.3 + 21.0 (impilati), non dichiarata. Soglia software di spegnimento 12.0 V."),
         "source": {"url": URL, "document": DOC, "retrieved": RET, **VERIFIED},
         "specs": {"compatible_form_factors_u": [1, 2, 3], "pv_channels": 3, "pv_voltage_v": [3.5, 13], "pv_power_w_max": None, "battery_voltage_v": None, "battery_families": None,
                   "integrated_battery_wh": 57.6, "integrated_battery_voltage_v": 14.4, "output_voltage_ranges_v": [[3.3, 3.3], [5, 5]], "output_power_w_max": None,
                   "data_interfaces": ["I2C"], "efficiency": None},
         "dimensions": {"mm": [96, 92, 32.3], "basis": "derived", "note": "Datasheet ISIS ICEPS2 issue 1.2: PIU 96 x 92 x 11.3 mm + batteria a 4 celle 94 x 89 x 21.0 mm; altezza derivata 11.3 + 21.0 = 32.3 mm."},
         "image": image("b"), "datasheet": dict(ds), "shape": dict(SHAPE)},
        {"id": "isis-iceps2-type-c", "category": "eps", "vendor": "ISISpace", "name": "ICEPS2 Type C (PIU + PBP-4S1P + DaughterBoard, 57.6 Wh)", "mass_kg": 0.360, "temp_op_c": [-20, 60], "power_w": 0.093,
         "notes": (COMMON + "TYPE C: come il Type B piu' la DaughterBoard (PIU-DB): 2 ingressi MPPT in piu' (3+2 = 5), 3 domini di tensione in piu' (VD3 e VD4 buck, default 5 V e 3.3 V, "
                   "personalizzabili 2.8-12.08 V a costo aggiuntivo; VD5 boost, default 28.2 V (27.4-29.0 V), 1.5 A) e 8 canali di uscita in piu'. Tensione funzionale MPPT 3.5-13 V, 2 A per canale. "
                   "Massa 360 g (355-365 g), senza indicare esplicitamente se comprende la batteria. Dimensioni: PIU + DaughterBoard 96 x 92 x 16 mm e batteria a 4 celle 94 x 89 x 21.0 mm come volumi separati: "
                   "altezza 37.0 mm DERIVATA come somma 16 + 21.0, non dichiarata. Soglia software di spegnimento 12.0 V."),
         "source": {"url": URL, "document": DOC, "retrieved": RET, **VERIFIED},
         "specs": {"compatible_form_factors_u": [1, 2, 3], "pv_channels": 5, "pv_voltage_v": [3.5, 13], "pv_power_w_max": None, "battery_voltage_v": None, "battery_families": None,
                   "integrated_battery_wh": 57.6, "integrated_battery_voltage_v": 14.4, "output_voltage_ranges_v": [[3.3, 3.3], [5, 5], [28.2, 28.2]], "output_power_w_max": None,
                   "data_interfaces": ["I2C"], "efficiency": None},
         "dimensions": {"mm": [96, 92, 37.0], "basis": "derived", "note": "Datasheet ISIS ICEPS2 issue 1.2: PIU + DaughterBoard 96 x 92 x 16 mm + batteria a 4 celle 94 x 89 x 21.0 mm; altezza derivata 16 + 21.0 = 37.0 mm."},
         "image": image("c"), "datasheet": dict(ds), "shape": dict(SHAPE)},
    ]
    ids = {c["id"] for c in new}
    comps[:] = [c for c in comps if c["id"] not in ids]
    last = max(i for i, c in enumerate(comps) if c["category"] == "eps")
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
    print(f"{len(new)} EPS aggiunti; catalogo: {len(comps)} componenti")


if __name__ == "__main__":
    main()

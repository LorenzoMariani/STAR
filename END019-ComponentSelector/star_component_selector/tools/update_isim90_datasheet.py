"""Aggiorna la Satlantis iSIM-90 (canale singolo) con il datasheet del fornitore (STAR, 2026-10-16).

Fonte: datasheet Satlantis "iSIM-90" SATL-MKT-T-005-0, scaricato dalla pagina satsearch https://satsearch.co/products/satlantis-isim-90
(file datasheets/Satlantis__iSIM-90_datasheet_SATL-MKT-T-005-0.pdf, fuori da git come gli altri PDF). Valori della colonna "Single channel":

  ottica                      308 x 114 x 100 mm3 (~3U)                     -> dimensions.mm
  elettronica                 209 x 96 x 46 mm3 (~2U), CPU 201 x 88 e TCS    -> dimensions.extra_mm (seconda scatola: volume e disposizione)
                              105 x 88 mm2 impilate
  massa                       < 4 kg                                        -> 4.0 (gia' nel catalogo)
  potenza                     25.3 W in acquisizione, senza riscaldatori     -> power_w
  alimentazione               9 - 34 V                                      -> specs.supply_voltage_ranges_v
  interfacce                  CAN, UART (RS-422/RS-485 opzionali),           -> specs.data_interfaces = CAN, UART, GigE (le opzionali nelle note)
                              GigE (SpaceWire, LVDS opzionali)
  rivelatore                  4096 x 3072 pixel, passo 5.5 um               -> specs.pixel_pitch_um
  memoria                     500 GB                                        -> specs.storage_gb
  risoluzione                 1.65 m a 500 km dopo l'elaborazione           -> GSD resta 2 m (pagina del fornitore, prudente), 1.65 m nelle note
  swath                       13 km a 500 km                                -> invariato

Forma: corpo con obiettivo (lens_box) con l'asse lungo i 308 mm: nella pila l'ottica sta lungo l'asse lungo del CubeSat e, larga 114 mm, occupa
due colonne di un 12U (layout.spec, span).

uso: python tools/update_isim90_datasheet.py      (idempotente)"""
import json
import shutil
import sys
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent
PDF_NAME = "Satlantis__iSIM-90_datasheet_SATL-MKT-T-005-0.pdf"
NOTES = ("Fonti: datasheet Satlantis SATL-MKT-T-005-0 (scaricato da satsearch il 2026-10-16) e pagina del fornitore (2026-10-13). Configurazione a "
         "canale singolo: massa < 4 kg (usato 4.0); ottica 308 x 114 x 100 mm (~3U) e scatola dell'elettronica 209 x 96 x 46 mm (~2U; schede CPU "
         "201 x 88 mm e TCS 105 x 88 mm impilate), contate entrambe nel volume e nella disposizione; potenza 25.3 W durante l'acquisizione, senza "
         "riscaldatori; alimentazione 9-34 V; interfacce CAN, UART e GigE (RS-422/RS-485, SpaceWire e LVDS opzionali); rivelatore CMOS 4096 x 3072 "
         "pixel da 5.5 um, 8/10/12 bit, 26 fps; memoria 500 GB; controllo termico attivo configurabile. Risoluzione 1.65 m a 500 km dopo "
         "l'elaborazione (super-risoluzione) secondo il datasheet, 2 m secondo la pagina del fornitore: usato 2 m. Swath 13 km a 500 km. Per CubeSat "
         "12U e 16U, convalidato in orbita nel Q4 2021. Versione a doppio canale (< 6 kg, ottica 308 x 216 x 115 mm ~6U, swath fino a 26 km, 30.5 W) "
         "e versione SWIR non modellate; la iSIM-170 per microsatelliti non e' inclusa.")


def main() -> None:
    cat_path = PROJ / "data" / "catalog.json"
    cat = json.loads(cat_path.read_text(encoding="utf-8"))
    c = next(x for x in cat["components"] if x["id"] == "satlantis-isim-90")
    c["power_w"] = 25.3
    c["volume_u"] = 5.0
    c["dimensions"] = {"mm": [308.0, 114.0, 100.0], "basis": "declared",
                       "note": "Datasheet SATL-MKT-T-005-0: ottica a canale singolo 308 x 114 x 100 mm3; extra_mm = scatola dell'elettronica.",
                       "extra_mm": [[209.0, 96.0, 46.0]], "extra_note": "electronics box"}
    s = c["specs"]
    s["pixel_pitch_um"] = 5.5
    s["data_interfaces"] = ["CAN", "UART", "GigE"]
    s["supply_voltage_ranges_v"] = [[9.0, 34.0]]
    s["storage_gb"] = 500.0
    c["shape"] = {"type": "lens_box", "axis": 0, "basis": "image", "set": "2026-10-16"}
    c["notes"] = NOTES
    c["source"] = {"url": "https://satsearch.co/products/satlantis-isim-90",
                   "document": "Datasheet Satlantis 'iSIM-90' SATL-MKT-T-005-0 (da satsearch); pagina 'Main Features iSIM 90' di Satlantis",
                   "retrieved": "2026-10-16", "verified": False,
                   "method": "trascritto dal datasheet del fornitore distribuito da satsearch; da controllare manualmente"}
    pdf = PROJ / "datasheets" / PDF_NAME
    if len(sys.argv) > 1 and not pdf.exists():
        shutil.copy2(sys.argv[1], pdf)
    if pdf.exists():
        c["datasheet"] = {"file": f"datasheets/{PDF_NAME}", "document": "Satlantis iSIM-90 datasheet SATL-MKT-T-005-0",
                          "source_url": "https://satsearch.co/products/satlantis-isim-90", "retrieved": "2026-10-16", "bytes": pdf.stat().st_size}
    cat_path.write_text(json.dumps(cat, indent=1, ensure_ascii=False), encoding="utf-8")
    print("iSIM-90 aggiornata dal datasheet" + (" (datasheet collegato)" if pdf.exists() else " (PDF non presente: datasheet non collegato)"))


if __name__ == "__main__":
    main()

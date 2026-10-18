"""Datasheet forniti dall'utente il 2026-10-17 (scaricati da satbase): NanoAvionics UHF Antenna System e scheda ADCS Blue Canyon 2019.

  nanoavionics-uhf-antenna-system   nuovo: datasheet NanoAvionics "UHF Antenna System" NA-RFS-G1-R0 rev. 0 (2018-12-04)
                                    turnstile UHF a 4 monopoli con splitter RF, 400-500 MHz, 2.03 dBi lungo Z (simulato su un 3U),
                                    circolare (sinistra vista dall'alto, destra dal basso), 10 W RF, 42 g, -40..+85 C; dispiegamento escluso.
                                    Pianta 99.6 x 99.6 mm (Figura 5); altezza 7.7 mm dalla pagina prodotto attuale (stesso prodotto, versione
                                    1x1U), i cui valori diversi (33 g, 1.37 dB, perdita di ritorno > 14 dB) sono nelle note.
                                    Il PDF non ha un URL pubblico: source.url = null e source.origin dice da dove viene; la copia locale in
                                    datasheets/ e' la prova della fonte e la foto viene dalla sua pagina 1.
  bct-xact-15/50/100                solo note: la scheda Blue Canyon 2019 (ottobre 2019) e' la versione precedente della scheda REV 1/2026 gia'
                                    in catalogo. Resta la 2026 (piu' recente): per l'XACT-100 la 2019 dichiara 0.433 kg + 1.38 kg (ruote +
                                    barre di torsione) contro 0.52 kg + 1 kg (ruote) della 2026, scritto nelle note; vita di progetto 5 anni in
                                    LEO; consumo non dichiarato in nessuna delle due. Il PDF e' salvato in datasheets/ (nel manifest, non collegato).

Il terzo PDF (Chelton 19-430-10) e' un'antenna UHF SatCOM per aerei (225-400 MHz, 3.4 kg, 404 x 210 mm, montaggio su fusoliera):
non e' un componente CubeSat e non entra nel catalogo.

La foto dell'antenna e' il JPEG incorporato a pagina 1 del datasheet NanoAvionics (stream DCTDecode estratto senza ricodifica e salvato
come uhf_antenna_p1.jpg nella cartella di lavoro), ritagliato sull'antenna (senza il logo).

uso: python tools/add_satbase_datasheets.py <cartella con satbase-uhf-antenna-system-datasheet.pdf, satbase-xact-100-datasheet.pdf, uhf_antenna_p1.jpg>
Idempotente."""
import csv
import json
import shutil
import sys
from pathlib import Path

from PIL import Image
from PIL.PngImagePlugin import PngInfo

PROJ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from add_datasheets import short_name  # noqa: E402

RET = "2026-10-17"
ORIGIN = "PDF fornito dall'utente il 2026-10-17 (scaricato da satbase), senza URL pubblico"
NOTICE = ("Immagine di proprieta' del produttore, qui solo come riferimento visivo del prodotto; per usi diversi (pubblicazioni, "
          "presentazioni esterne) chiedere il permesso al produttore.")
ANT_PDF, XACT_PDF, ANT_JPG = "satbase-uhf-antenna-system-datasheet.pdf", "satbase-xact-100-datasheet.pdf", "uhf_antenna_p1.jpg"
ANT_DOC = "NanoAvionics UHF Antenna System datasheet NA-RFS-G1-R0 rev. 0 (2018-12-04)"
XACT_DOC = "Blue Canyon Technologies Attitude Control Systems sheet (ottobre 2019)"
ANT_PAGE = "https://nanoavionics.com/cubesat-components/cubesat-uhf-antenna/"
ANT_ID, ANT_IMG = "nanoavionics-uhf-antenna-system", "NanoAvionics-UHFAntennaSystem.png"
CROP = (30, 440, 1580, 1050)     # pixel della foto di pagina 1 (1610 x 1760) che contengono l'antenna

ANT_NOTES = (
    "Datasheet NA-RFS-G1-R0 rev. 0 (NanoAvionics, 2018-12-04): splitter RF (adattamento d'impedenza e rete di sfasamento) con 4 monopoli "
    "per formare una turnstile a polarizzazione circolare, sinistra vista dall'alto e destra dal basso, lineare nel piano delle antenne; "
    "400-500 MHz, 50 ohm, potenza RF massima 10 W, perdita d'inserzione < 1.3 dB, perdita di ritorno > 28 dB, connettore MCX, massa 42 g, "
    "-40..+85 C. Guadagno 'sempre specifico del satellite': simulato su LituanicaSAT-2 (3U, antenne a 90 gradi dall'asse lungo) massimo "
    "2.03 dBi lungo l'asse lungo (Z) e da -1.9 a -0.2 dBi lungo X e Y (2.03 dBi usato come picco). Monopoli su cerniere a molla in "
    "alluminio 7075, ripiegati a 90 gradi quando stivati e lunghi 156.79 mm (Figura 4, piu' del lato di un 1U); il sistema di "
    "dispiegamento NON e' incluso (NanoAvionics lo vende a parte) e il datasheet non dichiara potenza. Compatibile con i prodotti "
    "NanoAvionics, CubeSat Kit e strutture ISIS; foro opzionale nello splitter per altri carichi. Pianta 99.6 x 99.6 mm (Figura 5); il "
    "connettore MCX sporge 10.36 mm sotto la scheda (Figura 4), escluso dall'altezza. "
    f"Pagina prodotto attuale ({ANT_PAGE}, letta il 2026-10-17): versioni 1x1U 33 g, 99.6 x 99.6 x 7.7 mm, guadagno tipico 1.37 dB; "
    "1x2U 50 g, 222 x 96 x 7.7 mm, 2.86 dB; 2x2U 65 g, 224 x 222 x 7.7 mm, 2-3 dB; perdita di ritorno > 14 dB, temperatura di rumore 360 K "
    "(nadir); prezzi 5,300 EUR (antenna a monopolo), 5,440 EUR (sistema per CubeSat 6U-16U), 5,580 EUR (microsatelliti), ordine minimo 4, "
    "consegna 2-4 mesi. Qui si usano massa e guadagno del datasheet (versione 1x1U del 2018) e l'altezza 7.7 mm della pagina. "
    "Stesso fornitore della radio NanoAvionics SatCOM UHF (395-440 MHz).")

XACT_NOTE_2019 = (
    " Scheda BCT precedente (ottobre 2019; PDF fornito dall'utente il 2026-10-17, da satbase): XACT-100 0.433 kg + 1.38 kg (ruote + "
    "barre di torsione) = 1.813 kg, 10 x 10 x 5 cm (0.5U) esclusi i componenti esterni, 100 mNms, 12 V, RS-422, slew >= 10 gradi/s "
    "(12U da 25 kg), puntamento +-0.003 gradi (1 sigma) su 2 assi e +-0.007 gradi sul terzo, vita di progetto 5 anni in LEO. Si tiene "
    "la massa della REV 1/2026 (piu' recente); per un bilancio di massa prudente il valore 2019 e' 0.29 kg piu' alto. Consumo non "
    "dichiarato nemmeno nella scheda 2019.")
FAMILY_NOTE_2019 = (" Scheda BCT precedente (ottobre 2019; PDF fornito dall'utente il 2026-10-17, da satbase): {mass}, {vol}, puntamento "
                    "+-0.003 gradi (1 sigma) su 2 assi e +-0.007 gradi sul terzo, 12 V, RS-422, vita di progetto 5 anni in LEO; consumo "
                    "non dichiarato.")
FAMILY = {"bct-xact-15": ("0.885 kg", "10 x 10 x 5 cm (0.5U)"), "bct-xact-50": ("1.23 kg", "10 x 10 x 7.54 cm (0.75U)")}


def copy_pdf(work: Path, src: str, name: str, doc: str) -> dict:
    f = "datasheets/" + short_name(name)
    shutil.copyfile(work / src, PROJ / f)
    return {"file": f, "document": doc, "source_url": None, "origin": ORIGIN, "retrieved": RET, "bytes": (PROJ / f).stat().st_size}


def save_image(work: Path) -> str:
    im = Image.open(work / ANT_JPG).convert("RGB").crop(CROP)
    meta = PngInfo()
    for k, v in (("Title", "NanoAvionics UHF Antenna System"), ("Author", "NanoAvionics"), ("Source", ANT_DOC),
                 ("Description", f"Foto di pagina 1 del datasheet ({ORIGIN})."), ("Copyright", NOTICE)):
        meta.add_text(k, v)
    im.save(PROJ / "images" / ANT_IMG, optimize=True, pnginfo=meta)
    return f"{im.size[0]}x{im.size[1]}"


def main() -> None:
    work = Path(sys.argv[1])
    cat_path = PROJ / "data" / "catalog.json"
    cat = json.loads(cat_path.read_text(encoding="utf-8"))
    comps = cat["components"]
    by_id = {c["id"]: c for c in comps}

    ds_ant = copy_pdf(work, ANT_PDF, "NanoAvionics__UHF-Antenna-System-NA-RFS-G1-R0.pdf", ANT_DOC)
    ds_xact = copy_pdf(work, XACT_PDF, "Blue-Canyon-Technologies__ACS-2019.pdf", XACT_DOC)
    px = save_image(work)

    ant = {
        "id": ANT_ID, "category": "antenna", "vendor": "NanoAvionics", "name": "UHF Antenna System (NA-RFS-G1-R0)",
        "mass_kg": 0.042, "power_w": None, "temp_op_c": [-40, 85], "notes": ANT_NOTES,
        "source": {"url": None, "origin": ORIGIN, "document": ANT_DOC, "retrieved": RET, "verified": False,
                   "method": "trascritto dal datasheet del fornitore fornito dall'utente (copia in datasheets/); da controllare manualmente"},
        "specs": {"bands": ["UHF"], "frequency_ranges_mhz": [[400.0, 500.0]], "antenna_type": "wire", "gain_dbi": 2.03, "beamwidth_deg": None,
                  "polarization": "RHCP/LHCP", "rf_power_w_max": 10.0, "deployable": True, "data_interfaces": None, "supply_voltage_ranges_v": None},
        "dimensions": {"mm": [99.6, 99.6, 7.7], "basis": "declared",
                       "note": ("Pianta 99.6 x 99.6 mm dal disegno del datasheet (Figura 5) e dalla pagina prodotto; altezza 7.7 mm dalla pagina prodotto "
                                "(versione 1x1U). Il connettore MCX sporge 10.36 mm sotto la scheda (Figura 4) e non e' compreso.")},
        "image": {"file": f"images/{ANT_IMG}", "image_url": ds_ant["file"] + "#page=1", "page_url": ds_ant["file"], "type": "estratta dal datasheet PDF",
                  "retrieved": RET, "note": f"Pagina 1 del datasheet {ANT_DOC} ({ORIGIN})."},
        "datasheet": dict(ds_ant),
        "shape": {"type": "patch", "axis": None, "basis": "image", "set": RET},
    }
    comps[:] = [c for c in comps if c["id"] != ANT_ID]
    last = max(i for i, x in enumerate(comps) if x["category"] == "antenna" and x["vendor"] in ("GomSpace", "ISISpace", "EnduroSat"))
    comps.insert(last + 1, ant)

    x = by_id["bct-xact-100"]
    x["notes"] = x["notes"].split(" Scheda BCT precedente")[0] + XACT_NOTE_2019
    for cid, (mass, vol) in FAMILY.items():
        c = by_id[cid]
        c["notes"] = c["notes"].split(" Scheda BCT precedente")[0] + FAMILY_NOTE_2019.format(mass=mass, vol=vol)
    cat_path.write_text(json.dumps(cat, indent=1, ensure_ascii=False), encoding="utf-8")

    mf = PROJ / "images" / "manifest.csv"
    with mf.open(encoding="utf-8-sig", newline="") as fh:
        rows = [r for r in csv.reader(fh) if r and r[0] != ANT_ID]
    rows.append([ANT_ID, "NanoAvionics", ant["name"], ANT_IMG, ant["image"]["type"], ant["image"]["image_url"], ant["image"]["page_url"], RET, px,
                 ant["image"]["note"]])
    with mf.open("w", encoding="utf-8-sig", newline="") as fh:
        csv.writer(fh).writerows(rows)

    dm = PROJ / "datasheets" / "manifest.csv"
    with dm.open(encoding="utf-8-sig", newline="") as fh:
        drows = [r for r in csv.reader(fh) if r]
    files = {Path(ds_ant["file"]).name: (ds_ant, ANT_ID, ""), Path(ds_xact["file"]).name: (ds_xact, "", "; versione precedente della REV 1/2026, non collegata")}
    drows = [r for r in drows if r[0] not in files]
    for name, (d, member, extra) in files.items():
        drows.append([name, f"{d['document']} ({ORIGIN}{extra})", "", RET, str(d["bytes"]), member])
    with dm.open("w", encoding="utf-8-sig", newline="") as fh:
        csv.writer(fh).writerows(drows)
    print(f"antenna UHF NanoAvionics aggiunta, note XACT dalla scheda 2019; catalogo: {len(comps)} componenti")


if __name__ == "__main__":
    main()

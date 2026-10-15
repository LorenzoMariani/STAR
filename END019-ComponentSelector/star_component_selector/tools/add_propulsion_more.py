"""Aggiunge 10 sistemi di propulsione per CubeSat da documenti pubblici dei fornitori.

  dawn-cubedrive-0-8u, -2u      Dawn Aerospace CubeDrive (bipropellente N2O/propilene), scheda tecnica 2025 (pagina Resources del sito)
  dawn-cubedrive-8u             Dawn Aerospace CubeDrive 8U (in sviluppo), solo la brochure panoramica 2025
  cuaerospace-mpuc-1u/1-5u/2u   CU Aerospace MPUC (monopropellente verde H2O2-etanolo), datasheet luglio 2024
  cuaerospace-puc, -mvp, -fppt  CU Aerospace PUC 0.35U, MVP 0.93U, FPPT 1.7U, matrice prestazioni luglio 2023
  enpulsion-micro-r3            Enpulsion MICRO R3 configurazione 030 (FEEP a indio), datasheet DAT-00006_2.00 (marzo 2026)

Non aggiunti: Dawn B20 e B1 (sono solo propulsori: nessun serbatoio, quindi impulso totale non definito; il B1 si vende solo in lotti da 10),
Dawn SatDrive (sistemi su misura per satelliti da 30 a 500 kg), Accion TILE (nessun documento del fornitore, solo schede di aggregatori),
Benchmark Halcyon/Starling ed Exotrail ExoMG (nessun datasheet del fornitore raggiungibile).
uso: python tools/add_propulsion_more.py <cartella con dawn1.pdf (panoramica), dawn4.pdf (scheda CubeDrive), mpuc24.pdf, cuaprop.pdf, micro.pdf>
Idempotente. I valori derivati (propellente = massa piena - massa a secco) sono marcati nelle note.
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
DAWN_SHEET = "https://www.dawnaerospace.com/_files/ugd/cfd301_f8a4f032deb94cbb93b3e95b6155a1f6.pdf"
DAWN_OVER = "https://www.dawnaerospace.com/_files/ugd/ac85e2_650518c1f53940b5ab0c3cd5418f3c29.pdf"
DAWN_PAGE = "https://www.dawnaerospace.com/resources"
MPUC_URL = "https://cuaerospace.com/Portals/0/SiteContent/assets/PDF/MPUC-Datasheet-240729b.pdf"
CUA_URL = "https://cuaerospace.com/Portals/0/SiteContent/assets/PDF/CUA-Propulsion-Systems-230731-PDF.pdf"
ENP_URL = "https://www.enpulsion.com/wp-content/uploads/DataSheet_Micro_20260323.pdf"
SHAPE = {"type": "box", "axis": None, "basis": "image", "set": RET}
FIELDS = ("propellant", "thrust_mn_min", "thrust_mn_max", "isp_s", "propellant_mass_kg", "dry_mass_kg", "power_w_firing", "power_w_standby", "min_form_factor_u",
          "data_interfaces", "supply_voltage_ranges_v", "propulsion_type", "total_impulse_ns")

DOCS = {   # chiave -> (file locale, nome nella cartella, documento, url)
    "dawn_sheet": ("dawn4.pdf", "Dawn-Aerospace__CubeDrive-Spec-Sheet-2025.pdf", "Dawn Aerospace CubeDrive Spec-Sheet (PDF dalla pagina Resources, 2025)", DAWN_SHEET),
    "dawn_over": ("dawn1.pdf", "Dawn-Aerospace__CubeDrive-Overview-2025.pdf", "Dawn Aerospace CubeDrive, brochure panoramica (PDF dalla pagina Resources, 2025)", DAWN_OVER),
    "mpuc": ("mpuc24.pdf", "CU-Aerospace__MPUC-Datasheet-240729b.pdf", "CU Aerospace MPUC System datasheet (luglio 2024)", MPUC_URL),
    "cua": ("cuaprop.pdf", "CU-Aerospace__Propulsion-Systems-230731.pdf", "CU Aerospace, Performance Matrices for CUA Propulsion Systems (luglio 2023)", CUA_URL),
    "micro": ("micro.pdf", "Enpulsion__MICRO-R3-Datasheet-20260323.pdf", "Enpulsion MICRO R3 Datasheet, configurazione 030 (Doc. DAT-00006_2.00, marzo 2026)", ENP_URL),
}
IMAGES = {   # nome PNG -> (documento, xref, venditore, titolo, pagina)
    "Dawn-CubeDrive-0-8U.png": ("dawn_sheet", 91, "Dawn Aerospace", "CubeDrive 0.8U", DAWN_PAGE),
    "CU-Aerospace-MPUC.png": ("mpuc", 32, "CU Aerospace", "MPUC (disegno della versione 1U con testa del propulsore)", MPUC_URL),
    "Enpulsion-MICRO-R3.png": ("micro", 402, "Enpulsion", "MICRO R3", ENP_URL),
}


def pdf_image(pdf, xref):
    d = pymupdf.open(pdf)
    pix = pymupdf.Pixmap(d, xref)
    if pix.n > 3:
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def specs(**kw):
    bad = set(kw) - set(FIELDS)
    assert not bad, bad
    return {k: kw.get(k) for k in FIELDS}


def main():
    work = Path(sys.argv[1])
    cat_path = PROJ / "data" / "catalog.json"
    cat = json.loads(cat_path.read_text(encoding="utf-8"))
    comps = cat["components"]

    ds = {}
    for key, (src, name, doc, url) in DOCS.items():
        f = "datasheets/" + short_name(name)
        shutil.copyfile(work / src, PROJ / f)
        ds[key] = {"file": f, "document": doc, "source_url": url, "retrieved": RET, "bytes": (PROJ / f).stat().st_size}
    px = {}
    for name, (key, xref, vendor, title, page) in IMAGES.items():
        im = pdf_image(work / DOCS[key][0], xref)
        meta = PngInfo()
        for k, v in (("Title", f"{vendor} {title}"), ("Author", vendor), ("Source", DOCS[key][3]), ("Description", f"Propulsione CubeSat. Documento di origine: {DOCS[key][3]}. Scaricata il {RET}."), ("Copyright", NOTICE)):
            meta.add_text(k, v)
        im.save(PROJ / "images" / name, optimize=True, pnginfo=meta)
        px[name] = f"{im.size[0]}x{im.size[1]}"

    def image(name, shared=None):
        key = IMAGES[name][0]
        d = {"file": "images/" + name, "image_url": DOCS[key][3] + ("" if key == "micro" else ""), "page_url": IMAGES[name][4], "type": "estratta dal datasheet PDF", "retrieved": RET}
        if shared:
            d["note"] = shared
        return d

    def src(key):
        return {"url": DOCS[key][3], "document": DOCS[key][2], "retrieved": RET, **VERIFIED}

    cd_img = "Foto del CubeDrive 0.8U (unico modulo fotografato nel documento), condivisa con le altre taglie della famiglia."
    cd_note = ("Bipropellente verde N2O (ossido di diazoto) + propilene, auto-pressurizzato (nessuna pompa ne' pressurante), serbatoi stampati in 3D in Inconel, con propulsore B1, valvole, "
               "strumenti di monitoraggio e elettronica di controllo. Bus dati CAN (altri protocolli su richiesta); alimentazione digitale 5-5.2 V e attuatori 14 V non regolati. "
               "Le potenze di valvole e accensione sono dichiarate solo per il propulsore B1 (valvola 17.5 W per 15 ms di apertura e 0.75 W di tenuta, accenditore 6.4 W al massimo per 50 ms) "
               "e non per il modulo: potenza del modulo lasciata non dichiarata. Isp non dichiarato per il modulo (il solo B1 dichiara >=248 s): lasciato null. ")
    mp_note = ("Datasheet luglio 2024: sistema a monopropellente verde (CUA monopropellant formulazione 10 'CMP-X', H2O2-etanolo, temperatura di fiamma circa 950 C), spinto da gas inerte, "
               "spinta 230 mN, portata 132 mg/s, Isp 178 s (media sulla vita; fino a 188 s a 230 mN in prova al banco), potenza nominale 3 W, 'prevista' da hardware precedente. "
               "TRL 6 per la testa del propulsore, 4 per il sistema integrato 1.5U. Il documento avverte che non va usato per il progetto ma solo come informazione e che le specifiche "
               "possono cambiare senza preavviso. Il volume e' del corpo del sistema senza la lunghezza della testa esterna del propulsore, che si assume alloggiata nella molla del deployer. "
               "Massa piena e propellente come dichiarati in tabella (massa piena = massa a secco + propellente). ")
    new = [
        {"id": "dawn-cubedrive-0-8u", "category": "propulsion", "vendor": "Dawn Aerospace", "name": "CubeDrive 0.8U (bipropellant, 400 N s)", "family": "dawn-cubedrive", "mass_kg": 1.25, "power_w": None, "volume_u": 0.8,
         "notes": (cd_note + "0.8U: in orbita (9 sistemi in orbita e 20+ ordinati secondo la brochure panoramica: non sono missioni, eredita' di volo non dichiarata), 1 propulsore B1, spinta 0.44-1.15 N, impulso minimo 68 mN s (bipropellente) e 0.48 mN s (gas freddo), "
                   "impulso totale 400 N s, massa a secco/a pieno carico 1051 g / 1250 g, 80 x 96 x 96 mm. Propellente 0.199 kg DERIVATO (1250 - 1051 g), non dichiarato. "
                   "Altre schede e pagine Dawn riportano valori diversi per lo stesso modulo (405 o 425 N s, 970-1080 g a secco): si usa solo il documento scaricato."),
         "source": src("dawn_sheet"),
         "specs": specs(propellant="nitrous oxide + propylene", thrust_mn_min=440.0, thrust_mn_max=1150.0, propellant_mass_kg=0.199, dry_mass_kg=1.051,
                        data_interfaces=["CAN"], supply_voltage_ranges_v=[[5.0, 5.2], [14.0, 14.0]], propulsion_type="bipropellant", total_impulse_ns=400.0),
         "dimensions": {"mm": [80, 96, 96], "basis": "declared", "note": "Scheda Dawn CubeDrive: 80 x 96 x 96 mm."},
         "image": image("Dawn-CubeDrive-0-8U.png"), "datasheet": dict(ds["dawn_sheet"]), "shape": dict(SHAPE)},
        {"id": "dawn-cubedrive-2u", "category": "propulsion", "vendor": "Dawn Aerospace", "name": "CubeDrive 2U (bipropellant, 1500 N s)", "family": "dawn-cubedrive", "mass_kg": 2.75, "power_w": None, "volume_u": 2.0,
         "notes": (cd_note + "2U: in qualificazione (non ancora in orbita), spinta e impulso minimo non dichiarati per il 2U, impulso totale 1500 N s, massa a secco/a pieno carico 2000 g / 2750 g, 200 x 96 x 96 mm. "
                   "Spinta del propulsore B1 (0.44-1.15 N) dichiarata solo per il modulo 0.8U: lasciata non dichiarata qui. Propellente 0.750 kg DERIVATO (2750 - 2000 g)."),
         "source": src("dawn_sheet"),
         "specs": specs(propellant="nitrous oxide + propylene", propellant_mass_kg=0.75, dry_mass_kg=2.0, data_interfaces=["CAN"], supply_voltage_ranges_v=[[5.0, 5.2], [14.0, 14.0]],
                        propulsion_type="bipropellant", total_impulse_ns=1500.0),
         "dimensions": {"mm": [200, 96, 96], "basis": "declared", "note": "Scheda Dawn CubeDrive: 200 x 96 x 96 mm."},
         "image": image("Dawn-CubeDrive-0-8U.png", cd_img), "datasheet": dict(ds["dawn_sheet"]), "shape": dict(SHAPE)},
        {"id": "dawn-cubedrive-8u", "category": "propulsion", "vendor": "Dawn Aerospace", "name": "CubeDrive 8U (bipropellant, 3500 N s)", "family": "dawn-cubedrive", "mass_kg": 7.9, "power_w": None, "volume_u": 8.0,
         "notes": ("Brochure panoramica 2025 (non la scheda tecnica): modulo CubeDrive 8U 'in sviluppo, disponibile nel 2026', 4 propulsori da 1 N, impulso totale 3500 N s, "
                   "massa a secco/a pieno carico 6 kg / 7.9 kg. Dimensioni, spinta totale, Isp, alimentazione e propellente non dichiarati nel documento: lasciati null. "
                   "Bipropellente N2O + propilene, auto-pressurizzato. Prodotto non ancora disponibile alla data del documento."),
         "source": src("dawn_over"),
         "specs": specs(propellant="nitrous oxide + propylene", dry_mass_kg=6.0, propulsion_type="bipropellant", total_impulse_ns=3500.0),
         "dimensions": None,
         "image": image("Dawn-CubeDrive-0-8U.png", cd_img), "datasheet": dict(ds["dawn_over"]), "shape": dict(SHAPE)},
        {"id": "cuaerospace-mpuc-1u", "category": "propulsion", "vendor": "CU Aerospace", "name": "MPUC 1U (green monopropellant, 740 N s)", "family": "cuaerospace-mpuc", "mass_kg": 1.774, "power_w": None, "volume_u": 1.0,
         "notes": (mp_note + "1U: volume del corpo 1000 cm3, impulso totale 740 N s, propellente 424 g, massa a secco 1350 g, massa piena 1774 g. Inviluppo di progetto 1U: corpo 10.2 x 9.5 x 9.5 cm piu' 5 cm di testa del propulsore "
                   "(dimensioni dichiarate qui senza la testa; il prodotto di 10.2 x 9.5 x 9.5 cm, 921 cm3, non coincide con i 1000 cm3 dichiarati)."),
         "source": src("mpuc"),
         "specs": specs(propellant="H2O2-ethanol (CMP-X)", thrust_mn_min=230.0, thrust_mn_max=230.0, isp_s=178.0, propellant_mass_kg=0.424, dry_mass_kg=1.35, power_w_firing=3.0,
                        propulsion_type="green_monoprop", total_impulse_ns=740.0),
         "dimensions": {"mm": [102, 95, 95], "basis": "declared", "note": "Datasheet MPUC luglio 2024, inviluppo di progetto 1U: corpo 10.2 x 9.5 x 9.5 cm, esclusa la testa del propulsore di 5 cm."},
         "image": image("CU-Aerospace-MPUC.png"), "datasheet": dict(ds["mpuc"]), "shape": dict(SHAPE)},
        {"id": "cuaerospace-mpuc-1-5u", "category": "propulsion", "vendor": "CU Aerospace", "name": "MPUC 1.5U (green monopropellant, 1407 N s)", "family": "cuaerospace-mpuc", "mass_kg": 2.446, "power_w": None, "volume_u": 1.5,
         "notes": (mp_note + "1.5U: volume del corpo 1500 cm3, impulso totale 1407 N s, propellente 805 g, massa a secco 1641 g, massa piena 2446 g. Dimensioni non dichiarate: lasciate null."),
         "source": src("mpuc"),
         "specs": specs(propellant="H2O2-ethanol (CMP-X)", thrust_mn_min=230.0, thrust_mn_max=230.0, isp_s=178.0, propellant_mass_kg=0.805, dry_mass_kg=1.641, power_w_firing=3.0,
                        propulsion_type="green_monoprop", total_impulse_ns=1407.0),
         "dimensions": None,
         "image": image("CU-Aerospace-MPUC.png", "Disegno della versione 1U, condiviso con le altre taglie della famiglia."), "datasheet": dict(ds["mpuc"]), "shape": dict(SHAPE)},
        {"id": "cuaerospace-mpuc-2u", "category": "propulsion", "vendor": "CU Aerospace", "name": "MPUC 2U (green monopropellant, 2122 N s)", "family": "cuaerospace-mpuc", "mass_kg": 3.25, "power_w": None, "volume_u": 2.0,
         "notes": (mp_note + "2U: volume del corpo 2000 cm3, impulso totale 2122 N s, propellente 1214 g, massa a secco 2036 g, massa piena 3250 g. Dimensioni non dichiarate: lasciate null."),
         "source": src("mpuc"),
         "specs": specs(propellant="H2O2-ethanol (CMP-X)", thrust_mn_min=230.0, thrust_mn_max=230.0, isp_s=178.0, propellant_mass_kg=1.214, dry_mass_kg=2.036, power_w_firing=3.0,
                        propulsion_type="green_monoprop", total_impulse_ns=2122.0),
         "dimensions": None,
         "image": image("CU-Aerospace-MPUC.png", "Disegno della versione 1U, condiviso con le altre taglie della famiglia."), "datasheet": dict(ds["mpuc"]), "shape": dict(SHAPE)},
        {"id": "cuaerospace-puc", "category": "propulsion", "vendor": "CU Aerospace", "name": "PUC 0.35U (micro-plasma, SO2)", "family": "cuaerospace-puc", "mass_kg": 0.718, "power_w": None, "volume_u": 0.35,
         "notes": ("Matrice prestazioni CU Aerospace luglio 2023 ('sistemi a gas caldo'): scarica a micro-plasma con SO2, volume del sistema 350 cm3 (serbatoio disponibile 219 cm3), potenza 15 W in spinta (10 W "
                   "con ciclo di lavoro medio), Isp 70 s, portata 6.5 mg/s, spinta 4.5 mN, impulso totale 184 N s, propellente 268 g, massa a secco 450 g, massa piena 718 g, spinta continua al massimo 20 min "
                   "(riposo 10 min), TRL 6. Il documento avverte che non va usato per il progetto ma solo come informazione. Dimensioni, interfacce e alimentazione non dichiarate. "
                   "Nessuna immagine nel documento."),
         "source": src("cua"),
         "specs": specs(propellant="SO2", thrust_mn_min=4.5, thrust_mn_max=4.5, isp_s=70.0, propellant_mass_kg=0.268, dry_mass_kg=0.45, power_w_firing=15.0, propulsion_type="warm_gas", total_impulse_ns=184.0),
         "dimensions": None, "datasheet": dict(ds["cua"])},
        {"id": "cuaerospace-mvp", "category": "propulsion", "vendor": "CU Aerospace", "name": "MVP 0.93U (micro-resistojet, Delrin)", "family": "cuaerospace-mvp", "mass_kg": 1.055, "power_w": None, "volume_u": 0.926,
         "notes": ("Matrice prestazioni CU Aerospace luglio 2023 ('sistemi a gas caldo'): micro-resistojet con fibra polimerica (Delrin), volume del sistema 926 cm3 (serbatoio disponibile 309 cm3), potenza 45 W in spinta "
                   "(13.5 W con ciclo di lavoro medio), Isp 66 s, portata 7.0 mg/s, spinta 4.5 mN, impulso totale 280 N s, propellente 433 g, massa a secco 622 g, massa piena 1055 g, spinta continua al massimo 3 min "
                   "(riposo 7 min), TRL 6. Il documento avverte che non va usato per il progetto ma solo come informazione. Dimensioni, interfacce e alimentazione non dichiarate. Nessuna immagine nel documento."),
         "source": src("cua"),
         "specs": specs(propellant="Delrin (polymer fiber)", thrust_mn_min=4.5, thrust_mn_max=4.5, isp_s=66.0, propellant_mass_kg=0.433, dry_mass_kg=0.622, power_w_firing=45.0, propulsion_type="warm_gas", total_impulse_ns=280.0),
         "dimensions": None, "datasheet": dict(ds["cua"])},
        {"id": "cuaerospace-fppt", "category": "propulsion", "vendor": "CU Aerospace", "name": "FPPT 1.7U (fiber-fed pulsed plasma, 24000 N s)", "family": "cuaerospace-fppt", "mass_kg": 3.03, "power_w": None, "volume_u": 1.719,
         "notes": ("Matrice prestazioni CU Aerospace luglio 2023 ('sistemi ad alto impulso totale'): propulsore al plasma pulsato alimentato a fibra di Teflon, volume del sistema 1719 cm3 (serbatoio disponibile 360 cm3), "
                   "potenza 32 W (a 1 Hz di frequenza d'impulso), energia del banco di condensatori 32 J, Isp 3200 s, portata 0.00265 mg/s, spinta 0.85 mN a 1 Hz, impulso totale 24000 N s, propellente 780 g, massa a secco "
                   "2250 g, massa piena 3030 g. Il documento avverte che non va usato per il progetto ma solo come informazione. La tabella unisce le celle di alcune righe tra MPUC e FPPT: i valori a 32 W e 32 J "
                   "sono attribuiti all'FPPT perche' sono gli unici dichiarati per la colonna. Dimensioni, interfacce e alimentazione non dichiarate. Nessuna immagine nel documento."),
         "source": src("cua"),
         "specs": specs(propellant="Teflon (fiber)", thrust_mn_min=0.85, thrust_mn_max=0.85, isp_s=3200.0, propellant_mass_kg=0.78, dry_mass_kg=2.25, power_w_firing=32.0, propulsion_type="pulsed_plasma", total_impulse_ns=24000.0),
         "dimensions": None, "datasheet": dict(ds["cua"])},
        {"id": "enpulsion-micro-r3", "category": "propulsion", "vendor": "Enpulsion", "name": "MICRO R3 (configuration 030)", "family": "enpulsion-micro", "mass_kg": 3.95, "power_w": None, "volume_u": 2.1,
         "notes": ("Datasheet DAT-00006_2.00 (marzo 2026): propulsore FEEP (emissione di campo) a indio con 4 emettitori, serbatoio da 1.25 kg di indio, configurazione impilata con la PPU sotto la testa con la stessa impronta. "
                   "Campo di spinta dinamico 0.5-1 mN (nominale 1 mN, garantito al 75% a fine vita), Isp 2700 s a 1 mN (intervallo 2700-3600 s; 2930 s al secondo punto garantito), impulso totale 26 kN s a 1 mN, "
                   "potenza di sistema 64-120 W (110 W alla spinta nominale con neutralizzatore), attesa a caldo 12-18 W (usati 110 W e 18 W, estremo superiore dichiarato per l'attesa), alimentazione 28 V, "
                   "interfaccia RS422/RS485. Massa a secco/a pieno carico con PPU 2.7 kg / 3.95 kg. Dimensioni esterne 140 x 120 x 126.5 mm senza sporgenze (131.5 mm con le sporgenze); volume del modulo con serbatoio 2.1 L. "
                   "Il modulo si fissa all'esterno del satellite. La spinta e' di millinewton: i tempi di manovra sono di mesi. "
                   "Coerenza dei valori: Isp x g0 x propellente = 2700 x 9.80665 x 1.25 = circa 33100 N s, piu' dei 26000 N s dichiarati; il datasheet non dice se parte del propellente non sia utilizzabile: "
                   "si usa il valore dichiarato (26 kN s) e la differenza resta non spiegata."),
         "source": src("micro"),
         "specs": specs(propellant="indium (solid)", thrust_mn_min=0.5, thrust_mn_max=1.0, isp_s=2700.0, propellant_mass_kg=1.25, dry_mass_kg=2.7, power_w_firing=110.0, power_w_standby=18.0,
                        data_interfaces=["RS-422", "RS-485"], supply_voltage_ranges_v=[[28.0, 28.0]], propulsion_type="feep", total_impulse_ns=26000.0),
         "dimensions": {"mm": [140, 120, 126.5], "basis": "declared", "note": "Datasheet Enpulsion MICRO R3, dimensioni esterne senza sporgenze (con sporgenze 140 x 120 x 131.5 mm)."},
         "image": image("Enpulsion-MICRO-R3.png"), "datasheet": dict(ds["micro"]), "shape": dict(SHAPE)},
    ]
    for c in new:
        if c["dimensions"] is None:
            del c["dimensions"]
    ids = {c["id"] for c in new}
    comps[:] = [c for c in comps if c["id"] not in ids]
    last = max(i for i, c in enumerate(comps) if c["category"] == "propulsion")
    comps[last + 1:last + 1] = new
    cat_path.write_text(json.dumps(cat, indent=1, ensure_ascii=False), encoding="utf-8")

    mf = PROJ / "images" / "manifest.csv"
    with mf.open(encoding="utf-8-sig", newline="") as fh:
        rows = [r for r in csv.reader(fh) if r and r[0] not in ids]
    for c in new:
        im = c.get("image")
        if not im:
            continue
        fname = Path(im["file"]).name
        rows.append([c["id"], c["vendor"], c["name"], fname, im["type"], im["image_url"], im["page_url"], im["retrieved"], px[fname], im.get("note", "")])
    with mf.open("w", encoding="utf-8-sig", newline="") as fh:
        csv.writer(fh).writerows(rows)

    dm = PROJ / "datasheets" / "manifest.csv"
    with dm.open(encoding="utf-8-sig", newline="") as fh:
        drows = [r for r in csv.reader(fh) if r]
    new_files = {Path(d["file"]).name for d in ds.values()}
    drows = [r for r in drows if r[0] not in new_files]
    for key, d in ds.items():
        members = " ".join(sorted(c["id"] for c in new if c["datasheet"]["file"] == d["file"]))
        drows.append([Path(d["file"]).name, d["document"], d["source_url"], RET, str(d["bytes"]), members])
    with dm.open("w", encoding="utf-8-sig", newline="") as fh:
        csv.writer(fh).writerows(drows)
    print(f"{len(new)} sistemi di propulsione aggiunti; catalogo: {len(comps)} componenti")


if __name__ == "__main__":
    main()

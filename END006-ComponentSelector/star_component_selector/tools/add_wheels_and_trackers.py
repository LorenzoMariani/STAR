"""Aggiunge 20 ruote di reazione e 3 star tracker da documenti pubblici dei fornitori.

Ruote: AAC RW400 (3 versioni) e RW222 (2), Astrofein (RW1 A e B, RW25, linea CubeSat RW35/RW90/RW100/RW150/RW250, linea SmallSat RWT150/RWT250),
       NewSpace NRWA-T005/T065/T2, Vectronic VRW-02 e VRW-1.
Star tracker: Sodern Auriga (testa ottica con baffle), Rocket Lab ST-16RT2 con baffle corto e con baffle grande (stessa scheda gia' in datasheets/).
Non aggiunti: CubeSpace CW0017/CW0162/CW0500/CW5000/CW40K, arcsec Sagitta e Twinkle, TY-Space (nessun documento del fornitore con valori), Tensor Tech (sfera e CMG: non sono ruote).

uso: python tools/add_wheels_and_trackers.py <cartella con rw400.pdf rw222.pdf astrofein.pdf nss_rw.pdf vrw1.pdf vrw02.pdf auriga8p.pdf>
Idempotente. Nessun valore e' stimato: i valori derivati sono marcati nelle note; massa e potenza non pubblicate restano null.
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
U = {"rw400": "https://www.aac-clyde.space/wp-content/uploads/2021/11/RW400.pdf",
     "rw222": "https://www.aac-clyde.space/wp-content/uploads/2023/02/RW222-1.pdf",
     "astrofein": "https://www.astrofein.com/wp-content/uploads/2023/04/ASTROFEIN-Reaction-Wheel-Family_20230425.pdf",
     "nss_rw": "https://www.cubesatshop.com/wp-content/uploads/2016/07/NewSpace-Reaction-Wheel_2021-10c.pdf",
     "vrw1": "https://www.vectronic-aerospace.com/wp-content/uploads/2020/03/VAS-VRW1-DS11.pdf",
     "vrw02": "https://www.vectronic-aerospace.com/wp-content/uploads/2020/03/VAS-VRW02-DS3.pdf",
     "auriga": "https://api.sodern.com/uploads/AURIGA_8_PAGE_a11f9a3724.pdf"}
DOC = {"rw400": "AAC Clyde Space RW400 reaction wheels datasheet (release 15 novembre 2021)",
       "rw222": "AAC Clyde Space RW222 reaction wheels datasheet (release 7 febbraio 2023)",
       "astrofein": "ASTROFEIN Reaction Wheel Family (25 aprile 2023)",
       "nss_rw": "NewSpace Systems Reaction Wheel datasheet 2021-10c (NRWA-T005, T065, T2)",
       "vrw1": "Vectronic Aerospace VRW-1 reaction wheel datasheet (VAS-VRW1-DS11)",
       "vrw02": "Vectronic Aerospace VRW-02 reaction wheel datasheet (VAS-VRW02-DS3)",
       "auriga": "Sodern AURIGA brochure (8 pagine)"}
FILES = {"rw400": "AAC-Clyde-Space__RW400-Reaction-Wheels.pdf", "rw222": "AAC-Clyde-Space__RW222-Reaction-Wheels.pdf", "astrofein": "ASTROFEIN__Reaction-Wheel-Family_20230425.pdf",
         "nss_rw": "NewSpace-Systems__NewSpace-Reaction-Wheel_2021-10c.pdf", "vrw1": "Vectronic__VAS-VRW1-DS11.pdf", "vrw02": "Vectronic__VAS-VRW02-DS3.pdf",
         "auriga": "Sodern__AURIGA-8-PAGE.pdf"}
SHAPE = {"type": "cylinder", "axis": None, "basis": "image", "set": RET}


def save_png(im, name, vendor, title, source, page, maxpx=900):
    im = im.convert("RGB")
    im.thumbnail((maxpx, maxpx))
    meta = PngInfo()
    for k, v in (("Title", f"{vendor} {title}"), ("Author", vendor), ("Source", source), ("Description", f"Componente per CubeSat. Pagina/documento di origine: {page}. Scaricata il {RET}."), ("Copyright", NOTICE)):
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
    by = {c["id"]: c for c in comps}
    rl = by["rocketlab-st16rt2"]

    ds = {}
    for key, fname in FILES.items():
        f = "datasheets/" + short_name(fname)
        shutil.copyfile(work / ("auriga8p.pdf" if key == "auriga" else f"{key}.pdf"), PROJ / f)
        ds[key] = {"file": f, "document": DOC[key], "source_url": U[key], "retrieved": RET, "bytes": (PROJ / f).stat().st_size}

    px = {}
    px["AAC-RW400.png"] = save_png(pdf_image(work / "rw400.pdf", 361).crop((60, 0, 350, 250)), "AAC-RW400.png", "AAC Clyde Space", "RW400", U["rw400"] + "#page=1", U["rw400"])
    px["AAC-RW222.png"] = save_png(pdf_image(work / "rw222.pdf", 314).crop((150, 100, 440, 300)), "AAC-RW222.png", "AAC Clyde Space", "RW222", U["rw222"] + "#page=1", U["rw222"])
    px["ASTROFEIN-RW.png"] = save_png(pdf_image(work / "astrofein.pdf", 17), "ASTROFEIN-RW.png", "ASTROFEIN", "Reaction Wheel Family", U["astrofein"] + "#page=1", U["astrofein"])
    px["NewSpace-NRWA.png"] = save_png(pdf_image(work / "nss_rw.pdf", 1425), "NewSpace-NRWA.png", "NewSpace Systems", "NRWA reaction wheel", U["nss_rw"] + "#page=1", U["nss_rw"])
    px["Vectronic-VRW02.png"] = save_png(pdf_image(work / "vrw02.pdf", 11), "Vectronic-VRW02.png", "Vectronic Aerospace", "VRW-02", U["vrw02"] + "#page=1", U["vrw02"])
    px["Sodern-AURIGA.png"] = save_png(pdf_image(work / "auriga8p.pdf", 335), "Sodern-AURIGA.png", "Sodern", "AURIGA", U["auriga"] + "#page=1", U["auriga"])

    def img(key, file, note=None, typ="estratta dal datasheet PDF"):
        d = {"file": "images/" + file, "image_url": U[key] + "#page=1", "page_url": U[key], "type": typ, "retrieved": RET}
        if note:
            d["note"] = note
        return d

    def wheel(cid, vendor, name, key, mass, dims, temp, tid, notes, specs, image, shape_axis=None, power_w=None):
        c = {"id": cid, "category": "reaction_wheel", "vendor": vendor, "name": name, "mass_kg": mass, "power_w": power_w, "temp_op_c": temp, "notes": notes,
             "source": {"url": U[key], "document": DOC[key], "retrieved": RET, **VERIFIED},
             "specs": {"momentum_mnms": None, "max_torque_mnm": None, "max_speed_rpm": None, "power_w_nominal": None, "power_w_peak": None, "supply_voltage_ranges_v": None, "data_interfaces": None, **specs},
             "dimensions": {"mm": dims, "basis": "declared", "note": f"{DOC[key]}."}, "datasheet": dict(ds[key]), "shape": {**SHAPE, "axis": shape_axis}}
        if tid is not None:
            c["tid_krad"] = tid
        if image:
            c["image"] = image
        return {k: v for k, v in c.items() if not (k == "power_w" and v is None)}

    new = []
    # --- AAC RW400: massa e momento nello stesso ordine del documento (197/210/375 g per 15/30/50 mN m s)
    for mom, mass in ((15, 0.197), (30, 0.21), (50, 0.375)):
        new.append(wheel(f"aac-rw400-{mom}", "AAC Clyde Space", f"RW400.{mom} reaction wheel", "rw400", mass, [50, 50, 27], [-40, 60], 36.0,
                         ("Per CubeSat 6U-12U. Momento +-15, +-30 o +-50 mN m s; massa 197 / 210 / 375 g riportata nello stesso ordine dei momenti. Coppia massima +-8 mN m (tabella; le caratteristiche "
                          "scrivono '>12 mN m in frenata'), 5000 giri/min, precisione di controllo +-1% del regime, 50 x 50 x 27 mm, alimentazione 4.5-5.25 V (5.0 tipica). Potenza: a vuoto <=75 mW, "
                          "nominale 1000 mW tipici, picco 1900 mW tipici e 15000 mW massimi (valori 'adattabili'); interfacce I2C e RS422 bidirezionale. Radiazioni '>36 krad (Si)' (limite inferiore), "
                          "-40..+60 C. Controllore interno 'fire-and-forget'."),
                         {"momentum_mnms": float(mom), "max_torque_mnm": 8.0, "max_speed_rpm": 5000, "power_w_nominal": 1.0, "power_w_peak": 1.9, "supply_voltage_ranges_v": [[4.5, 5.25]], "data_interfaces": ["I2C", "RS-422"]},
                         img("rw400", "AAC-RW400.png", note="Foto condivisa con le altre versioni RW400" if mom != 15 else None), shape_axis=2))
    # --- AAC RW222
    for mom in (3, 6):
        new.append(wheel(f"aac-rw222-{mom}0", "AAC Clyde Space", f"RW222.{mom}0 reaction wheel", "rw222", None, [25, 25, 15], [-20, 60], None,
                         ("Per CubeSat 1U-3U. Momento +-3.0 o +-6.0 mN m s, coppia massima 2 mN m, 25 x 25 x 15 mm, alimentazione 3.25-3.5 V (3.3 tipica), interfaccia I2C (altre su richiesta), "
                          "-20..+60 C. Il documento scrive massa 'TBC' e radiazioni 'TBC': non pubblicate. Velocita' massima '10000 / 15000' con unita' 'To be tested': non associata a una versione, "
                          "lasciata non dichiarata. Primo volo nel 2017."),
                         {"momentum_mnms": float(mom), "max_torque_mnm": 2.0, "supply_voltage_ranges_v": [[3.25, 3.5]], "data_interfaces": ["I2C"]},
                         img("rw222", "AAC-RW222.png", note="Foto condivisa con le altre versioni RW222" if mom != 3 else None), shape_axis=2))
    # --- Astrofein (la foto del documento non dice a quale modello appartenga)
    af_note = "Foto dal documento della famiglia ASTROFEIN: non indica a quale modello appartenga"
    af = [("rw1-a", "RW1 Type A", 0.58, 0.023, 16380, 0.024, [21, 21, 12], "1 anno di vita hardware; velocita' nominale 8000 giri/min, momento a 8000 giri/min"),
          ("rw1-b", "RW1 Type B", 0.1, 0.004, 16380, 0.012, [21, 21, 12], "1 anno di vita hardware; velocita' nominale 8000 giri/min, momento a 8000 giri/min"),
          ("rw25", "RW25", 30.0, 2.0, 5500, 0.2, [50, 50, 25], "2 (5) anni di vita hardware; velocita' nominale 5000 giri/min"),
          ("rw35", "RW35 (CubeSat line)", 100.0, 5.0, 5000, 0.5, [102, 102, 58], "5 anni di vita hardware; velocita' nominale 5000 giri/min; momento d'inerzia 1.9e-4 kg m2"),
          ("rw90", "RW90 (CubeSat line)", 350.0, 15.0, 7800, 0.9, [103, 101, 80], "7 anni di vita hardware; velocita' nominale 6000 giri/min, momento a 7800 giri/min; momento d'inerzia 4.2e-4 kg m2"),
          ("rw100", "RW100 (CubeSat line)", 400.0, 20.0, 7000, 0.8, [100, 100, 60], "7 anni di vita hardware; velocita' nominale 6000 giri/min; momento d'inerzia 6.52e-4 kg m2"),
          ("rw150", "RW150 (CubeSat line)", 1000.0, 30.0, 7080, 1.3, [150, 150, 60], "7 anni di vita hardware; velocita' nominale 6000 giri/min; momento d'inerzia 1.592e-3 kg m2"),
          ("rw250", "RW250 (CubeSat line)", 4000.0, 100.0, 5000, 2.7, [180, 180, 82], "7 anni di vita hardware; velocita' nominale 5000 giri/min; momento d'inerzia 7.65e-3 kg m2"),
          ("rwt150", "RWT150 (SmallSat line)", 1000.0, 100.0, 7080, 1.5, [150, 150, 60], "7 anni di vita hardware; velocita' nominale 6000 giri/min; momento d'inerzia 1.592e-3 kg m2"),
          ("rwt250", "RWT250 (SmallSat line)", 4000.0, 300.0, 5000, 3.0, [200, 200, 100], "7 anni di vita hardware; velocita' nominale 5000 giri/min; momento d'inerzia 7.65e-3 kg m2")]
    for i, (suffix, name, mom, torque, vmax, mass, dims, extra) in enumerate(af):
        new.append(wheel(f"astrofein-{suffix}", "ASTROFEIN", name, "astrofein", mass, dims, [-20, 50], None,
                         (f"Documento ASTROFEIN (famiglia di ruote): momento {mom:g} mN m s, coppia NOMINALE {torque:g} mN m (si riporta nel campo della coppia massima), velocita' massima {vmax} giri/min, "
                          f"massa '<={mass * 1000:g} g' (limite superiore), {dims[0]} x {dims[1]} x {dims[2]} mm, -20..+50 C; {extra}. Potenza, tensioni e interfacce non pubblicate nel documento."),
                         {"momentum_mnms": mom, "max_torque_mnm": torque, "max_speed_rpm": vmax},
                         img("astrofein", "ASTROFEIN-RW.png", note=af_note if i == 0 else "Foto condivisa con le altre voci ASTROFEIN: " + af_note), shape_axis=2))
    # --- NewSpace NRWA
    new.append(wheel("newspace-nrwa-t005", "NewSpace Systems", "NRWA-T005 reaction wheel (wheel only)", "nss_rw", 0.5, [65, 65, 65], [-30, 60], 10.0,
                     ("Datasheet NewSpace 2021-10c: momento massimo 0.05 N m s (a 10 mN m), coppia massima 10 mN m, +-9000 giri/min, ruota 65 x 65 x 65 mm e massa 500 g 'solo ruota': l'elettronica "
                      "di controllo e' un'unita' separata di 100 x 100 x 75 mm (massa non pubblicata, non inclusa). Consumo '40 mA per mN m' (non in W). Alimentazione 5 V o 12-20 V, "
                      "RS-422 o UART TTL, connettore D a 9 pin (potenza) e HD a 26 pin (dati), 4 fori M3. Radiazioni 10 krad a livello di componente; temperatura di accettazione -30..+60 C."),
                     {"momentum_mnms": 50.0, "max_torque_mnm": 10.0, "max_speed_rpm": 9000, "supply_voltage_ranges_v": [[5, 5], [12, 20]], "data_interfaces": ["RS-422", "TTL UART"]},
                     img("nss_rw", "NewSpace-NRWA.png", note="Foto del documento NewSpace: non indica a quale modello appartenga"), shape_axis=0))
    new.append(wheel("newspace-nrwa-t065", "NewSpace Systems", "NRWA-T065 reaction wheel", "nss_rw", 1.55, [102, 102, 105], [-20, 60], 10.0,
                     ("Datasheet NewSpace 2021-10c: momento massimo 0.65 N m s (a 20 mN m), coppia massima 20 mN m, +-9000 giri/min, 102 x 102 x 105 mm, 1.55 kg, elettronica interna, consumo '40 mA per mN m', "
                      "28 V non regolati, RS-422, connettore D a 9 pin, 4 fori M5, 10 krad a livello di componente, -20..+60 C. Ruota di classe SmallSat."),
                     {"momentum_mnms": 650.0, "max_torque_mnm": 20.0, "max_speed_rpm": 9000, "supply_voltage_ranges_v": [[28, 28]], "data_interfaces": ["RS-422"]},
                     img("nss_rw", "NewSpace-NRWA.png", note="Foto condivisa con le altre voci NewSpace NRWA"), shape_axis=2))
    new.append(wheel("newspace-nrwa-t2", "NewSpace Systems", "NRWA-T2 reaction wheel", "nss_rw", 2.55, [150, 150, 75], [-20, 60], 10.0,
                     ("Datasheet NewSpace 2021-10c: momento massimo 1.6 N m s, coppia massima 94 mN m, +-3050 giri/min, 150 x 150 x 75 mm, 2.55 kg, elettronica interna, consumo '12 mA per mN m', "
                      "28 V non regolati, RS-422, connettore D a 9 pin, 4 fori M5, 10 krad a livello di componente, -20..+60 C. Ruota di classe SmallSat."),
                     {"momentum_mnms": 1600.0, "max_torque_mnm": 94.0, "max_speed_rpm": 3050, "supply_voltage_ranges_v": [[28, 28]], "data_interfaces": ["RS-422"]},
                     img("nss_rw", "NewSpace-NRWA.png", note="Foto condivisa con le altre voci NewSpace NRWA"), shape_axis=2))
    # --- Vectronic
    vnote = ("Datasheet Vectronic: {mom}; coppia massima +-{tq} mN m; velocita' nominale +-5000 e massima +-6500 giri/min; {dims} mm, {mass} kg; potenza '<1.0 W' a 0 giri/min, '<3.0 W' a 4000 giri/min "
             "(riportata come nominale) e '<25 W' alla coppia massima (riportata come picco); {itf}; connettore {conn}; vita in orbita '>45000 ore'; -20..+70 C; radiazioni '>20 krad' (limite inferiore); "
             "vibrazioni 15 g rms; sbilanciamento statico/dinamico <1 g mm / 80 g mm2. Tensione di alimentazione non pubblicata.")
    new.append(wheel("vectronic-vrw-02", "Vectronic Aerospace", "VRW-02 reaction wheel", "vrw02", 1.0, [70, 70, 48], [-20, 70], 20.0,
                     vnote.format(mom="momento 0.2 N m s", tq=20, dims="70 x 70 x 48", mass="1.0", itf="interfacce RS422, RS485 e CAN", conn="MDM-25"),
                     {"momentum_mnms": 200.0, "max_torque_mnm": 20.0, "max_speed_rpm": 6500, "power_w_nominal": 3.0, "power_w_peak": 25.0, "data_interfaces": ["RS-422", "RS-485", "CAN"]},
                     img("vrw02", "Vectronic-VRW02.png"), shape_axis=2))
    new.append(wheel("vectronic-vrw-1", "Vectronic Aerospace", "VRW-1 reaction wheel", "vrw1", 1.8, [115, 115, 77], [-20, 70], 20.0,
                     vnote.format(mom="momento 1.0 N m s", tq=25, dims="115 x 115 x 77", mass="1.8", itf="interfaccia RS422 / RS485", conn="MDM-9"),
                     {"momentum_mnms": 1000.0, "max_torque_mnm": 25.0, "max_speed_rpm": 6500, "power_w_nominal": 3.0, "power_w_peak": 25.0, "data_interfaces": ["RS-422", "RS-485"]},
                     None, shape_axis=2))

    # --- star tracker
    st_shape = {"type": "lens_box", "axis": 2, "basis": "image", "set": RET}
    new.append({"id": "sodern-auriga-oh", "category": "star_tracker", "vendor": "Sodern", "name": "AURIGA optical head with 35 deg baffle", "mass_kg": 0.225, "power_w": 0.8, "temp_op_c": [-20, 40],
                "notes": ("Brochure Sodern (8 pagine): testa ottica (OH) con baffle da 35 gradi di esclusione solare: 66 x 59 x 94 mm, 225 g, 0.8 W per testa. Errore spaziale a bassa frequenza (campo di vista) "
                          "XY / Z a 3 sigma: 9 / 51 arcsec; a alta frequenza (pixel) 6.6 / 38 arcsec (si riporta il primo); bias nel caso peggiore 0.017 gradi; velocita' angolare in tracciamento "
                          "fino a 3 gradi/s. Aggiornamento: 'fino a 10 Hz' con piu' teste unite (limite superiore). Il campo di vista della testa non e' pubblicato. Per l'attitudine serve l'unita' "
                          "elettronica (EU), esclusa: 91 x 117 x 25 mm, 315 g, 2.1 W piu' 0.8 W per testa, RS-422 UART, 5 V, fino a 3 teste via SpaceWire (in alternativa il software gira sull'OBC). "
                          "Vita 10 anni in LEO (400-1200 km), 15 in GEO; temperatura operativa -20/+40 C; piu' di 1500 unita' lanciate dal 2019. Opzione baffle da 26 gradi (60 x 66 x 122 mm, <250 g, "
                          "FM nel 2025) non catalogata."),
                "source": {"url": U["auriga"], "document": DOC["auriga"], "retrieved": RET, **VERIFIED},
                "specs": {"accuracy_cross_arcsec": 9.0, "accuracy_roll_arcsec": 51.0, "accuracy_basis": "3-sigma", "update_rate_hz": 10.0, "fov_deg": None, "data_interfaces": ["SpaceWire", "RS-422 UART"],
                          "supply_voltage_ranges_v": [[5, 5]]},
                "dimensions": {"mm": [66, 59, 94], "basis": "declared", "note": "Brochure Sodern: 66 x 59 x 94 mm (altezza compreso il baffle)."},
                "image": img("auriga", "Sodern-AURIGA.png"), "datasheet": dict(ds["auriga"]), "shape": dict(st_shape)})
    for cid, name, mass, dims, fov, sun, note_dim in (
            ("rocketlab-st16rt2-short-baffle", "ST-16RT2 star tracker with short baffle", 0.185, [62, 56, 68], [16.0, 16.0], 34, "Scheda Rocket Lab: 62 x 56 x 68 mm con baffle corto."),
            ("rocketlab-st16rt2-large-baffle", "ST-16RT2 star tracker with large baffle", 0.235, [99, 99, 120], [15.0, 20.0], 22, "Scheda Rocket Lab: 99 mm di diametro x 120 mm con baffle grande (ingombro DERIVATO: scatola 99 x 99 x 120).")):
        c = json.loads(json.dumps(rl))
        c.update({"id": cid, "name": name, "mass_kg": mass, "volume_u": None})
        c["price"] = {"amount": 140000, "currency": "USD", "as_of": "scheda non datata (letta il 2026-10-13)"}
        c["specs"]["fov_deg"] = fov
        c["dimensions"] = {"mm": dims, "basis": "declared" if cid.endswith("short-baffle") else "derived", "note": note_dim}
        c["source"] = {**rl["source"], "retrieved": RET}
        c["notes"] = (f"Stessa scheda Rocket Lab ST-16RT2 (vedi rocketlab-st16rt2), variante con baffle {'corto' if 'short' in cid else 'grande'}: {int(mass * 1000)} g, esclusione solare "
                      f"{sun} gradi dal Sole alla boresight, US$140000. Campo di vista {'8 gradi di semiampiezza (16 gradi pieno, DERIVATO)' if 'short' in cid else '7.5 x 10 gradi di semiampiezza (15 x 20 pieno)'}. "
                      "Accuratezza, aggiornamento, tensioni e interfacce come la versione senza baffle.")
        c["image"] = {**rl["image"], "note": "Foto condivisa con le altre varianti/componenti della stessa famiglia: rocketlab-st16rt2"}
        c["shape"] = {"type": "lens_box", "axis": 2, "basis": "image", "set": RET}
        new.append(c)

    ids = {c["id"] for c in new}
    comps[:] = [c for c in comps if c["id"] not in ids]
    last_rw = max(i for i, c in enumerate(comps) if c["category"] == "reaction_wheel")
    rw = [c for c in new if c["category"] == "reaction_wheel"]
    comps[last_rw + 1:last_rw + 1] = rw
    last_st = max(i for i, c in enumerate(comps) if c["category"] == "star_tracker")
    comps[last_st + 1:last_st + 1] = [c for c in new if c["category"] == "star_tracker"]
    cat_path.write_text(json.dumps(cat, indent=1, ensure_ascii=False), encoding="utf-8")

    # manifest delle immagini e dei datasheet
    mf = PROJ / "images" / "manifest.csv"
    with mf.open(encoding="utf-8-sig", newline="") as fh:
        rows = [r for r in csv.reader(fh) if r and r[0] not in ids]
    for c in new:
        im = c.get("image")
        if not im:
            rows.append([c["id"], c["vendor"], c["name"], "", "nessuna immagine trovata", "", "", RET, "", "Nessuna foto del prodotto nel datasheet."])
            continue
        fname = Path(im["file"]).name
        rows.append([c["id"], c["vendor"], c["name"], fname, im["type"], im["image_url"], im["page_url"], im["retrieved"], px.get(fname, "da immagine esistente"), im.get("note", "")])
    with mf.open("w", encoding="utf-8-sig", newline="") as fh:
        csv.writer(fh).writerows(rows)
    dm = PROJ / "datasheets" / "manifest.csv"
    with dm.open(encoding="utf-8-sig", newline="") as fh:
        drows = list(csv.reader(fh))
    new_files = {Path(d["file"]).name for d in ds.values()}
    drows = [r for r in drows if r[0] not in new_files]
    rl_file = Path(rl["datasheet"]["file"]).name
    for r in drows[1:]:
        r[5] = " ".join(x for x in r[5].split() if x not in ids)
        if r[0] == rl_file:
            r[5] = (r[5] + " rocketlab-st16rt2-short-baffle rocketlab-st16rt2-large-baffle").strip()
    members = {}
    for c in new:
        for k in ds:
            if c.get("datasheet", {}).get("file") == ds[k]["file"]:
                members.setdefault(k, []).append(c["id"])
    for key, d in ds.items():
        drows.append([Path(d["file"]).name, d["document"], d["source_url"], RET, str(d["bytes"]), " ".join(members.get(key, []))])
    with dm.open("w", encoding="utf-8-sig", newline="") as fh:
        csv.writer(fh).writerows(drows)
    print(f"{len(new)} componenti aggiunti ({len(rw)} ruote, {len(new) - len(rw)} star tracker); catalogo: {len(comps)} componenti")


if __name__ == "__main__":
    main()

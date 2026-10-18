"""Aggiunge al catalogo le strutture 1U e le categorie `magnetorquer` e `reaction_wheel` (attuatori di assetto per CubeSat).
Tutti i valori vengono da documenti pubblici dei fornitori (o da pagine di prodotto dove indicato nelle note); `null` = non dichiarato.
Idempotente: rieseguirlo sostituisce le voci con gli stessi id.

    python tools/add_attitude_and_1u.py [cartella-del-progetto]
"""
import json
import sys
from pathlib import Path

PROJ = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
RET = "2026-10-14"
METHOD = "trascritto da documento pubblico del fornitore; da controllare manualmente"
METHOD_PAGE = "trascritto da una pagina di prodotto pubblica; da controllare manualmente"
CDS = ("max_total_mass_kg dalla CubeSat Design Specification Rev. 14.1, Table 1 (https://www.nasa.gov/wp-content/uploads/2018/01/"
       "cubesatdesignspecificationrev14_12022-02-09.pdf), non dal fornitore. ")


def comp(cid, category, vendor, name, mass, url, doc, specs, notes, dims=None, dim_note="", trl=None, heritage=None, tid=None, temp=None, family=None,
         method=METHOD, price=None, power=None):
    rec = {"id": cid, "category": category, "vendor": vendor, "name": name, "family": family, "mass_kg": mass, "power_w": power, "price": price,
           "trl": trl, "flight_heritage": heritage, "tid_krad": tid, "temp_op_c": temp, "notes": notes,
           "source": {"url": url, "document": doc, "retrieved": RET, "verified": False, "method": method}, "specs": specs}
    if dims:
        rec["dimensions"] = {"mm": dims, "basis": "declared", "note": dim_note}
    return {k: v for k, v in rec.items() if v is not None or k in ("mass_kg", "power_w")}


def structure(**kw):
    return {"form_factor_u": 1.0, "max_total_mass_kg": 2.0, "internal_volume_u": None, "panel_faces": None, **kw}


def mtq(**kw):
    base = dict(axes=None, magnetic_moment_am2=None, power_w_max=None, supply_voltage_ranges_v=None, data_interfaces=None)
    base.update(kw)
    return base


def rw(**kw):
    base = dict(momentum_mnms=None, max_torque_mnm=None, max_speed_rpm=None, power_w_nominal=None, power_w_peak=None, supply_voltage_ranges_v=None, data_interfaces=None)
    base.update(kw)
    return base


STRUCTURES = [
    comp("isis-structure-1u", "structure", "ISISpace", "1-Unit CubeSat Structure", 0.2,
         "https://www.cubesatshop.com/wp-content/uploads/2016/06/ISIS-CubeSat-Structures-Brochure-v1.pdf", "ISIS CubeSat Structures brochure v1",
         structure(), CDS + "Massa 200 g = struttura primaria (100 g) piu' secondaria, come per le altre strutture ISIS del catalogo; ingombro esterno 100 x 100 x 113.5 mm; volo dal 2012. "
         "Prezzo non pubblicato.", dims=[100.0, 100.0, 113.5], dim_note="Brochure ISIS, 'Outside Envelope'.", heritage=None, family="isis-structure"),
    comp("endurosat-structure-1u", "structure", "EnduroSat", "1U CubeSat Structure", 0.12,
         "https://endurosat.com/products/1u-cubesat-structure", "Pagina prodotto EnduroSat 1U CubeSat Structure (consultata 2026-10-14)",
         structure(), CDS + "Massa 120 g comprensiva di viti, due kill switch e due molle di separazione; 100 x 100 x 113.5 mm; alluminio 6082 anodizzato duro; compatibile PC/104 e CubeSat Standard. "
         "Un catalogo di terzi riporta 98 g, probabilmente senza kill switch e molle: qui si usa il valore del fornitore. Il datasheet e' scaricabile dalla pagina del prodotto.",
         dims=[100.0, 100.0, 113.5], dim_note="Pagina prodotto EnduroSat.", method=METHOD_PAGE, family="endurosat-structure"),
    comp("spacemanic-structure-1u", "structure", "Spacemanic", "1U CubeSat Structure", 0.115,
         "https://www.spacemanic.com/files/datasheet/datasheet-structure.pdf", "Spacemanic CubeSat structure datasheet",
         structure(), CDS + "Massa 115 g, ingombro esterno 100 x 100 x 113.5 mm e interno 98.4 mm per lato; materiali alluminio, titanio e acciaio inox. Il documento non era scaricabile dal programma di raccolta: "
         "valori letti da un riassunto della ricerca, da ricontrollare sul datasheet.", dims=[100.0, 100.0, 113.5], dim_note="Datasheet Spacemanic, ingombro esterno.", method=METHOD_PAGE,
         family="spacemanic-structure"),
]

MAGNETORQUERS = [
    comp("isis-imtq", "magnetorquer", "ISISpace", "iMTQ Magnetorquer Board", 0.196,
         "https://www.cubesatshop.com/wp-content/uploads/2016/06/iMTQ-Brochure-v1.pdf", "ISIS Magnetorquer Board (iMTQ) brochure v1",
         {"magnetorquer_type": "board"} | mtq(axes=3, magnetic_moment_am2=0.2, power_w_max=1.2, supply_voltage_ranges_v=[[5.0, 5.0]], data_interfaces=["I2C"]),
         "Scheda a tre assi (due barre e una bobina in aria) con magnetometro, sensori di corrente e algoritmo di detumbling: 0.2 A m2 nominali per asse a 20 C e 5 V, errore di inviluppo <5%, "
         "massa 196 g, 95.9 x 90.1 x 17 mm, 5 V, consumo 175 mW senza attuazione e <1.2 W con attuazione sui tre assi (usato 1.2 W), I2C o controllo analogico/PWM, -40..+70 C. "
         "Adatta a smorzare la rotazione fino a un 12U; puo' scaricare le ruote di reazione. Volo dal 2013.",
         dims=[95.9, 90.1, 17.0], dim_note="Brochure ISIS iMTQ.", temp=[-40, 70], family="isis-imtq"),
    comp("gomspace-nanotorque-gst-600-mk2", "magnetorquer", "GomSpace", "NanoTorque GST-600 Mk2", 0.18,
         "https://gomspace.com/wp-content/uploads/2025/09/gs-ds-NanoTorqueGST600mk2-1062432-2-EXT.pdf", "GomSpace NanoTorque GST-600 Mk2 datasheet DS 1062432 rev 2.0 (17 febbraio 2025)",
         {"magnetorquer_type": "board"} | mtq(axes=3, magnetic_moment_am2=0.4, power_w_max=2.15, supply_voltage_ranges_v=[[3.3, 5.5]], data_interfaces=["I2C"]),
         "Magnetorquer a tre assi con sensore di temperatura TMP100. Il datasheet riporta nella tabella con colonne Min/Typ/Max momento di dipolo 0.34 e 0.50 A m2 sull'asse Z e 0.23 e 0.40 A m2 sugli assi X e Y a 20 C "
         "(la colonna di ciascun valore non e' leggibile nel testo): usato il piu' basso dei valori maggiori, 0.40 A m2; sull'asse Z 0.50. Potenza massima 900 mW sull'asse Z e 625 mW su ciascuno di X e Y: "
         "2.15 W e' la loro SOMMA, derivata, non dichiarata. Ampiezza PWM raccomandata +-3.3..+-5.5 V, massa 180 g, 90.5 x 96.9 x 17.2 mm, I2C, -35..+70 C.",
         dims=[90.5, 96.9, 17.2], dim_note="Datasheet GomSpace GST-600 Mk2.", temp=[-35, 70], family="gomspace-nanotorque"),
]
CR = [  # (variante, momento A m2 minimo a 5 V, massa g, lunghezza mm, sezione mm)
    ("cr0002", 0.2, 16.5, 47, 10.5), ("cr0003", 0.3, 23.0, 59, 10.5), ("cr0004", 0.4, 23.0, 59, 10.5),
    ("cr0010", 1.0, 37.0, 92, 10.5), ("cr0012", 1.2, 45.0, 122, 13.0), ("cr0020", 2.0, 54.0, 152, 13.0)]
for v, m, g, ln, sec in CR:
    MAGNETORQUERS.append(comp(
        f"cubespace-cubetorquer-{v}", "magnetorquer", "CubeSpace", f"CubeTorquer {v.upper()} (rod)", g / 1000,
        "https://www.cubesatshop.com/product/magnetorquer-rods/", "Pagina prodotto CubeSatShop 'Magnetorquer Rods (CR0002-CR0020)' di CubeSpace (consultata 2026-10-14)",
        {"magnetorquer_type": "rod"} | mtq(axes=1, magnetic_moment_am2=m),
        f"Barra magnetica a un asse: momento magnetico minimo {m:g} A m2 a 5 V, massa {g:g} g, {ln} x {sec:g} x {sec:g} mm, tensione massima 5 V, linearita' 2.5%, vibrazioni 14.16 g RMS. "
        "Corrente e potenza non sono pubblicate (option sheet e ICD su richiesta): potenza non dichiarata. Per tre assi servono tre barre. La pagina non assegna in modo chiaro i dati delle varianti CR0005 e CR0006: omesse.",
        dims=[float(ln), sec, sec], dim_note="Pagina prodotto CubeSatShop (lunghezza x larghezza x altezza).", method=METHOD_PAGE, family="cubespace-cubetorquer"))

WHEELS = [
    comp("aac-rw210-15", "reaction_wheel", "Hyperion Technologies (AAC Hyperion)", "RW210.15 reaction wheel", 0.021,
         "https://www.aac-clyde.space/wp-content/uploads/2021/11/RW210.pdf", "AAC Clyde Space RW210 Reaction Wheels datasheet (release 15 novembre 2021)",
         rw(momentum_mnms=1.5, max_torque_mnm=0.1, max_speed_rpm=10000, power_w_nominal=0.4, power_w_peak=0.8, supply_voltage_ranges_v=[[3.25, 3.5]], data_interfaces=["I2C"]),
         "Per CubeSat da 1U a 3U. Momento +-1.5 mN m s, coppia massima 0.1 mN m, 10000 giri/min, massa 21 g, 25 x 25 x 15 mm, alimentazione 3.25-3.5 V, I2C, -20..+60 C. Potenza: a vuoto 65 mW tipici, "
         "400 mW tipici in regime nominale a 10000 giri/min (630 mW massimi), picco 800 mW: valori di riferimento per il modello RW210.15. Primo volo nel 2017.",
         dims=[25.0, 25.0, 15.0], dim_note="Datasheet AAC RW210.", tid=36.0, temp=[-20, 60], family="aac-rw210"),
    comp("aac-rw210-30", "reaction_wheel", "Hyperion Technologies (AAC Hyperion)", "RW210.30 reaction wheel", 0.032,
         "https://www.aac-clyde.space/wp-content/uploads/2021/11/RW210.pdf", "AAC Clyde Space RW210 Reaction Wheels datasheet (release 15 novembre 2021)",
         rw(momentum_mnms=3.0, max_torque_mnm=0.1, max_speed_rpm=15000, power_w_peak=0.8, supply_voltage_ranges_v=[[3.25, 3.5]], data_interfaces=["I2C"]),
         "Variante da +-3.0 mN m s: 15000 giri/min, massa 32 g, 25 x 25 x 15 mm. Il picco di 800 mW e' quello dichiarato per la serie; il consumo nominale e' dato solo per il modello RW210.15.",
         dims=[25.0, 25.0, 15.0], dim_note="Datasheet AAC RW210.", tid=36.0, temp=[-20, 60], family="aac-rw210"),
    comp("aac-rw210-60", "reaction_wheel", "Hyperion Technologies (AAC Hyperion)", "RW210.60 reaction wheel", 0.048,
         "https://www.aac-clyde.space/wp-content/uploads/2021/11/RW210.pdf", "AAC Clyde Space RW210 Reaction Wheels datasheet (release 15 novembre 2021)",
         rw(momentum_mnms=6.0, max_torque_mnm=0.1, max_speed_rpm=15000, power_w_peak=0.8, supply_voltage_ranges_v=[[3.25, 3.5]], data_interfaces=["I2C"]),
         "Variante da +-6.0 mN m s: 15000 giri/min, massa 48 g, 25 x 25 x 15 mm. Picco 800 mW dichiarato per la serie; consumo nominale non dichiarato per questo modello.",
         dims=[25.0, 25.0, 15.0], dim_note="Datasheet AAC RW210.", tid=36.0, temp=[-20, 60], family="aac-rw210"),
    comp("rocketlab-rw-0-003", "reaction_wheel", "Rocket Lab (Sinclair Interplanetary)", "RW-0.003 reaction wheel", 0.05,
         "https://www.rocketlab.co.nz/assets/Uploads/3-mNms-RW-0.003-Data-Sheet.pdf", "Rocket Lab 3 mNms RW-0.003 Data Sheet, versione 2 (7 aprile 2022)",
         rw(momentum_mnms=3.0, max_torque_mnm=1.0, supply_voltage_ranges_v=[[4.5, 9.0]], data_interfaces=["UART", "I2C"]),
         "Momento nominale 3 mN m s a 8500 giri/min (picco 5 mN m s a 5 V), coppia +-1 mN m al momento di picco, controllo di velocita' o di coppia con CPU integrata, massa <50 g (usato 50 g), 33.5 x 33.5 x 17 mm, "
         "alimentazione 4.5-9 V, UART o I2C/SMBus, -40..+70 C, >10 krad. Potenza non dichiarata. Oltre 100 ruote Sinclair in orbita (unita', non missioni). Prezzo 15000 USD, piu' 2000 USD per componenti schermati.",
         dims=[33.5, 33.5, 17.0], dim_note="Datasheet Rocket Lab RW-0.003.", tid=10.0, temp=[-40, 70], price={"amount": 15000, "currency": "USD", "as_of": "2022-04"}, family="rocketlab-rw"),
    comp("rocketlab-rw-0-01", "reaction_wheel", "Rocket Lab (Sinclair Interplanetary)", "RW-0.01 reaction wheel", 0.12,
         "https://www.rocketlab.co.nz/assets/Uploads/10-mNms-RW-0.01-Data-Sheet.pdf", "Rocket Lab 10 mNms RW-0.01 Data Sheet, versione 2 (7 aprile 2022)",
         rw(momentum_mnms=10.0, max_torque_mnm=1.0, power_w_peak=1.05, supply_voltage_ranges_v=[[3.4, 6.0]], data_interfaces=["UART", "I2C"]),
         "Momento nominale 10 mN m s (picco 18 mN m s a 5 V), coppia +-1 mN m, massa 120 g, 50 x 50 x 30 mm, alimentazione 3.4-6.0 V (massimo 8 V), UART o I2C/SMBus, -40..+70 C, >20 krad. Potenza 1.05 W a 10 mN m s con "
         "+1 mN m (usata come picco), 0.25 W a 18 mN m s a regime e 0.11 W a 5 mN m s a regime. Eredita': 10 unita' in orbita su 4 satelliti dal giugno 2014 (usato 4). Prezzo 20000 USD, piu' 2000 USD per componenti schermati.",
         dims=[50.0, 50.0, 30.0], dim_note="Datasheet Rocket Lab RW-0.01.", tid=20.0, temp=[-40, 70], heritage=4, price={"amount": 20000, "currency": "USD", "as_of": "2022-04"}, family="rocketlab-rw"),
    comp("cubespace-cubewheel-cw0057", "reaction_wheel", "CubeSpace", "CubeWheel CW0057 (Gen2)", 0.115,
         "https://www.cubesatshop.com/product/reaction-wheel-cw0057/", "Pagina prodotto CubeSatShop 'Reaction Wheel CW0057' di CubeSpace (consultata 2026-10-14)",
         rw(momentum_mnms=5.7, max_torque_mnm=2.0, max_speed_rpm=10000, power_w_nominal=0.77, power_w_peak=2.7, supply_voltage_ranges_v=[[6.4, 16.8]], data_interfaces=["CAN", "RS-485", "UART"]),
         "Momento nominale 5.7 mN m s a 6000 giri/min, coppia massima 2 mN m al momento nominale, massa 115 g, 35 x 35 x 24.2 mm, alimentazione motore 6.4-16.8 V e digitale 3.3 V, CAN/RS-485/UART (I2C su richiesta), "
         "24 krad, vibrazioni 14.16 g RMS. Potenza 770 mW al momento nominale e 2.7 W di picco (con l'elettronica digitale). Option sheet e ICD su richiesta; prezzo su richiesta (30080 USD per una piramide secondo un'altra fonte, non usato).",
         dims=[35.0, 35.0, 24.2], dim_note="Pagina prodotto CubeSatShop.", tid=24.0, method=METHOD_PAGE, family="cubespace-cubewheel"),
    comp("nanoavionics-rw0", "reaction_wheel", "NanoAvionics", "RW0 CubeSat Reaction Wheel", 0.137,
         "https://satsearch.co/products/kongsberg-nanoavionics-cubesat-reaction-wheel", "Pagina prodotto Kongsberg NanoAvionics RW0 su satsearch (consultata 2026-10-14)",
         rw(momentum_mnms=20.0, max_torque_mnm=3.2, max_speed_rpm=6500, power_w_nominal=0.15, data_interfaces=["SPI", "UART"]),
         "Momento massimo 20 mN m s, coppia massima 3.2 mN m, 6500 giri/min, massa 137 g, 43.5 x 43.5 x 24 mm, SPI/UART, -40..+85 C, TRL 9, ITAR-free. Potenza: 45 mW a riposo e 150 mW a regime a 1000 giri/min "
         "(non e' un picco: picco non dichiarato). Datasheet su richiesta, ordine minimo 4 pezzi.",
         dims=[43.5, 43.5, 24.0], dim_note="Pagina prodotto NanoAvionics/satsearch.", temp=[-40, 85], trl=9, method=METHOD_PAGE, family="nanoavionics-rw"),
    comp("gomspace-nanotorque-gsw-600", "reaction_wheel", "GomSpace", "NanoTorque GSW-600", 0.18,
         "https://gomspace.com/wp-content/uploads/2025/09/gs-ds-nanotorque-gsw-600-25-1.pdf", "GomSpace NanoTorque GSW-600 datasheet DS 1013128 rev 2.5 (5 novembre 2025)",
         rw(momentum_mnms=19.0, max_torque_mnm=1.5, max_speed_rpm=6000, power_w_nominal=0.65, power_w_peak=2.5, supply_voltage_ranges_v=[[4.9, 5.1]], data_interfaces=["SPI", "I2C"]),
         "Ruota per nano-satelliti 6U, 8U e 12U (la massa e il volume la fanno entrare anche in classi minori): 19 mN m s a 6000 giri/min, coppia continua +-1.5 mN m, massa 180 g, 44 x 44 x 27 mm, inerzia del volano 300 g cm2, "
         "alimentazione 5 V, SPI e I2C, -40..+80 C, vita di progetto 3 anni. Potenza non dichiarata direttamente: i valori usati sono DERIVATI da 5 V per la corrente dichiarata (500 mA alla coppia massima = 2.5 W; "
         "130 mA a 4500 giri/min a coppia nulla = 0.65 W). Versione a piramide (4 ruote): 940 g, 95 x 95 x 61.6 mm.",
         dims=[44.0, 44.0, 27.0], dim_note="Datasheet GomSpace GSW-600, una ruota.", temp=[-40, 80], family="gomspace-nanotorque"),
    comp("bct-rwp015", "reaction_wheel", "Blue Canyon Technologies", "RWp015 reaction wheel", 0.13,
         "https://www.bluecanyontech.com/components/reaction-wheels/", "Pagina prodotto Blue Canyon Technologies 'Reaction Wheels' (consultata 2026-10-14)",
         rw(momentum_mnms=15.0, max_torque_mnm=4.0),
         "Momento massimo 0.015 N m s, coppia massima 0.004 N m, massa 0.13 kg. Dimensioni, potenza, tensione e interfacce non sono nella pagina (altri cataloghi riportano 42 x 42 x 19 mm e circa 1 W: non usati). "
         "Il fornitore chiede di contattarlo per i dati di progetto.", method=METHOD_PAGE, family="bct-rw"),
    comp("bct-rwp050", "reaction_wheel", "Blue Canyon Technologies", "RWp050 reaction wheel", 0.24,
         "https://www.bluecanyontech.com/components/reaction-wheels/", "Pagina prodotto Blue Canyon Technologies 'Reaction Wheels' (consultata 2026-10-14)",
         rw(momentum_mnms=50.0, max_torque_mnm=7.0),
         "Momento massimo 0.050 N m s, coppia massima 0.007 N m, massa 0.24 kg. Dimensioni, potenza, tensione e interfacce non dichiarate nella pagina.", method=METHOD_PAGE, family="bct-rw"),
]

if __name__ == "__main__":
    cat_path = PROJ / "data" / "catalog.json"
    cat = json.loads(cat_path.read_text(encoding="utf-8"))
    new = STRUCTURES + MAGNETORQUERS + WHEELS
    new_ids = {c["id"] for c in new}
    cat["components"] = [c for c in cat["components"] if c["id"] not in new_ids] + new
    cat_path.write_text(json.dumps(cat, indent=1, ensure_ascii=False), encoding="utf-8")
    print(len(STRUCTURES), "strutture 1U,", len(MAGNETORQUERS), "magnetorquer,", len(WHEELS), "ruote;", len(cat["components"]), "componenti in totale")

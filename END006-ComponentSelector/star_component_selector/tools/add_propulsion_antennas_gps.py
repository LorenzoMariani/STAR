"""Aggiunge al catalogo le categorie `propulsion` (propulsori e sistemi di propulsione per CubeSat), `antenna` (antenne di comunicazione)
e `gps` (ricevitori GNSS). Tutti i valori vengono da documenti pubblici dei fornitori (o da schede di terzi dove indicato nelle note);
`null` = non dichiarato. Idempotente: rieseguirlo sostituisce le voci con gli stessi id.

    python tools/add_propulsion_antennas_gps.py [cartella-del-progetto]
"""
import json
import sys
from pathlib import Path

PROJ = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
RET = "2026-10-14"
METHOD = "trascritto da documento pubblico del fornitore; da controllare manualmente"
METHOD_3P = "trascritto da una pagina di prodotto (scheda del fornitore pubblicata su un sito di terzi); da controllare manualmente"
G0 = 9.80665


def vol(dims):
    a, b, c = dims
    return None if None in dims else round(a * b * c / 1e6, 3)


def comp(cid, category, vendor, name, mass, url, doc, specs, notes, dims=None, dim_basis="declared", dim_note="", power=None, trl=None, heritage=None, tid=None,
         temp=None, family=None, method=METHOD, volume=None, page=None):
    rec = {"id": cid, "category": category, "vendor": vendor, "name": name, "family": family, "mass_kg": mass, "power_w": power,
           "volume_u": volume if volume is not None else (vol(dims) if dims else None), "trl": trl, "flight_heritage": heritage, "tid_krad": tid, "temp_op_c": temp,
           "notes": notes, "source": {"url": url, "document": doc, "retrieved": RET, "verified": False, "method": method}, "specs": specs}
    if dims:
        rec["dimensions"] = {"mm": dims, "basis": dim_basis, "note": dim_note}
    return {k: v for k, v in rec.items() if v is not None or k in ("mass_kg", "power_w")}


def prop(**kw):
    base = dict(propellant=None, thrust_mn_min=None, thrust_mn_max=None, isp_s=None, propellant_mass_kg=None, dry_mass_kg=None, power_w_firing=None,
                power_w_standby=None, min_form_factor_u=None, data_interfaces=None, supply_voltage_ranges_v=None)
    base.update(kw)
    return base


def ant(**kw):
    base = dict(frequency_ranges_mhz=None, gain_dbi=None, beamwidth_deg=None, polarization=None, rf_power_w_max=None, deployable=None, data_interfaces=None,
                supply_voltage_ranges_v=None)
    base.update(kw)
    return base


def gps(**kw):
    base = dict(constellations=None, accuracy_position_m=None, accuracy_basis=None, accuracy_velocity_m_s=None, ttff_cold_s=None, update_rate_hz=None, channels=None,
                antenna_included=None, data_interfaces=None, supply_voltage_ranges_v=None)
    base.update(kw)
    return base


DISCLAIMER_L3H = ("Le prestazioni sono 'impulso di sistema' a regime stazionario: l'impulso reale dipende dal ciclo di lavoro. Impulso specifico, potenza, tensione e "
                  "interfacce non sono dichiarati nel brochure: il delta-v e' calcolato come impulso totale diviso la massa di lancio (stima per difetto). Spinta 0.25-1.0 N per propulsore. "
                  "Dimensioni dalle taglie nominali del brochure (1U circa 10 x 10 x 10 cm). ")

PROPULSION = [
    comp("enpulsion-nano-r3", "propulsion", "Enpulsion", "NANO R3 (configuration 030)", 1.5,
         "https://www.enpulsion.com/wp-content/uploads/DataSheet_Nano_20260319.pdf", "Enpulsion NANO R3 Datasheet, configurazione 030 (Doc. DAT-00007_1.00, marzo 2026)",
         prop(propellant="indium (solid)", thrust_mn_min=0.15, thrust_mn_max=0.35, isp_s=2500.0, propellant_mass_kg=0.215, dry_mass_kg=1.28, power_w_firing=45.0,
              power_w_standby=7.0, data_interfaces=["RS-422", "RS-485"], supply_voltage_ranges_v=[[12.0, 12.0]]) | {"propulsion_type": "feep", "total_impulse_ns": 5300.0},
         "Propulsore FEEP (emissione di campo) a indio. Campo di spinta 150-350 uN (nominale 350 uN, prestazione garantita al 75% a fine vita); Isp 2500 s a 350 uN "
         "(2960 s a un altro punto garantito); impulso totale 5300 N s a 350 uN; propellente 215 g +-2%. Massa a secco <1280 g e a pieno carico <1500 g (usata 1.5 kg, estremo superiore "
         "dichiarato). Potenza 45 W alla spinta nominale con neutralizzatore (sistema 30-50 W), attesa a caldo 4-7 W (usati 45 W e 7 W). Alimentazione 12 V, interfaccia RS422/RS485. "
         "Oltre 40 unita' R3 in orbita (marzo 2026), oltre 240 della famiglia NANO: non sono missioni, quindi l'eredita' di volo resta non dichiarata. La spinta e' di micronewton: "
         "i tempi di manovra sono di mesi (vedi l'indicatore del tempo di spinta). Dimensioni 98.0 x 99.0 x 95.3 mm senza sporgenze.",
         dims=[98.0, 99.0, 95.3], dim_note="Datasheet Enpulsion NANO R3, esclusi gli elementi sporgenti (con sporgenze 100.95 x 99.0 x 97.3 mm).", family="enpulsion-nano"),
    comp("thrustme-npt30-i2-1u", "propulsion", "ThrustMe", "NPT30-I2 1U", 1.2,
         "https://thrustme.fr/base/stock/ProductBannerFiles/2_thrustme-npt30-i2.pdf", "ThrustMe NPT30-I2-1U product information (2021)",
         prop(propellant="iodine (solid)", thrust_mn_min=0.3, thrust_mn_max=1.1, isp_s=2400.0, power_w_firing=65.0, data_interfaces=["I2C", "CAN"],
              supply_voltage_ranges_v=[[12.0, 28.0]]) | {"propulsion_type": "gridded_ion", "total_impulse_ns": 5500.0},
         "Propulsore a ioni a griglia a iodio solido, precaricato e non pressurizzato al lancio. Spinta 0.3-1.1 mN; impulso totale 'fino a' 5500 N s e Isp 'fino a' 2400 s "
         "(sono i valori massimi dichiarati, usati come tali); massa totale a pieno carico 1.2 kg; potenza totale 35-65 W (usati 65 W); vettore di spinta preciso entro 1 grado; "
         "alimentazione 12-28 V, I2C e CAN. Sistema integrato con PPU, serbatoio e controllo termico passivo. Spinta di millinewton: manovre di settimane o mesi.",
         dims=[96.0, 96.0, 113.0], dim_note="Datasheet ThrustMe NPT30-I2-1U (formato 1U).", family="thrustme-npt30"),
    comp("thrustme-npt30-i2-1-5u", "propulsion", "ThrustMe", "NPT30-I2 1.5U", 1.7,
         "https://thrustme.fr/base/stock/ProductBannerFiles/2_thrustme-npt30-i2.pdf", "ThrustMe NPT30-I2-1.5U product information (2021)",
         prop(propellant="iodine (solid)", thrust_mn_min=0.3, thrust_mn_max=1.1, isp_s=2400.0, power_w_firing=65.0, data_interfaces=["I2C", "CAN"],
              supply_voltage_ranges_v=[[12.0, 28.0]]) | {"propulsion_type": "gridded_ion", "total_impulse_ns": 9500.0},
         "Versione 1.5U dello stesso sistema: impulso totale 'fino a' 9500 N s (valore massimo dichiarato), massa a pieno carico 1.7 kg, altre prestazioni come la 1U. "
         "Dimensioni 93 x 93 x 155 mm.",
         dims=[93.0, 93.0, 155.0], dim_note="Datasheet ThrustMe NPT30-I2-1.5U (formato 1.5U).", family="thrustme-npt30"),
    comp("busek-bgt-x5", "propulsion", "Busek", "BGT-X5 (1U green monopropellant)", 1.5,
         "https://www.busek.com/bgtx5", "Pagina prodotto Busek BGT-X5 (consultata 2026-10-14)",
         prop(propellant="ASCENT (AF-M315E, green)", thrust_mn_max=500.0, isp_s=220.0, power_w_firing=20.0, data_interfaces=["RS-485"], supply_voltage_ranges_v=[[6.0, 16.0]])
         | {"propulsion_type": "green_monoprop", "total_impulse_ns": 565.0},
         "Monopropellente verde ASCENT: spinta nominale 500 mN, Isp 220-225 s (usato 220), impulso totale 565 N s in un volume 1U, potenza di sistema 20 W, "
         "alimentazione 6-16 V (nominale 12 V), RS-485, massa del sistema 1.5 kg a inizio vita (BOL, a pieno carico). La taglia 1U e' il solo dato geometrico dichiarato "
         "(le dimensioni in mm non sono nel testo della pagina): si usa 100 x 100 x 100 mm come taglia nominale.",
         dims=[100.0, 100.0, 100.0], dim_basis="derived", dim_note="Derivate dalla taglia nominale 1U dichiarata da Busek ('1U volume'); le dimensioni in mm non sono pubbliche nella pagina.",
         family="busek-bgt"),
    comp("busek-bit-3", "propulsion", "Busek", "BIT-3 (iodine RF ion thruster)", 2.78,
         "https://www.busek.com/s/BIT3_v10.pdf", "Busek BIT-3 RF Ion Thruster datasheet, versione 1.0 (agosto 2021)",
         prop(propellant="iodine (solid)", thrust_mn_max=1.1, isp_s=2150.0, propellant_mass_kg=1.5, dry_mass_kg=1.28, power_w_firing=75.0, data_interfaces=["RS-485"],
              supply_voltage_ranges_v=[[28.0, 28.0]]) | {"propulsion_type": "gridded_ion", "total_impulse_ns": 31626.0},
         "Spinta fino a 1.1 mN e Isp fino a 2150 s (valori massimi dichiarati); potenza di sistema 56-75 W (usati 75 W), dissipazione termica circa 35 W, alimentazione 28 V, RS-485, "
         "-15..+45 C. Massa a secco 1.28 kg senza gimbal (1.40 kg con gimbal) e carico di propellente fino a 1.50 kg: la massa a pieno carico 2.78 kg e' DERIVATA come somma. "
         "L'impulso totale NON e' dichiarato: 31626 N s e' DERIVATO come Isp x g0 x propellente (2150 s x 9.80665 x 1.5 kg) e coerente con il delta-v dichiarato di 2.39 km/s per un "
         "CubeSat da 14 kg. Una versione piu' recente del sito Busek riporta valori maggiori (fino a 1.25 mN, 2300 s, 56-80 W): qui si usa il datasheet v1.0. "
         "Il gimbal opzionale non e' incluso. Ingombro 180 x 88 x 102 mm.",
         dims=[180.0, 88.0, 102.0], dim_note="Datasheet Busek BIT-3 v1.0 (ingombro del sistema, senza gimbal).", temp=[-15, 45], family="busek-bit"),
    comp("aac-pm200", "propulsion", "AAC Clyde Space", "PM200 (bipropellant propulsion module, with Dawn Aerospace)", 1.41,
         "https://www.aac-clyde.space/wp-content/uploads/2021/11/PM200.pdf", "AAC Clyde Space PM200 Propulsion datasheet (release 6 agosto 2021)",
         prop(propellant="nitrous oxide / propene", thrust_mn_max=500.0, isp_s=285.0, propellant_mass_kg=0.31, dry_mass_kg=1.1, power_w_firing=12.0, power_w_standby=0.1,
              min_form_factor_u=3.0, data_interfaces=["I2C", "RS-422", "RS-485"], supply_voltage_ranges_v=[[5.0, 5.0], [12.0, 12.0]])
         | {"propulsion_type": "bipropellant", "total_impulse_ns": 850.0},
         "Modulo 1U per CubeSat da 3U a 6U, autopressurizzante, non tossico. Spinta nominale 0.5 N, Isp >285 s, impulso totale >850 N s (usati i limiti dichiarati), delta-v >230 m/s "
         "per un satellite da 4 kg che include il modulo. Massa a secco 1100 g e propellente 310 g: la massa a pieno carico 1.41 kg e' DERIVATA come somma. Potenza <12 W in spinta, "
         "<0.1 W in attesa; alimentazione 5 e 12 V; I2C oppure RS422/RS485; -5..+35 C; pressioni di stoccaggio 45 bar (ossidante) e 9 bar (combustibile). Impulso minimo 35 mN s, "
         "massimo 5 N s per accensione.",
         dims=[97.7, 95.4, 95.4], dim_note="Datasheet AAC Clyde Space PM200, dimensioni esterne.", temp=[-5, 35], family="aac-pm"),
    comp("vacco-mips-0-5u", "propulsion", "VACCO", "Standard MiPS 0.5U (cold gas)", 0.743,
         "https://www.vacco.com/images/uploads/pdfs/MiPS_standard_0714.pdf", "VACCO Standard Micro Propulsion System X14029003-0X (rev. 6/15)",
         prop(propellant="R134a", thrust_mn_min=10.0, thrust_mn_max=10.0, isp_s=40.0, power_w_firing=10.0, power_w_standby=0.25, data_interfaces=["RS-422"],
              supply_voltage_ranges_v=[[9.0, 12.6]]) | {"propulsion_type": "cold_gas", "total_impulse_ns": 103.0},
         "Sistema a gas freddo con cinque propulsori da 10 mN (beccheggio, imbardata, rollio e delta-v), propellente R134a non tossico. Variante 0.5U: profondita' 50 mm, massa "
         "a pieno carico 743 g, impulso totale 103 N s, Isp 40 s. Potenza massima in regime stazionario 10 W, attesa 0.25 W, alimentazione 9.0-12.6 V, interfaccia RS422, "
         "0..+60 C. Il datasheet avverte che le prestazioni 'sono basate sui requisiti del cliente e non rappresentano i limiti dei componenti'. Dimensioni: dichiarata solo la "
         "profondita'; la sezione 100 x 100 mm e' la taglia nominale del CubeSat.",
         dims=[100.0, 100.0, 50.0], dim_basis="derived", dim_note="Profondita' 50 mm dichiarata da VACCO; sezione 100 x 100 mm derivata dalla taglia nominale CubeSat.",
         temp=[0, 60], family="vacco-mips"),
    comp("vacco-mips-1u", "propulsion", "VACCO", "Standard MiPS 1U (cold gas)", 1.245,
         "https://www.vacco.com/images/uploads/pdfs/MiPS_standard_0714.pdf", "VACCO Standard Micro Propulsion System X14029003-0X (rev. 6/15)",
         prop(propellant="R134a", thrust_mn_min=10.0, thrust_mn_max=10.0, isp_s=40.0, power_w_firing=10.0, power_w_standby=0.25, data_interfaces=["RS-422"],
              supply_voltage_ranges_v=[[9.0, 12.6]]) | {"propulsion_type": "cold_gas", "total_impulse_ns": 250.0},
         "Variante 1U dello stesso sistema a gas freddo: profondita' 100 mm, massa a pieno carico 1245 g, impulso totale 250 N s, 5 propulsori da 10 mN, Isp 40 s, 9.0-12.6 V, "
         "RS422. Stesse avvertenze della variante 0.5U (prestazioni basate sui requisiti del cliente).",
         dims=[100.0, 100.0, 100.0], dim_basis="derived", dim_note="Profondita' 100 mm dichiarata da VACCO; sezione 100 x 100 mm derivata dalla taglia nominale CubeSat.",
         temp=[0, 60], family="vacco-mips"),
    comp("gomspace-nanoprop-cgp3", "propulsion", "GomSpace", "NanoProp CGP3", 0.35,
         "https://satcatalog.s3.amazonaws.com/components/1082/SatCatalog_-_GomSpace_-_NanoProp_CGP3_-_Datasheet.pdf", "GomSpace NanoProp CGP3 flyer (datasheet ospitato da SatCatalog)",
         prop(propellant="butane", thrust_mn_max=1.0, isp_s=60.0, dry_mass_kg=0.3, power_w_firing=2.0, data_interfaces=["CAN", "I2C"],
              supply_voltage_ranges_v=[[5.0, 5.0], [12.0, 12.0]]) | {"propulsion_type": "cold_gas", "total_impulse_ns": 40.0},
         "Gas freddo a butano con quattro propulsori indipendenti a controllo in anello chiuso. Spinta 1 mN (risoluzione 10 uN), Isp 60-110 s (usato 60), impulso totale 40 N s, "
         "massa 300/350 g (a secco/a pieno carico), consumo medio <2 W, pressione di esercizio 2-5 bar, 0..+50 C, CAN e I2C, alimentazione 5 e 12 V, cavi liberi. "
         "Ingombro 100 x 100 x 50 mm con la scheda elettronica, interfaccia 4 x M3 (PC/104); occupa circa mezza unita'. Volato nel 2015 (secondo il datasheet).",
         dims=[100.0, 100.0, 50.0], dim_note="Datasheet GomSpace NanoProp CGP3 (scheda elettronica inclusa, interfaccia PC/104).", temp=[0, 50], family="gomspace-nanoprop"),
    comp("l3harris-mps-120-1u", "propulsion", "L3Harris (Aerojet Rocketdyne)", "MPS-120 1U (hydrazine)", 1.6,
         "https://satcatalog.s3.amazonaws.com/components/892/SatCatalog_-_Aerojet_Rocketdyne_-_MPS-120-1U_-_Datasheet.pdf", "Aerojet Rocketdyne / L3Harris CubeSat Modular Propulsion Systems (la0174-18)",
         prop(propellant="hydrazine", thrust_mn_min=250.0, thrust_mn_max=1000.0, dry_mass_kg=1.2) | {"propulsion_type": "hydrazine_monoprop", "total_impulse_ns": 810.0},
         DISCLAIMER_L3H + "Impulso >810 N s (usato come limite), massa 1.2 kg a secco e 1.6 kg a pieno carico. Propellente tossico: richiede procedure di manipolazione specifiche.",
         dims=[100.0, 100.0, 100.0], dim_basis="derived", dim_note="Taglia nominale 1U del brochure (circa 10 x 10 x 10 cm).", family="l3harris-mps"),
    comp("l3harris-mps-120-2u", "propulsion", "L3Harris (Aerojet Rocketdyne)", "MPS-120 2U (hydrazine)", 2.5,
         "https://satcatalog.s3.amazonaws.com/components/892/SatCatalog_-_Aerojet_Rocketdyne_-_MPS-120-1U_-_Datasheet.pdf", "Aerojet Rocketdyne / L3Harris CubeSat Modular Propulsion Systems (la0174-18)",
         prop(propellant="hydrazine", thrust_mn_min=250.0, thrust_mn_max=1000.0, dry_mass_kg=1.5) | {"propulsion_type": "hydrazine_monoprop", "total_impulse_ns": 1960.0},
         DISCLAIMER_L3H + "Impulso >1960 N s, massa 1.5 kg a secco e 2.5 kg a pieno carico. Propellente tossico.",
         dims=[100.0, 100.0, 200.0], dim_basis="derived", dim_note="Taglia nominale 2U del brochure (circa 10 x 10 x 20 cm).", family="l3harris-mps"),
    comp("l3harris-mps-130-1u", "propulsion", "L3Harris (Aerojet Rocketdyne)", "MPS-130 1U (green propellant AF-M315E)", 1.7,
         "https://satcatalog.s3.amazonaws.com/components/892/SatCatalog_-_Aerojet_Rocketdyne_-_MPS-120-1U_-_Datasheet.pdf", "Aerojet Rocketdyne / L3Harris CubeSat Modular Propulsion Systems (la0174-18)",
         prop(propellant="AF-M315E (green)", thrust_mn_min=250.0, thrust_mn_max=1000.0, dry_mass_kg=1.1) | {"propulsion_type": "green_monoprop", "total_impulse_ns": 1130.0},
         DISCLAIMER_L3H + "Impulso >1130 N s, massa 1.1 kg a secco e 1.7 kg a pieno carico.",
         dims=[100.0, 100.0, 100.0], dim_basis="derived", dim_note="Taglia nominale 1U del brochure (circa 10 x 10 x 10 cm).", family="l3harris-mps"),
    comp("l3harris-mps-130-2u", "propulsion", "L3Harris (Aerojet Rocketdyne)", "MPS-130 2U (green propellant AF-M315E)", 2.8,
         "https://satcatalog.s3.amazonaws.com/components/892/SatCatalog_-_Aerojet_Rocketdyne_-_MPS-120-1U_-_Datasheet.pdf", "Aerojet Rocketdyne / L3Harris CubeSat Modular Propulsion Systems (la0174-18)",
         prop(propellant="AF-M315E (green)", thrust_mn_min=250.0, thrust_mn_max=1000.0, dry_mass_kg=1.4) | {"propulsion_type": "green_monoprop", "total_impulse_ns": 2720.0},
         DISCLAIMER_L3H + "Impulso >2720 N s, massa 1.4 kg a secco e 2.8 kg a pieno carico.",
         dims=[100.0, 100.0, 200.0], dim_basis="derived", dim_note="Taglia nominale 2U del brochure (circa 10 x 10 x 20 cm).", family="l3harris-mps"),
    comp("l3harris-mps-135-4u", "propulsion", "L3Harris (Aerojet Rocketdyne)", "MPS-135 4U (green propellant, pump-fed)", 7.2,
         "https://satcatalog.s3.amazonaws.com/components/892/SatCatalog_-_Aerojet_Rocketdyne_-_MPS-120-1U_-_Datasheet.pdf", "Aerojet Rocketdyne / L3Harris CubeSat Modular Propulsion Systems (la0174-18)",
         prop(propellant="AF-M315E (green)", thrust_mn_min=250.0, thrust_mn_max=1000.0, dry_mass_kg=3.5) | {"propulsion_type": "green_monoprop", "total_impulse_ns": 7290.0},
         DISCLAIMER_L3H + "Impulso >7290 N s, massa 3.5 kg a secco e 7.2 kg a pieno carico. Taglia 4U (circa 22 x 20 x 10 cm): entra solo nei satelliti da 12U.",
         dims=[220.0, 200.0, 100.0], dim_basis="derived", dim_note="Taglia nominale 4U del brochure (circa 22 x 20 x 10 cm).", family="l3harris-mps"),
    comp("cuaerospace-chips-180", "propulsion", "CU Aerospace", "CHIPS-180 (0.54U, warm/cold gas)", 1.027,
         "https://cuaerospace.com/Portals/0/SiteContent/assets/PDF/CHIPS-Data-Sheet-230724-180.pdf", "CU Aerospace CHIPS System Overview (giugno 2023)",
         prop(propellant="R134a", thrust_mn_min=15.0, thrust_mn_max=15.0, isp_s=67.0, propellant_mass_kg=0.277, power_w_firing=20.0) | {"propulsion_type": "warm_gas", "total_impulse_ns": 176.0},
         "Resistojet (modo gas caldo) con modo gas freddo, controllo di assetto a tre assi con fino a 8 propulsori ACS. Modo caldo: spinta 15 mN, Isp 67 s, impulso totale 176 N s, potenza 20 W; "
         "modo freddo: Isp 45 s e 118 N s. Massa a pieno carico 1027 g (propellente 277 g), pacco 6 x 9 x 10 cm (540 cm3, 0.54U), durata 3+ anni dal carico. Il documento avverte che "
         "non va usato per il progetto ma solo come informazione e che le dimensioni sono illustrative. Tensione e interfacce non dichiarate (porta personalizzabile).",
         dims=[100.0, 90.0, 60.0], dim_note="Datasheet CU Aerospace CHIPS-180 (pacco 10 x 9 x 6 cm), dimensioni illustrative.", family="cuaerospace-chips"),
    comp("cuaerospace-chips-500", "propulsion", "CU Aerospace", "CHIPS-500 (warm/cold gas)", 1.835,
         "https://cuaerospace.com/Portals/0/SiteContent/assets/PDF/CHIPS-Data-Sheet-230724-180.pdf", "CU Aerospace CHIPS System Overview (giugno 2023)",
         prop(propellant="R134a", thrust_mn_min=25.0, thrust_mn_max=25.0, isp_s=69.0, propellant_mass_kg=0.77, power_w_firing=25.0) | {"propulsion_type": "warm_gas", "total_impulse_ns": 505.0},
         "Modo caldo: spinta 25 mN, Isp 69 s, impulso totale 505 N s, potenza 25 W; modo freddo: 18 mN, Isp 46 s e 350 N s. Massa a pieno carico 1835 g (propellente 770 g), "
         "volume 1300 cm3 (13 x 10 x 10 cm). Stesse avvertenze di CHIPS-180 (informazione, dimensioni illustrative).",
         dims=[100.0, 100.0, 130.0], dim_note="Datasheet CU Aerospace CHIPS-500 (13 x 10 x 10 cm), dimensioni illustrative; l'ordine degli assi non e' specificato.", family="cuaerospace-chips"),
    comp("cuaerospace-chips-1000", "propulsion", "CU Aerospace", "CHIPS-1000 (warm/cold gas)", 3.13,
         "https://cuaerospace.com/Portals/0/SiteContent/assets/PDF/CHIPS-Data-Sheet-230724-180.pdf", "CU Aerospace CHIPS System Overview (giugno 2023)",
         prop(propellant="R134a", thrust_mn_min=31.0, thrust_mn_max=31.0, isp_s=70.0, propellant_mass_kg=1.513, power_w_firing=30.0) | {"propulsion_type": "warm_gas", "total_impulse_ns": 1030.0},
         "Modo caldo: spinta 31 mN, Isp 70 s, impulso totale 1030 N s, potenza 30 W; modo freddo: 21 mN, Isp 46 s e 715 N s. Massa a pieno carico 3130 g (propellente 1513 g), "
         "volume 2500 cm3 (12.5 x 20 x 10 cm). Stesse avvertenze (informazione, dimensioni illustrative).",
         dims=[200.0, 100.0, 125.0], dim_note="Datasheet CU Aerospace CHIPS-1000 (12.5 x 20 x 10 cm), dimensioni illustrative; l'ordine degli assi non e' specificato.", family="cuaerospace-chips"),
]

NOTE_ES_ANT = ("Scheda pubblicata da EnduroSat e riportata da satsearch (datasheet e CAD solo su richiesta). ")
ANTENNAS = [
    comp("isis-ants-1u3u", "antenna", "ISISpace", "Deployable Antenna System (1U/3U)", 0.085,
         "https://www.cubesatshop.com/wp-content/uploads/2016/06/ISIS-Antenna-systems-Brochure-v1.pdf", "ISISpace Antenna Systems brochure (ISIS deployable antenna system for 1U/3U CubeSats)",
         ant(frequency_ranges_mhz=None, gain_dbi=0.0, polarization="linear/circular", rf_power_w_max=2.0, deployable=True, data_interfaces=["I2C"],
             supply_voltage_ranges_v=[[3.3, 3.3], [5.0, 5.0]]) | {"bands": ["VHF", "UHF"], "antenna_type": "wire"},
         "Sistema di dispiegamento con fino a 4 antenne a nastro (UHF circa 17 cm, VHF circa 55 cm): configurabile come monopoli, dipoli o turnstile (UHF o VHF), polarizzazione "
         "circolare o lineare. Guadagno di fascio principale 0 dBi (UHF e VHF), potenza RF massima 2 W, banda >50 MHz (UHF, -10 dB) e >10 MHz (VHF), dispiegamento <3 s a 15 C, "
         "massa 77-85 g (usati 85 g), ingombro stivato 98 x 98 x 7 mm, consumo nominale <40 mW e <2 W durante il dispiegamento (usati 40 mW), alimentazione 3.3 o 5 V, I2C, "
         "-20..+60 C, 30 mm di foro passante (non con turnstile). Compatibile con strutture ISIS e Pumpkin 1U-3U. In volo dal 2010, oltre 200 unita' consegnate (non missioni). "
         "Versione per 6U/12U: nessun dato numerico pubblicato.",
         dims=[98.0, 98.0, 7.0], dim_note="Brochure ISISpace, ingombro stivato (lunghezza x larghezza x altezza).", power=0.04, temp=[-20, 60], family="isis-ants"),
    comp("endurosat-uhf-antenna-iii", "antenna", "EnduroSat", "UHF Antenna III (deployable)", 0.21,
         "https://www.endurosat.com/products/uhf-antenna-iii", "Pagina prodotto EnduroSat UHF Antenna (consultata 2026-10-14)",
         ant(frequency_ranges_mhz=[[144.0, 148.0], [400.0, 403.0], [435.0, 438.0]], gain_dbi=0.0, polarization="linear", rf_power_w_max=2.0, deployable=True,
             data_interfaces=["RS-485", "I2C", "UART"]) | {"bands": ["VHF", "UHF"], "antenna_type": "wire"},
         "Antenna omnidirezionale dispiegabile a polarizzazione lineare con dispiegamento a filo bruciabile triplamente ridondante con feedback; bande VHF 144-148, UHF commerciale 400-403 e UHF "
         "amatoriale 435-438 MHz. Guadagno '>0 dBi' (usato 0: e' un minimo, non un picco), potenza RF 2 W, massa 210 g, controllo RS-485/I2C/UART. Compatibile con strutture 6U. "
         "Dimensioni, alimentazione, consumo e temperatura non sono nella pagina. La pagina non specifica il tipo di elemento (monopolo/dipolo).",
         family="endurosat-antenna"),
    comp("gomspace-nanocom-ant430", "antenna", "GomSpace", "NanoCom ANT430", 0.03,
         "https://satcatalog.s3.amazonaws.com/components/667/SatCatalog_-_GomSpace_-_NanoCom_ANT430_-_Datasheet.PDF", "GomSpace NanoCom ANT430 Datasheet DS 1010590 rev 3.5 (2 agosto 2018)",
         ant(frequency_ranges_mhz=[[430.0, 440.0]], gain_dbi=1.6, polarization="RHCP/LHCP", rf_power_w_max=10.0, deployable=True) | {"bands": ["UHF"], "antenna_type": "wire"},
         "Turnstile UHF inclinata a quattro aste rigide con rete di sfasamento: 435 +-5 MHz, guadagno da -1 a 1.6 dBi (1.6 dBi usato come picco; a un 2U uniforme il valore simulato e' "
         "massimo 1.4 dBi lungo Z e da 0.6 a -0.3 dBi lungo X e Y), polarizzazione circolare (sinistra vista dall'alto, destra dal basso), potenza RF 10 W, massa totale 30 g, "
         "PCB 98 x 98 mm, aste di 163 mm (110 mm nella versione 1U), -40..+85 C. Il sistema di dispiegamento NON e' incluso (filo bruciabile con schede GomSpace a parte). "
         "Altezza del PCB non dichiarata.",
         dims=[98.0, 98.0, None], dim_note="Datasheet GomSpace ANT430, PCB 98 x 98 mm; altezza non dichiarata.", temp=[-40, 85], family="gomspace-ant"),
    comp("isis-s-band-patch", "antenna", "ISISpace", "S-band Patch Antenna", 0.05,
         "https://satcatalog.s3.amazonaws.com/components/555/SatCatalog_-_Innovative_Solutions_In_Space_-_S-Band_Patch_Antenna_-_Datasheet.pdf", "ISISpace S-Band Patch Antenna datasheet ISIS-QMS-TPL-0045 v0.0 (2021)",
         ant(frequency_ranges_mhz=[[2200.0, 2290.0]], gain_dbi=6.5, beamwidth_deg=100.0, polarization="RHCP", rf_power_w_max=2.0, deployable=False)
         | {"bands": ["S"], "antenna_type": "patch"},
         "Patch a polarizzazione circolare destra per la banda S 2200-2290 MHz: guadagno in boresight 6.5 dBic, apertura a meta' potenza 100 gradi, perdita di ritorno >13 dB, banda >100 MHz, "
         "rapporto assiale <3 dB (+-100 gradi), potenza 2 W, massa <50 g, diametro 80 mm e altezza 5.0 mm senza connettore (connettore SMA 8.8 mm), -20..+50 C, 4 x M2.5. "
         "Montabile su una faccia 1U o su un 'tuna can'. Il datasheet e' una bozza (versione 0.0, data non compilata).",
         dims=[80.0, 80.0, 5.0], dim_note="Datasheet ISISpace: disco di diametro 80 mm, altezza 5.0 mm senza connettore.", temp=[-20, 50], family="isis-patch"),
    comp("iq-spacecom-x-band-patch", "antenna", "IQ Technologies for Earth and Space (IQ spacecom)", "X-Band Antenna (patch 60 x 40 mm)", 0.02,
         "https://www.cubesatshop.com/wp-content/uploads/2023/04/X-Band-Antenna-Datasheet-09.2022.pdf", "IQ spacecom X Band Antenna datasheet (09-22)",
         ant(frequency_ranges_mhz=[[8025.0, 8400.0], [7145.0, 7250.0]], gain_dbi=10.0, beamwidth_deg=40.0, polarization="RHCP", rf_power_w_max=2.0, deployable=False)
         | {"bands": ["X"], "antenna_type": "patch_array"},
         "Patch composto da quattro elementi (60 x 40 mm) per 8.025-8.400 GHz oppure 7.145-7.250 GHz (varianti), guadagno massimo 10 dBi, apertura 40 gradi, polarizzazione RHCP (LHCP "
         "opzionale), potenza RF <2 W, VSWR <1.4 tipico, -30..+60 C, massa 20 g, connettore SMA femmina. TRL 9 dichiarato dal fornitore con diverse missioni LEO riuscite. "
         "Compatibile con un 1U.",
         dims=[60.0, 40.0, 1.8], dim_note="Datasheet IQ spacecom, dimensioni esterne senza connettore.", temp=[-30, 60], trl=9, family="iq-xband"),
    comp("endurosat-x-band-patch", "antenna", "EnduroSat", "X-Band Patch Antenna (single)", 0.003,
         "https://satsearch.co/products/endurosat-x-band-single-patch-antenna", "Scheda satsearch EnduroSat X-Band Single Patch Antenna (aggiornata 2025-09-25)",
         ant(frequency_ranges_mhz=[[8025.0, 8400.0]], gain_dbi=6.0, beamwidth_deg=74.0, polarization="RHCP", rf_power_w_max=4.0, deployable=False)
         | {"bands": ["X"], "antenna_type": "patch"},
         NOTE_ES_ANT + "Guadagno '>6 dBi' (usato 6 come minimo), HPBW 74 gradi, RF fino a 4 W, connettore SMP, -40..+125 C, qualifica ECSS-E-ST-10-03C e NASA GEVS, TRL 9. "
         "Discrepanze nella scheda: massa 2.2 g (caratteristiche) contro 3 g (specifiche tecniche): usati 3 g; polarizzazione RHCP o LHCP selezionabile (caratteristiche) contro solo RHCP (specifiche): usata RHCP.",
         dims=[24.0, 24.0, 5.62], dim_note="Scheda EnduroSat/satsearch: 24 +-0.1 x 24 +-0.1 x 5.62 mm.", temp=[-40, 125], trl=9, family="endurosat-xband", method=METHOD_3P),
    comp("endurosat-x-band-2x2", "antenna", "EnduroSat", "X-Band 2x2 Patch Array Antenna", 0.0232,
         "https://satsearch.co/products/endurosat-x-band-2x2-patch-array-antenna", "Scheda satsearch EnduroSat X-Band 2x2 Patch Array Antenna",
         ant(frequency_ranges_mhz=[[8025.0, 8400.0]], gain_dbi=None, beamwidth_deg=40.0, polarization="RHCP", rf_power_w_max=4.0, deployable=False)
         | {"bands": ["X"], "antenna_type": "patch_array"},
         NOTE_ES_ANT + "Il guadagno e' CONTRADDITTORIO nella stessa scheda ('>12 dBi' nelle caratteristiche, '2+ dBi' nelle specifiche tecniche): lasciato non dichiarato. HPBW 40 gradi, "
         "RF fino a 4 W, connettore SMP, -40..+125 C, TRL 9, massa 23.15-23.2 g.",
         dims=[60.0, 60.0, 7.04], dim_note="Scheda EnduroSat/satsearch: 60 +-0.1 x 60 +-0.1 x 7.04 mm.", temp=[-40, 125], trl=9, family="endurosat-xband", method=METHOD_3P),
    comp("endurosat-x-band-4x4", "antenna", "EnduroSat", "X-Band 4x4 Patch Array Antenna", 0.053,
         "https://satsearch.co/products/endurosat-x-band-4x4-patch-array-antenna", "Scheda satsearch EnduroSat X-Band 4x4 Patch Array Antenna",
         ant(frequency_ranges_mhz=[[8025.0, 8400.0]], gain_dbi=16.0, beamwidth_deg=18.0, polarization="RHCP", rf_power_w_max=4.0, deployable=False)
         | {"bands": ["X"], "antenna_type": "patch_array"},
         NOTE_ES_ANT + "Guadagno '>16 dBi' (usato 16 come minimo), HPBW 18 gradi, RF fino a 4 W (la scheda lo chiama 'ingresso' e 'uscita' in punti diversi), connettore SMP, "
         "-40..+125 C, TRL 9, massa 52.85-53 g. Polarizzazione RHCP o LHCP nelle caratteristiche, solo RHCP nelle specifiche: usata RHCP.",
         dims=[82.6, 98.0, 7.0], dim_note="Scheda EnduroSat/satsearch: 82.6 +-0.1 x 98 +-0.1 x 7 mm.", temp=[-40, 125], trl=9, family="endurosat-xband", method=METHOD_3P),
    comp("endurosat-x-band-8x12", "antenna", "EnduroSat", "X-Band 8x12 Patch Array Antenna", 0.4,
         "https://satsearch.co/products/endurosat-x-band-8x12-patch-array-antenna", "Scheda satsearch EnduroSat X-Band 8x12 Patch Array Antenna",
         ant(frequency_ranges_mhz=[[8000.0, 8400.0]], gain_dbi=24.0, beamwidth_deg=11.0, polarization="RHCP", rf_power_w_max=4.0, deployable=False)
         | {"bands": ["X"], "antenna_type": "patch_array"},
         NOTE_ES_ANT + "96 patch, guadagno '>24 dBi' (usato 24 come minimo), HPBW 8 x 11 gradi (usato 11, il piu' largo), RHCP fissa, RF fino a 4 W, connettore SMA, -40..+125 C, "
         "massa 400 g. Qualifica ECSS/GEVS dichiarata; TRL ed eredita' non indicati. Ingombro 254 x 172 x 6 mm: richiede una faccia lunga (6U o 12U) e un puntamento al nadir molto preciso "
         "(fascio stretto).",
         dims=[254.0, 172.0, 6.0], dim_note="Scheda EnduroSat/satsearch: 254 x 172 x 6 mm.", temp=[-40, 125], family="endurosat-xband", method=METHOD_3P),
    comp("endurosat-s-band-commercial", "antenna", "EnduroSat", "S-Band Antenna Commercial (patch, tipo II)", 0.081,
         "https://satsearch.co/products/endurosat-s-band-patch-antenna-type-ii", "Scheda satsearch EnduroSat S-Band Antenna Commercial (aggiornata 2026-07-14)",
         ant(frequency_ranges_mhz=[[2025.0, 2110.0]], gain_dbi=None, beamwidth_deg=70.0, polarization="RHCP/LHCP", rf_power_w_max=4.0, deployable=False)
         | {"bands": ["S"], "antenna_type": "patch"},
         NOTE_ES_ANT + "Il guadagno e' CONTRADDITTORIO nella stessa scheda ('<7 dBi' nelle specifiche tecniche, 'piu' di 7 dBi' nelle caratteristiche): lasciato non dichiarato. "
         "Patch impilato con due punti di alimentazione (RHCP o LHCP selezionabile), 2025-2110 MHz, HPBW 70 gradi, RF <4 W, -40..+125 C, TRL 9. Massa 81 g (specifiche) contro 77.4 g "
         "(caratteristiche): usati 81 g. Connettore non indicato.",
         dims=[98.0, 98.0, 14.3], dim_note="Scheda EnduroSat/satsearch: 98 +-0.2 x 98 +-0.2 x 14.3 mm.", temp=[-40, 125], trl=9, family="endurosat-sband", method=METHOD_3P),
    comp("endurosat-s-band-wideband", "antenna", "EnduroSat", "S-Band Antenna Wideband", 0.115,
         "https://endurosat.com/products/s-band-antenna-wideband", "Pagina prodotto EnduroSat S-Band Antenna Wideband (consultata 2026-10-14)",
         ant(frequency_ranges_mhz=[[2025.0, 2110.0], [2200.0, 2290.0]], gain_dbi=5.0, beamwidth_deg=70.0, polarization="RHCP/LHCP", rf_power_w_max=4.0, deployable=False)
         | {"bands": ["S"], "antenna_type": "patch"},
         "Antenna a banda larga che copre sia l'uplink (2025-2110 MHz) sia il downlink (2200-2290 MHz) in banda S, polarizzazione circolare selezionabile, guadagno '5+ dBi' (usato 5 come "
         "minimo), HPBW 70 gradi, RF fino a 4 W, montaggio X/Y o Z. Massa 96-115 g secondo la configurazione (usati 115 g). Dimensioni, interfacce e temperatura solo nel "
         "datasheet su richiesta.",
         family="endurosat-sband"),
]

GPS = [
    comp("newspace-ngps-03-422", "gps", "NewSpace Systems", "NGPS-03-422 (L1 GPS receiver, PC/104)", 0.13,
         "https://www.cubesatshop.com/wp-content/uploads/2020/11/NewSpace-GPS-Receiver_2020-10a.pdf", "NewSpace Systems GPS Receiver datasheet, versione 10a (ottobre 2020)",
         gps(constellations=["GPS"], accuracy_position_m=10.0, accuracy_basis="1-sigma", accuracy_velocity_m_s=0.25, update_rate_hz=1.0, channels=12, antenna_included=False,
             data_interfaces=["RS-422", "UART"], supply_voltage_ranges_v=[[3.3, 3.3], [5.0, 5.0]]),
         "Ricevitore hardware a 12 canali L1 (1575.42 MHz) con software modificato per quota e velocita' orbitali: posizione <10 m (1-sigma), velocita' <25 cm/s, 1 Hz, massa <130 g, "
         "potenza 1 W esclusa l'antenna attiva, alimentazione 5 e 3.3 V, RS-422 o UART TTL, connettore Nano D, ingombro 96 x 91 x 18 mm sull'impronta PC/104 (4 x M3), -10..+50 C "
         "(accettazione), 10 krad (a livello di componente). Oltre 30 unita' consegnate della famiglia NGPS-01/03. L'antenna GNSS e' un prodotto a parte (NANT-PTCL1: 54 x 54 x 14.1 mm, "
         "<80 g, <80 mW, 5 V) e NON e' inclusa nel selettore.",
         dims=[96.0, 91.0, 18.0], dim_note="Datasheet NewSpace Systems NGPS-03-422.", power=1.0, tid=10.0, temp=[-10, 50], family="newspace-ngps"),
    comp("newspace-ngps-01-422", "gps", "NewSpace Systems", "NGPS-01-422 (L1 GPS receiver, boxed)", 0.5,
         "https://www.cubesatshop.com/wp-content/uploads/2020/11/NewSpace-GPS-Receiver_2020-10a.pdf", "NewSpace Systems GPS Receiver datasheet, versione 10a (ottobre 2020)",
         gps(constellations=["GPS"], accuracy_position_m=10.0, accuracy_basis="1-sigma", accuracy_velocity_m_s=0.25, update_rate_hz=1.0, channels=12, antenna_included=False,
             data_interfaces=["RS-422"], supply_voltage_ranges_v=[[24.0, 36.0]]),
         "Versione in scatola dello stesso ricevitore: stesse prestazioni (posizione <10 m 1-sigma, velocita' <25 cm/s, 1 Hz), massa <500 g, 1.5 W esclusa l'antenna, alimentazione "
         "24-36 V non regolata (isolata), RS-422, ingombro 155 x 76 x 34 mm esclusi i connettori, 4 x M4, -10..+50 C, 10 krad. Antenna non inclusa.",
         dims=[155.0, 76.0, 34.0], dim_note="Datasheet NewSpace Systems NGPS-01-422, esclusi i connettori.", power=1.5, tid=10.0, temp=[-10, 50], family="newspace-ngps"),
    comp("skyfox-pinav-ng", "gps", "SkyFox Labs", "piNAV-NG (low-power L1 GPS receiver)", 0.024,
         "https://satcatalog.s3.amazonaws.com/components/58/SatCatalog_-_SkyFox_Labs_-_piNAV-NG_-_Datasheet.pdf", "SkyFox Labs piNAV-NG Product Datasheet rev. F (2018)",
         gps(constellations=["GPS"], accuracy_position_m=10.0, accuracy_basis="2-sigma", accuracy_velocity_m_s=0.1, ttff_cold_s=90.0, update_rate_hz=1.0, channels=15,
             antenna_included=False, data_interfaces=["UART"], supply_voltage_ranges_v=[[2.7, 3.6]]),
         "Ricevitore L1 C/A a 15 canali: accuratezza orizzontale 10 m (2-sigma) senza multipath e con HDOP <3, velocita' 10 cm/s (2-sigma), TTFF a freddo 90 s, 1 Hz, quota operativa fino a "
         "3600 km, velocita' fino a 9 km/s (modello di volo; 0.5 km/s per i modelli ingegneristici), consumo 125 mW tipico a 3.3 V, alimentazione 2.7-3.6 V, UART 3.3 V (NMEA), "
         "71.1 x 45.7 x 11 mm, 24 g, -40..+85 C. Supporta antenne attive o passive (non incluse). Componenti COTS senza circuiti rad-hard: tolleranza alle radiazioni non dichiarata.",
         dims=[71.1, 45.7, 11.0], dim_note="Datasheet SkyFox Labs piNAV-NG, incluso lo schermo.", power=0.125, temp=[-40, 85], family="skyfox-pinav"),
    comp("hyperion-gnss200", "gps", "Hyperion Technologies (AAC Hyperion)", "GNSS200", 0.003,
         "https://satcatalog.s3.amazonaws.com/components/39/SatCatalog_-_Hyperion_Technologies_-_GNSS200_-_Datasheet.pdf", "AAC Hyperion GNSS200 datasheet V2.1",
         gps(accuracy_position_m=8.0, ttff_cold_s=90.0, update_rate_hz=10.0, antenna_included=False, data_interfaces=["UART"], supply_voltage_ranges_v=[[3.25, 3.5]]),
         "Modulo ricevitore multicostellazione (costellazioni non elencate nel datasheet), 20 x 14.5 x 3.1 mm e 3 g. Accuratezza in orbita <8 m (nota 'da confermare' nel datasheet, base statistica "
         "non dichiarata), velocita' 'TBD', aggiornamento >10 Hz, TTFF <90 s con antenna attiva (<120 s con passiva; non e' indicato se a freddo), potenza 148-165 mW (157 mW tipico), "
         "3.25-3.5 V, UART TTL, -40..+85 C, tolleranza alle radiazioni >36 krad (Si). Con eredita' di volo dal 2018 (numero di missioni non dichiarato). Antenna non inclusa.",
         dims=[20.0, 14.5, 3.1], dim_note="Datasheet AAC Hyperion GNSS200.", power=0.157, tid=36.0, temp=[-40, 85], family="hyperion-gnss"),
    comp("sstl-sgr-ligo", "gps", "Surrey Satellite Technology (SSTL)", "SGR-Ligo", 0.09,
         "https://satcatalog.s3.amazonaws.com/components/68/SatCatalog_-_Surrey_Satellite_Technology_-_SGR-Ligo_-_Datasheet.pdf", "SSTL SGR-Ligo Space GNSS Receiver datasheet (SSTL#0295011)",
         gps(constellations=["GPS"], accuracy_position_m=5.0, accuracy_velocity_m_s=0.1, ttff_cold_s=90.0, update_rate_hz=None, channels=24, antenna_included=False,
             data_interfaces=["UART", "CAN", "I2C"], supply_voltage_ranges_v=[[3.3, 3.3], [5.0, 5.0]]),
         "Ricevitore GNSS sull'impronta PC/104 con 24 canali: GPS L1 C/A (GLONASS G1 e Galileo E1 opzionali, non incluse nella lista), posizione tipica 5 m e velocita' 10 cm/s in un'orbita polare "
         "a 680 km con puntamento alla Terra (base statistica non dichiarata), TTFF <90 s con NVRAM, tempo UTC 100 ns, supporta 1-2 antenne attive o passive (non incluse), <0.5 W a 5 V "
         "(<0.4 W a 3.3 V in modo a 12 canali), 3.3 o 5 V, UART/CAN/I2C, 92 x 87 x 12 mm, 90 g, >5 krad (nucleo provato a 10 krad), -20..+50 C, mitigazione SEE/SEL. Datasheet del 2019: "
         "'in lancio su due CubeSat nel 2019'.",
         dims=[92.0, 87.0, 12.0], dim_note="Datasheet SSTL SGR-Ligo.", power=0.5, tid=5.0, temp=[-20, 50], family="sstl-sgr"),
    comp("spacemanic-celeste", "gps", "Spacemanic", "Celeste (multi-constellation GNSS)", 0.025,
         "https://spacemanic.com/products/celeste/", "Pagina prodotto Spacemanic Celeste (consultata 2026-10-14)",
         gps(constellations=["GPS", "Galileo", "BeiDou", "GLONASS"], update_rate_hz=1.0, antenna_included=False, data_interfaces=["I2C", "RS-485", "CAN", "UART"],
             supply_voltage_ranges_v=[[3.3, 3.3], [5.0, 5.0]]),
         "Ricevitore multicostellazione (GPS L1, Galileo E1, BeiDou B1, GLONASS G1: opzioni di configurazione), 1 Hz tipico (25 Hz massimo), accuratezza temporale 5 ns, velocita' "
         "fino a 8 km/s tipici (10 km/s massimi), 67 x 42 x 7.5 mm, 25 g, 3.3 V (5 V per il CAN), 250 mW medi, interfacce CSP I2C/RS485/CAN e UART di debug, -40..+85 C, ITAR free. "
         "Eredita' di volo: oltre 5 missioni CubeSat (LASARSat, CroCube, GRBBeta, Veronika, GRBAlpha). L'accuratezza di posizione, il TTFF, i canali e la TID non sono nella pagina. "
         "Antenna non inclusa (il fornitore indica come prodotto correlato un'antenna patch 'Zenith').",
         dims=[67.0, 42.0, 7.5], dim_note="Pagina prodotto Spacemanic Celeste.", power=0.25, heritage=5, temp=[-40, 85], family="spacemanic-celeste", method=METHOD_3P),
]

if __name__ == "__main__":
    cat_path = PROJ / "data" / "catalog.json"
    cat = json.loads(cat_path.read_text(encoding="utf-8"))
    new = PROPULSION + ANTENNAS + GPS
    new_ids = {c["id"] for c in new}
    cat["components"] = [c for c in cat["components"] if c["id"] not in new_ids] + new
    cat_path.write_text(json.dumps(cat, indent=1, ensure_ascii=False), encoding="utf-8")
    print(len(PROPULSION), "propulsori,", len(ANTENNAS), "antenne,", len(GPS), "GNSS;", len(cat["components"]), "componenti in totale")

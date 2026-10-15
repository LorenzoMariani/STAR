"""Genera data/catalog.json. Ogni valore e' trascritto dal documento indicato in `source`.
Convenzione: None = non dichiarato dal fornitore (non stimato)."""
import json, sys

RET = "2026-10-13"
ES_CAT = ("https://endurosat.com/wp-content/uploads/2022/02/Endurosat_Product_Catalogue_02_22.pdf",
          "EnduroSat Product Catalogue 02/2022")
ISIS_STR = ("https://www.cubesatshop.com/wp-content/uploads/2016/06/ISIS-CubeSat-Structures-Brochure-v1.pdf",
            "ISIS CubeSat Structures Brochure v1")
ISIS_PV = ("https://www.cubesatshop.com/wp-content/uploads/2016/06/ISIS-Solar-Panels-Brochure-v1.pdf",
           "ISIS Solar Panels Brochure v1")
ISIS_TRX = ("https://www.cubesatshop.com/wp-content/uploads/2016/06/VHF-UHF-Full-Duplex-Transceiver-Brochure-web-1.pdf",
            "ISIS VHF uplink/UHF downlink transceiver brochure")
AAC_OPT = ("https://www.aac-clyde.space/wp-content/uploads/2021/10/AAC_DataSheet_Optimus.pdf",
           "AAC Clyde Space OPTIMUS datasheet (release 28 Jul 2020)")
AAC_SB = ("https://www.aac-clyde.space/wp-content/uploads/2021/11/AAC_DataSheet_Starbuck-Nano.pdf",
          "AAC Clyde Space STARBUCK-NANO datasheet (release 28 Jul 2020)")
CUBESPACE = ("https://www.cubesatshop.com/wp-content/uploads/2023/05/GEN-1-ADCS-Jan-2023-web.pdf",
             "CubeSpace GEN 1 closed-loop ADCS brochure (Jan 2023)")
CDS = "CubeSat Design Specification Rev. 14.1, Table 1 (https://www.nasa.gov/wp-content/uploads/2018/01/cubesatdesignspecificationrev14_12022-02-09.pdf)"


def es_page(slug, title):
    return (f"https://www.endurosat.com/products/{slug}", f"Pagina prodotto EnduroSat '{title}'")


out = []


PRICE_ASOF = {"Pumpkin": "2022-04-09", "CubeSpace": "2023-01"}
# True = ricetrasmettitore, False = solo trasmettitore (dal nome e dalla descrizione del fornitore)
HAS_RX = {"endurosat-uhf": True, "endurosat-sband": True, "endurosat-xband": False, "isis-trxvu": True,
          "gomspace-nanocom-ax100": True, "nanoavionics-satcom-uhf": True, "satlab-srs-3": True, "satlab-srs-4": True,
          "satlab-srx-8": False, "aac-pulsar-utrx": True, "aac-pulsar-vutrx": True, "aac-pulsar-stx": False,
          "aac-pulsar-hstx": False, "aac-trx-u": True, "aac-quasar-strx": True,
          "endurosat-sband-max": True, "endurosat-xband-sdr": None}


def add(cat, cid, vendor, name, mass, specs, src, **kw):
    if cat == "comms":
        specs = {**specs, "has_receiver": HAS_RX[cid]}
    if "price_usd" in kw:  # compatibilita' con le voci gia' scritte
        kw["price"] = {"amount": kw.pop("price_usd"), "currency": "USD", "as_of": PRICE_ASOF[vendor]}
    out.append({"id": cid, "category": cat, "vendor": vendor, "name": name, "mass_kg": mass, **kw,
                "source": {"url": src[0], "document": src[1], "retrieved": RET, "verified": False,
                           "method": "trascritto da documento pubblico del fornitore; da controllare manualmente"},
                "specs": specs})


def struct(ff, mass, faces):
    return dict(form_factor_u=ff, max_total_mass_kg={3: 6.0, 6: 12.0}[ff], internal_volume_u=None, panel_faces=faces)


GEOM = ("max_total_mass_kg dalla " + CDS + ", non dal fornitore. panel_faces derivato dalla geometria della struttura, non dal fornitore. ")

# ---------------- STRUTTURE ----------------
add("structure", "endurosat-structure-3u", "EnduroSat", "3U Structure", 0.290,
    struct(3, 0.29, {"3U": 4}), ES_CAT, trl=None,
    notes=GEOM + "Dimensioni 100x100x340.5 mm, Al 6082, massa complessiva 290 g (catalogo p.20).")
add("structure", "endurosat-structure-6u", "EnduroSat", "6U Structure", 0.850,
    struct(6, 0.85, {"6U": 2, "3U": 2}), ES_CAT,
    notes=GEOM + "Dimensioni 100x226.3x366 mm, Al 6082, massa complessiva 850 g (catalogo p.20).")
add("structure", "isis-structure-3u", "ISISpace", "3-Unit CubeSat Structure", 0.304,
    struct(3, 0.304, {"3U": 4}), ISIS_STR,
    notes=GEOM + "Massa 304 g = struttura primaria (243 g) + secondaria. Ingombro 100x100x340.5 mm. Eredita' di volo dichiarata dal 2013.")
add("structure", "isis-structure-6u", "ISISpace", "6-Unit CubeSat Structure", 1.100,
    struct(6, 1.1, {"6U": 2, "3U": 2}), ISIS_STR,
    notes=GEOM + "Massa 1100 g = struttura primaria (900 g) + secondaria. Ingombro 100x226.3x340.5 mm. Eredita' di volo dichiarata dal 2015.")

# ---------------- OBC ----------------
add("obc", "endurosat-obc", "EnduroSat", "Onboard Computer", 0.123,
    dict(data_interfaces=["CAN", "RS-422", "RS-485", "SPI", "I2C", "UART", "Ethernet"], supply_voltage_ranges_v=[[12, 12]]),
    es_page("onboard-computer", "Onboard Computer"),
    notes="123 g (173 g con ricevitore GNSS). ARM Cortex M7, 2 MB flash, 2x16 GB SD NAND, 2x2 MB FRAM. "
          "Controllo: 2x CAN 1 Mbps (CSPES); payload: CAN-FD, RS-422, RS-485, SPI, I2C, UART, 100BASE-TX. "
          "Il catalogo EnduroSat 02/2022 riportava 130 g e interfacce diverse (generazione precedente): qui si usa la pagina corrente. "
          "Consumo, TID e temperatura non dichiarati.")

# ---------------- EPS ----------------
add("eps", "endurosat-eps-i", "EnduroSat", "EPS I (con batteria 10.2 Wh)", 0.208,
    dict(compatible_form_factors_u=None, pv_channels=3, pv_voltage_v=None, pv_power_w_max=None, battery_voltage_v=None,
         battery_families=None, integrated_battery_wh=10.2, integrated_battery_voltage_v=3.7,
         output_voltage_ranges_v=[[3.3, 3.3], [5, 5]], output_power_w_max=None, data_interfaces=["UART", "I2C", "USB"],
         efficiency=None), ES_CAT,
    notes="Massa 208 g comprende la batteria standard. Uscite: 3.3 V, 5 V e battery raw. Corrente massima 1.8 A per canale PV. "
          "La riga 'Current Limitation' del catalogo riporta 'up to 5.5 V' (significato ambiguo, non trascritto). "
          "Catalogo 02/2022: potrebbe essere superato.")
add("eps", "endurosat-eps-ii", "EnduroSat", "EPS II (con batteria 84 Wh)", 1.280,
    dict(compatible_form_factors_u=None, pv_channels=3, pv_voltage_v=None, pv_power_w_max=None, battery_voltage_v=None,
         battery_families=None, integrated_battery_wh=84.0, integrated_battery_voltage_v=17.8,
         output_voltage_ranges_v=[[3.3, 3.3], [5, 5], [6, 12]], output_power_w_max=None, data_interfaces=["RS-485", "USB"],
         efficiency=None), ES_CAT,
    notes="Massa 1280 g comprende la batteria standard. Corrente massima 4 A per canale PV, connettori PV ridondanti, "
          "uscite 3.3 V x2, 5 V x2 (ridondanti), battery raw, uscita programmabile 6-12 V. "
          "La riga 'Current Limitation' riporta '10-36 V' (ambiguo, non trascritto). Catalogo 02/2022: potrebbe essere superato.")
add("eps", "aac-starbuck-nano", "AAC Clyde Space", "STARBUCK-NANO", 0.086,
    dict(compatible_form_factors_u=[2, 3], pv_channels=None, pv_voltage_v=[8.2, 8.2], pv_power_w_max=None,
         battery_voltage_v=None, battery_families=["aac-optimus"], integrated_battery_wh=None,
         integrated_battery_voltage_v=None, output_voltage_ranges_v=[[3.3, 3.3], [5, 5], [12, 12]],
         output_power_w_max=None, data_interfaces=["I2C"], efficiency=None), AAC_SB,
    tid_krad=10, temp_op_c=[-40, 85], family="aac-starbuck",
    notes="Versione NANO: 2U-3U con pannelli body-mounted, batteria esterna (variante NANO-PICO con batteria integrata 10/20 Wh e NANO-PLUS 3-12U non inclusi). "
          "8.2 V = tensione di massima potenza; 'Max. Battery Voltage' 8.2 V. 10 Latching Current Limiter configurabili. "
          "Datasheet: compatibile con batterie OPTIMUS e pannelli PHOTON. Vita di progetto 5 anni in LEO.")

# ---------------- BATTERIE ----------------
OPT_NOTE = ("Litio-polimero, 2S; carica massima 8.4 V, scarica minima 6.2 V (tipici: fine carica 8.26 V). Riscaldatori integrati. "
            "Ottimizzata per LEO fino a 850 km; qualificata NASA EP-Wi-032. Ingombro 95.89 x 90.17 mm, altezza {h} mm. "
            "'Over 100 missions' dichiarate per la famiglia. DoD e cicli non dichiarati.")
for wh, mass, amp, h in ((30, 0.268, 1.95, 21.55), (40, 0.335, 2.6, 27.35), (80, 0.670, 5.2, 56.94)):
    add("battery", f"aac-optimus-{wh}", "AAC Clyde Space", f"OPTIMUS-{wh}", mass,
        dict(voltage_range_v=[6.2, 8.4], capacity_wh=float(wh), max_discharge_a=amp, max_dod=None, cycle_life=None),
        AAC_OPT, family="aac-optimus", temp_op_c=[-10, 50], flight_heritage=100, notes=OPT_NOTE.format(h=h))

# ---------------- PANNELLI ----------------
add("solar_panel", "endurosat-solar-3u", "EnduroSat", "3U Solar Panel", 0.147,
    dict(face="3U", peak_power_w=8.4, voltage_options_v=None, open_circuit_voltage_v=17.5, degradation_per_year=None),
    es_page("3u-solar-panel", "3U Solar Panel"),
    notes="7 celle triple giunzione, efficienza BOL 30+%, EOL 29+%. Tensione massima 17.5 V (7 celle), corrente massima 512 mA; "
          "configurazioni in parallelo possibili. Vita di progetto 5 anni.")
add("solar_panel", "endurosat-solar-6u", "EnduroSat", "6U Solar Panel", 0.392,
    dict(face="6U", peak_power_w=19.2, voltage_options_v=None, open_circuit_voltage_v=39.8, degradation_per_year=None),
    es_page("6u-solar-panel", "6U Solar Panel"),
    notes="16 celle (16S1P), tensione massima 39.8 V. Il catalogo 02/2022 riporta 19.4 W invece di 19.2 W: si usa la pagina corrente.")
add("solar_panel", "isis-solar-3u", "ISISpace", "Solar Panel 3U", 0.150,
    dict(face="3U", peak_power_w=6.9, voltage_options_v=[3, 5, 8], open_circuit_voltage_v=None, degradation_per_year=None), ISIS_PV,
    temp_op_c=[-40, 125],
    notes="Celle GaAs AZUR Space, efficienza 30%. Tensione 3 V standard (5 V e 8 V su richiesta). Massa dichiarata '150 g, dipende dalla configurazione'. "
          "Tolleranza alle radiazioni: 'minimo 2 anni in LEO' (nessun valore di TID).")

# ---------------- COMUNICAZIONI ----------------
add("comms", "endurosat-uhf", "EnduroSat", "UHF Transceiver", 0.195,
    dict(band="UHF", data_rate_kbps_max=19.6, power_w_idle=1.2, power_w_tx=5.5, data_interfaces=["CAN", "UART"],
         supply_voltage_ranges_v=[[5, 5]]),
    es_page("uhf-transceiver-ii", "UHF Transceiver"),
    notes="Potenza DC 5.5 W in TX a 33 dBm, 1.2 W idle; RF 30 dBm (commerciale) / 33 dBm (radioamatori); data rate 1.2-19.6 kbps. "
          "Il catalogo 02/2022 indicava 94 g e 1 W RF per 'UHF Transceiver II' (19.2 kbps): prodotto/versione diversi, qui si usa la pagina corrente.")
add("comms", "endurosat-sband", "EnduroSat", "S-Band Transceiver", 0.320,
    dict(band="S", data_rate_kbps_max=125.0, power_w_idle=1.2, power_w_tx=11.0, data_interfaces=["CAN"],
         supply_voltage_ranges_v=[[11, 28]]),
    es_page("s-band-transmitter", "S-Band Transceiver"),
    notes="Massa 320 g +-5%. Consumo 1.2 W (solo Rx, 12 V), 11 W max a 33 dBm. RF 24-33 dBm. Il catalogo 02/2022 riportava un S-band TX da 20 Mbps (prodotto diverso).")
add("comms", "endurosat-xband", "EnduroSat", "X-Band Transmitter", 0.396,
    dict(band="X", data_rate_kbps_max=150000.0, power_w_idle=None, power_w_tx=None, data_interfaces=["CAN", "Ethernet"],
         supply_voltage_ranges_v=[[10, 28]]),
    es_page("x-band-transmitter", "X-Band Transmitter"), tid_krad=25,
    notes="Massa 396 g +-5%. Data rate fino a 150 Mbps (DVB-S2), RF 26-33 dBm. Qualificato -35..+65 C, >=25 krad TID, GEVS 14.1 g RMS "
          "(valori di qualifica, non range operativo). Consumo DC non dichiarato.")
add("comms", "isis-trxvu", "ISISpace", "VHF/UHF Duplex Transceiver (TRXVU)", 0.075,
    dict(band="VHF/UHF", data_rate_kbps_max=9.6, power_w_idle=0.48, power_w_tx=4.0, data_interfaces=["I2C"],
         supply_voltage_ranges_v=[[6.5, 20]]),
    ISIS_TRX, temp_op_c=[-20, 60],
    notes="Uplink VHF 145.8-146 MHz, downlink UHF 435-438 MHz; TX 27 dBm; 1200-9600 bps. Eredita' di volo dichiarata dal 2016. 90x96x15 mm.")

# ---------------- ADCS ----------------
add("adcs", "cubespace-cubeadcs-3axis-small", "CubeSpace", "CubeADCS 3-Axis Small", 0.500,
    dict(pointing_accuracy_deg=None, data_interfaces=None, supply_voltage_ranges_v=None), CUBESPACE,
    temp_op_c=[-10, 60], family="cubeadcs", price_usd=37000,
    notes="Massa '<500 g'. 3 ruote CubeWheel Small, 2 CubeTorquer Small, 1 CubeCoil; satelliti tipici 2U-3U; 90x96x57 mm. "
          "Listino base USD 37,000 (sensori fine sun / star tracker / magnetometro ridondante opzionali). "
          "Accuratezza di puntamento non dichiarata (dipende dai sensori e dalla missione), consumo non dichiarato.")
add("adcs", "cubespace-cubeadcs-ymomentum-small", "CubeSpace", "CubeADCS Y-Momentum Small", 0.300,
    dict(pointing_accuracy_deg=None, data_interfaces=None, supply_voltage_ranges_v=None), CUBESPACE,
    temp_op_c=[-10, 60], family="cubeadcs", price_usd=26780,
    notes="Massa '<300 g'. Una ruota + magnetorquer: puntamento al nadir, non 3 assi completi; taglie 2U-16U; 90x96x48 mm. "
          "Listino base USD 26,780. Accuratezza e consumo non dichiarati.")

# ======================= GomSpace =======================
GS = "https://gomspace.com/wp-content/uploads/"
GS_NOTE = "Il datasheet riporta un avviso di confidenzialita' GomSpace: non ridistribuire questi dati senza consenso. "
gs_a3200 = (GS + "2025/09/NanoMind_A3200.pdf", "GomSpace NanoMind A3200 Datasheet DS 1006901 rev 1.17 (29 Jan 2021)")
gs_ax100 = (GS + "2025/09/gs-ds-nanocom-ax100.pdf", "GomSpace NanoCom AX100 Datasheet DS 1013823 rev 3.7 (29 Nov 2019)")
gs_p60 = (GS + "2025/09/gs-ds-nanopower-p60-dock-30.pdf", "GomSpace NanoPower P60 Dock Datasheet DS 1013119 rev 3.0 (29 Nov 2024) + pagina prodotto NanoPower P60")
gs_p80 = (GS + "2025/09/Data-Sheet-NanoPower-P80.pdf", "GomSpace NanoPower P80 Datasheet DS 1047423 rev 2.3.0 (24 Sep 2024) + pagina prodotto NanoPower P80")
gs_bpx = (GS + "2025/09/gs-ds-nanopower-BPX-100-Wh-1076870-1.1.0.pdf", "GomSpace NanoPower BPX 100 Wh Datasheet DS 1076870 rev 1.1.0 (21 Apr 2026)")
gs_bp8 = (GS + "2025/08/gs-ds-nanopower-bp8-100-Wh-2.pdf", "GomSpace NanoPower BP8 100 Wh Datasheet DS 1069134 rev 1.2.0")
gs_dsp = (GS + "2025/09/Datasheet-NanoPower-Deployable-Solar-Panel.pdf", "GomSpace NanoPower DSP Datasheet DS 1018088 rev 3.2 (25 Aug 2025) + pagina prodotto")
gs_str = (GS + "2025/09/gs-ds-nanostructure-6u-Mk2-1060779-12-EXT.pdf", "GomSpace Nanostructure 6U MK2 Datasheet DS 1060779 + pagina prodotto Nanostruct 6U")

add("structure", "gomspace-nanostruct-6u", "GomSpace", "Nanostruct 6U", 0.665,
    struct(6, 0.665, {"6U": 2, "3U": 2}), gs_str,
    notes=GEOM + "Massa 665 g = struttura di default (2 telai + 4 angolari, con viti e perni). Ingombro 340.5x226.3x100 mm, Al 7075-T7351, "
                 "fino a 3U per il payload, 4 killswitch retrattili. " + GS_NOTE.replace("Il datasheet riporta", "Verifica se il datasheet riporta"))
add("obc", "gomspace-nanomind-a3200", "GomSpace", "NanoMind A3200", 0.024,
    dict(data_interfaces=["I2C", "CAN", "UART", "SPI"], supply_voltage_ranges_v=[[3.2, 3.4]]), gs_a3200,
    power_w=0.17, temp_op_c=[-30, 85],
    notes=GS_NOTE + "MCU AVR32 AT32UC3C (8-64 MHz), 512 KB flash + 128 MB NOR, 32 MB SDRAM, 32 kB FRAM. Include magnetometro, giroscopio e 3 driver PWM per magnetorquer. "
          "Consumo a 3.3 V: 0.17 W tipico, 0.9 W massimo (con flash esterna). 65x40x7.1 mm. CAN fino a 1 Mbit/s. "
          "La pagina prodotto rimanda alla rev 2.0 (2025), non verificata: qui rev 1.17 del 2021. TID non dichiarata.")
add("eps", "gomspace-nanopower-p60", "GomSpace", "NanoPower P60 (dock + 1 ACU + 1 PDU)", 0.181,
    dict(compatible_form_factors_u=None, pv_channels=6, pv_voltage_v=None, pv_power_w_max=128.0, battery_voltage_v=[12.0, 33.6],
         battery_families=None, integrated_battery_wh=None, integrated_battery_voltage_v=None,
         output_voltage_ranges_v=[[3.3, 3.3], [5, 5], [3.3, 18]], output_power_w_max=128.0,
         data_interfaces=["CAN", "I2C", "UART", "RS-422"], efficiency=None), gs_p60,
    temp_op_c=[-35, 85],
    notes=GS_NOTE + "Massa: dock 80 g + 54 g per ACU + 47 g per PDU (configurazione standard 1 ACU 6 canali MPPT, 1 PDU 9 canali). "
          "Ingressi PV fino a 25 V e 2 A per canale. Batteria raccomandata 16 V (12-16.8 V) o 32 V (24-33.6 V): il range [12, 33.6] unisce le due configurazioni. "
          "Uscite: 3.3 V e 5 V sul connettore PC104, 3 tensioni configurabili 3.3-18 V sul PDU, tensione batteria grezza. 128 W in uscita con Vbat = 32 V. "
          "Abbinato dal fornitore alle batterie BPX e BP4. Consumo proprio ed efficienza non dichiarati nella documentazione letta.")
add("eps", "gomspace-nanopower-p80", "GomSpace", "NanoPower P80 (3 moduli)", 0.3608,
    dict(compatible_form_factors_u=[6, 8, 12, 16], pv_channels=12, pv_voltage_v=None, pv_power_w_max=300.0, battery_voltage_v=[28.8, 33.6],
         battery_families=None, integrated_battery_wh=None, integrated_battery_voltage_v=None,
         output_voltage_ranges_v=[[3.3, 3.3], [5, 5], [12, 12], [16, 21.8]], output_power_w_max=300.0,
         data_interfaces=["CAN", "I2C"], efficiency=None), gs_p80,
    power_w=1.25, temp_op_c=[-40, 85],
    notes=GS_NOTE + "Massa 360.8 g con 3 moduli (619.6 g con 5), dalla pagina prodotto. Consumo a vuoto: PMU 0.5 W + PDU 0.45 W + ACU 0.3 W. "
          "12 canali PV (1.1 A ciascuno, VOC max 25 V), 300 W max, tensione batteria in ingresso 28.8-33.6 V. "
          "Uscite: 3.3/5/12 V, 16-21.8 V e batteria grezza. Efficienza 'fino al 96%' (valore di picco, non trascritto). "
          "La pagina prodotto riporta cifre di canali incoerenti tra sezioni (12 vs 48 PV, 24 vs 96 uscite): si usa il datasheet. Taglie '6U e oltre'.")

add("battery", "gomspace-bpx-100wh-16v", "GomSpace", "NanoPower BPX 100 Wh (4S-2P, 16 V)", 0.500,
    dict(voltage_range_v=[11.8, 16.8], capacity_wh=86.0, max_discharge_a=6.0, max_dod=None, cycle_life=None), gs_bpx,
    temp_op_c=[-20, 60], family="gomspace-bpx",
    notes=GS_NOTE + "Capacita' nominale 100 Wh; 86-89 Wh nel range di tensione raccomandato (valore usato: 86). 8 celle 18650 da 3500 mAh. "
          "Scarica -20..60 C, carica 0..45 C. Riscaldatore da 6 W. 93x86x41 mm. Configurazione 8S-1P 32 V disponibile come componente separato.")
add("battery", "gomspace-bpx-100wh-32v", "GomSpace", "NanoPower BPX 100 Wh (8S-1P, 32 V)", 0.500,
    dict(voltage_range_v=[23.6, 33.6], capacity_wh=86.0, max_discharge_a=6.0, max_dod=None, cycle_life=None), gs_bpx,
    temp_op_c=[-20, 60], family="gomspace-bpx",
    notes=GS_NOTE + "Come la versione 16 V; tensione nominale 28.8 V, range raccomandato 23.6-32.0 V, carica fino a 33.6 V.")
add("battery", "gomspace-bp8-100wh", "GomSpace", "NanoPower BP8 100 Wh", 0.486,
    dict(voltage_range_v=[23.6, 33.6], capacity_wh=86.0, max_discharge_a=4.0, max_dod=None, cycle_life=None), gs_bp8,
    temp_op_c=[-20, 45], family="gomspace-bp8",
    notes="8S-1P, 18650 da 3500 mAh; capacita' nominale 100 Wh (86 Wh nel range raccomandato, valore usato). Scarica 4 A, carica 3.4 A, "
          "protezioni OVLO/UVLO/sovracorrente integrate. Scarica -20..60 C, carica -10..45 C (si usa l'intervallo piu' stretto). 94.8x95x42 mm.")

add("solar_panel", "gomspace-dsp-135-mk2", "GomSpace", "NanoPower DSP 135 deg MK2 (deployable)", 0.449,
    dict(face="3U", peak_power_w=18.0, voltage_options_v=[14.1], open_circuit_voltage_v=None, degradation_per_year=None), gs_dsp,
    temp_op_c=[-40, 85],
    notes=GS_NOTE + "Pannello dispiegabile sul lato di un 3U o 6U (richiede spazio di dispiegamento): 18 celle (3 stringhe da 6 in serie, parallelo di default), 449 g. "
          "'Fino a 18 W' dalla pagina prodotto; il datasheet calcola 21.15 W al meglio (14.1 V, 1.5 A) a inizio vita. Celle 30% con 1.135-1.2 W ciascuna. "
          "Le varianti 90 deg e 135 deg reverse (390 g, meno celle) non sono incluse. Temperatura: elettronica -40..85 C.")

# ---- comunicazioni GomSpace ----
add("comms", "gomspace-nanocom-ax100", "GomSpace", "NanoCom AX100", 0.0245,
    dict(band="UHF", data_rate_kbps_max=38.4, power_w_idle=0.18, power_w_tx=2.64, data_interfaces=["I2C", "UART", "CAN"],
         supply_voltage_ranges_v=[[3.3, 3.3]]), gs_ax100,
    temp_op_c=[-30, 85],
    notes=GS_NOTE + "Ricetrasmettitore half-duplex GFSK/GMSK; potenza RF 24-30 dBm regolabile (29-31 dBm tipico a 30 dBm), sensibilita' fino a -137 dBm a 100 bps; "
          "bit rate 0.1-38.4 kbps (19.2 kbps entro 25 kHz). Consumo a 3.3 V: RX 55 mA tipico (0.18 W), TX 800 mA tipico a potenza massima (2.64 W). "
          "Versioni UHF 430-440 MHz e UHF Low 395-405 MHz. 65x40x6.5 mm.")

# ======================= Pumpkin =======================
PK = "https://www.cubesatkit.com/docs/datasheet/"
PK_PRICE = "Listino Pumpkin PL-1 del 9 aprile 2022 (MSRP in USD): http://www.pumpkininc.com/content/doc/forms/pricelist.pdf. "
PK_OLD = "Datasheet datato: i prodotti CubeSat Kit sono di generazione precedente (documenti 2010-2014), verificare la disponibilita' attuale. "
pk_mb = (PK + "DS_CSK_MB_710-00484-E.pdf", "Pumpkin CubeSat Kit Motherboard 710-00484 Rev E (doc Rev A, mar 2012) + PPM A1 710-00485 Rev B (doc Rev C, gen 2010)")
pk_leps = (PK + "DS_CSK_Linear_EPS_711-00338-D.pdf", "Pumpkin CubeSat Kit Linear EPS 711-00338 Rev D (doc Rev F, lug 2012)")
pk_bm1 = (PK + "DS_CSK_BM_1_710-01006-A.pdf", "Pumpkin CubeSat Kit Battery Module 1 (BM 1) 710-01006 Rev A (doc Rev B, feb 2014)")
pk_mai100 = (PK + "DS_CSK_ADACS_634-00412-A.pdf", "Pumpkin/MAI MAI-100 ADACS 634-00412 (doc Rev G, apr 2011)")
pk_mai200 = (PK + "DS_CSK_ADACS_634-00458-A.pdf", "Pumpkin/MAI MAI-200 ADACS 634-00458 (doc Rev G, apr 2011)")

add("obc", "pumpkin-csk-mb-ppma1", "Pumpkin", "CubeSat Kit Motherboard + PPM A1 (MSP430F1612)", 0.088,
    dict(data_interfaces=["I2C", "SPI", "UART", "USB"], supply_voltage_ranges_v=[[5, 5]]), pk_mb,
    price_usd=2230, temp_op_c=[-40, 85],
    notes=PK_PRICE + PK_OLD + "Massa 88 g = motherboard con PPM A1 montato e minuteria (103 g con estensori del connettore e distanziali per MHX). "
          "Prezzo = MB 1,575 + PPM A1 655 USD. MCU TI MSP430F1612 (55 KB programma, 5 KB SRAM), 2 SCI (UART/SPI/I2C), RTC I2C, presa SD, USB 2.0 device, presa per transceiver Microhard MHX. "
          "Alimentazione +5 V dal CubeSat Kit Bus (PPM a 3.3 V). Corrente: PPM A1 3 mA in LPM0, MB 0.5 mA tipici: il consumo a pieno regime non e' dichiarato, quindi power_w e' null. TID non dichiarata.")

# --- altre combinazioni Motherboard + PPM e FM430 ---
MB_PPM_NOTE = (PK_PRICE + PK_OLD + "Massa = motherboard con minuteria per PPM corto (77 g, datasheet MB) + massa del PPM ({ppm} g); "
               "per il PPM A1 il datasheet MB riporta direttamente 88 g. Prezzo = MB 1,575 + PPM 655 USD. Come per il PPM A1: +5 V dal CubeSat Kit Bus, "
               "temperatura -40..85 C, RTC I2C, presa SD, USB 2.0, presa MHX; consumo a pieno regime non dichiarato (power_w null). TID non dichiarata. {extra}")
for tag, slug, ppm_g, mcu, extra, ifaces in (
        ("A2", "ppma2", 11, "TI MSP430F1611 (50 KB programma, 10 KB SRAM)",
         "PPM A2 (710-00486, doc Rev C, gen 2010): 2 SCI (UART/SPI/I2C), ADC 12 bit, DAC 12 bit; corrente 3 mA tipici in LPM0 a 3.3 V.", ["I2C", "SPI", "UART", "USB"]),
        ("A3", "ppma3", 11, "TI MSP430F2618 (116 KB programma, 8 KB SRAM)",
         "PPM A3 (710-00516, doc Rev D, set 2010): 2 USCI_A (UART/SPI) e 2 USCI_B (I2C/SPI); corrente 3 mA tipici in LPM0 a 3.3 V.", ["I2C", "SPI", "UART", "USB"]),
        ("B1", "ppmb1", 16, "Silicon Labs C8051F120 8 bit (128 KB programma, 8448 B SRAM + 128 KB SRAM esterna, fino a 100 MHz)",
         "PPM B1 (710-00487, doc Rev B, ago 2009): 2 UART, 1 SPI, 1 I2C; correnti 'TBD' nel datasheet. Il listino lo descrive con 256 KB di SRAM.", ["I2C", "SPI", "UART", "USB"]),
        ("D1", "ppmd1", 17, "Microchip PIC24FJ256GA110 16 bit (256 KB programma, 16 KB SRAM, 64 Mbit flash SPI, fino a 16 MIPS)",
         "PPM D1 (710-00527, doc Rev E, ott 2010): 4 UART, 3 SPI, 3 I2C; corrente tipica 20 mA.", ["I2C", "SPI", "UART", "USB"]),
        ("D2", "ppmd2", 17, "Microchip dsPIC33FJ256GP710 16 bit (256 KB programma, 30 KB SRAM, 64 Mbit flash SPI, fino a 40 MIPS)",
         "PPM D2 (710-00528, doc Rev H, ott 2010): 2 UART, 2 SPI, 2 I2C e 2 ECAN del MCU (CAN non registrato tra le interfacce: il datasheet non dice se e' esposto sul CubeSat Kit Bus); corrente tipica 20 mA.", ["I2C", "SPI", "UART", "USB"])):
    add("obc", f"pumpkin-csk-mb-{slug}", "Pumpkin", f"CubeSat Kit Motherboard + PPM {tag}", round((77 + ppm_g) / 1000, 3),
        dict(data_interfaces=ifaces, supply_voltage_ranges_v=[[5, 5]]),
        (PK + f"DS_CSK_PPM_{tag}_" + {"A2": "710-00486-B", "A3": "710-00516-B", "B1": "710-00487-A", "D1": "710-00527-A", "D2": "710-00528-A"}[tag] + ".pdf",
         f"Pumpkin CubeSat Kit PPM {tag} + Motherboard 710-00484 Rev E (doc Rev A, mar 2012)"),
        price_usd=2230, temp_op_c=[-40, 85],
        notes=f"MCU {mcu}. " + MB_PPM_NOTE.format(ppm=ppm_g, extra=extra))
add("obc", "pumpkin-fm430", "Pumpkin", "CubeSat Kit FM430 Flight Module", 0.074,
    dict(data_interfaces=["I2C", "SPI", "UART", "USB"], supply_voltage_ranges_v=[[5, 5]]),
    (PK + "DS_CSK_FM430_710-00252-C.pdf", "Pumpkin CubeSat Kit FM430 Flight Module 710-00252 Rev C (doc Rev J, giu 2008)"),
    temp_op_c=[-40, 85], status="nla",
    notes=PK_OLD + "Segnalato come obsoleto nell'indice dei datasheet di cubesatkit.com (status nla); sostituito da Motherboard + PPM. "
          "Single-board computer con MSP430 a 16 bit (50-60 KB flash, 2-10 KB RAM), 2 USART, 2 SPI, 1 I2C, ADC/DAC 12 bit, presa SD, USB 2.0. "
          "Massa 74 g senza standoff MHX (90 g con standoff e estensore del connettore). +5 V singolo, corrente tipica 2 mA a 3.3 V (consumo a pieno regime non dichiarato). Nessun prezzo nel listino 2022. TID non dichiarata.")

for wh, mass, price, opt in ((11.0, 0.155, 980, "/00"), (22.0, 0.210, 1145, "/01")):
    add("eps", f"pumpkin-linear-eps-{int(wh)}wh", "Pumpkin", f"Linear EPS {opt} ({int(wh)} Wh)", mass,
        dict(compatible_form_factors_u=None, pv_channels=0, pv_voltage_v=None, pv_power_w_max=None, battery_voltage_v=None,
             battery_families=None, integrated_battery_wh=wh, integrated_battery_voltage_v=7.4,
             output_voltage_ranges_v=[[3.3, 3.3], [5, 5]], output_power_w_max=None, data_interfaces=["I2C"], efficiency=None), pk_leps,
        price_usd=price, temp_op_c=[-40, 85],
        notes=PK_PRICE + PK_OLD + "NON HA INGRESSI SOLARI: la batteria si ricarica solo da USB (+5 V esterno), quindi non e' utilizzabile per una missione in orbita senza altra fonte (pv_channels = 0). "
              "Batterie iPod Li-Po da 1500 mAh, 2S (7.4 V nominale, derivato dal datasheet: 6-8.2 V non regolati). Regolatori lineari LDO +5 V (trip 1 A) e +3.3 V (trip 500 mA). "
              "Telemetria I2C indicata come 'possibile miglioria software futura'. Massa e capacita' per l'opzione " + opt + ((" (prezzo = 980 + 165 per la seconda batteria)") if opt == "/01" else "") + ".")

add("battery", "pumpkin-bm1-40wh", "Pumpkin", "Battery Module 1 (BM 1) 40 Wh", 0.310,
    dict(voltage_range_v=[6.2, 8.4], capacity_wh=40.0, max_discharge_a=5.0, max_dod=None, cycle_life=None), pk_bm1,
    notes=PK_OLD + "Quattro celle 18650 Li-Ion (2S2P, due pacchi da 20 Wh indipendenti con protezioni OC/OV/UT/OT/UV). Soglie: sovratensione 8.40 V (reset 8.30 V), sottotensione 5.00 V (reset 6.20 V); "
          "6.2-8.4 V usato come range. 'Overcurrent trip 5 A' (non specificato se per pacco o totale). Molti campi del datasheet sono ancora 'TBD' (corrente di quiescenza, temperature). "
          "Temperatura: -40..+85 C vale per l'elettronica, non per le celle (tipico 0..45 C). Nessun prezzo nel listino 2022. Nel MISC 3 e' abbinato all'EPS Clyde Space XUEPS.")

ITAR = ("Il listino 2022 indica il kit come NLA (non piu' disponibile) e il prodotto come soggetto a ITAR (22 CFR 121.1, Cat. XV, determinazione di ottobre 2010): "
        "le vendite fuori dagli USA richiedono licenza di esportazione. ")
add("adcs", "pumpkin-mai-100", "Pumpkin / Maryland Aerospace", "MAI-100 ADACS", 0.885,
    dict(pointing_accuracy_deg=1.0, data_interfaces=["RS-232", "UART"], supply_voltage_ranges_v=[[7, 16]]), pk_mai100,
    power_w=1.5, tid_krad=30, temp_op_c=[-40, 80], status="nla",
    notes=ITAR + PK_OLD + "Massa 885 g = ADACS 865 g + magnetometro esterno 20 g. 3 ruote (1.1 mNms ciascuna, 0.635 mNm), 3 bobine; 100x100x78.74 mm. "
          "Potenza 1.5 W tipica (<4.5 W max) a +12 V (elettronica da 7 V, motori a coppia piena da 9 V). Puntamento 1 grado con i sensori forniti (1-3 arcsec solo con giroscopio e star tracker aggiuntivi, non inclusi). "
          "Interfaccia seriale RS-232; verso il CubeSat Kit Bus tramite ADACS Interface Module 711-00408 (UART): per questo e' indicato anche UART. "
          "TID 30 krad dichiarata ma 'inferita, non testata, non garantita'.")
add("adcs", "pumpkin-mai-200", "Pumpkin / Maryland Aerospace", "MAI-200 ADACS", 0.930,
    dict(pointing_accuracy_deg=1.0, data_interfaces=["RS-232", "UART"], supply_voltage_ranges_v=[[7, 16]]), pk_mai200,
    power_w=3.5, tid_krad=30, temp_op_c=[-40, 80], status="nla",
    notes=ITAR + PK_OLD + "Massa 930 g = ADACS 910 g + magnetometro 20 g. Ruote da 10.8 mNms (0.625 mNm), 3 bobine; 100x100x78.74 mm. "
          "Potenza 3.5 W tipica (<6 W max) a +12 V. Puntamento 1 grado con i sensori forniti. Interfaccia RS-232 (UART tramite ADACS Interface Module). "
          "TID 30 krad 'inferita, non testata'.")

# ======================= NanoAvionics =======================
NA = "https://nanoavionics.com/cubesat-components/"
NA_NOTE = ("Fonte: pagina prodotto sul sito del fornitore (nessun datasheet pubblico: la brochure e' dietro un modulo), letta il 2026-10-13. "
           "I prezzi sono 'per unita', supporto tecnico escluso' e con ordine minimo; la massa e' dichiarata solo per alcuni prodotti. ")


def na_price(amount):
    return {"amount": amount, "currency": "EUR", "as_of": RET}


add("structure", "nanoavionics-frame-6u", "NanoAvionics", "CubeSat Structural Frame 6U", None,
    struct(6, None, {"6U": 2, "3U": 2}), (NA + "cubesat-structural-frame/", "Pagina prodotto NanoAvionics 'CubeSat Structural Frame'"),
    price=na_price(5040),
    notes=NA_NOTE + GEOM + "Massa NON dichiarata. Telaio 7075-T7351 anodizzato duro, conforme alla CubeSat Design Specification e allo standard PC/104, "
          "prove shock/vibrazioni secondo NASA GEVS 7000. Prezzo 5,040 EUR, ordine minimo 3 pezzi, consegna 1-3 mesi. "
          "Esistono anche 8U (7,470 EUR), 12U (10,000 EUR) e 16U (12,750 EUR), non inclusi: il catalogo gestisce solo 3U e 6U. La pagina non elenca telai 1U o 3U.")
add("obc", "nanoavionics-satbus-3c2", "NanoAvionics", "SatBus 3C2 (Main Bus Unit)", None,
    dict(data_interfaces=["CAN", "SPI", "I2C", "UART", "USB"], supply_voltage_ranges_v=None),
    (NA + "satbus-3c2/", "Pagina prodotto NanoAvionics 'SatBus 3C2'"), price=na_price(4460),
    notes=NA_NOTE + "Massa, consumo, tensione di alimentazione, temperatura e TID NON dichiarati. Processore fino a 400 MHz, 1 MB RAM, 2 MB flash, 2x512 kB FRAM, 256 MB NOR flash; "
          "magnetometro e tre giroscopi a bordo; CAN/SPI/I2C/UART multipli, PWM, GPIO, debug USB/SWD, CSP. Prezzo 4,460 EUR, ordine minimo 3 pezzi.")
add("eps", "nanoavionics-eps-1-0", "NanoAvionics", "CubeSat EPS 1.0 (175 W)", None,
    dict(compatible_form_factors_u=None, pv_channels=8, pv_voltage_v=[2.6, 12.0], pv_power_w_max=None, battery_voltage_v=[7.0, 8.3],
         battery_families=None, integrated_battery_wh=None, integrated_battery_voltage_v=None,
         output_voltage_ranges_v=[[3.3, 12.0]], output_power_w_max=175.0, data_interfaces=["CAN", "USB"], efficiency=None),
    (NA + "electrical-power-system/", "Pagina prodotto NanoAvionics 'CubeSat EPS 1.0 and Accessory Boards'"),
    notes=NA_NOTE + "Massa NON dichiarata. Formato PC/104, 8 canali PV su 4 convertitori MPPT (25 W ciascuno, ingresso 2.6-12 V), batteria 2S nominale 7.4 V (rail non regolato 7.0-8.3 V, usato come range), "
          "uscite regolate 3.3 V, 5 V e 3.3-12 V configurabile (20 W per convertitore), fino a 175 W e 18 canali, efficienza fino al 96% (valore di picco). "
          "Le batterie 2S1P-2S7P (23-161 Wh) sono vendute a parte e non sono in catalogo. Prezzo del sistema 8,470-26,710 EUR secondo la configurazione (non e' un prezzo unico, quindi non registrato), ordine minimo 3 pezzi.")
add("eps", "nanoavionics-eps-2-0", "NanoAvionics", "SmallSat EPS 2.0 (660 W)", None,
    dict(compatible_form_factors_u=None, pv_channels=12, pv_voltage_v=[6.0, 42.0], pv_power_w_max=None, battery_voltage_v=[12.0, 33.2],
         battery_families=None, integrated_battery_wh=None, integrated_battery_voltage_v=None,
         output_voltage_ranges_v=[[3.3, 3.3], [5, 5], [12, 12], [28, 28]], output_power_w_max=660.0,
         data_interfaces=["CAN", "UART", "RS-422", "USB"], efficiency=None),
    (NA + "cubesat-electrical-power-system-eps/", "Pagina prodotto NanoAvionics 'SmallSat EPS 2.0'"),
    notes=NA_NOTE + "Massa e temperatura NON dichiarate. 12 canali PV per scheda PCU (4 convertitori MPPT da 50 W, fino a 4 schede), ingresso 6-42 V; batterie Li-Ion 4S (12-16.6 V) o 8S (24-33.2 V) "
          "da 100 a 600 Wh con BMS integrato (range batteria unito: 12-33.2 V); 20 canali per scheda PDU (fino a 4), rail 3.3/5/12/28 V regolati e Vbat; fino a 660 W; "
          "efficienza fino al 97% (valore di picco, non trascritto). Prezzo non indicato sulla pagina.")

add("comms", "nanoavionics-satcom-uhf", "NanoAvionics", "SatCOM UHF (SAT2RF1-1D)", 0.0075,
    dict(band="UHF", data_rate_kbps_max=2.4, power_w_idle=None, power_w_tx=None, data_interfaces=["CAN", "UART"],
         supply_voltage_ranges_v=[[3.3, 3.3]]),
    (NA + "satcom-uhf/", "Pagina prodotto NanoAvionics 'SatCOM UHF'"), price=na_price(6350),
    notes=NA_NOTE + "Half-duplex GFSK2 (MSK) a 2400 bps, UHF programmabile 395-440 MHz, potenza RF 2 W, sensibilita' tipica -120 dBm, MCU ARM Cortex-M4. 56.1x32.9x6.56 mm. "
          "CAN sul modulo di bordo e UART sul modulo di terra. Consumo DC, temperatura e TID non dichiarati. Ordine minimo 4 pezzi. Il nome SAT2RF1-1D viene dalla pagina SatBus.")
# (NanoAvionics elenca anche S-band SRS-3 e SRS-4 con specifiche identiche a quelle Satlab: nel catalogo c'e' una sola voce, quella Satlab)

# ======================= Satlab =======================
SL = "https://www.satlab.com/resources/"
SL_NOTE = ("Fonte: datasheet del fornitore e pagina prodotto satlab.com, letti il 2026-10-13. Prezzo e tempi di consegna 'su richiesta'. "
           "NanoAvionics pubblica una pagina 'S-Band Transceiver SRS-3 / SRS-4' con massa, dimensioni e tensioni identiche: e' lo stesso prodotto Satlab, qui registrato una sola volta. ")
add("comms", "satlab-srs-3", "Satlab", "SRS-3 S-band Transceiver", 0.190,
    dict(band="S", data_rate_kbps_max=512.0, power_w_idle=0.55, power_w_tx=5.0, data_interfaces=["CAN", "RS-422", "Ethernet"],
         supply_voltage_ranges_v=[[5, 40]]),
    (SL + "SLDS-SRS3-1.3.pdf", "Satlab SRS-3 Datasheet rev 1.3 + pagina prodotto"), temp_op_c=[-40, 70], trl=9,
    notes=SL_NOTE + "GMSK, TX 2200-2290 MHz da 9.6 a 512 kBd, RX 2025-2110 MHz da 9.6 a 128 kBd, potenza RF 20-30 dBm con ALC, sensibilita' -107 dBm. "
          "GMSK trasporta 1 bit per simbolo: 512 kBd = 512 kbps lordi (prima della FEC). Consumo a 5 V, 20 C, 30 dBm: 0.55 W in attesa di frame, 5.0 W in full-duplex. "
          "Temperatura RX -40..85 C, TX -40..70 C (si usa il piu' stretto). 87.0x93.0x17.0 mm. Eredita': dal 2019, oltre 100 unita' consegnate (unita', non missioni). TID non dichiarata.")
add("comms", "satlab-srs-4", "Satlab", "SRS-4 S-band Transceiver", 0.253,
    dict(band="S", data_rate_kbps_max=5000.0, power_w_idle=1.5, power_w_tx=10.8, data_interfaces=["CAN", "RS-422", "Ethernet"],
         supply_voltage_ranges_v=[[5.1, 28.8]]),
    (SL + "SLDS-SRS4-1.2.pdf", "Satlab SRS-4 Datasheet rev 1.2 + pagina prodotto"), temp_op_c=[-40, 70], trl=9,
    notes=SL_NOTE + "BPSK/QPSK/8PSK, velocita' di simbolo 100 kBd-5 MBd in TX e RX (BPSK/QPSK in RX); 5000 e' un valore in baud usato come data rate minimo garantito (8PSK trasporta fino a 3 bit per simbolo). "
          "Potenza RF 20-33 dBm, sensibilita' -122 dBm. Consumo a 6 V, 20 C: RX 1.5 W (5 MBd, usato come potenza a riposo), RX+TX 10.8 W a 33 dBm. "
          "Temperatura RX -40..85 C, TX -40..70 C (si usa il piu' stretto). 93.0x87.2x18.0 mm (la pagina riporta 17.5 mm). Eredita': dal 2021, oltre 100 unita' consegnate. TID non dichiarata.")
add("comms", "satlab-srx-8", "Satlab", "SRX-8 X-band Transmitter", 0.300,
    dict(band="X", data_rate_kbps_max=1400000.0, power_w_idle=4.3, power_w_tx=27.0, data_interfaces=["CAN", "RS-422", "Ethernet"],
         supply_voltage_ranges_v=[[7.5, 40]]),
    (SL + "SL-PRO-DS-SRX-8-1.0.pdf", "Satlab SRX-8 Datasheet rev 1.0 + pagina prodotto"), temp_op_c=[-40, 70],
    notes="Fonte: datasheet del fornitore e pagina prodotto satlab.com, letti il 2026-10-13. Prezzo 'su richiesta'. "
          "Solo trasmettitore X-band (8025-8400 MHz) DVB-S2 QPSK/8PSK/16APSK/32APSK, fino a 1.4 Gbit/s (1-312.5 MBd), potenza RF 27-33 dBm. "
          "Consumo: 27 W in TX (312.5 MBd, 33 dBm), 4.3 W a riposo. Ethernet 1000BASE-T e 10GBASE-R per i dati, CAN e RS-422 con CSP per configurazione e telemetria. "
          "93.0x87.2x22.0 mm. Eredita' e TID non dichiarate.")

# ======================= Blue Canyon Technologies =======================
bct_adcs = ("https://www.bluecanyontech.com/wp-content/uploads/ADCS-2026.pdf", "Blue Canyon Technologies ADCS product sheet REV 1/2026")
bct_batt = ("https://www.bluecanyontech.com/wp-content/uploads/Batteries-2026.pdf", "Blue Canyon Technologies 28V Batteries product sheet REV 1/2026")
BCT_NOTE = "La scheda e' 'solo informativa e soggetta a modifiche': BCT chiede di contattarla per i dati di progetto aggiornati. "

for tag, mass, sat, mom, torque, dims, ext in (
        ("15", 0.89, "3U (4 kg)", "15 mNms per asse", "0.005 Nm", "10x10x5 cm (0.5U)", ""),
        ("50", 1.23, "6U (14 kg)", "50 mNms per asse", "0.006 Nm", "10x10x7.54 cm (0.75U)", ""),
        ("100", 1.52, "12U (25 kg)", "fino a 4 ruote da 100 mNms", "0.006 Nm", "10x10x5 cm (0.5U) esclusi i componenti esterni",
         "Massa '0.52 kg + 1 kg (ruote)': sommata (1.52 kg), ma la scheda non dice a quante ruote si riferisce il chilogrammo. ")):
    add("adcs", f"bct-xact-{tag}", "Blue Canyon Technologies", f"XACT-{tag}", mass,
        dict(pointing_accuracy_deg=round(25 / 3600, 5), data_interfaces=["RS-422"], supply_voltage_ranges_v=[[12, 12]]), bct_adcs,
        temp_op_c=[-20, 60], family="bct-xact",
        notes=BCT_NOTE + ext + f"ADCS completo con tracker stellare, ruote e barre di torsione (satellite tipico {sat}); {mom}, coppia massima {torque}, slew fino a 10 gradi/s; {dims}. "
              "Puntamento 1 sigma: +-10 arcsec su 2 assi e +-25 arcsec sul terzo; si usa il valore peggiore (25 arcsec = 0.00694 gradi). Tensione 12 V, interfaccia RS-422 e intervallo operativo -20..+60 C "
              "valgono per la famiglia XACT. Eredita': 38 unita' XACT lanciate, 5.4 anni la piu' longeva in orbita (non e' un numero di missioni). Consumo, TID e prezzo non dichiarati. "
              "Nota: la famiglia FleXcore (28 V, massa 'dipendente dalla configurazione') non e' inclusa.")

for tag, wh, mass, foot, ah, extra in (
        ("1p8s", 99.0, 0.685, "1.8 x 4.2 pollici, altezza 3.5 pollici", 3.4, " La pagina prodotto riporta 'IP8S' (probabilmente 1P8S) e '<650 g'; si usa la scheda REV 1/2026."),
        ("2p8s", 198.0, 1.210, "1.8 x 7.2 pollici, altezza 3.5 pollici", 6.8, " La pagina prodotto riporta '<1200 g'; si usa la scheda REV 1/2026.")):
    add("battery", f"bct-battery-{tag}", "Blue Canyon Technologies", f"28 V Battery {tag.upper()} ({int(wh)} Wh)", mass,
        dict(voltage_range_v=[24.0, 33.6], capacity_wh=wh, max_discharge_a=None, max_dod=None, cycle_life=None), bct_batt,
        notes=BCT_NOTE + f"Configurazione {tag.upper()}, {ah} Ah nominali, tensione nominale 28 V, 24-33.6 V; ingombro {foot}; massa 'minore di' {int(mass * 1000)} g (limite superiore). "
              "Protezioni da sottotensione e sovracorrente, bilanciamento delle celle, riscaldatori integrati (intervallo non dichiarato)." + extra +
              " Eredita' dichiarata dal sito per la linea batterie: 595 prodotte, 140 lanciate (unita', non missioni). Corrente massima, cicli e temperatura non dichiarati.")

# ======================= NPC Spacemind =======================
SM_URL = "https://www.npcspacemind.com/product/"
SM_NOTE = ("Fonte: pagina prodotto su npcspacemind.com, letta il 2026-10-13: il sito non pubblica datasheet (i link 'Datasheet' puntano a '#'; "
           "i dati completi si ottengono con 'Request Quote'). ")


def sm_price(amount):
    return {"amount": amount, "currency": "EUR", "as_of": RET}


add("structure", "spacemind-sm03", "NPC Spacemind", "SM03 CubeSat structure 3U", None,
    struct(3, None, {"3U": 4}), (SM_URL + "sm03/", "Pagina prodotto NPC Spacemind 'SM03'"), price=sm_price(3500),
    notes=SM_NOTE + GEOM + "Massa, materiale e volume utile NON dichiarati. Ingombro 340.5 x 100 x 100 mm (senza kill switch), fino a 8 interruttori di rilascio, fino a 4 kill switch su standoff piu' 4 su guida, "
          "stack di schede configurabili in orizzontale o verticale, compatibile PC104 e PC104 PLUS, inserti helicoil, anelli intermedi da 1U opzionali. Prezzo 3,500 EUR.")
add("structure", "spacemind-sm06", "NPC Spacemind", "SM06 CubeSat structure 6U", None,
    struct(6, None, {"6U": 2, "3U": 2}), (SM_URL + "sm06/", "Pagina prodotto NPC Spacemind 'SM06'"),
    notes=SM_NOTE + GEOM + "Massa, materiale e volume utile NON dichiarati; prezzo solo su richiesta. Ingombro 340.5 x 226.3 x 100 mm (senza kill switch), fino a 8 interruttori di rilascio, "
          "stack di schede indipendente dalla struttura, compatibile PC104 e PC104 PLUS, anelli intermedi da 1U e 2U opzionali. Non inclusi SM01 (1.800 EUR), SM02 (2.700 EUR), SM04, SM08, SM12, SM16: "
          "il catalogo gestisce solo 3U e 6U.")
add("eps", "spacemind-gemini-eps", "NPC Spacemind", "GEMINI EPS (batteria 84 Wh)", 0.300,
    dict(compatible_form_factors_u=[3, 6, 8, 12, 16], pv_channels=6, pv_voltage_v=[5.0, 20.0], pv_power_w_max=None, battery_voltage_v=None,
         battery_families=None, integrated_battery_wh=84.0, integrated_battery_voltage_v=None,
         output_voltage_ranges_v=[[3.3, 3.3], [5, 5], [6, 12], [24, 24]], output_power_w_max=None, data_interfaces=None, efficiency=None),
    (SM_URL + "gemini-cubesat-eps/", "Pagina prodotto NPC Spacemind 'GEMINI EPS'"),
    notes=SM_NOTE + "EPS modulare 'per piattaforme 3U-16U' (taglie ammesse dedotte dalla dicitura), 90.2 x 95.9 x 25 mm, 6 canali PV da 5 a 20 V, bus di uscita programmabile 3.3 / 5 / 6-12 / 24 V, "
          "protezioni OV, OC e OP. Pacco batteria integrato da 84 Wh (8 celle), fino a 8 pacchi in parallelo. NON e' chiaro se i 300 g includano il pacco batteria: se non lo includono la massa e' sottostimata. "
          "Altri siti (satsearch, satnow) riportano cifre diverse (50 Wh, 12 MPPT, 3.6-24 V): si usa la pagina del fornitore. Tensione batteria, interfacce ('configurabili'), efficienza, temperatura e TID non dichiarati.")
add("solar_panel", "spacemind-sp3x", "NPC Spacemind", "SPM SP3X body-mounted panel", 0.137,
    dict(face="3U", peak_power_w=8.0, voltage_options_v=[16.0, 17.5], open_circuit_voltage_v=19.3, degradation_per_year=None),
    (SM_URL + "spm-sp3x/", "Pagina prodotto NPC Spacemind 'SP3X'"), price=sm_price(4700),
    notes=SM_NOTE + "Celle UTJ a tripla giunzione (numero non dichiarato), potenza di picco 8-8.8 W (usato 8.0), Vmp 16-17.5 V, Imp 500-520 mA, Voc 18.2-19.3 V (usato il massimo). "
          "Montaggio sul lato XY, compatibile con strutture 3U e 6U; 2 connettori picoblade in parallelo; opzioni: sensore di temperatura, NTC, 2 sensori solari, IMU, magnetometro, RBF. "
          "Prezzo 4,700 EUR. Efficienza, temperatura, TID ed eredita' non dichiarate.")
add("solar_panel", "spacemind-sp6x", "NPC Spacemind", "SPM SP6X body-mounted panel", 0.335,
    dict(face="6U", peak_power_w=18.4, voltage_options_v=[18.4, 20.0], open_circuit_voltage_v=22.0, degradation_per_year=None),
    (SM_URL + "spm-sp6x/", "Pagina prodotto NPC Spacemind 'SP6X'"),
    notes=SM_NOTE + "Potenza di picco 18.4-20 W (usato 18.4), Vmp 18.4-20 V, Imp 1-1.04 A, Voc 20.8-22 V (usato il massimo: supera il limite di 20 V per canale dichiarato per l'EPS GEMINI, quindi il selettore non li accoppia). "
          "Montaggio sul lato XY, compatibile con strutture 6U e 12U; 4 connettori PicoBlade in parallelo. Prezzo solo su richiesta. "
          "Gli altri pannelli della famiglia SP1X, SP1Z, SP2X (87 g, 4.6-5 W), SP2Z, SP4X, SP4Z e SP8X sono per taglie o facce non gestite dal catalogo.")

# ======================= Hyperion Technologies (oggi AAC Hyperion, marchio di AAC Clyde Space) =======================
HY = "https://www.aac-clyde.space/wp-content/uploads/2021/11/"
HY_NOTE = ("Hyperion Technologies e' oggi il marchio AAC Hyperion di AAC Clyde Space (pagina 'our brands/hyperion' del sito): i prodotti sono pubblicati su aac-clyde.space. "
           "Fonte: datasheet del fornitore (release febbraio 2023) e pagina prodotto, letti il 2026-10-13. Prezzo non pubblicato. ")
add("adcs", "hyperion-iadcs200", "Hyperion Technologies (AAC Hyperion)", "iADCS200", 0.470,
    dict(pointing_accuracy_deg=1.0, data_interfaces=["I2C"], supply_voltage_ranges_v=[[4.0, 15.0]]),
    (HY + "iADCS200.pdf", "AAC Hyperion iADCS200 datasheet (release 08 Feb 2023) + pagina prodotto"),
    power_w=1.4, tid_krad=45, temp_op_c=[-20, 40], trl=9, family="hyperion-iadcs",
    notes=HY_NOTE + "ADCS integrato per CubeSat 3U (0.3U, 95x90x32 mm, 2 schede PC104): tracker stellare ST200, ruote RW210 (una per asse), magnetorquer MTQ200 e IMU. "
          "Massa 400 / 435 / 470 g secondo il modello di ruote (momento +-1.5 / +-3.0 / +-6.0 mNms): il datasheet non dice quale massa corrisponda a quale, quindi si usa il caso peggiore, 470 g. "
          "Accuratezza di puntamento '<1 grado' (usato 1.0) e determinazione d'assetto 30 arcsec (3 sigma). Potenza: 1.15 W a riposo, 1.4 W nominale (usato), 4.0-4.5 W di picco, escluse ruote e tracker aggiuntivi. "
          "Alimentazione 5 V tipici (4.0 V min dai pin 5 V, fino a 15 V da VBAT). Interfaccia I2C standard; RS-422, RS-485 e UART opzionali (non registrate). "
          "TID: componenti primari provati fino a 45 krad (il datasheet riporta '>459' per un artefatto di nota a pie di pagina). "
          "Temperatura: il datasheet scrive '-45 / -20 to +40 / +85' senza etichette; si usa -20..+40 (come il tracker ST200). Eredita': in orbita dal 2017 in varie configurazioni. Tempo di consegna 9 mesi.")
add("adcs", "hyperion-iadcs400", "Hyperion Technologies (AAC Hyperion)", "iADCS400", 1.700,
    dict(pointing_accuracy_deg=1.0, data_interfaces=["I2C"], supply_voltage_ranges_v=[[4.9, 15.0]]),
    (HY + "iADCS400-1.pdf", "AAC Hyperion iADCS400 datasheet (release 13 Feb 2023) + pagina prodotto"),
    power_w=2.0, tid_krad=45, temp_op_c=[-20, 40], trl=9, family="hyperion-iadcs",
    notes=HY_NOTE + "ADCS integrato per piattaforme 6U-12U (0.7U, 95.4x95.9x67.3 mm): tracker ST200, ruote RW400 (una per asse), magnetorquer MTQ400 (0.5 A m2). "
          "Massa 1150 / 1300 / 1700 g secondo il modello di ruote: si usa il caso peggiore, 1.7 kg. Accuratezza di puntamento '<1 grado' (usato 1.0), determinazione 30 arcsec. "
          "Il datasheet cita sia '+-30 mNms per asse' (testo) sia '+-1.5/3.0/6.0 mNms' (tabella), incoerenti. Coppia massima 2-2.5 mNm. "
          "Potenza: 0.9 W a riposo (2.4 W max), 2.0 W nominale (usato), picco fino a 5 W (il testo dice '<4 W'). Alimentazione 5 V tipici (4.9 V min, 15 V max). "
          "Interfaccia I2C standard; RS-422, RS-485, UART e CAN opzionali (non registrate). TID fino a 45 krad (il datasheet riporta '>458' per lo stesso artefatto), schermatura aggiuntiva integrata. "
          "Eredita': in orbita dal 2023 (pagina prodotto). Opzionale: OBC/payload processor integrato CP400.")

# ======================= Alen Space =======================
add("obc", "alenspace-dara-obc", "Alén Space", "DARA OBC", None,
    dict(data_interfaces=["RS-422", "UART", "CAN", "I2C"], supply_voltage_ranges_v=None),
    ("https://alen.space/products/dara-obc/", "Pagina prodotto Alén Space 'DARA OBC' + comunicato del 14 novembre 2024 (alen.space/?p=29015)"),
    power_w=0.28, temp_op_c=[-40, 85], trl=9,
    notes="Fonte: pagina prodotto e comunicato di Alén Space, letti il 2026-10-13. Il datasheet (con CAD e brochure) e' inviato via email dopo la compilazione di un modulo: non e' pubblico. "
          "Massa, dimensioni, tensione di alimentazione e TID NON dichiarate; prezzo su richiesta. PC104, ARM Cortex-M7 fino a 280 MHz, 280 mW tipici, 2 MB flash, 1.4 MB RAM, 32 MB SDRAM, 512 KB MRAM resistente a SEU/SEL, "
          "microSD fino a 128 GB; 3 RS-422, 1 UART, 2 CAN, 2 I2C, 15 GPIO; IMU a 3 assi, opzione GNSS interno (GPS, Galileo, GLONASS, BeiDou); AES e HMAC; SDK FreeRTOS con CSP. "
          "Altri prodotti Alén: le piattaforme 3U/6U/12U, il transceiver S-band 'payload' (2 Mbps BPSK, senza massa ne' consumi), gli SDR TOTEM e TREVO (senza data rate ne' consumi) e il segmento di terra non sono componenti utilizzabili dal selettore.")

# ======================= Innoflight =======================
add("obc", "innoflight-cfc-400-champs", "Innoflight", "CFC-400 CHAMPS Flight Computer (MPSoC)", 0.250,
    dict(data_interfaces=["UART", "RS-422", "SPI", "I2C", "MIL-STD-1553"], supply_voltage_ranges_v=[[3.3, 3.3], [28, 28]]),
    ("https://satcatalog.s3.amazonaws.com/components/434/SatCatalog_-_Innoflight_-_CFC-400_-_Datasheet.pdf?lastmod=20210708055852",
     "Innoflight 'CHAMPS Flight Computer (MPSoC CFC-400)' specification sheet, 26 gen 2019 (copia ospitata da SatCatalog)"),
    power_w=12.0, tid_krad=30, temp_op_c=[-40, 85],
    notes="Scheda tecnica del fornitore del 2019, ospitata da SatCatalog (innoflight.com non pubblica dati tecnici: la pagina prodotto elenca solo i nomi). Il listino attuale riporta il CFC-400XS, "
          "per cui non esiste una scheda pubblica (cifre di terzi discordanti: 239-350 g, 6-25 W): verificare che il CFC-400 sia ancora offerto. "
          "Massa <= 250 g con contenitore (82 x 82 x 29 mm senza scheda figlia, 3.3 V regolati, senza porte transceiver). Potenza 0.6-12 W regolata dinamicamente: si usa il massimo, 12 W, come valore prudente "
          "(il consumo medio dipende dalla missione e puo' essere molto minore). Alimentazione a scelta: 28 V non regolati (con DC/DC isolato rad-tolerante) o 3.3 V regolati. "
          "TID 30 krad, immune a SEL; -40..+85 C all'interfaccia di montaggio; GEVS. Doppia piattaforma: FPGA rad-tolerante con CPU LEON3FT e 8 MB MRAM (alta affidabilita'), "
          "MPSoC Xilinx con quad-core Cortex-A53 fino a 1 GHz, 2 GB LPDDR4 e 16 GB NAND (alte prestazioni). "
          "I/O: fino a 4 seriali (UART o sincrona, 3.3 V o RS-422), 2 SPI, 2 I2C, MIL-STD-1553 doppio ridondante, analogici, lane seriali veloci (SGMII, SRIO, PCIe, Aurora: non registrate). "
          "Non inclusi: SCR-100/104/106/154/208/504 (radio software-defined, senza massa ne' consumi nelle fonti di terzi), router e switch, unita' crittografiche, SSD, CFC-405XP/450XP/510P/600P e MPE (senza dati).")

# ======================= AAC Clyde Space (Clyde Space): altre linee =======================
AAC = "https://www.aac-clyde.space/what-we-do/space-products-components/"
AACW = "https://www.aac-clyde.space/wp-content/uploads/"
AAC_PAGE = ("Fonte: pagina prodotto su aac-clyde.space letta il 2026-10-13 (i valori del sito possono differire dai datasheet PDF piu' vecchi: per gli OPTIMUS la pagina riporta masse piu' alte del PDF 2020); "
            "prezzo non pubblicato. ")
SAT_TRX_NOTE = "Potenze DC: 'ricezione' usata come potenza a riposo, il massimo dell'intervallo in trasmissione. "

# --- strutture ZAPHOD (datasheet letto direttamente, release 26 feb 2025) ---
for ff, mass, dim, faces in ((3, 0.394, "100 x 100 x 340.5 mm", {"3U": 4}), (6, 0.674, "100 x 226.3 x 340.5 mm", {"6U": 2, "3U": 2})):
    add("structure", f"aac-zaphod-{ff}u", "AAC Clyde Space", f"ZAPHOD {ff}U structure", mass,
        struct(ff, mass, faces), (AACW + "2021/11/AAC_DataSheet_Zaphod-2.pdf", "AAC Clyde Space ZAPHOD datasheet (release 26 Feb 2025)"),
        temp_op_c=[-40, 80], family="aac-zaphod",
        notes=GEOM + f"Massa {int(mass * 1000)} g, {dim}, alluminio 7075 e 6082, qualificata NASA GEVS (14.1 gRMS), 4 interruttori di rilascio. Compatibile con i pannelli PHOTON e con le batterie OPTIMUS. "
              "Prezzo non pubblicato. Il datasheet parla di forme da 1U a 6U: qui solo 3U e 6U.")

# --- pannello PHOTON-SIDE (datasheet letto direttamente, release 28 lug 2020) ---
add("solar_panel", "aac-photon-side-3u", "AAC Clyde Space", "PHOTON-SIDE 3U body-mounted panel", 0.135,
    dict(face="3U", peak_power_w=9.0, voltage_options_v=None, open_circuit_voltage_v=None, degradation_per_year=None),
    (AACW + "2021/11/AAC_DataSheet_Photon_original.pdf", "AAC Clyde Space PHOTON datasheet (release 28 Jul 2020) + pagina prodotto"),
    temp_op_c=[-40, 80], family="aac-photon",
    notes="Fino a 9 W per faccia 3U popolata, celle Spectrolab XTJ Prime al 30.7%, substrato FR4, altezza a riposo 3.5 mm, massa 135 g per la faccia 3U (disponibile anche per 1U, 2U e 6U senza massa dichiarata). "
          "Sensori di temperatura e solari grossolani inclusi. Compatibile con le strutture ZAPHOD e (secondo il datasheet STARBUCK) con gli EPS STARBUCK. Tensione, Voc e prezzo non dichiarati. "
          "Le versioni dispiegabili PHOTON-SD (310 g), -DD e -TD (330 g) non dichiarano la potenza e non sono incluse.")

# --- EPS STARBUCK-NANO-PLUS (dallo stesso datasheet gia' usato per il NANO) ---
add("eps", "aac-starbuck-nano-plus", "AAC Clyde Space", "STARBUCK-NANO-PLUS", 0.148,
    dict(compatible_form_factors_u=[3, 6, 8, 12], pv_channels=None, pv_voltage_v=[8.2, 8.2], pv_power_w_max=None,
         battery_voltage_v=None, battery_families=["aac-optimus"], integrated_battery_wh=None,
         integrated_battery_voltage_v=None, output_voltage_ranges_v=[[3.3, 3.3], [5, 5], [12, 12]],
         output_power_w_max=None, data_interfaces=["I2C"], efficiency=None), AAC_SB,
    tid_krad=10, temp_op_c=[-40, 85], family="aac-starbuck",
    notes="Versione NANO-PLUS dello stesso datasheet del NANO: piu' regolatori di carica (BCR) per 3U con pannelli dispiegabili fino a missioni 12U ad alte prestazioni, 148 g, 95.89 x 90.17 x 20.82 mm, batteria esterna. "
          "Numero di canali PV e potenza massima non dichiarati. Altri dati come lo STARBUCK-NANO (8.2 V di tensione di massima potenza, 3.3/5/12 V, 10 LCL, I2C, 10 krad, 5 anni in LEO). "
          "Compatibile con batterie OPTIMUS e pannelli PHOTON secondo il datasheet.")

# --- OBC ---
add("obc", "aac-kryten-m3", "AAC Clyde Space", "KRYTEN-M3 OBC", 0.070,
    dict(data_interfaces=["I2C", "SPI", "UART", "RS-422", "CAN"], supply_voltage_ranges_v=None),
    (AAC + "command-data-handling/kryten-m3", "Pagina prodotto AAC Clyde Space 'Kryten-M3' (datasheet: " + AACW + "2021/10/AAC_DataSheet_Kryten.pdf)"),
    power_w=0.4, tid_krad=20, temp_op_c=[-40, 80], trl=9,
    notes=AAC_PAGE + "SmartFusion2 con ARM Cortex-M3 a 50 MHz, 16 MB MRAM, 4 GB flash SLC, RTEMS, formato PC104 95.89 x 90.17 x 5.51 mm. Potenza 0.4 W tipici, 1 W max. "
          "Interfacce (conteggi della pagina, tabella ambigua): 2 I2C, 1 SPI, 8 UART, 1 RS-422 (anche 2 x RS-485), 1 CAN, JTAG, LVDS, QSPI, 17 GPIO. TID 20 krad, vita di progetto 5 anni in LEO, in volo dal 2014. "
          "Tensione di alimentazione non dichiarata; la versione PLUS aggiunge un GPS.")
add("obc", "aac-sirius-obc-leon3ft", "AAC Clyde Space", "SIRIUS-OBC-LEON3FT (SmallSat OBC)", 0.130,
    dict(data_interfaces=["RS-422", "RS-485", "UART", "SpaceWire"], supply_voltage_ranges_v=[[4.5, 16.0]]),
    (AAC + "command-data-handling/smallsat-sirius-obc", "Pagina prodotto AAC Clyde Space 'SMALLSAT SIRIUS-OBC-LEON3FT' (datasheet: " + AACW + "2021/10/AAC_DataSheet_Sirius-OBC.pdf)"),
    power_w=1.3, tid_krad=20, temp_op_c=[-30, 60], trl=9,
    notes=AAC_PAGE + "LEON3FT SPARC v8 a 50 MHz, 64 MB SDRAM, 2 GB NAND, 130 g, 95.89 x 90.17 x 17.2 mm, 1.3 W nominali, 4.5-16 V. 2 porte SpaceWire, 6 UART RS-422/RS-485 piu' 2 solo RS-485, "
          "8 ingressi analogici, 16 GPIO; 2 CAN solo con scheda figlia opzionale (non registrati). TID 20 krad qualificati (>30 krad per la nota di qualifica). In volo dal 2021.")
add("obc", "aac-q7s", "AAC Clyde Space", "Q7S processor module", 0.032,
    dict(data_interfaces=["Ethernet", "USB", "RS-232", "RS-422", "RS-485"], supply_voltage_ranges_v=[[6.0, 28.0]]),
    (AAC + "command-data-handling/q7s", "Pagina prodotto AAC Clyde Space 'Q7S' (datasheet: " + AACW + "2021/10/Q7S.pdf)"),
    power_w=1.0, temp_op_c=[-40, 85],
    notes=AAC_PAGE + "Modulo con SoC ARM dual-core Cortex-A9 fino a 766 MHz e Linux: 24 g senza connettore RJ45, 32 g con (usato 32 g), 78 x 43 x 9-19 mm. Consumo tipico 1 W (scalabile), 6-28 V (opzioni sotto 6 V). "
          "Gigabit Ethernet, USB 2.0, RS-232/422/485 selezionabili, 90 I/O sul connettore mezzanino. TID non dichiarata, 'oltre un decennio di eredita' di progetto'.")

# --- radio (pagine prodotto) ---
for tag, name, band, dr, idle, tx, sup, ifaces, temp, extra in (
        ("pulsar-utrx", "PULSAR-UTRX (UHF)", "UHF", 9.6, 0.2, 5.1, [[3.3, 3.3], [5, 5]], ["I2C"], [-25, 61],
         "Trasmettitore e ricevitore UHF (UTRX-C 400-420 MHz, UTRX-A 430-440 MHz), 96 x 90 x 16.35 mm, <100 g, I2C a 400 kHz, 9600 bps GFSK e 1200 bps AFSK, RF 27-33 dBm. "
         "Potenza: ricezione <200 mW (altrove 240 mW), trasmissione 3-5.1 W."),
        ("pulsar-vutrx", "PULSAR-VUTRX (VHF/UHF)", "VHF/UHF", 9.6, 0.162, 5.5, [[3.3, 3.3], [5, 5]], ["I2C"], [-25, 61],
         "Uplink VHF 140-150 MHz, downlink UHF 400-420 o 430-440 MHz, 96 x 90 x 16.51 mm, <100 g, I2C a 400 kHz, 9600 bps GFSK e 1200 bps AFSK, RF 27-33 dBm. "
         "Potenza: ricezione 162 mW, trasmissione 3-5.5 W."),
        ("pulsar-stx", "PULSAR-STX (S-band, solo TX)", "S", 2000.0, None, 5.0, [[6, 12], [5, 5]], None, [-25, 51],
         "Solo trasmettitore S-band (2.2-2.3 GHz commerciale, 2.4-2.45 GHz radioamatori), <100 g, fino a 2 Mbps O/QPSK, RF 24-30 dBm (1 W), <5 W DC al massimo; vita di progetto 2 anni in LEO. "
         "Non riceve: serve un'altra radio per l'uplink. Interfacce dati e dimensioni non dichiarate."),
        ("pulsar-hstx", "PULSAR-HSTX (S-band alta velocita', solo TX)", "S", 8000.0, None, 5.0, [[6, 12], [5, 5]], None, [-25, 61],
         "Solo trasmettitore S-band (2.2-2.3 GHz commerciale: 8 Mbps; 2.4-2.45 GHz radioamatori: 10 Mbps), <100 g, 96 x 90 x 17.41 mm, OQPSK/QPSK, RF 24-30 dBm (1 W), <5 W DC; vita di progetto 2 anni in LEO. "
         "Si usa il valore piu' basso (8 Mbps). Non riceve. Interfacce dati non dichiarate."),
        ("trx-u", "TRX-U UHF transceiver", "UHF", 19.2, 0.25, 8.0, [[3.3, 42]], None, [-35, 80],
         "UHF 370-470 MHz, FSK/GFSK a 2.4-19.2 kbps, RF 0.25-5 W, 125 g, 83 x 57 x 16 mm; in volo dal 2014, TRL 9. Potenza: RX 250 mW, TX 8 W per >5 W RF con 6 V. "
         "Connettore Micro-D a 15 poli (interfaccia dati non descritta)."),):
    add("comms", f"aac-{tag}", "AAC Clyde Space", name, (0.125 if tag == "trx-u" else 0.100),
        dict(band=band, data_rate_kbps_max=dr, power_w_idle=idle, power_w_tx=tx, data_interfaces=ifaces, supply_voltage_ranges_v=sup),
        (AAC + "communications/" + tag, f"Pagina prodotto AAC Clyde Space '{name}'"), temp_op_c=temp,
        notes=AAC_PAGE + SAT_TRX_NOTE + ("Massa '<100 g': usato 100 g come limite superiore. " if tag != "trx-u" else "") + extra + " TID non dichiarata.")
add("comms", "aac-quasar-strx", "AAC Clyde Space", "QUASAR-STRX S-band transceiver", None,
    dict(band="S", data_rate_kbps_max=512.0, power_w_idle=3.4, power_w_tx=None, data_interfaces=["CAN", "SPI", "I2C"], supply_voltage_ranges_v=None),
    (AAC + "communications/quasar-strx", "Pagina prodotto AAC Clyde Space 'QUASAR-STRX' (datasheet: " + AACW + "2021/10/Quasar-STRX-Datasheet-2.pdf)"),
    temp_op_c=[-25, 55],
    notes=AAC_PAGE + "Massa dichiarata solo come 'maggiore di 250 g' (limite inferiore: non e' un valore utilizzabile, quindi mass_kg e' null). 93 x 88 x 24 mm, SDR S-band TX 2.200-2.290 GHz fino a 512 kSimboli/s (la pagina cita anche 5 Msimboli/s in un'altra sezione), "
          "RX 2.025-2.110 GHz a 32 kSps, RF fino a 27/30/33 dBm. Potenza RX 3.4 W sempre attivo (TBC), TX non dichiarata, TID in 'TBC'. Alimentazione non dichiarata.")

# --- correzione OPTIMUS: la pagina corrente riporta masse e temperatura diverse dal PDF del 2020 ---
for c in out:
    if c["id"].startswith("aac-optimus-"):
        wh = int(c["id"].split("-")[-1])
        c["mass_kg"] = {30: 0.288, 40: 0.360, 80: 0.720}[wh]
        c["temp_op_c"] = [-10, 45]
        c["notes"] += (" AGGIORNAMENTO: la pagina prodotto attuale (aac-clyde.space, cubesat-batteries, letta il 2026-10-13) riporta massa 288 / 360 / 720 g, temperatura operativa -10..+45 C "
                       "e altezza 58.95 mm per l'80 Wh; il PDF del 2020 riportava 268 / 335 / 670 g e -10..+50 C. Si usano i valori della pagina, piu' prudenti.")

# ======================= EnduroSat: componenti mancanti (pagine prodotto correnti) =======================
ES_NOTE = ("Fonte: pagina prodotto su endurosat.com letta il 2026-10-13 (il datasheet e' disponibile solo via modulo di richiesta); prezzo non pubblicato. ")
add("eps", "endurosat-cubesat-eps", "EnduroSat", "CubeSat EPS (6U-16U, pacco da 99 Wh)", 1.478,
    dict(compatible_form_factors_u=[6, 8, 12, 16], pv_channels=3, pv_voltage_v=None, pv_power_w_max=None, battery_voltage_v=None,
         battery_families=None, integrated_battery_wh=99.0, integrated_battery_voltage_v=None,
         output_voltage_ranges_v=[[3.3, 3.3], [5, 5], [12, 12], [14.7, 17.5], [28, 28]], output_power_w_max=437.0,
         data_interfaces=["CAN"], efficiency=None),
    ("https://www.endurosat.com/products/cubesat-eps/", "Pagina prodotto EnduroSat 'CubeSat EPS'"),
    notes=ES_NOTE + "Sostituisce nel listino attuale l'EPS I/II del catalogo 2022. Massa 1478 g 'impilato con un pacco 4S1P' (la pagina scrive 99 Wh per pacco 4S2P: incoerente; la massa senza batteria non e' dichiarata). "
          "3 canali PV per stadio di ingresso, fino a 45 V e 3 A per canale (75 W di picco per canale; il minimo non e' dichiarato, quindi pv_voltage_v e' null), diodo ideale per pannello. "
          "Uscite: 3.3/5/12 V, bus di sistema 14.7-17.5 V, 2 x 28 V regolati, 6 uscite payload configurabili, VRTC 3.3 V; 437 W continui, 5 A per gruppo di canali. "
          "Per 6U-8U un pacco, per 12U-16U due pacchi. Interfacce 2 x CAN 1 Mbps (CSPES). Efficienza, temperatura e TID non dichiarate.")
add("comms", "endurosat-sband-max", "EnduroSat", "S-Band Transceiver Max", 0.380,
    dict(band="S", data_rate_kbps_max=4000.0, power_w_idle=3.0, power_w_tx=11.0, data_interfaces=["CAN", "Ethernet"],
         supply_voltage_ranges_v=[[10, 28]]),
    ("https://www.endurosat.com/products/s-band-transceiver-max/", "Pagina prodotto EnduroSat 'S-Band Transceiver Max'"),
    notes=ES_NOTE + "Full-duplex BPSK/QPSK, simbolo configurabile 0.5-4 Msps (4000 e' un valore in baud, usato come data rate senza conversione in bit/s), RF 26-33 dBm, Tx 2200-2290 MHz, Rx 2025-2110 MHz, "
          "massa 380 g +-5%, 3 W a riposo (solo Rx) e 11 W al massimo (33 dBm) a 12 V, alimentazione 10-28 V, 2 x CAN e Ethernet 100BASE-TX, cifratura AES-256-GCM. Temperatura, TID ed eredita' non dichiarate.")
add("comms", "endurosat-xband-sdr", "EnduroSat", "X-Band Software Defined Radio", None,
    dict(band="X", data_rate_kbps_max=1000000.0, power_w_idle=None, power_w_tx=None,
         data_interfaces=["CAN", "Ethernet", "SpaceWire", "UART", "RS-485", "SPI", "I2C"], supply_voltage_ranges_v=[[12, 28]]),
    ("https://www.endurosat.com/products/x-band-sdr/", "Pagina prodotto EnduroSat 'X-Band Software Defined Radio'"),
    notes=ES_NOTE + "Massa e consumi NON dichiarati. 8000-8400 MHz, oltre 1 Gbps lordi (122 MSPS), DVB-S2X fino a 256-APSK, 12-28 V, controllo CSP su CAN, Gigabit Ethernet e SpaceWire su LVDS per i dati, "
          "4 GB DDR4 e fino a 160 GB di eSSD. La pagina descrive 'due canali full-duplex' ma la intitola 'trasmettitore ad alta velocita'': il campo has_receiver e' quindi null. Potenza RF non chiara.")
for tag, name, mass, power, cells, note in (
        ("single", "3U Deployable Solar Array (singolo)", 0.315, 16.8, 14, "Massa 285-315 g (usato 315 g), 14 celle."),
        ("double", "3U Deployable Solar Array (doppio)", 0.468, 25.2, 21, "Massa 438-468 g (usato 468 g), 21 celle.")):
    add("solar_panel", f"endurosat-solar-3u-deployable-{tag}", "EnduroSat", name, mass,
        dict(face="3U", peak_power_w=power, voltage_options_v=None, open_circuit_voltage_v=17.5, degradation_per_year=None),
        ("https://www.endurosat.com/products/3u-deployable-solar-array/", "Pagina prodotto EnduroSat '3U Deployable Solar Array'"),
        notes=ES_NOTE + f"{note} Potenza in LEO: {power} W per questa configurazione (la pagina cita 8.4 W come valore base per 7 celle e fino a 16.8 / 25.2 W per singolo / doppio). "
              "Tensione massima 17.5 V (per 7 celle), efficienza 30+% BOL e 29+% EOL, rilascio con filo bruciabile, richiede un'alimentazione a 5 V. "
              "Dispiegabile: non si controlla lo spazio di dispiegamento. Dimensioni 84-87 x 335 x 7.7-8.5 mm. Temperatura non dichiarata.")
add("solar_panel", "endurosat-solar-6u-deployable-single", "EnduroSat", "6U Deployable Solar Array (singolo)", 0.770,
    dict(face="6U", peak_power_w=38.4, voltage_options_v=None, open_circuit_voltage_v=39.8, degradation_per_year=None),
    ("https://www.endurosat.com/products/6u-deployable-solar-array/", "Pagina prodotto EnduroSat '6U Deployable Solar Array'"),
    notes=ES_NOTE + "Massa 655-770 g (usato 770 g) per il singolo dispiegabile, 32 celle. La pagina scrive '19.2 W per lato, max 38.4 W (singolo e doppio X/Y) o 29.3 W (doppio Z)': "
          "con 32 celle il singolo dispiegabile e' letto come 38.4 W, ma la lettura e' incerta. Doppio dispiegabile 1065 g non incluso (potenza non chiara). Tensione massima 39.8 V (16S1P), corrente 4 A (4S8P). "
          "209 x 342 x 8.7 mm. Dispiegabile: spazio di dispiegamento non controllato.")

# ======================= Payload di osservazione della Terra: camere e telescopi =======================


def eo(gsd=None, swath=None, ref=None, bands=("RGB",), focal=None, aperture=None, pitch=None, pixels=None, min_u=None,
       ifaces=None, supply=None, storage=None):
    return dict(spectral_bands=list(bands), reference_altitude_km=ref, gsd_m_at_ref=gsd, swath_km_at_ref=swath, focal_length_mm=focal,
                aperture_mm=aperture, pixel_pitch_um=pitch, across_track_pixels=pixels, min_form_factor_u=min_u,
                data_interfaces=ifaces, supply_voltage_ranges_v=supply, storage_gb=storage)


# --- Dragonfly Aerospace (pagine prodotto ufficiali; brochure dietro modulo) ---
DF = "https://dragonflyaerospace.com/products/"
DF_IF = ["LVDS", "SpaceWire", "SPI", "I2C", "CAN", "RS-422", "RS-485"]
DF_NOTE = ("Fonte: pagina prodotto su dragonflyaerospace.com letta il 2026-10-13 (brochure solo via modulo, prezzo non pubblicato). GSD e swath a 500 km, 5 V, "
           "memoria di massa integrata 128 GB, compressione RAW o J2K, uscita 8/10 bit. Temperatura operativa +10..+30 C (sopravvivenza -20..+55 C). Focale, apertura, rivelatore, passo pixel, TID ed eredita' non dichiarati. ")
for cid, name, bands, gsd, swath, mass, power, vol, min_u, note in (
        ("gecko", "Gecko imager (RGB)", ["RGB", "VIDEO"], 39.0, 80.0, 0.5, 6.0, 1.0, 2, "Massa '<0.5 kg' (usato 0.5), 65 x 90 x 105 mm, potenza <6 W in acquisizione e <4 W in lettura. Adatto a CubeSat da 2U."),
        ("gecko-wide", "Gecko imager (RGB, wide swath)", ["RGB", "VIDEO"], 39.0, 160.0, 0.5, 7.0, 1.0, 2, "Variante a largo swath (160 km): massa circa 0.5 kg, <7 W in acquisizione e <4 W in lettura."),
        ("mantis-rgb", "Mantis imager (RGB, snapshot)", ["RGB"], 16.0, 32.0, 0.5, 6.0, 1.0, 2, "Massa '<0.5 kg' (usato 0.5), 65 x 90 x 107 mm, <6 W in acquisizione e <4 W in lettura. Adatto a CubeSat da 2U."),
        ("mantis-ms", "Mantis imager (multispettrale, 6 bande)", ["PAN", "MS"], 32.0, 32.0, 0.5, 6.0, 1.0, 2, "Push-broom con PAN a 16 m e 6 bande MS a 32 m: si usa 32 m (valore MS, piu' prudente). Dati come la variante RGB."),
        ("mantis-hs", "Mantis imager (iperspettrale, 96 bande)", ["PAN", "HS"], 32.0, 32.0, 0.5, 6.0, 1.0, 2, "Push-broom con PAN a 16 m e fino a 96 bande HS; GSD usato 32 m (valore MS, prudente). Dati come la variante RGB."),
        ("chameleon-rgb", "Chameleon imager (RGB, snapshot)", ["RGB"], 10.0, 39.0, 1.6, 10.0, 2.5, None, "Massa 1.6 kg, 2.5U (100 x 100 x 215 mm), <10 W in acquisizione e <5 W in lettura."),
        ("chameleon-ms", "Chameleon imager (multispettrale, 11 bande)", ["PAN", "MS"], 20.0, 39.0, 1.6, 10.0, 2.5, None, "Push-broom con PAN a 10 m e 11 bande MS a 20 m (usato 20 m): GSD binnabile a 20 o 40 m. Dati come la variante RGB."),
        ("chameleon-hs", "Chameleon imager (iperspettrale, 96 bande)", ["PAN", "HS"], 20.0, 20.0, 1.6, 10.0, 2.5, None, "Push-broom con 96 bande HS, swath 20 km; la pagina riporta PAN 10 m e MS 20 m (usato 20 m). Dati come la variante RGB."),
        ("caiman-rgb", "Caiman imager (RGB, snapshot)", ["RGB"], 3.25, 13.0, 1.4, 10.0, 3.0, 6, "Massa 1.4 kg, 3U (100 x 100 x 250 mm) con nCCM posteriore, <10 W in acquisizione e <4 W in lettura. La descrizione dice 'per CubeSat 6U' ma la taglia dichiarata e' 3U (usato 6U come taglia minima)."),
        ("caiman-ms", "Caiman imager (multispettrale, 11 bande)", ["PAN", "MS"], 6.5, 13.0, 1.4, 10.0, 3.0, 6, "Push-broom con PAN a 3.25 m e 11 bande MS a 6.5 m (usato 6.5 m). Dati come la variante RGB.")):
    add("payload", f"dragonfly-{cid}", "Dragonfly Aerospace", name, mass,
        eo(gsd=gsd, swath=swath, ref=500.0, bands=bands, min_u=min_u, ifaces=DF_IF, supply=[[5, 5]], storage=128.0),
        (DF + cid.split("-")[0] + "/", f"Pagina prodotto Dragonfly Aerospace '{cid.split('-')[0].capitalize()}'"),
        power_w=power, volume_u=vol, temp_op_c=[10, 30], trl=9, notes=DF_NOTE + note)

# --- AAC Hyperion IM200 ---
add("payload", "hyperion-im200", "Hyperion Technologies (AAC Hyperion)", "IM200 optical imager", 0.059,
    eo(bands=["MONO", "RGB"], focal=50.0, pixels=2048, ifaces=["USB", "UART"], supply=[[3.6, 5.0]]),
    ("https://www.aac-clyde.space/wp-content/uploads/2021/11/IM200.pdf", "AAC Hyperion IM200 datasheet (release 15 Nov 2021) + pagina prodotto"),
    power_w=0.7, tid_krad=9, temp_op_c=[-20, 40], trl=9,
    notes=HY_NOTE + "Imager generico da 4 Mpixel (2048 x 1944), frame buffer da 25 immagini, 5 fps a piena risoluzione, obiettivi standard da 16, 25, 35 o 50 mm (F1.2 o F2.0): la massa 59 g e le dimensioni 29 x 29 x 70.7 mm sono con l'obiettivo da 50 mm. "
          "Il passo pixel NON e' dichiarato, quindi GSD e swath non sono calcolabili (un requisito di GSD o swath lo scarta). USB 2.0 (480 Mbps) e UART TTL standard; RS-422/RS-485 e I2C opzionali. "
          "0.7 W tipici (0.4-1.0 W), 3.6-5 V, TID >9 krad, in orbita dal 2019, derivato dallo star tracker ST200.")

# --- Simera Sense (pagine di ciascuna variante, lette il 2026-10-13) ---
SIM = "https://simera-sense.com/"
SIM_IF = ["I2C", "SPI", "RS-422", "SpaceWire", "LVDS"]
SIM_NOTE = ("Fonte: pagina della variante su simera-sense.com letta il 2026-10-13 (ICD, manuali e brochure sono dietro modulo o richiesta; TRL, eredita' di volo e prezzo non pubblicati). "
            "GSD e swath a 500 km. Potenza: in acquisizione il valore dichiarato (usato come power_w), a riposo e' nelle note. 'Pienamente funzionante fino a 15 krad' non e' etichettato come TID ma e' usato come tid_krad. ")


def simera(cid, name, bands, url, family, gsd, swath, mass, vol, min_u, focal, aperture, pitch, pixels, power, idle, supply, storage, tid, dims, sensor_note):
    add("payload", f"simera-{cid}", "Simera Sense", name, mass,
        eo(gsd=gsd, swath=swath, ref=500.0, bands=bands, focal=focal, aperture=aperture, pitch=pitch, pixels=pixels, min_u=min_u,
           ifaces=SIM_IF, supply=supply, storage=storage),
        (SIM + url, f"Pagina prodotto Simera Sense '{name.split(' (')[0]}'"),
        power_w=power, volume_u=vol, tid_krad=tid, temp_op_c=[-10, 50],
        notes=SIM_NOTE + sensor_note + (f" Ingombro {dims}." if dims else "") + (f" Potenza a riposo {idle} W." if idle else "")
              + (" Potenza in acquisizione non pubblicata (power_w null: si assume un valore generico)." if power is None else "")
              + f" Famiglia {family}: " + {"xScape50": "taglia minima 3U (le FAQ del sito dicono 3U, le schede 1U di volume), 120.5 x 95.88 x 90.17 mm, 0.51 kg.",
                                           "xScape100": "volume 1.5U, taglia minima 6U secondo le FAQ del sito.",
                                           "xScape200": "per bus da 16U o piu' secondo il sito (volume dichiarato '12U' ma 339 x 216 x 216 mm), ITAR-free."}[family])


V5 = [[4.75, 5.25]]
V20 = [[11.5, 20.0]]
simera("triscape50", "TriScape50 (xScape50, RGB)", ["RGB", "VIDEO"], "products/triscape50/", "xScape50", 30.0, 120.0, 0.51, 1.0, 3, 93.9, 11.75, 5.5, 4096,
       None, None, V5, 128.0, 15.0, "120.5 x 95.88 x 90.17 mm", "Snapshot/video 1080p30, CMOS a otturatore globale 4096 x 3072 (12.6 MP), Bayer RGB con filtro NIR, 10 bit, 450-670 nm, campo 13.68 x 10.28 gradi; 5 V, 1.8 A.")
simera("multiscape50", "MultiScape50 (xScape50, 1 PAN + 7 VNIR)", ["PAN", "MS", "VNIR"], "products/multiscape50/", "xScape50", 30.0, 120.0, 0.51, 1.0, 3, 93.9, 11.75, 5.5, 4096,
       5.5, 3.25, V5, 128.0, 15.0, "120.5 x 95.88 x 90.17 mm", "Push-broom CMOS 4096 pixel, 12 bit, dTDI da 1 a 32 stadi per banda, 8 bande VNIR (450-900 nm); 5 V, 1.8 A (1.1 A in acquisizione).")
simera("hyperscape50", "HyperScape50 (xScape50, 32 bande VNIR)", ["HS", "VNIR"], "products/hyperscape50/", "xScape50", 30.0, 120.0, 0.51, 1.0, 3, 93.9, 11.75, 5.5, 4096,
       7.75, 4.5, V5, 128.0, 15.0, "120.5 x 95.88 x 90.17 mm", "Push-broom CMOS 4096 pixel, 12 bit, 32 bande scelte tra 400 (460-860 nm, FWHM 3.5%), dTDI 1-8 stadi; riconfigurabile da terra.")
simera("triscape100", "TriScape100 (xScape100, RGB)", ["RGB", "VIDEO"], "products/triscape100/", "xScape100", 4.75, 19.4, 1.26, 1.5, 6, 580.0, 95.0, 5.5, 4096,
       6.75, 2.75, V5, 128.0, 15.0, "176.5 x 98.3 x 98.3 mm", "Snapshot/video 1080p30, CMOS 4096 x 3072 (12.6 MP), Bayer RGB, 10 bit, 450-670 nm, campo 2.22 x 1.66 gradi; massa 1.26 kg +-5%.")
simera("multiscape100", "MultiScape100 (xScape100, 1 PAN + 7 VNIR)", ["PAN", "MS", "VNIR"], "products/multiscape100/", "xScape100", 4.75, 19.4, 1.26, 1.5, 6, 580.0, 95.0, 5.5, 4096,
       7.0, 3.25, V5, 128.0, 15.0, "176.5 x 98.3 x 98.3 mm", "Push-broom CMOS a otturatore globale 4096 pixel, 12 bit, dTDI 1-32 per banda, 8 bande VNIR (450-900 nm), campo 2.22 gradi; massa 1.26 kg +-5%.")
simera("hyperscape100", "HyperScape100 (xScape100, 32 bande VNIR)", ["HS", "VNIR"], "products/hyperscape100/", "xScape100", 4.75, 19.4, 1.26, 1.5, 6, 580.0, 95.0, 5.5, 4096,
       7.75, 4.0, V5, 128.0, 15.0, "176.5 x 98.3 x 98.3 mm", "Push-broom 4096 pixel, 12 bit, 32 bande scelte tra 400 (460-860 nm), dTDI 1-8; massa 1.26 kg +-5%.")
simera("monoscape200", "MonoScape200 DU (xScape200, monocromatico)", ["MONO", "PAN"], "earth-observation-cameras/xscape200-dual-use/", "xScape200", 1.5, 12.3, 9.3, 12.0, 16, 1067.0, 190.0, 3.2, 8192,
       None, None, V20, 128.0, 25.0, "339 x 216 x 216 mm", "Snapshot con sensore monocromatico XGS45000: la pagina non ha una scheda propria, i dati sono quelli del livello famiglia (consumi non pubblicati; alimentazione 11.5-20 V presa dalle varianti TriScape e MultiScape200).")
simera("triscape200", "TriScape200 DU (xScape200, RGB)", ["RGB"], "products/triscape200/", "xScape200", 1.5, 12.3, 9.3, 12.0, 16, 1067.0, 190.0, 3.2, 8192,
       8.5, 2.5, V20, 128.0, 25.0, "339 x 216 x 216 mm", "Snapshot XGS45000 a colori 8192 x 5460, 12 bit, Bayer RGB, 450-680 nm, campo 1.4 x 0.94 gradi; 11.5-20 V, 2.5 A; potenze a 25 C.")
simera("multiscape200", "MultiScape200 DU (xScape200, 1 PAN + 8 MS)", ["PAN", "MS", "VNIR"], "products/multiscape200/", "xScape200", 1.5, 12.3, 9.3, 12.0, 16, 1067.0, 190.0, 3.2, 8192,
       8.75, 4.0, V20, 128.0, 25.0, "339 x 216 x 216 mm", "Push-broom XGS45000, 8192 pixel, 16 bit, 9 bande (1 PAN + 8 VNIR); 11.5-20 V, 2.5 A; potenze a 25 C.")

# --- Satlantis iSIM-90 ---
add("payload", "satlantis-isim-90", "Satlantis", "iSIM-90 telescope/camera", 4.0,
    eo(gsd=2.0, swath=13.0, ref=500.0, bands=["PAN", "VNIR"], min_u=12),
    ("https://www.satlantis.com/jet-popup/main-features-isim-90/", "Pagina 'Main Features iSIM 90' di Satlantis"),
    notes="Fonte: pagina del fornitore letta il 2026-10-13 (consumi, dimensioni, interfacce e prezzo non pubblicati). Massa 'sotto 4 kg' (usato 4.0), per CubeSat 12U e 16U, convalidato in orbita nel Q4 2021. "
          "GSD 2 m in PAN e VNIR a 500 km con swath 13-23.5 km (usato 13 km); la versione SWIR ha GSD 5 m e swath 8.2 km (non modellata). Esiste anche la versione iSIM-170 per microsatelliti (circa 15 kg), non inclusa. "
          "Altri cataloghi riportano 25 W medi e masse fino a 6 kg: non verificati sulle pagine del fornitore.")

SAT_NOTE = ("Fonte: pagine del fornitore (Main Features, letta il 2026-10-13); consumi, dimensioni, interfacce, TRL e prezzo non pubblicati (cataloghi di terzi riportano 25 W medi per l'iSIM-90: non verificati). ")
add("payload", "satlantis-isim-90-swir", "Satlantis", "iSIM-90 telescope/camera (canale SWIR)", 4.0,
    eo(gsd=5.0, swath=8.2, ref=500.0, bands=["SWIR"], min_u=12),
    ("https://www.satlantis.com/jet-popup/main-features-isim-90/", "Pagina 'Main Features iSIM 90' di Satlantis"),
    notes=SAT_NOTE + "Canale SWIR dello stesso strumento a due canali (VNIR e/o SWIR): GSD 5 m e swath 8.2 km a 500 km; la massa 'sotto 4 kg' e' quella dello strumento, non e' in aggiunta al canale VNIR. Per CubeSat 12U e 16U.")
for cid, name, bands, gsd, swath, note in (
        ("satlantis-isim-170", "iSIM-170 telescope/camera", ["PAN", "VNIR"], 1.0, 7.5, "PAN e VNIR: GSD 'sotto 1 m' (usato 1.0) e swath 7.5-13.5 km (usato 7.5) a 500 km."),
        ("satlantis-isim-170-swir", "iSIM-170 telescope/camera (canale SWIR)", ["SWIR"], 2.5, 4.2, "Canale SWIR: GSD 2.5 m e swath 4.2 km a 500 km.")):
    add("payload", cid, "Satlantis", name, 15.0,
        eo(gsd=gsd, swath=swath, ref=500.0, bands=bands),
        ("https://www.satlantis.com/jet-popup/main-features-isim-170/", "Pagina 'Main Features iSIM 170' di Satlantis"),
        notes=SAT_NOTE + "Per microsatelliti (50-100 kg), non per CubeSat: massa 'sotto 15 kg' (usato 15.0, supera i 12 kg ammessi a una struttura 6U) e taglia minima non dichiarata. Validato in orbita nel Q2 2020. " + note)
add("payload", "satlantis-graphium", "Satlantis", "GRAPHIUM telescope", 100.0,
    eo(gsd=0.5, swath=10.0, ref=None, bands=["PAN", "VNIR", "VIDEO"]),
    ("https://www.satlantis.com/graphium/", "Pagina prodotto Satlantis 'GRAPHIUM'"),
    notes="Fonte: pagina del fornitore letta il 2026-10-13. Telescopio ad altissima risoluzione con immagini e video per MINISATELLITI, non CubeSat: GSD 0.5 m, swath 10 km, PAN piu' fino a 6 bande VNIR, massa 'sotto 100 kg' (usato 100.0). "
          "La quota di riferimento di GSD e swath NON e' dichiarata, quindi GSD e swath non si scalano con la quota e un requisito EO lo scarta. Consumi, dimensioni, interfacce e prezzo non pubblicati.")

# --- GomSpace NanoCam C1U (fuori produzione) ---
for tag, focal, mass, gsd650, vol, dim in (("8mm", 8.2, 0.167, 260.0, None, "86.0 x 91.7 x 55.1"), ("35mm", 35.0, 0.169, 60.0, None, "86.0 x 91.7 x 57.9"), ("70mm", 70.0, 0.277, 30.0, None, "86.0 x 91.7 x 97.2")):
    add("payload", f"gomspace-nanocam-c1u-{tag}", "GomSpace", f"NanoCam C1U ({tag.replace('mm', ' mm')})", mass,
        eo(gsd=gsd650, swath=round(gsd650 * 2048 / 1000, 1), ref=650.0, bands=["RGB"], focal=focal, pixels=2048, min_u=1,
           ifaces=["CAN", "I2C", "UART"], supply=[[3.2, 3.6]], storage=2.0),
        ("https://gomspace.com/wp-content/uploads/2025/12/gs-ds-nanocam-c1u_DS_-_1010105_-_1_-_18_-_1.pdf", "GomSpace NanoCam C1U datasheet DS 1010105 rev 1.8 (12 Jul 2018) + pagina prodotto"),
        power_w=0.8, temp_op_c=[0, 60], status="nla",
        notes="Il datasheet riporta un avviso di confidenzialita' GomSpace. Segnalato dal fornitore come fuori produzione ('non piu' in vendita'). CMOS a colori da 1/2 pollice, 2048 x 1536, Bayer RGGB a 10 bit, GSD '<" + f"{gsd650:g}" + " m' a 650 km (e' un limite superiore). "
              "Lo swath e' DERIVATO come 2048 pixel x GSD (non dichiarato). Massa e ingombro " + dim + " mm per questa ottica (77 g senza ottica). Potenza: 0.38 W a riposo, 0.8 W in acquisizione, 1.3 W all'avvio; 3.2-3.6 V; "
              "0-60 C; PC/104 96 x 90 mm; ARM SAMA5D35, 512 MB DDR2 e 2 GB di immagini; CSP su CAN, I2C e UART. TID non dichiarata.")

# immagini: fonte di ciascuna (generata da build.py)
import os
_info = os.path.join(os.path.dirname(os.path.abspath(__file__)), "image_info.json")
if os.path.exists(_info):
    _imgs = json.load(open(_info, encoding="utf-8"))
    for _c in out:
        if _c["id"] in _imgs:
            _c["image"] = _imgs[_c["id"]]

json.dump({"_comment": "Catalogo da documenti pubblici dei fornitori. verified=false: nessun valore e' stato ricontrollato da una persona. "
                       "null = non dichiarato dal fornitore.", "components": out},
          open(sys.argv[1], "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print(len(out), "componenti")

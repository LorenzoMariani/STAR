"""Aggiunge `dimensions` ai componenti del catalogo, dalle fonti gia' citate in `source` e da pagine di prodotto lette il 2026-10-14.

    python tools/add_dimensions.py <cartella-del-progetto>

basis: declared = numeri scritti dal fornitore; standard = formato normato (PC/104, struttura CubeSat della CDS) con l'altezza dichiarata o, se
cosi' scritto, il passo del modulo; derived = dalla taglia nominale (es. 1U = 100 mm). Un valore null = non dichiarato. I componenti non elencati
non hanno dimensioni pubbliche (EnduroSat le fornisce solo dietro modulo con CAD e datasheet; Satlantis, NanoAvionics e Spacemind non le pubblicano)."""
import json
import sys
from pathlib import Path

PROJ = Path(sys.argv[1])
PC104 = [95.89, 90.17]          # CubeSat Kit / PC/104-size: 3.775 x 3.550 in
IN = 25.4
D, S, V = "declared", "standard", "derived"

TABLE = {
    # --- strutture (ingombro esterno; la lunghezza lunga e' la z)
    "endurosat-structure-3u": ([100, 100, 340.5], D, "Catalogo EnduroSat 02/2022 p.20, X-Y-Z."),
    "endurosat-structure-6u": ([100, 226.3, 366], D, "Catalogo EnduroSat 02/2022 p.20, X-Y-Z."),
    "isis-structure-3u": ([100, 100, 340.5], D, "Brochure ISIS, 'ingombro'."),
    "isis-structure-6u": ([100, 226.3, 340.5], D, "Brochure ISIS; la lunghezza dichiarata (340.5) differisce dai 366 mm del 6U della CDS."),
    "gomspace-nanostruct-6u": ([340.5, 226.3, 100], D, "Datasheet GomSpace, senza kill switch; ordine z, x, y come nel datasheet."),
    "gomspace-nanostruct-12u": ([340.5, 226.3, 226.3], D, "Datasheet GomSpace 1043916, senza kill switch; ordine z, x, y."),
    "aac-zaphod-3u": ([100, 100, 340.5], D, "Datasheet AAC ZAPHOD."),
    "aac-zaphod-6u": ([100, 226.3, 340.5], D, "Datasheet AAC ZAPHOD; la lunghezza dichiarata (340.5) differisce dai 366 mm del 6U della CDS."),
    "aac-zaphod-12u": ([340.5, 226.3, 226.3], D, "Scheda satsearch del fornitore; ordine z, x, y."),
    "spacemind-sm03": ([340.5, 100, 100], D, "Pagina prodotto Spacemind, senza kill switch; ordine z, x, y."),
    "spacemind-sm06": ([340.5, 226.3, 100], D, "Pagina prodotto Spacemind, senza kill switch; ordine z, x, y."),
    "spacemind-sm12": ([340.5, 226.3, 226.3], D, "Pagina prodotto Spacemind, senza kill switch; ordine z, x, y."),
    "nanoavionics-frame-6u": ([100, 226.3, 366], S, "La pagina non pubblica dimensioni: ingombro nominale del 6U secondo la CDS Rev. 14.1."),
    # --- schede PC/104 e moduli
    "aac-optimus-30": ([95.89, 90.17, 21.55], D, "Datasheet AAC OPTIMUS."),
    "aac-optimus-40": ([95.89, 90.17, 27.35], D, "Datasheet AAC OPTIMUS."),
    "aac-optimus-80": ([95.89, 90.17, 56.94], D, "Datasheet AAC OPTIMUS."),
    "aac-starbuck-nano-plus": ([95.89, 90.17, 20.82], D, "Datasheet AAC STARBUCK-NANO PLUS."),
    "aac-kryten-m3": ([95.89, 90.17, 5.51], D, "Datasheet AAC KRYTEN-M3."),
    "aac-sirius-obc-leon3ft": ([95.89, 90.17, 17.2], D, "Datasheet AAC SIRIUS-OBC."),
    "aac-q7s": ([78, 43, 19], D, "Datasheet AAC Q7S: altezza 9-19 mm secondo il connettore (usato il massimo)."),
    "aac-pulsar-utrx": ([96, 90, 16.35], D, "Datasheet AAC PULSAR-UTRX."),
    "aac-pulsar-vutrx": ([96, 90, 16.51], D, "Datasheet AAC PULSAR-VUTRX."),
    "aac-pulsar-hstx": ([96, 90, 17.41], D, "Datasheet AAC PULSAR-HSTX."),
    "aac-trx-u": ([83, 57, 16], D, "Datasheet AAC TRX-U."),
    "aac-quasar-strx": ([93, 88, 24], D, "Datasheet AAC QUASAR."),
    "isis-trxvu": ([90, 96, 15], D, "Brochure ISIS TRXVU."),
    "cubespace-cubeadcs-3axis-small": ([90, 96, 57], D, "Datasheet CubeSpace CubeADCS Gen 1."),
    "cubespace-cubeadcs-ymomentum-small": ([90, 96, 48], D, "Datasheet CubeSpace CubeADCS Gen 1."),
    "gomspace-nanomind-a3200": ([65, 40, 7.1], D, "Datasheet GomSpace A3200 (scheda piccola, non PC/104 pieno)."),
    "gomspace-nanocom-ax100": ([65, 40, 6.5], D, "Datasheet GomSpace AX100 (scheda piccola, non PC/104 pieno)."),
    "gomspace-nanopower-p60": ([92, 88.9, 19.9], D, "Pagina GomSpace: 19.9 mm con 3 moduli (dock + ACU + PDU), 28.9 mm con 5."),
    "gomspace-nanopower-p80": ([95, 95, 38.8], D, "Pagina GomSpace: 38.8 mm con 3 moduli (PMU + ACU + PDU), fino a 65 mm con 5."),
    "gomspace-bpx-100wh-16v": ([93, 86, 41], D, "Datasheet GomSpace BPX."),
    "gomspace-bpx-100wh-32v": ([93, 86, 41], D, "Pagina GomSpace BPX (stesso ingombro delle altre configurazioni)."),
    "gomspace-bp8-100wh": ([94.8, 95, 42], D, "Datasheet GomSpace BP8."),
    "pumpkin-mai-100": ([100, 100, 78.74], D, "Datasheet MAI-100."),
    "pumpkin-mai-200": ([100, 100, 78.74], D, "Datasheet MAI-200."),
    "nanoavionics-satcom-uhf": ([56.1, 32.9, 6.56], D, "Pagina NanoAvionics SatCOM UHF."),
    "satlab-srs-3": ([87.0, 93.0, 17.0], D, "Datasheet Satlab SRS-3."),
    "satlab-srs-4": ([93.0, 87.2, 18.0], D, "Datasheet Satlab SRS-4 (la pagina riporta 17.5 mm)."),
    "satlab-srx-8": ([93.0, 87.2, 22.0], D, "Datasheet Satlab SRX-8."),
    "bct-xact-15": ([100, 100, 50], D, "Scheda Blue Canyon XACT (0.5U)."),
    "bct-xact-50": ([100, 100, 75.4], D, "Scheda Blue Canyon XACT (0.75U)."),
    "bct-xact-100": ([100, 100, 50], D, "Scheda Blue Canyon XACT, esclusi i componenti esterni."),
    "bct-battery-1p8s": ([round(1.8 * IN, 1), round(4.2 * IN, 1), round(3.5 * IN, 1)], D, "Scheda Blue Canyon: 1.8 x 4.2 pollici, altezza 3.5 pollici."),
    "bct-battery-2p8s": ([round(1.8 * IN, 1), round(7.2 * IN, 1), round(3.5 * IN, 1)], D, "Scheda Blue Canyon: 1.8 x 7.2 pollici, altezza 3.5 pollici."),
    "spacemind-gemini-eps": ([90.2, 95.9, 25], D, "Pagina Spacemind GEMINI."),
    "hyperion-iadcs200": ([95, 90, 32], D, "Datasheet AAC Hyperion iADCS200 (2 schede PC104)."),
    "hyperion-iadcs400": ([95.4, 95.9, 67.3], D, "Datasheet AAC Hyperion iADCS400."),
    "innoflight-cfc-400-champs": ([82, 82, 29], D, "Scheda CFC-400 su SatCatalog, senza scheda figlia."),
    "hyperion-im200": ([29, 29, 70.7], D, "Datasheet AAC Hyperion IM200, con l'obiettivo indicato nelle note."),
    "aac-starbuck-nano": ([95.89, 90.17, 16.2], D, "Pagina prodotto AAC STARBUCK-NANO (il datasheet 2021 non riporta le dimensioni)."),
    "endurosat-uhf": ([95, 89, 23.2], D, "Scheda satsearch (89 x 95 x 23.2 mm, aggiornata il 2026-07-14): non e' sul sito EnduroSat, dove le quote sono dietro modulo CAD/datasheet."),
    "endurosat-xband": ([95.9, 90.2, 23.3], D, "Scheda satsearch (95.9 x 90.2 x 23.3 mm): attenzione, la scheda riporta 270 g come il catalogo EnduroSat 2022, mentre la pagina attuale ne dichiara 396: le quote potrebbero riferirsi a una revisione precedente."),
    # --- schede con ingombro in pianta normato PC/104 e altezza = passo del modulo dichiarato dal fornitore (15 mm)
    "pumpkin-csk-mb-ppma1": (PC104 + [15.0], S, "Datasheet Pumpkin: 'PC/104-size footprint', passo normale tra moduli 15 mm; le quote sono nel disegno, non nel testo."),
    "pumpkin-csk-mb-ppma2": (PC104 + [15.0], S, "Come il motherboard CubeSat Kit: ingombro PC/104, passo 15 mm."),
    "pumpkin-csk-mb-ppma3": (PC104 + [15.0], S, "Come il motherboard CubeSat Kit: ingombro PC/104, passo 15 mm."),
    "pumpkin-csk-mb-ppmb1": (PC104 + [15.0], S, "Come il motherboard CubeSat Kit: ingombro PC/104, passo 15 mm."),
    "pumpkin-csk-mb-ppmd1": (PC104 + [15.0], S, "Come il motherboard CubeSat Kit: ingombro PC/104, passo 15 mm."),
    "pumpkin-csk-mb-ppmd2": (PC104 + [15.0], S, "Come il motherboard CubeSat Kit: ingombro PC/104, passo 15 mm."),
    "pumpkin-fm430": (PC104 + [15.0], S, "Datasheet FM430: 'PC/104-size footprint', passo normale 15 mm."),
    "pumpkin-linear-eps-11wh": (PC104 + [15.0], S, "Ingombro PC/104; il datasheet dichiara pin di 10.4 mm esclusi e 25 mm liberi sopra con l'opzione /01: altezza reale con batterie non estratta."),
    "pumpkin-linear-eps-22wh": (PC104 + [15.0], S, "Ingombro PC/104; il datasheet dichiara pin di 10.4 mm esclusi e 25 mm liberi sopra con l'opzione /01: altezza reale con batterie non estratta."),
    "pumpkin-bm1-40wh": (PC104 + [15.0], S, "Ingombro PC/104; altezza con le celle non estratta dal disegno."),
    "nanoavionics-eps-1-0": (PC104 + [None], S, "La pagina dichiara lo standard PC/104 senza quote: ingombro in pianta normato, altezza non dichiarata."),
    "alenspace-dara-obc": (PC104 + [None], S, "La pagina dichiara il formato PC104 senza quote: ingombro in pianta normato, altezza non dichiarata."),
    # --- pannelli
    "endurosat-solar-3u-deployable-single": ([87, 335, 8.5], D, "Pagina EnduroSat: 84-87 x 335 x 7.7-8.5 mm (usati i massimi)."),
    "endurosat-solar-3u-deployable-double": ([87, 335, 8.5], D, "Pagina EnduroSat: 84-87 x 335 x 7.7-8.5 mm (usati i massimi); la versione doppia non ha dimensioni separate."),
    "endurosat-solar-6u-deployable-single": ([209, 342, 8.7], D, "Pagina EnduroSat."),
    "aac-photon-side-3u": ([100, 340.5, 3.5], V, "Datasheet AAC PHOTON-SIDE: taglia di faccia 3U (100 x 340.5 mm nominali), altezza 3.5 mm."),
    "isis-solar-3u": ([100, 340.5, 2.5], V, "Brochure ISIS: pannello laterale 3U, spessore 2.5 mm (superiore e inferiore 1.8 mm); taglia di faccia nominale."),
    # --- payload e star tracker
    "dragonfly-gecko": ([65, 90, 105], D, "Pagina Dragonfly Aerospace Gecko."),
    "dragonfly-gecko-wide": ([65, 90, 105], D, "Pagina Dragonfly Aerospace: stessa taglia della versione standard."),
    "dragonfly-mantis-rgb": ([65, 90, 107], D, "Pagina Dragonfly Aerospace Mantis."),
    "dragonfly-mantis-ms": ([65, 90, 107], D, "Pagina Dragonfly Aerospace: stessa taglia di tutte le versioni Mantis."),
    "dragonfly-mantis-hs": ([65, 90, 107], D, "Pagina Dragonfly Aerospace: stessa taglia di tutte le versioni Mantis."),
    "dragonfly-chameleon-rgb": ([100, 100, 215], D, "Pagina Dragonfly Aerospace Chameleon (2.5U)."),
    "dragonfly-chameleon-ms": ([100, 100, 215], D, "Pagina Dragonfly Aerospace: stessa taglia di tutte le versioni Chameleon."),
    "dragonfly-chameleon-hs": ([100, 100, 215], D, "Pagina Dragonfly Aerospace: stessa taglia di tutte le versioni Chameleon."),
    "dragonfly-caiman-rgb": ([100, 100, 250], D, "Pagina Dragonfly Aerospace Caiman (3U, con nCCM posteriore)."),
    "dragonfly-caiman-ms": ([100, 100, 250], D, "Pagina Dragonfly Aerospace: stessa taglia delle versioni Caiman."),
    "simera-triscape50": ([120.5, 95.88, 90.17], D, "Pagina Simera Sense xScape50."),
    "simera-multiscape50": ([120.5, 95.88, 90.17], D, "Pagina Simera Sense xScape50."),
    "simera-hyperscape50": ([120.5, 95.88, 90.17], D, "Pagina Simera Sense xScape50."),
    "simera-triscape100": ([176.5, 98.3, 98.3], D, "Pagina Simera Sense xScape100."),
    "simera-multiscape100": ([176.5, 98.3, 98.3], D, "Pagina Simera Sense xScape100."),
    "simera-hyperscape100": ([176.5, 98.3, 98.3], D, "Pagina Simera Sense xScape100."),
    "simera-monoscape200": ([339, 216, 216], D, "Pagina Simera Sense xScape200."),
    "simera-triscape200": ([339, 216, 216], D, "Pagina Simera Sense xScape200."),
    "simera-multiscape200": ([339, 216, 216], D, "Pagina Simera Sense xScape200."),
    "gomspace-nanocam-c1u-8mm": ([86.0, 91.7, 55.1], D, "Datasheet GomSpace NanoCam C1U, ottica 8 mm."),
    "gomspace-nanocam-c1u-35mm": ([86.0, 91.7, 57.9], D, "Datasheet GomSpace NanoCam C1U, ottica 35 mm."),
    "gomspace-nanocam-c1u-70mm": ([86.0, 91.7, 97.2], D, "Datasheet GomSpace NanoCam C1U, ottica 70 mm."),
    "hyperion-st200": ([29, 29, 38.1], D, "Datasheet AAC Hyperion ST200, senza baffle."),
    "cubespace-cubestar": ([35, 49, 24], D, "Pagina CubeSat Shop CubeStar (L x A x P come sulla pagina)."),
    "rocketlab-st16rt2": ([62, 56, 38], D, "Scheda Rocket Lab ST-16RT2 senza baffle (62 x 56 x 68 con baffle corto)."),
    "bct-nst-standard": ([100, 55, 50], D, "Datasheet Blue Canyon NST REV 1/2026: 10 x 5.5 x 5 cm."),
    "bct-nst-mid": ([170, 85, 70], D, "Datasheet Blue Canyon NST REV 1/2026: 17 x 8.5 x 7 cm."),
    "bct-nst-full": ([250, 100, 100], D, "Datasheet Blue Canyon NST REV 1/2026: 25 x 10 x 10 cm."),
    "tesat-cubelct": ([90, 95, 35], D, "Datasheet Tesat CubeLCT 2019-09: 9 x 9.5 x 3.5 cm."),
    "aac-cubecat": ([96, 96, 96], D, "Datasheet AAC CubeCAT."),
    "tesat-scot20": ([100, 100, 100], V, "Taglia nominale 1U dalla scheda satsearch; dimensioni reali non pubblicate."),
    "tesat-scot30": ([230, 280, 200], D, "Datasheet Tesat SCOT30 2026-08."),
    "tesat-scot80": ([310, 290, 470], D, "Datasheet Tesat SCOT80 2025-03: testa ottica 31 x 29 x 47 cm; l'elettronica LCT (26 x 19 x 24 cm) e' un'unita' a parte."),
}

path = PROJ / "data" / "catalog.json"
cat = json.loads(path.read_text(encoding="utf-8"))
ids = {c["id"] for c in cat["components"]}
unknown = set(TABLE) - ids
assert not unknown, unknown
n = 0
for c in cat["components"]:
    entry = TABLE.get(c["id"])
    if entry is None:
        c.pop("dimensions", None)
        continue
    mm, basis, note = entry
    c["dimensions"] = {"mm": mm, "basis": basis, "note": note}
    n += 1
path.write_text(json.dumps(cat, indent=1, ensure_ascii=False), encoding="utf-8")
missing = [c["id"] for c in cat["components"] if "dimensions" not in c]
print(n, "componenti con dimensioni;", len(missing), "senza")
print("senza:", ", ".join(missing))

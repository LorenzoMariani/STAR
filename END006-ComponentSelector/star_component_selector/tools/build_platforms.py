"""Crea data/platforms.json (piattaforme complete Tyvak/Terran Orbital) e le relative immagini con la fonte."""
import csv, json, sys
from pathlib import Path
from PIL import Image
from PIL.PngImagePlugin import PngInfo

SCR, PROJ = Path(sys.argv[1]), Path(sys.argv[2])
RET = "2026-10-13"
BASE = "https://assets.science.nasa.gov/content/dam/science/cds/spacecraft-development/rsdo/rapid-iv-catalog/"
NOTICE = ("Immagine di proprieta' del produttore, qui solo come riferimento visivo del prodotto; per usi diversi (pubblicazioni, "
          "presentazioni esterne) chiedere il permesso al produttore.")
COMMON_COMMS = {"UHF": "9.6 kbps (uplink e downlink)", "S-band": "125 kbps uplink, 2 Mbps downlink", "X-band": "50 Mbps downlink"}
P = [
    dict(id="tyvak-triumph", name="Triumph (6U)", pdf="TYVAK_TRIUMPH_PLATFORM_DATA_SHEET.pdf", img="triumph", page=1, file="Tyvak-Triumph.png",
         form_factor_u=6, orbit="LEO", native_orbits_km=[400, 1200], launch_mass_kg_max=14.0, payload_mass_kg_max=5.0, solar_array_power_w_max=100.0,
         redundancy="single-string", power_buses="12 V non regolati, 3.3 V, 5 V", comms=COMMON_COMMS, propulsion="nessuna di serie, opzioni disponibili",
         pointing_arcsec=[30, 75], dimensions=None,
         modules=["Flight computer", "Backplane", "Moduli batteria 12 V (2)", "MPPT 12 V", "Load controller 12 V", "Sensori solari grossolani (2)",
                  "Star tracker (2)", "GPS", "Magnetorquer (3)", "Ruote di reazione (3)", "Radio LDRR", "Radio MDR", "IMU"],
         notes="Piattaforma 6U piu' volata della linea, in precedenza chiamata Trestles; array solare compatto a tre sezioni; compatibile con dispenser a rotaie "
               "(anche quelli venduti da Terran Orbital). Hardware con eredita' di volo (NASA Pathfinder Technology Demonstrator, GeoStare SV2)."),
    dict(id="tyvak-renegade", name="Renegade (12U)", pdf="TYVAK_RENEGADE_PLATFORM_DATA_SHEET.pdf", img="renegade", page=1, file="Tyvak-Renegade.png",
         form_factor_u=12, orbit="LEO", native_orbits_km=[400, 1200], launch_mass_kg_max=25.0, payload_mass_kg_max=10.0, solar_array_power_w_max=100.0,
         redundancy="single-string", power_buses="12 V non regolati, 3.3 V, 5 V", comms=COMMON_COMMS, propulsion="nessuna di serie, opzioni disponibili",
         pointing_arcsec=[30, 75], dimensions=None,
         modules=["Flight computer", "Backplane", "Moduli batteria 12 V (3)", "MPPT 12 V (2)", "Load controller 12 V (1)", "Sensori solari grossolani (2)",
                  "Star tracker (2)", "GPS", "Magnetorquer (3)", "Ruote di reazione (3)", "Radio LDRR", "Radio MDR", "IMU (1)"],
         notes="Configurabile anche a 16U. Il miglior rapporto massa piattaforma/massa payload della linea, puo' ospitare un imager ottico da 19 cm di diametro. "
               "Derivata dalla piattaforma Trestles; array solare compatto a tre sezioni; dispenser a rotaie."),
    dict(id="tyvak-nebula", name="Nebula (ESPA)", pdf="TYVAK_NEBULA%20_PLATFORM_DATA_SHEET.pdf", img="nebula", page=2, file="Tyvak-Nebula.png",
         form_factor_u=None, orbit="LEO", native_orbits_km=[400, 1200], launch_mass_kg_max=250.0, payload_mass_kg_max=130.0, solar_array_power_w_max=1000.0,
         redundancy="dual-string", power_buses="sistema a 66 V; 28 V, 12 V e 9 V disponibili per il payload",
         comms={"S-band": "125 kbps uplink, 2 Mbps downlink", "X-band": "650 Mbps downlink"},
         propulsion="elettrica a effetto Hall di serie (impulso specifico 2150 s), spinta 1.1 mN", pointing_arcsec=[10, 50],
         dimensions="82 x 58 x 39 cm senza pannelli solari",
         modules=["Flight computer (2)", "Watchdog", "Backplane", "Moduli batteria 66 V (8-12)", "MPPT 66 V (2)", "Load controller 66 V",
                  "Punti di carico 28 V alta potenza (variabili)", "Punti di carico 28 V bassa potenza (variabili)", "Sensori solari grossolani (4)",
                  "Gruppo giroscopi", "Star tracker (3)", "GPS (2)", "Magnetorquer (3)", "Ruote di reazione (4)", "Radio LDRR (2)", "Radio MDR (2)"],
         notes="Microsatellite su porta ESPA da 15 pollici o ESPA Grande da 24 pollici; crittografia Type 1 opzionale (DoD/Intel). Non e' un CubeSat. "
               "La generazione precedente (Zuma) e' servita per la Tranche 0 Transport Layer della Space Development Agency."),
]
out, rows = [], []
for p in P:
    img_url = f"{BASE}{p['pdf']}#page={p['page']}"
    meta = PngInfo()
    for k, v in (("Title", f"Tyvak {p['name']}"), ("Author", "Tyvak Nano-Satellite Systems (Terran Orbital)"), ("Source", img_url),
                 ("Description", f"Piattaforma {p['id']}. Documento di origine: {BASE}{p['pdf']}. Scaricata il {RET}."), ("Copyright", NOTICE)):
        meta.add_text(k, v)
    im = Image.open(SCR / "tyvak" / f"{p['img']}_img.png").convert("RGB")
    im.thumbnail((1000, 1000))
    im.save(PROJ / "images" / p["file"], optimize=True, pnginfo=meta)
    rows.append([p["id"], "Tyvak", p["name"], p["file"], "estratta dal datasheet PDF", img_url, f"{BASE}{p['pdf']}", RET, f"{im.size[0]}x{im.size[1]}", ""])
    d = {k: v for k, v in p.items() if k not in ("pdf", "img", "page", "file")}
    d.update(vendor="Tyvak", kind="platform",
             source={"url": f"{BASE}{p['pdf']}", "document": f"Scheda tecnica NASA RSDO Rapid IV catalog: Terran Orbital/Tyvak {p['name']} (luglio 2024)",
                     "retrieved": RET, "verified": False, "method": "trascritto dalla scheda tecnica pubblica del fornitore; da controllare manualmente"},
             image={"file": f"images/{p['file']}", "image_url": img_url, "page_url": f"{BASE}{p['pdf']}", "type": "estratta dal datasheet PDF", "retrieved": RET})
    out.append(d)
(PROJ / "data" / "platforms.json").write_text(json.dumps({
    "_comment": "Piattaforme complete (non componenti): riferimento, non usate dal selettore. verified=false. null = non dichiarato.",
    "platforms": out}, indent=1, ensure_ascii=False), encoding="utf-8")
mf = PROJ / "images" / "manifest.csv"
with mf.open("a", newline="", encoding="utf-8-sig") as f:
    csv.writer(f).writerows(rows)
print(len(out), "piattaforme;", mf)

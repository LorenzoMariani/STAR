"""Aggiunge le piattaforme Terran Orbital (oltre alle tre Tyvak) a data/platforms.json, con immagini e fonti."""
import csv, json, sys
from pathlib import Path
from PIL import Image
from PIL.PngImagePlugin import PngInfo

SCR, PROJ = Path(sys.argv[1]), Path(sys.argv[2])
RET = "2026-10-13"
U = "https://terranorbital.com/wp-content/uploads/"
PAGE = "https://terranorbital.com/spacecraft-platforms/"
NOTICE = ("Immagine di proprieta' del produttore, qui solo come riferimento visivo del prodotto; per usi diversi (pubblicazioni, "
          "presentazioni esterne) chiedere il permesso al produttore.")
S_X = {"S-band": "125 kbps uplink, 2 Mbps downlink", "X-band": "650 Mbps downlink"}
P = [
    dict(id="terranorbital-voyager", name="Voyager", key="voyager", pdf="2024/10/0071_TO_VOYAGER_PLATFORM_101024.pdf", png="2023/09/voyager-1100px.png",
         page=PAGE + "voyager", file="TerranOrbital-Voyager.png", configuration="16U", form_factor_u=16, applications="GEO, MEO, cislunare",
         orbit="GEO/MEO/cislunare", native_orbits_km=[30000, None], launch_mass_kg_max=30.0, payload_mass_kg_max=8.0, solar_array_power_w_max=100.0,
         redundancy="dual-string", power_buses="12 V non regolati, 3.3 V, 5 V", comms={"X-band": "deep space, uplink e downlink (velocita' non dichiarata)"},
         propulsion="standard, impulso specifico 200 s", thrust_mn=None, pointing_arcsec=[30, 75], dimensions=None,
         modules=["Flight computer (2)", "Watchdog", "Backplane", "Moduli batteria 12 V (3)", "MPPT 12 V (2)", "Load controller 12 V (2)",
                  "Sensori solari grossolani (2)", "Star tracker (2)", "Magnetorquer (3, se necessari)", "Ruote di reazione (4)", "IMU (2)"],
         notes="Piattaforma 16U per spazio profondo. Massa massima non supportata su tutti i lanciatori/dispenser. Array solare di terzi incluso."),
    dict(id="terranorbital-excelsior", name="Excelsior", key="excelsior", pdf="2024/10/0072_TO_EXCELSIOR_PLATFORM_031824_1150.pdf",
         png="2023/09/Excelsior-update-1-1-1.png", page=PAGE + "excelsior", file="TerranOrbital-Excelsior.png", configuration="half-ESPA",
         form_factor_u=None, applications="LEO", orbit="LEO", native_orbits_km=[400, 1200], launch_mass_kg_max=125.0, payload_mass_kg_max=50.0,
         solar_array_power_w_max=500.0, redundancy="single-string", power_buses="sistema a 66 V; 28 V, 12 V e 9 V disponibili", comms=S_X,
         propulsion="standard, impulso specifico 400 s", thrust_mn=None, pointing_arcsec=[10, 50], dimensions=None,
         modules=["Watchdog", "Backplane", "Flight computer (2)", "Moduli batteria 66 V (2-4)", "MPPT 66 V (1-2)", "Load controller 66 V",
                  "Punti di carico 28 V bassa potenza (variabili)", "Punti di carico 28 V alta potenza (variabili)", "Sensori solari grossolani (2)",
                  "Gruppo giroscopi", "Star tracker (3)", "GPS (2)", "Magnetorquer (3)", "Ruote di reazione (3)", "Radio LDRR (2)", "Radio MDR (2)"],
         notes="Microsatellite d'ingresso, pensato per lanciarne due da una porta ESPA da 15 pollici. Array solare di terzi incluso. Massa massima non "
               "supportata su tutti i lanciatori/dispenser."),
    dict(id="terranorbital-ambassador", name="Ambassador", key="ambassador", pdf="2024/10/0074_TO_AMBASSADOR_PLATFORM_101024.pdf",
         png="2023/09/Ambassador-2-1-1.png", page=PAGE + "ambassador", file="TerranOrbital-Ambassador.png", configuration="ESPA Grande",
         form_factor_u=None, applications="LEO", orbit="LEO", native_orbits_km=[400, 1200], launch_mass_kg_max=500.0, payload_mass_kg_max=200.0,
         solar_array_power_w_max=1500.0, redundancy="dual-string", power_buses="sistema a 66 V; 12 V e 9 V disponibili", comms=S_X,
         propulsion="effetto Hall standard, impulso specifico 1150 s (altre opzioni)", thrust_mn=17.0, pointing_arcsec=[10, 50],
         dimensions="piano payload 104 x 112 cm",
         modules=["Flight computer (2)", "Watchdog", "Backplane", "Moduli batteria 66 V (8-12)", "MPPT 66 V (2-3)", "Load controller 66 V",
                  "Punti di carico 28 V bassa potenza (variabili)", "Punti di carico 28 V alta potenza (variabili)", "Sensori solari grossolani (4)",
                  "Gruppo giroscopi", "Star tracker (3)", "GPS (2)", "Magnetorquer (3)", "Ruote di reazione (4)", "Radio LDRR (2)", "Radio MDR (2)"],
         notes="Piattaforma per rideshare su ESPA Grande. Array solare di terzi incluso."),
    dict(id="terranorbital-enterprise", name="Enterprise", key="enterprise", pdf="2024/03/0065_TO_ENTERPRISE-PLATFORM_031824_1147.pdf",
         png="2023/09/Enterprise-rendering-4-1-1024x692-1.png", page=PAGE + "enterprise", file="TerranOrbital-Enterprise.png",
         configuration="flat packing, tre configurazioni (A, B, C)", form_factor_u=None, applications="LEO (A, B), MEO/GEO (C)", orbit="LEO/MEO/GEO",
         native_orbits_km=[400, 35000], launch_mass_kg_max=1250.0, payload_mass_kg_max=750.0, solar_array_power_w_max=None, payload_power_w_max=3000.0,
         redundancy="dual-string", power_buses="rail a 66, 28, 12 e 9 V", comms={**S_X, "configurazione C": "TT&C in S, X e Ka, velocita' alte e basse"},
         propulsion=None, thrust_mn=None, pointing_arcsec=[10, 50], dimensions=None, modules=None,
         configurations=[
             dict(name="A", orbit="LEO 400-1200 km", launch_mass_kg=500.0, payload_mass_kg=200.0, payload_power_w=2000.0,
                  payload_deck_cm="100 x 200", payload_electronics_cm="40 x 20 x 20"),
             dict(name="B", orbit="LEO 400-1200 km", launch_mass_kg=1000.0, payload_mass_kg=650.0, payload_power_w=3000.0,
                  payload_deck_cm="114.3 x 254", payload_electronics_cm="76.2 x 30.5 x 30.5"),
             dict(name="C", orbit="MEO/GEO 1200-35000 km", launch_mass_kg=1250.0, payload_mass_kg=750.0, payload_power_w=3000.0,
                  payload_deck_cm="114.3 x 254", payload_electronics_cm="76.2 x 30.5 x 30.5")],
         notes="Piattaforma piu' grande della linea. I valori in cima sono i massimi tra le tre configurazioni (la B dichiara 650 kg di payload, la C 750 kg). "
               "La potenza e' quella disponibile al payload, la potenza dell'array non e' dichiarata. Nessun elenco di moduli di base nella scheda."),
    dict(id="terranorbital-smallsat-geo", name="SmallSat GEO", key="smallsatgeo", pdf="2024/09/0041_TO_SMALSAT-GEO_BROCHURE_091724_SPREAD.pdf",
         png="2024/09/smallsat-geo-front-1.png", page="https://terranorbital.com/smallsat-geo/", file="TerranOrbital-SmallSatGEO.png",
         configuration="lancio rideshare, dedicato o multi-manifest su GTO super-sincrona", form_factor_u=None, applications="GEO", orbit="GEO",
         native_orbits_km=None, launch_mass_kg_max=1250.0, payload_mass_kg_max=300.0, solar_array_power_w_max=None, payload_power_w_max=3000.0,
         redundancy=None, power_buses=None, comms={"frequenze supportate": "VHF, UHF, C, X, Ku, K, Ka, Q, V"},
         propulsion="nominale tutta elettrica; opzioni elettrica e chimica", thrust_mn=None, pointing_arcsec=None, dimensions=None, modules=None,
         dry_mass_kg=[500.0, 750.0], lifetime_years=7.0,
         notes="Piattaforma per GEO: massa a secco 500-750 kg secondo la configurazione, vita nominale 7 anni (personalizzabile), elaborazione Versal/ARM/RFSoC/"
               "MPSoC, payload con riflettori multipli o phased array multi-fascio. Opzioni extra su richiesta commerciale."),
]
plats = json.loads((PROJ / "data" / "platforms.json").read_text(encoding="utf-8"))
existing = {p["id"]: p for p in plats["platforms"]}
CONF = {"tyvak-triumph": "6U", "tyvak-renegade": "12U (16U opzionale)", "tyvak-nebula": "ESPA 15 pollici o ESPA Grande 24 pollici"}
for pid, c in CONF.items():
    existing[pid].setdefault("configuration", c)
    existing[pid].setdefault("applications", "LEO")
    existing[pid]["notes"] = existing[pid]["notes"].replace("  ", " ")
    existing[pid].setdefault("brand_note", "Venduta anche con il marchio Terran Orbital (stessa societa').")
plats["platforms"] = [p for p in plats["platforms"] if not p["id"].startswith("terranorbital-")]
rows = []
for p in P:
    pdf_url = U + p["pdf"]
    img_url = U + p["png"]
    meta = PngInfo()
    for k, v in (("Title", f"Terran Orbital {p['name']}"), ("Author", "Terran Orbital Corporation"), ("Source", img_url),
                 ("Description", f"Piattaforma {p['id']}. Pagina di origine: {p['page']}. Scaricata il {RET}."), ("Copyright", NOTICE)):
        meta.add_text(k, v)
    im = Image.open(SCR / "to" / f"{p['key']}_web.png").convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    bg.alpha_composite(im)
    im = bg.convert("RGB")
    im.thumbnail((1000, 1000))
    im.save(PROJ / "images" / p["file"], optimize=True, pnginfo=meta)
    rows.append([p["id"], "Terran Orbital", p["name"], p["file"], "immagine dal sito del produttore", img_url, p["page"], RET,
                 f"{im.size[0]}x{im.size[1]}", ""])
    d = {k: v for k, v in p.items() if k not in ("pdf", "png", "page", "file", "key")}
    d.update(vendor="Terran Orbital", kind="platform",
             source={"url": pdf_url, "document": f"Scheda tecnica Terran Orbital {p['name']} (2024), pagina {p['page']}", "retrieved": RET, "verified": False,
                     "method": "trascritto dalla scheda tecnica pubblica del fornitore, confrontata con la pagina web; da controllare manualmente"},
             image={"file": f"images/{p['file']}", "image_url": img_url, "page_url": p["page"], "type": "immagine dal sito del produttore", "retrieved": RET})
    plats["platforms"].append(d)
(PROJ / "data" / "platforms.json").write_text(json.dumps(plats, indent=1, ensure_ascii=False), encoding="utf-8")
mf = PROJ / "images" / "manifest.csv"
with mf.open("a", newline="", encoding="utf-8-sig") as f:
    csv.writer(f).writerows(rows)
print(len(plats["platforms"]), "piattaforme")

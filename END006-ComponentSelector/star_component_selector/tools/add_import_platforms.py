"""Add the CubeSat-class platforms found in the new datasheet import (C3S 3U-16U, Blue Canyon XB3-XB16, Spacemanic CORVUS) to
data/platforms.json, with the first page of the vendor PDF as image. Reference data only: the component selector does not use platforms.

Values are the ones the vendor PDF declares; what it does not declare is null (launch mass, payload mass, solar array power for most).
Pointing accuracies are converted from degrees to arcsec (1 deg = 3600 arcsec).

usage (star env, pymupdf + PIL): python tools/add_import_platforms.py <folder with the vendor PDFs, e.g. Datasheet_CubeSat_1U-12U/_selezione>
The PDFs are looked up by file name in every sub-folder. Idempotent: entries with the same id are replaced.
"""
import json
import sys
from pathlib import Path

import pymupdf
from PIL import Image
from PIL.PngImagePlugin import PngInfo

PROJ = Path(__file__).resolve().parent.parent
RET = "2026-10-23"
METHOD = "trascritto dalla scheda tecnica pubblica del fornitore; da controllare manualmente"
NOTICE = ("Immagine di proprieta' del produttore, qui solo come riferimento visivo del prodotto; per usi diversi (pubblicazioni, "
          "presentazioni esterne) chiedere il permesso al produttore.")
C3S = "https://c3s.hu/wp-content/uploads/2023/02/"
BCT = "https://www.bluecanyontech.com/wp-content/uploads/"
C3S_COMMS = {"UHF": "399-401 MHz, 30 dBm, uplink 1.25-150 kbps, downlink 5-150 kbps (OOK/FSK/GFSK); higher band on request"}
C3S_COMMON = dict(orbit="LEO", native_orbits_km=None, redundancy="subsystem-level cold redundancy", comms=C3S_COMMS, propulsion=None,
                  pointing_arcsec=[720, 7200], dimensions=None, vendor="C3S Electronics Development", kind="platform",
                  brand_note=None, applications="Earth observation, IoT, IOD, space weather monitoring")
C3S_MODULES = ["On-board computer (ARM Cortex-M7, cold-redundant pair)", "Communication subsystem (UHF)", "Power system with battery pack",
               "Rigid backplane (nano-D / micro-D connectors)", "Structure with card guides"]
BCT_COMMON = dict(orbit="LEO", native_orbits_km=None, redundancy=None, propulsion="electric and chemical systems available",
                  dimensions=None, vendor="Blue Canyon Technologies", kind="platform", brand_note=None, applications="LEO > 5 years; GEO/Lunar/Deep Space > 2 years")
BCT_MODULES = ["Attitude control (star trackers)", "Power system with battery and solar array", "On-board data storage (4 GB)",
               "S-band radio (2 Mbps standard)"]
P = [
    dict(id="c3s-3u", name="3U / 3U PLUS platform", pdf="C3s__3U-3UPLUS-Platform-Datasheet-2.pdf", url=C3S + "C3S_3U_3UPLUS_Platform_Datasheet_2.pdf", file="C3S-3U.png",
         form_factor_u=3, launch_mass_kg_max=None, payload_mass_kg_max=4.7, solar_array_power_w_max=None, power_buses="3.3 V, 5.0 V, 9.9-12.6 V", modules=C3S_MODULES,
         document="C3S platform data sheet v03, 3U/3U PLUS (02/02/2022)",
         notes="Platform mass 3.3 kg, 100 x 100 x 340.5 mm, battery 58 / 65 Wh, average consumption 4.5 W, peak 20 W; payload allowance up to 4.7 kg, 1.25-1.4 U, "
               "146.5 x 94 x 94 mm. Knowledge accuracy 0.2 deg, pointing 2 deg (pointing_arcsec = [knowledge, pointing]). 5-year design lifetime in LEO. "
               "Flight heritage RadCube (2021).", **C3S_COMMON),
    dict(id="c3s-6u", name="6U platform", pdf="C3s__6U-platform-datasheet.pdf", url=C3S + "C3S_6U_platform_datasheet.pdf", file="C3S-6U.png",
         form_factor_u=6, launch_mass_kg_max=None, payload_mass_kg_max=None, solar_array_power_w_max=None, power_buses="3.3 V, 5.0 V, 9.9-12.6 V", modules=C3S_MODULES,
         document="C3S platform data sheet v03, 6U (02/02/2022)",
         notes="Platform mass 5 kg, 226.3 x 100 x 366 mm, battery 115 / 155 / 190 Wh, average consumption 7.9 W, peak 25 W; payload allowance: average up to 40 W, "
               "peak up to 165 W, 4.9-5.3 U, 94 x 216.2 x 244.4 mm. Knowledge accuracy 0.2 deg, pointing 2 deg (pointing_arcsec = [knowledge, pointing]).",
         **C3S_COMMON),
    dict(id="c3s-12u", name="12U platform", pdf="C3s__12U-platform-datasheet-2.pdf", url=C3S + "C3S_12U_platform_datasheet_2.pdf", file="C3S-12U.png",
         form_factor_u=12, launch_mass_kg_max=None, payload_mass_kg_max=None, solar_array_power_w_max=None, power_buses="13.2-16.8 V", modules=C3S_MODULES,
         document="C3S platform data sheet v03, 12U (02/02/2022)",
         notes="226.3 x 226.3 x 366 mm, battery 115 / 155 / 190 Wh, average consumption 7.9 W, peak 25 W; payload allowance: average up to 40 W, peak up to 165 W, "
               "12.3-13.1 U. Knowledge accuracy 0.2 deg, pointing 2 deg (pointing_arcsec = [knowledge, pointing]). Platform mass not declared.", **C3S_COMMON),
    dict(id="c3s-16u", name="16U platform", pdf="C3s__16U-platform-datasheet.pdf", url=C3S + "C3S_16U_platform_datasheet.pdf", file="C3S-16U.png",
         form_factor_u=16, launch_mass_kg_max=None, payload_mass_kg_max=None, solar_array_power_w_max=None, power_buses="13.2-16.8 V", modules=C3S_MODULES,
         document="C3S platform data sheet v04, 16U (25/02/2022)",
         notes="226.3 x 226.3 x 454 mm, battery 115 / 155 / 190 Wh, average consumption 7.9 W, peak 25 W; payload allowance: average up to 50 W, peak up to 155 W, "
               "15.5-16.5 U. Knowledge accuracy 0.2 deg, pointing 2 deg (pointing_arcsec = [knowledge, pointing]). Platform mass not declared "
               "(the PDF shows a '19 kg' figure without a label).", **C3S_COMMON),
    dict(id="bct-xb3", name="XB3 (3U)", pdf="Bluecanyontech__3U-2026.pdf", url=BCT + "3U-2026.pdf", file="BCT-XB3.png", form_factor_u=3,
         launch_mass_kg_max=None, payload_mass_kg_max=None, solar_array_power_w_max=27.0, power_buses="3.3 V, 5.0 V, 12 V (28 V in 6U, 12U and 16U)",
         comms={"S-band": "2 Mbps standard", "X-band": "up to 10 Mbps"}, pointing_arcsec=[10.8, 25.2], modules=BCT_MODULES,
         document="Blue Canyon Technologies CubeSat summary XB3 (REV 1/2026)",
         notes="Payload volume 1.5 U typical, energy storage 6.8 Ah, agility > 10 deg/s, 4 GB data storage, position knowledge 10 m / 0.15 m/s (1-sigma). "
               "Pointing +-0.003 deg (1-sigma) on 2 axes with 1 tracker, +-0.007 deg on the third (pointing_arcsec = [first, third]). Data for information only.",
         **BCT_COMMON),
    dict(id="bct-xb6", name="XB6 (6U)", pdf="Bluecanyontech__6U-2026.pdf", url=BCT + "6U-2026.pdf", file="BCT-XB6.png", form_factor_u=6,
         launch_mass_kg_max=None, payload_mass_kg_max=None, solar_array_power_w_max=108.0, power_buses="3.3 V, 5.0 V, 12 V, 28 V",
         comms={"S-band": "2 Mbps standard", "X-band": "up to 10 Mbps"}, pointing_arcsec=[7.2, 7.2], modules=BCT_MODULES,
         document="Blue Canyon Technologies CubeSat summary XB6 (REV 1/2026)",
         notes="Payload volume 4 U typical, energy storage 6.8-20.4 Ah, solar array 92-108 W, agility > 6 deg/s, 4 GB data storage (expandable), pointing "
               "+-0.002 deg (1-sigma) on 3 axes with 2 trackers. Data for information only.", **BCT_COMMON),
    dict(id="bct-xb12", name="XB12 (12U)", pdf="Bluecanyontech__12U-2026.pdf", url=BCT + "12U-2026.pdf", file="BCT-XB12.png", form_factor_u=12,
         launch_mass_kg_max=None, payload_mass_kg_max=None, solar_array_power_w_max=108.0, power_buses="3.3 V, 5.0 V, 12 V, 28 V",
         comms={"S-band": "2 Mbps standard", "X-band": "up to 10 Mbps"}, pointing_arcsec=[7.2, 7.2], modules=BCT_MODULES,
         document="Blue Canyon Technologies CubeSat summary XB12 (REV 1/2026)",
         notes="Payload volume 8 U typical, energy storage 6.8-20.4 Ah, solar array 92-108 W, agility > 5 deg/s, 4 GB data storage (expandable), pointing "
               "+-0.002 deg (1-sigma) on 3 axes with 2 trackers. Data for information only.", **BCT_COMMON),
    dict(id="bct-xb16", name="XB16 (16U)", pdf="Bluecanyontech__16U-2026.pdf", url=BCT + "16U-2026.pdf", file="BCT-XB16.png", form_factor_u=16,
         launch_mass_kg_max=None, payload_mass_kg_max=None, solar_array_power_w_max=108.0, power_buses="3.3 V, 5.0 V, 12 V, 28 V",
         comms={"S-band": "2 Mbps standard"}, pointing_arcsec=[7.2, 7.2], modules=BCT_MODULES,
         document="Blue Canyon Technologies CubeSat summary XB16 (REV 1/2026)",
         notes="Payload volume 12 U typical, energy storage 6.8-20.4 Ah, solar array 92-108 W, agility > 3 deg/s, 4 GB data storage (expandable), pointing "
               "+-0.002 deg (1-sigma) on 3 axes with 2 trackers. Data for information only.", **BCT_COMMON),
    dict(id="spacemanic-corvus", name="CORVUS platform family (1U-16U)", pdf="Spacemanic__CORVUS-PLATFORM.pdf",
         url="https://newspacemarket.com/wp-content/uploads/kls-datasheets/dafe0509fd24021fd96bba5e4e238378e0e542c3.pdf", file="Spacemanic-CORVUS.png",
         form_factor_u=None, launch_mass_kg_max=None, payload_mass_kg_max=None, solar_array_power_w_max=None,
         power_buses="regulated 3.3 / 5 / 12 V channels (up to 9.8 W @ 5 V, 48 W @ 12 V per channel), unregulated VBat 6.8-8.4 V (1U-3U) or 13.6-16.8 V (6U-16U)",
         orbit="LEO", native_orbits_km=None, redundancy=None, comms={"UHF": "400-402 MHz commercial or 430-440 MHz amateur, 9600/19200 bps", "VHF": "144-146 MHz amateur",
         "S-band": "optional, downlink 250-512 kbps, uplink 9.6-128 kbps"}, propulsion=None, pointing_arcsec=[1800, 3600],
         dimensions=None, modules=["Deep Thought CDHS", "Power supply unit (battery 23 / 46 / 92 Wh)", "UHF/VHF communication", "AOCS option: magnetorquers, reaction wheels, "
         "fine sun sensors, magnetometer, gyroscopes, optional star tracker", "Celeste GNSS receiver"],
         vendor="Spacemanic", kind="platform", brand_note=None, applications="LEO, up to 5 years design lifetime",
         document="Spacemanic CORVUS platform datasheet SM-COR-DS-0118 issue 3.0 (16/12/2025)",
         notes="One datasheet for all classes (columns 1U, 2U|3U, 6U|8U, 12U|16U). Available payload mass without AOCS: 1U up to 1 kg, 2U|3U 2.5 | 4 kg, 6U|8U 7.5 | 11.5 kg; "
               "with AOCS: 0.5 kg, 2 | 3.5 kg, 6.5 | 10.5 kg, 12U|16U 16 | 22 kg. Battery baseline 23 Wh (1U), 46 Wh, 92 Wh. Baseline 6U with star tracker: "
               "knowledge 0.5 deg, pointing 1.0 deg (1-sigma) (pointing_arcsec = [knowledge, pointing]); slew about 1.5 deg/s. GNSS 2.0 m CEP, 0.1 m/s."),
    dict(id="exa-kratos-1u", name="KRATOS 1U spacecraft bus", pdf="EXA__Diapositiva-1.pdf",
         url="https://newspacemarket.com/wp-content/uploads/kls-datasheets/6f36e2aa2a4d8e1e82412d56f3b2df4b785431c5.pdf", file="EXA-KRATOS-1U.png",
         form_factor_u=1, launch_mass_kg_max=None, payload_mass_kg_max=None, solar_array_power_w_max=16.0,
         power_buses="5 V @ 25 W, 3.3 V @ 10 W, 12 V @ 50 W, 1 unregulated rail", orbit="LEO", native_orbits_km=None, redundancy=None,
         comms={"SDR (70 MHz-6 GHz)": "full duplex, 1 transceiver and 2 receive-only ports; monopole/dipole antennas VHF to L-band",
                "Laser (optional)": "10 Mbps downlink"}, propulsion=None, pointing_arcsec=None, dimensions=None,
         modules=["ICEPS all-in-one (OBC, EPS, SDR radio, ADCS)", "OBC Xilinx ARM9 dual core 733 MHz, 512 MB DDR3L, 32-512 GB SSD", "EPS with 4 power rails and 4-channel UMPPT",
                  "Battery 25-100 Wh with passive heater (active optional)", "Deployable solar panels (1-3)", "Magnetorquers (4 + 1 on Z)", "Sun sensors (6) and temperature sensors",
                  "IMU", "Embedded antennas", "Release/deploy actuators"],
         vendor="EXA (Ecuadorian Civil Space Agency)", kind="platform", brand_note=None, applications="LEO, 4 years minimum radiation tolerance",
         document="EXA KRATOS 1U spacecraft bus datasheet (newspacemarket.com copy)",
         notes="Payload power available 20-95 W; the summary says up to 32 W of solar power and 100 W of battery power, the EPS specification says solar array 3.75-16 W "
               "and 100 W maximum delivered power (array tables: 3-16.8 W at BOL). solar_array_power_w_max = 16 W from the EPS specification. Panel mass 460-540 g "
               "depending on 1-3 panels (platform mass not declared). Room for 6 standard payload boards and 3 cameras; operating temperature -80 to +140 C. "
               "Magnetic moment 0.14 A m2 (x4) and 0.19 A m2 (Z). Pointing accuracy not declared."),
]


def find_pdf(root, name):
    hits = list(root.rglob(name))
    if not hits:
        raise SystemExit(f"PDF not found: {name}")
    return hits[0]


def main():
    root = Path(sys.argv[1])
    path = PROJ / "data" / "platforms.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    items = [p for p in data["platforms"] if p["id"] not in {x["id"] for x in P}]
    for p in P:
        pdf = find_pdf(root, p["pdf"])
        pix = pymupdf.open(pdf)[0].get_pixmap(dpi=110)
        im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        meta = PngInfo()
        meta.add_text("Source", p["url"])
        meta.add_text("Notice", NOTICE)
        im.save(PROJ / "images" / p["file"], pnginfo=meta)
        item = {k: v for k, v in p.items() if k not in ("pdf", "url", "file", "document")}
        item["configuration"] = f"{p['form_factor_u']}U" if p["form_factor_u"] else "1U-16U"
        item["source"] = {"url": p["url"], "document": p["document"], "retrieved": RET, "verified": False, "method": METHOD}
        item["image"] = {"file": f"images/{p['file']}", "image_url": p["url"] + "#page=1", "page_url": p["url"], "type": "estratta dal datasheet PDF", "retrieved": RET}
        items.append(item)
    data["platforms"] = items
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(P)} platforms added/updated; total {len(items)}")


if __name__ == "__main__":
    main()

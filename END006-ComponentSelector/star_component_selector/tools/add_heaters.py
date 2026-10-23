"""Adds the catalogue category `heater` (battery film heaters, STAR phase F4 2026-10-23) and the field integrated_heater_w
of the battery packs and EPS boards.

  minco-hk6900 ... minco-hk6911   Minco "Thermal Solutions Design Guide", page 27 "Stock Polyimide Thermofoil Heaters"
                                   (size, type, resistance, typical power at 28 V, effective area) and page 9 "Space and
                                   weight savings" (a polyimide heater weighs 0.04 g/cm2, 0.25 mm over the element)
  gomspace-bpx-100wh-16v / -32v   GomSpace NanoPower BPX 100 Wh datasheet DS 1076870 1.1.0, table 6.1: heater power 6 W
  gomspace-bp8-100wh              GomSpace NanoPower BP8 100 Wh datasheet: "PH Heater power usage 6.0 W"

usage: python tools/add_heaters.py <Minco-Thermal-Solutions-Design-Guide.pdf already downloaded>
Idempotent. Derived values are marked in the notes: the mass is the published areal density x the heated area (lead wires
not included, not published); the power at the bus voltage is V^2 / R (the selector computes it, mission.battery_heater).
Packs whose datasheet declares a heater without publishing its power keep integrated_heater_w = null with a note.
"""
import json
import shutil
import sys
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent
RET = "2026-10-23"
MINCO_URL = "https://www.minco.com/wp-content/uploads/Minco-Thermal-Solutions-Design-Guide.pdf"
MINCO_DOC = "Minco Thermal Solutions Design Guide (stock polyimide Thermofoil heaters, page 27)"
MINCO_FILE = "datasheets/Minco__Minco-Thermal-Solutions-Design-Guide.pdf"
AREAL_G_CM2 = 0.04          # Minco design guide, page 9: "A polyimide (e.g. Kapton) heater typically weighs only 0.009 oz/in2 (0.04 g/cm2)"
# page 27: model, X x Y [mm], type, resistance [ohm], typical power [W] at [V], effective area [cm2]
MINCO_STOCK = [
    ("HK6900", 12.7, 25.4, 21, 210.1, 4, 28, 2.39),
    ("HK6901", 12.7, 50.8, 21, 100.1, 8, 28, 5.03),
    ("HK6905", 12.7, 254.0, 21, 19.3, 41, 28, 26.19),
    ("HK6906", 25.4, 25.4, 21, 94.7, 8, 28, 5.35),
    ("HK6907", 25.4, 50.8, 1, 47.8, 16, 28, 10.59),
    ("HK6911", 50.8, 50.8, 1, 22.1, 36, 28, 22.90),
    ("HK6912", 50.8, 76.2, 1, 14.7, 53, 28, 34.32),
]
INTEGRATED_W = {"gomspace-bpx-100wh-16v": 6.0, "gomspace-bpx-100wh-32v": 6.0, "gomspace-bp8-100wh": 6.0}
DECLARED_NO_POWER = {     # the datasheet declares a battery heater but publishes no power
    "aac-optimus-30": "AAC Optimus datasheet: 'autonomous integrated heater systems'",
    "aac-optimus-40": "AAC Optimus datasheet: 'autonomous integrated heater systems'",
    "aac-optimus-80": "AAC Optimus datasheet: 'autonomous integrated heater systems'",
    "pumpkin-bm1-40wh": "Pumpkin BM 1 datasheet: battery heaters driven by the supervisor MCU",
    "isis-iceps2-type-a": "ISIS ICEPS2 datasheet: 'automatic integrated battery heater and thermostat control'",
    "isis-iceps2-type-b": "ISIS ICEPS2 datasheet: 'automatic integrated battery heater and thermostat control'",
    "isis-iceps2-type-c": "ISIS ICEPS2 datasheet: 'automatic integrated battery heater and thermostat control'",
}


def heater(model, x, y, typ, ohm, watt, volt, area_cm2, ds_bytes):
    mass_g = AREAL_G_CM2 * x * y / 100.0
    return {
        "id": f"minco-{model.lower()}", "category": "heater", "vendor": "Minco", "name": f"{model} stock polyimide Thermofoil heater",
        "family": "Minco polyimide Thermofoil", "mass_kg": round(mass_g / 1000.0, 6), "power_w": None, "volume_u": 0,
        "temp_op_c": [-32, 100],
        "notes": (f"{x:g} x {y:g} mm, type {typ}, {ohm:g} ohm, typical {watt:g} W at {volt:g} V (reference only; power at the bus "
                  f"voltage = V^2/R). Mass derived: {AREAL_G_CM2:g} g/cm2 (design guide p. 9) x {x * y / 100.0:.2f} cm2 = {mass_g:.2f} g, "
                  "lead wires (12 in min.) not included. Temperature range of the acrylic PSA backing (-32..100 C). Outgassing of the "
                  "polyimide Thermofoil construction: 0.36% TML, 0.01% CVCM per NASA-JSC (design guide)."),
        "source": {"url": MINCO_URL, "document": MINCO_DOC, "retrieved": RET, "verified": False,
                   "method": "transcribed from the vendor's public design guide; to be checked manually"},
        "specs": {"heater_type": "polyimide film (Kapton) Thermofoil", "resistance_ohm": ohm, "rated_power_w": watt,
                  "rated_voltage_v": volt, "effective_area_cm2": area_cm2},
        "dimensions": {"mm": [x, y, 0.25], "basis": "declared", "note": "heated area X x Y; 0.25 mm over the element (design guide p. 9)"},
        "shape": {"type": "panel", "axis": None, "basis": "subsystem", "set": RET},      # a flat film, no product image
        "datasheet": {"file": MINCO_FILE, "document": MINCO_DOC, "source_url": MINCO_URL, "retrieved": RET, "bytes": ds_bytes},
    }


def main(pdf: str) -> None:
    dst = PROJ / MINCO_FILE
    if not dst.is_file():
        shutil.copy2(pdf, dst)
    path = PROJ / "data" / "catalog.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    comps = data["components"]
    for c in comps:
        if c["category"] in ("battery", "eps"):
            c["specs"].setdefault("integrated_heater_w", None)
            if c["id"] in INTEGRATED_W:
                c["specs"]["integrated_heater_w"] = INTEGRATED_W[c["id"]]
            if c["id"] in DECLARED_NO_POWER and "heater power not published" not in (c.get("notes") or ""):
                c["notes"] = ((c.get("notes") or "") + f" Integrated battery heater declared ({DECLARED_NO_POWER[c['id']]}), "
                              "heater power not published: integrated_heater_w = null.").strip()
    comps[:] = [c for c in comps if c["category"] != "heater"]
    at = next((i for i, c in enumerate(comps) if c["category"] == "payload"), len(comps))
    comps[at:at] = [heater(*row, dst.stat().st_size) for row in MINCO_STOCK]
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    manifest = PROJ / "datasheets" / "manifest.csv"
    text = manifest.read_text(encoding="utf-8-sig")
    name = Path(MINCO_FILE).name
    if name not in text:
        ids = " ".join(f"minco-{row[0].lower()}" for row in MINCO_STOCK)
        sep = "" if text.endswith("\n") else "\n"
        manifest.write_text(text + sep + f'{name},"{MINCO_DOC}",{MINCO_URL},{RET},{dst.stat().st_size},{ids}\n', encoding="utf-8-sig")
    print(f"{len(MINCO_STOCK)} heaters, integrated_heater_w on {sum(c['category'] in ('battery', 'eps') for c in comps)} packs/EPS")


if __name__ == "__main__":
    main(sys.argv[1])

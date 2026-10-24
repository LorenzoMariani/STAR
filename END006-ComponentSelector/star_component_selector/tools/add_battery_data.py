"""Adds `battery_data` to the battery packs of the catalogue (STAR battery-data branch, 2026-10-24): charge and discharge cell
temperature limits, cell and pack configuration, each value with the datasheet page it was read from. Nothing is estimated:
a value the datasheet does not publish stays null (the STAR runners then keep their documented fallback).

  battery_data = {temp_charge_c, temp_discharge_c, cell: {description, nominal_capacity_ah}, cells_in_series, cells_in_parallel,
                  sources: {<field>: {page, quote}}, note}

usage: python tools/add_battery_data.py        Idempotent. Pages are 1-based PDF pages of the datasheet in `datasheet.file`.
"""
import json
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent

IBEOS_B28 = {"temp_charge_c": [0, 45], "temp_discharge_c": [-25, 55]}
IBEOS_B28_SRC = {"temp_charge_c": {"page": 1, "quote": "Charge Cell Temperature 0 to 45 C"},
                 "temp_discharge_c": {"page": 1, "quote": "Discharge Cell Temperature -25 to 55 C"}}
BPX_SRC = {"temp_discharge_c": {"page": 8, "quote": "TOP Operating temperature, Discharge -20.0 .. 60.0 C"},
           "temp_charge_c": {"page": 8, "quote": "TOP Operating temperature, Charge 0.0 .. 45.0 C"},
           "cells_in_series": {"page": 6, "quote": "standard configurations 4S-2P / 8S-1P"},
           "cell": {"page": 5, "quote": "Utilizes 18650 Lithium-ion cells with nominal capacity of 3500mAh"}}
BPX_CELL = {"description": "18650 Li-ion", "nominal_capacity_ah": 3.5}


def b28(config: str, series: int, parallel: int) -> dict:
    return {**IBEOS_B28, "cells_in_series": series, "cells_in_parallel": parallel,
            "sources": {**IBEOS_B28_SRC, "cells_in_series": {"page": 1, "quote": f"Configuration {config}"}},
            "note": "cell type not published in the datasheet"}


DATA = {
    "ibeos-b14-m45": {"temp_charge_c": [10, 45], "temp_discharge_c": [0, 45],
                      "sources": {"temp_charge_c": {"page": 1, "quote": "Operating Cell Temperature, Charge 10 to 45 C"},
                                  "temp_discharge_c": {"page": 1, "quote": "Operating Cell Temperature, Discharge 0 to 45 C"}},
                      "note": "cell type and series/parallel configuration not published in the datasheet (only the 13.2-16.8 V typical operating voltage)"},
    "ibeos-b28-135": {"temp_charge_c": [0, 45], "temp_discharge_c": [0, 45],
                      "sources": {"temp_charge_c": {"page": 1, "quote": "Recommended Operating Temperature 0 to 45 C"},
                                  "temp_discharge_c": {"page": 1, "quote": "Recommended Operating Temperature 0 to 45 C"}},
                      "note": "the datasheet gives one recommended range for charge and discharge; cell and configuration not published"},
    "ibeos-b28-275": b28("8S2P", 8, 2), "ibeos-b28-550": b28("8S4P", 8, 4),
    "ibeos-b28-825": b28("8S6P", 8, 6), "ibeos-b28-1100": b28("8S8P", 8, 8),
    "ibeos-b50-412": {**b28("12S2P", 12, 2), "cells_in_series": 12},
    "ibeos-b50-825": {**b28("12S4P", 12, 4), "cells_in_series": 12},
    "ibeos-b50-1237": {**b28("12S6P", 12, 6), "cells_in_series": 12},
    "gomspace-bpx-100wh-16v": {"temp_charge_c": [0, 45], "temp_discharge_c": [-20, 60], "cell": BPX_CELL, "cells_in_series": 4,
                               "cells_in_parallel": 2, "sources": BPX_SRC},
    "gomspace-bpx-100wh-32v": {"temp_charge_c": [0, 45], "temp_discharge_c": [-20, 60], "cell": BPX_CELL, "cells_in_series": 8,
                               "cells_in_parallel": 1, "sources": BPX_SRC},
    "gomspace-bp8-100wh": {"temp_charge_c": [-10, 45], "temp_discharge_c": [-20, 60],
                           "cell": {"description": "Li-ion cell (type not named)", "nominal_capacity_ah": 3.5},
                           "cells_in_series": 8, "cells_in_parallel": 1,
                           "sources": {"temp_charge_c": {"page": 9, "quote": "Operating temperature, Charge -10 .. 45 C"},
                                       "temp_discharge_c": {"page": 9, "quote": "Operating temperature, Discharge -20 .. 60 C"},
                                       "cells_in_series": {"page": 5, "quote": "8S1P configuration with nominal capacity of 3500 mAh"},
                                       "cell": {"page": 5, "quote": "8S1P configuration with nominal capacity of 3500 mAh"}}},
    "pumpkin-bm1-40wh": {"cell": {"description": "18650 Li-ion", "nominal_capacity_ah": None}, "cells_in_series": 2, "cells_in_parallel": 2,
                         "sources": {"cell": {"page": 1, "quote": "Two 18650 Li-Ion cells per battery (2S2P)"},
                                     "cells_in_series": {"page": 3, "quote": "two 18650 cells connected in series (2S1P), two batteries in parallel (2S2P)"}},
                         "note": "no charge/discharge temperature limit: the datasheet only says most Li-ion cells are typically 0-45 C (page 4, footnote)"},
}


def main() -> None:
    path = PROJ / "data" / "catalog.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    done = []
    for comp in data["components"]:
        if comp["id"] in DATA:
            comp["battery_data"] = DATA[comp["id"]]
            done.append(comp["id"])
    missing = sorted(set(DATA) - set(done))
    if missing:
        raise SystemExit(f"not in the catalogue: {missing}")
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"battery_data written for {len(done)} batteries")


if __name__ == "__main__":
    main()

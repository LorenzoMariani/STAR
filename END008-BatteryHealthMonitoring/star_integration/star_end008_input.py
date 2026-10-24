"""STAR -> END-008: the input.json of battery_monitoring.exe.

Flow (the official one): power_budget.xlsx (star_end008_power_budget) -> power_budget_to_input.py (build_input + dump,
imported by path from the delivery, never copied or modified) with ``--base`` = the base input built here from what STAR
knows (mission duration, cell and pack, battery temperature, timing, simulation, output).

The user template ``Input/input_battery_health_monitoring.json`` (optional) overrides DEFAULT_TEMPLATE section by section.
Every value that STAR chose or assumed is returned in ``provenance`` as ``(key, value, source)``.
"""
from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import json
import re
import tempfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
VENDOR_DIR = HERE.parent
CONVERTER = "power_budget_to_input.py"
EXE = "battery_monitoring.exe"

# run settings: Test = 1 year with a 120 s step, Full = mission lifetime with a 60 s step
RUN_SETTINGS = {"test": {"duration_years": 1.0, "time_step_s": 120.0}, "full": {"duration_years": None, "time_step_s": 60.0}}
DEFAULT_DURATION_YEARS = 5.0                       # full run when the requirements give no mission lifetime
DEFAULT_TEMPERATURE_C = 20.0

# defaults of the sections that are not in the power budget (cell: 18650 of the END-008 example, 2S pack)
DEFAULT_TEMPLATE: dict[str, Any] = {
    "cell": {"name": "18650 Li-ion", "nominal_capacity_Ah": 2.9, "nominal_voltage_V": 3.6, "max_voltage_V": 4.2,
             "min_voltage_V": 2.5},
    "pack": {"cells_in_series": 2, "SOC_max": 0.95, "SOC_min": 0.2, "SOC_initial": 0.95},
    "power": {"charge_efficiency": 1.0, "discharge_efficiency": 1.0},
    "timing": {"BEACON_UHF": {"period_s": 60}, "ADCS": {"period_s": 60}, "SDR": {"start_sunlight_min": 15.0},
               "CAMERAS": {"start_sunlight_min": 15.0}, "TX_UHF": {"start_eclipse_min": 10.0},
               "RX_S_BAND": {"start_eclipse_min": 10.0}, "TX_S_BAND": {"start_eclipse_min": 10.0},
               "THERMAL": {"start_eclipse_min": 0.0}},
    "timing_per_mode": {},
    "simulation": {"degradation_model": "teacher_LEO", "uncertainty": True, "EOL_threshold_SOH": 0.8, "law_cycle": "orbit",
                   "equivalent_depth": 0.05, "SOC_detail_days": [1]},
    "output": {"file": "battery_monitoring_output", "format": "json", "save_time_series": False},
}


def load_template(path: str | Path | None = None) -> dict[str, Any]:
    """DEFAULT_TEMPLATE with the sections of the user template (if the file exists) on top."""
    tpl = copy.deepcopy(DEFAULT_TEMPLATE)
    if path and Path(path).is_file():
        user = json.loads(Path(path).read_text("utf-8"))
        for key, val in user.items():
            if key.startswith("_"):
                continue
            if isinstance(val, dict) and isinstance(tpl.get(key), dict):
                tpl[key].update({k: v for k, v in val.items() if not str(k).startswith("_")})
            else:
                tpl[key] = val
    return tpl


def battery_temperature_C(thermal_summaries: list[dict[str, Any]] | None) -> tuple[float, str]:
    """Mean battery temperature of the END-019 summaries (nodes.BAT.mean_C, mean over the satellites), else 20 C."""
    vals = []
    for s in thermal_summaries or []:
        try:
            vals.append(float(s["nodes"]["BAT"]["mean_C"]))
        except (KeyError, TypeError, ValueError):
            continue
    if not vals:
        return DEFAULT_TEMPERATURE_C, "default (no END-019 battery temperature)"
    return round(sum(vals) / len(vals), 2), "END-019 mean battery temperature over {} satellite(s)".format(len(vals))


def mission_lifetime_years(requirement_texts: list[str] | None) -> float | None:
    """Mission lifetime in years from requirement texts ("... operational lifetime of 5 years"), else None."""
    words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
    pat = re.compile(r"(?:mission|operational|design)\s+(?:life(?:time)?|duration)[^.;]{0,60}?(\d+(?:[.,]\d+)?|" + "|".join(words)
                     + r")[\s-]*years?", re.I)
    for text in requirement_texts or []:
        m = pat.search(text or "")
        if m:
            g = m.group(1).lower()
            return float(words[g]) if g in words else float(g.replace(",", "."))
    return None


def build_base(template: dict[str, Any], *, run_mode: str = "test", mission_name: str = "STAR mission",
               battery_wh: float, lifetime_years: float | None = None,
               temperature_C: float | None = None,
               datasheet: dict[str, Any] | None = None) -> tuple[dict[str, Any], list[tuple[str, Any, str]]]:
    """The --base input for the official converter and the provenance of every value STAR chose.
    datasheet = battery_data of the END-006 battery (cell and pack read from its datasheet): the values it publishes replace
    the template ones and are recorded with their source; a value it does not publish keeps the template (and its fallback)."""
    run_mode = "full" if str(run_mode).lower() == "full" else "test"
    st = RUN_SETTINGS[run_mode]
    prov: list[tuple[str, Any, str]] = []
    if run_mode == "test":
        years, why = st["duration_years"], "test run: 1 year"
    elif lifetime_years:
        years, why = float(lifetime_years), "mission lifetime of the requirements"
    else:
        years, why = DEFAULT_DURATION_YEARS, "full run, no mission lifetime in the requirements: default"
    prov.append(("mission.duration_years", years, why))
    cell = dict(template["cell"])
    pack = dict(template["pack"])
    ds = datasheet or {}
    ds_cell = ds.get("cell") or {}
    if ds_cell.get("description"):
        cell["name"] = ds_cell["description"]
    if ds_cell.get("nominal_capacity_ah"):
        cell["nominal_capacity_Ah"] = float(ds_cell["nominal_capacity_ah"])
    if ds.get("cells_in_series"):
        pack["cells_in_series"] = int(ds["cells_in_series"])
    series = int(pack.get("cells_in_series") or 1)
    if ds.get("cells_in_parallel"):
        pack["cells_in_parallel"] = int(ds["cells_in_parallel"])
    else:
        cell_wh = series * float(cell["nominal_voltage_V"]) * float(cell["nominal_capacity_Ah"])
        pack["cells_in_parallel"] = max(1, int(round(float(battery_wh) / cell_wh)))
    src = ds.get("sources") or {}
    prov.append(("cell", cell.get("name"), ("datasheet" if ds_cell.get("description") else "assumption") + (
        " page {}".format(src["cell"]["page"]) if ds_cell.get("description") and src.get("cell") else
        ": END-006 gives only the battery energy ({:.4g} Wh), cell from the template".format(float(battery_wh)))))
    if ds.get("cells_in_parallel"):
        prov.append(("pack.cells_in_parallel", pack["cells_in_parallel"], "datasheet page {}".format((src.get("cells_in_series") or {}).get("page"))))
    else:
        prov.append(("pack.cells_in_parallel", pack["cells_in_parallel"],
                     "round({:.4g} Wh / ({} S x {} V x {} Ah))".format(float(battery_wh), series, cell["nominal_voltage_V"],
                                                                        cell["nominal_capacity_Ah"])))
    if temperature_C is None:
        temperature_C = DEFAULT_TEMPERATURE_C
        prov.append(("pack.temperature_C", temperature_C, "default"))
    else:
        prov.append(("pack.temperature_C", temperature_C, "END-019 battery temperature"))
    pack["temperature_C"] = float(temperature_C)
    sim = dict(template["simulation"])
    sim["time_step_s"] = st["time_step_s"]
    prov.append(("simulation.time_step_s", st["time_step_s"], "{} run".format(run_mode)))
    base = {"mission": {"name": mission_name, "duration_years": years}, "cell": cell, "pack": pack,
            "power": dict(template["power"]), "timing": copy.deepcopy(template["timing"]),
            "timing_per_mode": copy.deepcopy(template["timing_per_mode"]), "simulation": sim,
            "output": dict(template["output"])}
    return base, prov


def load_converter(vendor_dir: str | Path = VENDOR_DIR):
    """power_budget_to_input.py of the delivery, imported by path (its module object is not cached)."""
    path = Path(vendor_dir) / CONVERTER
    if not path.is_file():
        raise FileNotFoundError("END-008 converter not found: {}".format(path))
    spec = importlib.util.spec_from_file_location("end008_power_budget_to_input", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_input(xlsx: str | Path, base: dict[str, Any], vendor_dir: str | Path = VENDOR_DIR) -> tuple[dict[str, Any], str, list[str]]:
    """Official converter on the xlsx with the base; returns (input dict, input.json text, converter notes)."""
    conv = load_converter(vendor_dir)
    with tempfile.TemporaryDirectory() as tmp:
        base_path = Path(tmp) / "base_input.json"
        base_path.write_text(json.dumps(base, indent=2), "utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cfg = conv.build_input(str(xlsx), str(base_path))
        text = conv.dump(cfg)
    notes = [ln.strip() for ln in buf.getvalue().splitlines() if ln.strip()]
    return cfg, text, notes


def write_input(xlsx: str | Path, base: dict[str, Any], out_path: str | Path,
                vendor_dir: str | Path = VENDOR_DIR) -> tuple[dict[str, Any], list[str]]:
    cfg, text, notes = build_input(xlsx, base, vendor_dir)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(text, "utf-8")
    return cfg, notes


def exe_path(vendor_dir: str | Path = VENDOR_DIR) -> Path | None:
    p = Path(vendor_dir) / EXE
    return p if p.is_file() else None

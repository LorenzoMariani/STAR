from __future__ import annotations

import json
import math
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from runners.star_runner_io import (
    coerce_float,
    ensure_module_output_layout,
    find_upstream_artifact,
    input_value,
    load_json,
    load_selected_passes,
    load_spacecraft_definition,
    make_runtime_input_copy,
    normalize_direct_module_outputs,
    write_json,
)

STAR_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_END004_DIR = STAR_ROOT / "END004-PowerBudget"
LogCallback = Callable[[str, str], Any]
MU_EARTH = 3.986004415e14          # m^3/s^2, as END-001
R_EARTH = 6378137.0                # m, reference of the END-001 altitudes
MODE_KEYS = ("idle", "tx_uhf", "tx_sband", "payload")


def _orbit_from_upstream(star_payload: dict[str, Any], end003_csv: Path | None, end003_runtime_json: Path | None) -> dict[str, Any] | None:
    """Period, sunlight and eclipse of the orbit of this run (2026-10-17): the period from the semi-major axis of the
    satellite END-003 selected (END-001 elements, R = 6378.137 km), the eclipse from the shadow fraction END-003 computed
    on its 48 h window (KPI-14). None when the upstream products are missing (the template values are used then)."""
    orbit = None
    selected = load_selected_passes(star_payload, end003_csv)
    if selected:
        orbit = (selected.get("imaging_pass") or {}).get("orbit") or None
    if not orbit and end003_runtime_json and Path(end003_runtime_json).exists():
        orbit = (load_json(Path(end003_runtime_json)) or {}).get("orbit")
    try:
        alt = 0.5 * (float(orbit["alt_perigee_m"]) + float(orbit["alt_apogee_m"]))
    except (TypeError, KeyError, ValueError):
        return None
    a = R_EARTH + alt
    period_min = 2.0 * math.pi * math.sqrt(a ** 3 / MU_EARTH) / 60.0
    out: dict[str, Any] = {"period_min": round(period_min, 4), "daily_orbits": round(1440.0 / period_min, 3),
                           "source": f"END-001 orbit of the satellite selected by END-003 (altitude {alt / 1000:.1f} km)"}
    summary = find_upstream_artifact(star_payload, ["attitude_summary.json"], [".json"])
    if summary and Path(summary).exists():
        for kpi in (load_json(Path(summary)) or {}).get("kpis", []):
            if kpi.get("id") == "KPI-14" and isinstance(kpi.get("value"), (int, float)):
                eclipse = period_min * float(kpi["value"]) / 100.0
                out.update({"eclipse_min": round(eclipse, 4), "sunlight_min": round(period_min - eclipse, 4)})
                out["source"] += f"; eclipse {float(kpi['value']):.1f}% of the orbit (END-003 KPI-14)"
                break
    return out


# Template loads (Input/input_power_budget.json) of the subsystems END-006 selects; the entry of the transmitter takes
# the peak power END-006 declares, the other ones keep the template power and duty cycles.
ROLE_TEMPLATE = {"obc": ["OBDH"], "eps": ["EPS"], "comms_uhf": ["RX UHF", "TX UHF", "BEACON UHF"],
                 "comms_s": ["RX S BAND", "TX S BAND"], "adcs": ["ADCS"], "payload_imager": ["CAMERAS"]}
ROLE_POWER_ENTRY = {"comms_uhf": "TX UHF", "comms_s": "TX S BAND"}
ALWAYS_ON = ("gps", "gnss_antenna", "star_tracker", "reaction_wheel", "magnetorquer", "obc", "eps")
NO_LOAD = ("structure", "solar_panel", "battery", "antenna_s", "antenna_uhf", "antenna_x")
FACE_KEYS = {"+X": "x_plus", "-X": "x_minus", "+Y": "y_plus", "-Y": "y_minus", "+Z": "z_plus", "-Z": "z_minus"}


def _subsystems_from_satellite(template: list[dict[str, Any]], sat: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    """Power loads of the END-006 satellite: template entries of the subsystems it has (with the declared powers), the heaters,
    and its other subsystems with a declared power; template entries of subsystems it does not have are dropped."""
    by_name = {str(s.get("name")): s for s in template}
    comps = sat.get("components") or {}
    powers = sat.get("consumers_declared_peak_w") or {}
    modes = list(((template[0] if template else {}).get("duty") or {}).keys()) or list(MODE_KEYS)
    out: list[dict[str, Any]] = []
    notes: list[str] = []
    for role, names in ROLE_TEMPLATE.items():
        if role not in comps:
            continue
        target = ROLE_POWER_ENTRY.get(role, names[0])
        for name in names:
            if name not in by_name:
                continue
            entry = json.loads(json.dumps(by_name[name]))
            if name == target and powers.get(role) is not None:
                entry["powerW"] = float(powers[role])
                entry["source"] = f"END-006 {comps[role]} (declared peak power)"
            elif name == target:
                entry["source"] = f"template (power of {comps[role]} not published)"
                notes.append(f"{name}: power of {comps[role]} not published, template {entry.get('powerW')} W kept")
            else:
                entry["source"] = "template"
            out.append(entry)
    if "THERMAL" in by_name:
        out.append({**json.loads(json.dumps(by_name["THERMAL"])), "source": "template (heaters, not a subsystem END-006 selects)"})
    camera_duty = (by_name.get("CAMERAS") or {}).get("duty")
    tx_duty = (by_name.get("TX S BAND") or {}).get("duty")
    for role, comp in comps.items():
        if role in ROLE_TEMPLATE or role in NO_LOAD:
            continue
        power = powers.get(role)
        if power is None:
            notes.append(f"{role}: power of {comp} not published, not in the budget")
            continue
        if role in ALWAYS_ON:
            duty = {m: {"sun": 1, "eclipse": 1} for m in modes}
        elif role == "propulsion":
            duty = {m: {"sun": 0, "eclipse": 0} for m in modes}
        elif role.startswith("payload") and camera_duty:
            duty = json.loads(json.dumps(camera_duty))
        elif role.startswith("comms") and tx_duty:
            duty = json.loads(json.dumps(tx_duty))
        else:
            duty = {m: {"sun": 1, "eclipse": 1} for m in modes}
        out.append({"name": role.upper().replace("_", " "), "powerW": float(power), "duty": duty,
                    "source": f"END-006 {comp} (declared peak power)" + ("; fires only for manoeuvres" if role == "propulsion" else "")})
    return out, notes


def _operations(star_payload: dict[str, Any]) -> dict[str, Any] | None:
    """Daily operations END-001 computed on the ephemerides (operations_summary.json): acquisitions over the AOI and
    ground-station contacts, constellation mean."""
    path = find_upstream_artifact(star_payload, ["operations_summary.json"], [".json"])
    if path and Path(path).exists():
        data = load_json(Path(path)) or {}
        if isinstance(data.get("constellation_mean"), dict):
            return data
    return None


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _apply_duty_cycles(runtime_data: dict[str, Any], ops: dict[str, Any] | None, sat: dict[str, Any], report: dict[str, Any]) -> None:
    """Duty cycles and daily mode allocation from the operations of the run (2026-10-17): payload on while the AOI is in the
    footprint (END-001), transmitters on during the ground-station contacts (sunlit and eclipse parts), receivers, computers,
    ADCS and GNSS always on; beacon and heaters keep the template duty. Orbits per day: payload = orbits with acquisitions,
    contact mode = orbits with a contact and no acquisition, idle = the rest."""
    subs = runtime_data.get("subsystems") or []
    orbit = runtime_data.get("orbit") or {}
    if not ops or not subs or not orbit.get("sunlight_min") or not orbit.get("eclipse_min"):
        report["duty_cycles"] = {"source": "template (END-001 operations_summary.json not available)"}
        return
    m = ops["constellation_mean"]
    sun_min, ecl_min, daily = float(orbit["sunlight_min"]), float(orbit["eclipse_min"]), float(orbit.get("daily_orbits") or 0)
    img_orb = float(m.get("imaging_orbits_per_day") or 0.0)
    img_s = float(m.get("imaging_s_per_imaging_orbit") or 0.0) if img_orb > 0 else 0.0
    con_orb = float(m.get("contact_orbits_per_day") or 0.0)
    c_sun = float(m.get("contact_s_sunlit_per_contact_orbit") or 0.0)
    c_ecl = float(m.get("contact_s_eclipse_per_contact_orbit") or 0.0)
    both = min(float(m.get("orbits_with_imaging_and_contact_per_day") or 0.0), img_orb, con_orb)
    radios = sat.get("radios") or {}
    contact_mode = "tx_sband" if "comms_s" in (sat.get("components") or {}) else "tx_uhf"
    cam = {"sun": round(_clamp01(img_s / 60.0 / sun_min), 5), "eclipse": 0.0}
    tx = {"sun": round(_clamp01(c_sun / 60.0 / sun_min), 5), "eclipse": round(_clamp01(c_ecl / 60.0 / ecl_min), 5)}
    share = both / img_orb if img_orb > 0 else 0.0               # payload orbits that also have a contact
    tx_in_payload = {"sun": round(tx["sun"] * share, 5), "eclipse": round(tx["eclipse"] * share, 5)}
    off = {"sun": 0.0, "eclipse": 0.0}
    on = {"sun": 1.0, "eclipse": 1.0}
    modes = list(MODE_KEYS)

    def duty(payload: dict[str, float], contact: dict[str, float], other: dict[str, float]) -> dict[str, dict[str, float]]:
        return {k: dict(payload if k == "payload" else contact if k == contact_mode else other) for k in modes}

    out, rules = [], {}
    for s in subs:
        name = str(s.get("name"))
        rule = None
        if name in ("OBDH", "EPS", "ADCS", "GPS", "GNSS ANTENNA", "RX UHF"):
            s["duty"] = duty(on, on, on); rule = "always on"
        elif name == "RX S BAND":
            if (radios.get("comms_s") or {}).get("has_receiver") is False:
                rules[name] = f"dropped: {radios['comms_s'].get('component')} is a transmitter only"
                continue
            s["duty"] = duty(on, on, on); rule = "always on (receiver)"
        elif name in ("TX S BAND", "TX UHF") or name.startswith("COMMS"):
            s["duty"] = duty(tx_in_payload, tx, off); rule = "on during the ground-station contacts"
        elif name == "CAMERAS" or name.startswith("PAYLOAD"):
            s["duty"] = duty(cam, off, off); rule = "on while the AOI is in the footprint (payload orbits)"
        elif name == "PROPULSION":
            s["duty"] = duty(off, off, off); rule = "off (fires only for manoeuvres)"
        else:
            rule = "template duty (" + ("periodic beacon" if "BEACON" in name else "heaters" if name == "THERMAL" else "not modelled") + ")"
        # published idle / transmit powers of the selected radios replace the template powers
        for slot, entry in (("comms_s", "RX S BAND"), ("comms_uhf", "RX UHF")):
            if name == entry and (radios.get(slot) or {}).get("power_w_idle") is not None:
                s["powerW"] = float(radios[slot]["power_w_idle"]); s["source"] = f"END-006 {radios[slot]['component']} (published receive/idle power)"
        for slot, entry in (("comms_s", "TX S BAND"), ("comms_uhf", "TX UHF")):
            if name == entry and (radios.get(slot) or {}).get("power_w_tx") is not None:
                s["powerW"] = float(radios[slot]["power_w_tx"]); s["source"] = f"END-006 {radios[slot]['component']} (published transmit power)"
        rules[name] = rule
        out.append(s)
    runtime_data["subsystems"] = out
    ops_alloc = {"payload": round(img_orb, 3), contact_mode: round(max(0.0, con_orb - both), 3)}
    alloc = runtime_data.setdefault("operations", {}).setdefault("mode_orbits_per_day", {})
    for k in modes:
        alloc[k] = ops_alloc.get(k, 0.0)
    alloc["idle"] = round(max(0.0, daily - sum(v for k, v in alloc.items() if k != "idle")), 3)
    report["duty_cycles"] = {
        "source": "END-001 operations_summary.json (constellation mean over the ephemeris window)",
        "rules": rules,
        "payload_duty_sun": cam["sun"], "contact_duty": tx, "payload_orbits_with_contact_fraction": round(share, 3),
        "mode_orbits_per_day": dict(alloc),
        "inputs": {"imaging_orbits_per_day": img_orb, "imaging_s_per_imaging_orbit": img_s, "contact_orbits_per_day": con_orb,
                   "contact_s_sunlit_per_contact_orbit": c_sun, "contact_s_eclipse_per_contact_orbit": c_ecl,
                   "orbits_with_imaging_and_contact_per_day": both},
        "note": "upper bound: payload on whenever the AOI is in the footprint, transmitters on for the whole contact (no data-volume model)"}


def _illumination(star_payload: dict[str, Any]) -> dict[str, float] | None:
    summary = find_upstream_artifact(star_payload, ["attitude_summary.json"], [".json"])
    if summary and Path(summary).exists():
        ill = (load_json(Path(summary)) or {}).get("illumination") or {}
        return ill.get("mean_cos_sunlit") or None
    return None


def _apply_satellite(runtime_data: dict[str, Any], star_payload: dict[str, Any], sat: dict[str, Any] | None, report: dict[str, Any]) -> None:
    """Loads, battery and solar generation of the END-006 satellite (the inputs approved in STAR win, see _apply_star_inputs)."""
    if not sat:
        report["satellite"] = {"source": "template (no END-006 in the workflow)"}
        return
    subs, notes = _subsystems_from_satellite(list(runtime_data.get("subsystems") or []), sat)
    if subs:
        runtime_data["subsystems"] = subs
    report["subsystems"] = {"value": [{k: s.get(k) for k in ("name", "powerW", "source")} for s in subs], "notes": notes,
                            "source": f"END-006 initial design ({sat.get('form_factor')})"}
    if sat.get("battery_wh"):
        runtime_data.setdefault("battery", {})["capacity_Wh"] = float(sat["battery_wh"])
        report["battery_capacity_Wh"] = {"value": float(sat["battery_wh"]), "source": "END-006 initial design (battery / EPS integrated battery)"}
    _apply_duty_cycles(runtime_data, _operations(star_payload), sat, report)
    panels = sat.get("solar_panels") or {}
    illum = _illumination(star_payload)
    orbit = runtime_data.get("orbit") or {}
    if panels.get("peak_power_w_per_panel") and panels.get("body_faces") and illum and orbit.get("sunlight_min"):
        factor = sum(float(illum.get(FACE_KEYS[f], 0.0)) for f in panels["body_faces"] if f in FACE_KEYS)
        p_sun = float(panels["peak_power_w_per_panel"]) * factor
        energy = p_sun * float(orbit["sunlight_min"]) / 60.0
        runtime_data.setdefault("generation", {})["power_generated_per_orbit_Wh"] = round(energy, 4)
        runtime_data["generation"]["solar_power_W"] = None
        report["power_generated_per_orbit_Wh"] = {
            "value": round(energy, 4),
            "source": (f"END-006 panels {panels.get('component')} ({panels.get('peak_power_w_per_panel')} W peak on {', '.join(panels['body_faces'])}) "
                       f"x illumination of those faces in the END-003 attitude (sum of mean cosines {factor:.3f}) x sunlight "
                       f"{float(orbit['sunlight_min']):.1f} min; beginning of life, no temperature or wiring losses")}
    else:
        report["power_generated_per_orbit_Wh"] = {"value": (runtime_data.get("generation") or {}).get("power_generated_per_orbit_Wh"),
                                                  "source": "template (panel data or END-003 illumination not available)"}


def _user_input(star_payload: dict[str, Any], name: str) -> Any:
    """Value of an END-004 input the user gave or edited in STAR; registry first guesses (not reviewed) give None, so that
    they do not override the satellite of the run."""
    for item in star_payload.get("resolved_inputs") or []:
        if isinstance(item, dict) and item.get("parameter") == name:
            if item.get("source") in ("module_registry_default", "module_registry_required_input") and not item.get("reviewed_by_user"):
                return None
            return input_value({"resolved_inputs": [item]}, name, None)
    return None


def _apply_star_inputs(runtime_data: dict[str, Any], star_payload: dict[str, Any], orbit: dict[str, Any] | None) -> dict[str, Any]:
    """Orbit of the run and the END-004 inputs approved in STAR over the native template; returns the decisions."""
    report: dict[str, Any] = {}
    tmpl_orbit = dict(runtime_data.get("orbit") or {})
    if orbit:
        runtime_data["orbit"] = {**tmpl_orbit, **{k: v for k, v in orbit.items() if k != "source"}}
        if "eclipse_min" not in orbit:          # no END-003 shadow fraction: keep the template eclipse, sunlight from the period
            runtime_data["orbit"]["sunlight_min"] = round(orbit["period_min"] - float(tmpl_orbit.get("eclipse_min", 35.0)), 4)
        report["orbit"] = {"value": runtime_data["orbit"], "source": orbit["source"]}
    else:
        report["orbit"] = {"value": tmpl_orbit, "source": "template (END-003/END-001 products not found)"}
    _apply_satellite(runtime_data, star_payload, load_spacecraft_definition(star_payload), report)
    battery = coerce_float(_user_input(star_payload, "battery_capacity_Wh"), 0.0)
    if battery > 0:
        runtime_data.setdefault("battery", {})["capacity_Wh"] = battery
        report["battery_capacity_Wh"] = {"value": battery, "source": "STAR input"}
    generated = coerce_float(_user_input(star_payload, "power_generated_per_orbit_Wh"), 0.0)
    if generated > 0:
        runtime_data.setdefault("generation", {})["power_generated_per_orbit_Wh"] = generated
        report["power_generated_per_orbit_Wh"] = {"value": generated, "source": "STAR input"}
    ops = runtime_data.setdefault("operations", {}).setdefault("mode_orbits_per_day", {})
    allocation = _user_input(star_payload, "daily_mode_allocation")
    if isinstance(allocation, dict):
        for key in MODE_KEYS:
            if key in allocation:
                ops[key] = coerce_float(allocation[key], float(ops.get(key, 0.0)))
        report["daily_mode_allocation"] = {"value": dict(ops), "source": "STAR input"}
    # the modes fill the orbits of a day: idle takes what the other modes leave
    daily = float(runtime_data.get("orbit", {}).get("daily_orbits") or sum(float(ops.get(k, 0.0)) for k in MODE_KEYS))
    busy = sum(float(ops.get(k, 0.0)) for k in MODE_KEYS if k != "idle")
    ops["idle"] = round(max(0.0, daily - busy), 3)
    report["mode_orbits_per_day"] = {"value": dict(ops), "source": f"idle = {daily:g} orbits/day - the other modes"}
    return report


def _emit(cb: LogCallback | None, level: str, msg: str) -> None:
    if callable(cb):
        try:
            cb(level, msg)
        except Exception:
            pass


def _quote(path: Path | str) -> str:
    return str(path).replace("\\", "/").replace("'", "''")


def _duration(seconds: float) -> str:
    if seconds < 1:
        return f"{seconds*1000:.0f} ms"
    if seconds < 60:
        return f"{seconds:.2f} s"
    minutes, remaining = divmod(seconds, 60)
    if minutes < 60:
        return f"{int(minutes)} min {remaining:.1f} s"
    hours, minutes = divmod(minutes, 60)
    return f"{int(hours)} h {int(minutes)} min {remaining:.1f} s"


def _collect(path: Path) -> list[str]:
    return [str(p) for p in sorted(path.rglob("*")) if p.is_file()] if path.exists() else []


def _find_dir(star_root: str | None = None) -> Path:
    env = os.environ.get("STAR_END004_DIR", "").strip()
    if env and Path(env).exists():
        return Path(env)
    root = Path(star_root) if star_root else STAR_ROOT
    candidates = [
        root / "END004-PowerBudget",
        root / "END004_PowerBudget",
        root / "END004-Power Budget",
        root / "END004",
        DEFAULT_END004_DIR,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"END-004 Power Budget folder not found. Expected {root / 'END004-PowerBudget'}")


def _find_script(folder: Path) -> Path:
    env = os.environ.get("STAR_END004_SCRIPT", "").strip()
    if env and Path(env).exists():
        return Path(env)
    for name in ["star_power_budget.m", "STAR_END004_POWER_BUDGET.m"]:
        candidate = folder / name
        if candidate.exists():
            return candidate
    hits = sorted(folder.rglob("*power*budget*.m"))
    if hits:
        return hits[0]
    raise FileNotFoundError(f"END-004 Power Budget MATLAB script not found in {folder}")


def _find_native_template(folder: Path, star_root: str | None = None) -> Path:
    env = os.environ.get("STAR_END004_TEMPLATE", "").strip()
    if env and Path(env).exists():
        return Path(env)
    root = Path(star_root) if star_root else STAR_ROOT
    candidates = [
        root / "Input" / "input_power_budget.json",
        folder / "Input" / "input_power_budget.json",
        folder / "input_power_budget.json",
        Path(__file__).resolve().parent / "templates" / "input_power_budget.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("input_power_budget.json template not found. Place it in STAR/Input, END004-PowerBudget/Input, or runners/templates.")


def _find_end003_runtime_json(star_payload: dict[str, Any]) -> Path | None:
    for key in ("upstream_artifacts_absolute", "upstream_artifacts"):
        items = star_payload.get(key, []) or []
        if isinstance(items, str):
            items = [items]
        for item in items:
            path = Path(str(item))
            text = str(path).lower().replace("\\", "/")
            if "end-003" in text and path.name.lower() == "end003_runtime_input.json":
                if path.exists():
                    return path
                return path
    return None


def _prepare_runtime_script(source: Path, runtime: Path, config: Path, output_folder: Path, module_folder: Path) -> None:
    """Create a runtime MATLAB script with explicit module-path binding.

    MATLAB's run('absolute/path/script.m') temporarily executes the script from
    the script folder. Since the runtime copy is stored inside the run output
    folder, relying on cd(module_folder) is not sufficient. The installed
    END004-PowerBudget folder must be added explicitly to the MATLAB path.
    """
    module_folder = module_folder.resolve()
    entry_file = module_folder / "STAR_END004_POWER_BUDGET.m"
    source_file = source.resolve()

    robust_call = r"""
entryFile = fullfile(module_folder, 'STAR_END004_POWER_BUDGET.m');
if ~isfile(entryFile)
    fprintf('[STAR END-004] MATLAB folder listing for diagnostics:\n');
    try
        disp(dir(module_folder));
    catch
    end
    error('STAR_END004_POWER_BUDGET:EntryFileNotFound', 'The MATLAB entry point file was not found: %s', entryFile);
end
entryPoint = which('STAR_END004_POWER_BUDGET');
if isempty(entryPoint)
    addpath(module_folder);
    addpath(genpath(module_folder));
    rehash;
    entryPoint = which('STAR_END004_POWER_BUDGET');
end
if isempty(entryPoint)
    error('STAR_END004_POWER_BUDGET:EntryPointNotFound', 'The MATLAB entry point STAR_END004_POWER_BUDGET.m exists but is not visible on the MATLAB path: %s', entryFile);
end
fprintf('[STAR END-004] MATLAB entry point: %s\n', entryPoint);
try
    status = STAR_END004_POWER_BUDGET(file_input, path_output);
catch ME
    isSignatureMismatch = contains(ME.message, 'Incorrect number or types of inputs or outputs') || contains(ME.message, 'Too many output arguments');
    if isSignatureMismatch
        fprintf('[STAR END-004] Entry point does not return a status argument. Re-running without output capture.\n');
        STAR_END004_POWER_BUDGET(file_input, path_output);
        status = 'completed';
    else
        rethrow(ME);
    end
end
if isstring(status) || ischar(status)
    fprintf('[STAR END-004] Completed with status: %s\n', char(status));
else
    fprintf('[STAR END-004] Completed with numeric status: %g\n', status);
end
""".lstrip()

    text = (
        "% star_power_budget_runtime.m\n"
        "% Runtime wrapper generated by runners.end004_runner.\n"
        "clear; clc; close all;\n"
        "set(0, 'DefaultFigureVisible', 'off');\n"
        f"module_folder = '{_quote(module_folder)}';\n"
        f"source_script = '{_quote(source_file)}';\n"
        f"expected_entry_file = '{_quote(entry_file)}';\n"
        "addpath(module_folder);\n"
        "addpath(genpath(module_folder));\n"
        "rehash;\n"
        f"file_input = '{_quote(config)}';\n"
        f"path_output = '{_quote(output_folder)}';\n"
        "star_input_override = getenv('STAR_END004_INPUT_FILE');\n"
        "star_output_override = getenv('STAR_END004_OUTPUT_DIR');\n"
        "if isempty(star_output_override)\n"
        "    star_output_override = getenv('STAR_MODULE_OUTPUT_DIR');\n"
        "end\n"
        "if ~isempty(star_input_override)\n"
        "    file_input = string(star_input_override);\n"
        "end\n"
        "if ~isempty(star_output_override)\n"
        "    path_output = string(star_output_override);\n"
        "end\n"
        "fprintf('[STAR END-004] Input JSON: %s\\n', file_input);\n"
        "fprintf('[STAR END-004] Output folder: %s\\n', path_output);\n"
        "fprintf('[STAR END-004] Installed module folder: %s\\n', module_folder);\n"
        "fprintf('[STAR END-004] Expected entry file: %s\\n', expected_entry_file);\n"
        + robust_call
    )
    runtime.parent.mkdir(parents=True, exist_ok=True)
    runtime.write_text(text, encoding="utf-8")

def _terminate(proc: subprocess.Popen, cb: LogCallback | None) -> None:
    if proc.poll() is not None:
        return
    _emit(cb, "EXECUTION", f"Stop requested. Terminating END-004 MATLAB process tree. PID={proc.pid}")
    if sys.platform.startswith("win"):
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    try:
        proc.terminate()
        proc.wait(timeout=8)
    except Exception:
        try:
            proc.kill()
            proc.wait(timeout=8)
        except Exception:
            pass


def _reader(proc: subprocess.Popen, q: queue.Queue[str | None]) -> None:
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            q.put(line)
    except Exception as exc:
        q.put(f"[stdout-reader-error] {exc}\n")
    finally:
        q.put(None)


def _run_process(proc: subprocess.Popen, stdout_path: Path, cb: LogCallback | None, stop_event: threading.Event | None) -> tuple[str, int | None]:
    q: queue.Queue[str | None] = queue.Queue()
    threading.Thread(target=_reader, args=(proc, q), daemon=True).start()
    status, rc, stdout_done = "running", None, False
    with stdout_path.open("w", encoding="utf-8", errors="replace") as f:
        while True:
            if stop_event is not None and stop_event.is_set():
                status = "stopped"
                _terminate(proc, cb)
                rc = proc.poll()
                break
            try:
                item = q.get(timeout=0.2)
            except queue.Empty:
                item = "__NO_LINE__"
            if item is None:
                stdout_done = True
            elif item != "__NO_LINE__":
                f.write(item)
                f.flush()
                if item.rstrip():
                    _emit(cb, "END-004", item.rstrip())
            rc = proc.poll()
            if rc is not None and stdout_done:
                status = "completed" if rc == 0 else "failed"
                break
        while True:
            try:
                item = q.get_nowait()
            except queue.Empty:
                break
            if item:
                f.write(item)
                f.flush()
                if item.rstrip():
                    _emit(cb, "END-004", item.rstrip())
    return status, rc


def run_end004(
    input_file: str,
    output_dir: str,
    run_id: str,
    log_callback: LogCallback | None = None,
    stop_event: threading.Event | None = None,
    star_root: str | None = None,
    star_output_root: str | None = None,
    run_output_dir: str | None = None,
    modules_output_root: str | None = None,
    module_product_output_dir: str | None = None,
    module_results_dir: str | None = None,
) -> dict[str, Any]:
    input_path = Path(input_file)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    product_dir, results_dir = ensure_module_output_layout(output_path, "END-004")
    if module_product_output_dir:
        product_dir = Path(module_product_output_dir)
        product_dir.mkdir(parents=True, exist_ok=True)
    if module_results_dir:
        results_dir = Path(module_results_dir)
        results_dir.mkdir(parents=True, exist_ok=True)

    star_payload = load_json(input_path)
    folder = _find_dir(star_root)
    script = _find_script(folder)
    native_template = _find_native_template(folder, star_root)

    end003_csv = (
        find_upstream_artifact(star_payload, ["output_attitude_propagation.csv"], [".csv"])
        or find_upstream_artifact(star_payload, ["output_attitude_propagation"], [".csv"])
        or find_upstream_artifact(star_payload, ["attitude", "propagation"], [".csv"])
    )
    end003_runtime_json = _find_end003_runtime_json(star_payload)

    runtime_extra = {
        "module_id": "END-004",
        "run_id": run_id,
        "star_root": str(star_root or STAR_ROOT),
        "end003_output_csv": str(end003_csv) if end003_csv else "",
        "end003_runtime_input_json": str(end003_runtime_json) if end003_runtime_json else "",
    }

    runtime_input = output_path / "end004_runtime_input.json"
    make_runtime_input_copy(
        source_input=native_template,
        destination=runtime_input,
        module_root=output_path,
        product_dir=product_dir,
        results_dir=results_dir,
        star_payload=star_payload,
        extra=runtime_extra,
    )

    # Ensure the native JSON schema receives the dynamically resolved paths.
    runtime_data = load_json(runtime_input)
    runtime_data.setdefault("paths", {})
    if end003_csv:
        runtime_data["paths"]["attitudeCsv"] = str(end003_csv)
    if end003_runtime_json:
        runtime_data["paths"]["attitudeConfigJson"] = str(end003_runtime_json)
    runtime_data.setdefault("star_runtime", {}).update(runtime_extra)
    decisions = _apply_star_inputs(runtime_data, star_payload, _orbit_from_upstream(star_payload, end003_csv, end003_runtime_json))
    runtime_data["star_runtime"]["end004_inputs"] = decisions
    write_json(runtime_input, runtime_data)
    o = runtime_data.get("orbit", {})
    _emit(log_callback, "EXECUTION" if "template" not in decisions["orbit"]["source"] else "WARNING",
          f"END-004 orbit: period {o.get('period_min')} min, sunlight {o.get('sunlight_min')} min, eclipse {o.get('eclipse_min')} min, "
          f"{o.get('daily_orbits')} orbits/day ({decisions['orbit']['source']}).")

    stdout_path = output_path / "matlab_stdout.txt"
    stderr_path = output_path / "matlab_stderr.txt"
    process_info_path = output_path / "end004_process_result.json"
    invocation_path = output_path / "end004_runner_invocation.json"
    runtime_script = output_path / "star_power_budget_runtime.m"

    started_at = datetime.now().isoformat()
    started_perf = time.perf_counter()
    matlab = os.environ.get("MATLAB_EXECUTABLE", "matlab")
    _prepare_runtime_script(script, runtime_script, runtime_input, output_path, folder)
    command = f"cd('{_quote(folder)}'); run('{_quote(runtime_script)}');"

    write_json(invocation_path, {
        "run_id": run_id,
        "started_at": started_at,
        "star_input_file": str(input_path),
        "native_template_file": str(native_template),
        "runtime_input_file": str(runtime_input),
        "runtime_matlab_file": str(runtime_script),
        "output_dir": str(output_path),
        "product_output_dir": str(product_dir),
        "results_output_dir": str(results_dir),
        "end003_output_csv": str(end003_csv) if end003_csv else None,
        "end003_runtime_input_json": str(end003_runtime_json) if end003_runtime_json else None,
        "matlab_command": command,
    })

    if stop_event is not None and stop_event.is_set():
        write_json(process_info_path, {"run_id": run_id, "status": "stopped", "reason": "Stop requested before MATLAB launch."})
        return {"status": "stopped", "evidence": "END-004 stopped before MATLAB launch.", "generated_artifacts": _collect(output_path)}

    env = os.environ.copy()
    env.update({
        "STAR_END004_INPUT_FILE": str(runtime_input),
        "STAR_END004_OUTPUT_DIR": str(output_path),
        "STAR_END004_PRODUCT_OUTPUT_DIR": str(product_dir),
        "STAR_END004_RESULTS_DIR": str(results_dir),
        "STAR_MODULE_OUTPUT_DIR": str(output_path),
        "STAR_MODULE_PRODUCT_OUTPUT_DIR": str(product_dir),
        "STAR_MODULE_RESULTS_DIR": str(results_dir),
        "STAR_MODULE_INPUT_FILE": str(input_path),
    })
    if end003_csv:
        env["STAR_END003_OUTPUT_CSV"] = str(end003_csv)
    if end003_runtime_json:
        env["STAR_END003_RUNTIME_INPUT_JSON"] = str(end003_runtime_json)

    _emit(log_callback, "EXECUTION", f"END-004 Power Budget started. MATLAB: {matlab}")
    _emit(log_callback, "EXECUTION", f"END-004 runtime config: {runtime_input}")
    _emit(log_callback, "EXECUTION", f"END-004 output directory: {output_path}")

    proc = subprocess.Popen(
        [matlab, "-batch", command],
        cwd=str(folder),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform.startswith("win") else 0,
    )
    _emit(log_callback, "EXECUTION", f"END-004 MATLAB process started with PID={proc.pid}.")

    status, rc = _run_process(proc, stdout_path, log_callback, stop_event)
    stderr_path.write_text("", encoding="utf-8")
    duration = time.perf_counter() - started_perf

    if status == "failed":
        reason = f"MATLAB END-004 failed with return code {rc}. See {stdout_path}."
        _emit(log_callback, "ERROR", reason)

    normalize_direct_module_outputs(
        output_path,
        product_dir,
        results_dir,
        keep_names={
            "end004_runner_invocation.json",
            "end004_runtime_input.json",
            "star_power_budget_runtime.m",
            "matlab_stdout.txt",
            "matlab_stderr.txt",
            "end004_process_result.json",
        },
        log_callback=log_callback,
        module_label="END-004",
    )

    artifacts = _collect(output_path)
    write_json(process_info_path, {
        "run_id": run_id,
        "started_at": started_at,
        "completed_at": datetime.now().isoformat(),
        "duration_seconds": round(duration, 3),
        "duration_human": _duration(duration),
        "return_code": rc,
        "status": status,
        "stdout_file": str(stdout_path),
        "stderr_file": str(stderr_path),
        "pid": proc.pid,
        "generated_artifacts": artifacts,
    })

    _emit(log_callback, "EXECUTION", f"END-004 finished with status={status}. Execution time: {_duration(duration)} ({duration:.2f} s).")
    return {
        "status": status,
        "evidence": "Power budget computed from END-003 attitude/orbit products and native END-004 power-budget configuration." if status == "completed" else f"END-004 ended with status={status}.",
        "generated_artifacts": artifacts,
    }

"""STAR runner for END-019 Components Thermal Analysis (2026-10-15).

END-019 is a lumped-parameter thermal model of a CubeSat (1U, 3U, 6U, 12U;
calibrated on in-orbit temperatures of a 3U, WildtrackCube / SIMBA), MATLAB
sources in END019-ComponentsThermalAnalysis/src (entry star_thermal_main):
it reads input_termico.json and the STAR products of END-001
(satellite_XX.json) and END-003 (selected_pass_summary.csv and the pass
attitude, output_attitude_propagation_ECI.csv) and writes, per satellite,
output_thermal_SAT-XX.csv (temperature of every face, panel and internal node,
SAR on, eclipse), thermal_summary_SAT-XX.json and
thermal_constellation_output.csv.

Called by the orchestrator (FrontEnd/star_frontend_v5.py ->
StarApi.call_module_runner_or_placeholder) as run_end019(input_file=..., ...).
The runner
1. checks the domain: a CubeSat of 1U-12U; a satellite above 24 kg, or a mission
   that names no CubeSat (and no class approved by the user), is skipped;
2. builds input_termico.json from the requirements and the approved inputs
   (CubeSat class, solar panels, SAR payload and its power); what the mission
   does not state is left to the model's own defaults, and every value records
   where it came from;
3. copies the END-001 and END-003 products of this run into one star_input_dir;
4. runs the sources in MATLAB (matlab -batch; MATLAB_EXECUTABLE overrides the
   command, STAR_END019_MATLAB_SOURCE the source folder). With
   STAR_END019_EXECUTABLE = blackbox_build/star_thermal.exe it runs the compiled
   black box instead (the model as delivered, before the 2026-10-15 fixes;
   needs the MATLAB Runtime R2026a, a missing Runtime is reported explicitly);
5. with the MATLAB sources, runs BackEnd/runners/matlab/end019_heater_cases.m in the same session (phase F4,
   outside the module: END-019 is a black box): battery heater sizing in the cold case (ideal thermostat) and
   verification with the heater of the design, heater_cases.json;
6. writes thermal_run_info.json (configuration, provenance, domain notes,
   status) for the results tab.
"""
from __future__ import annotations

import csv
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime

try:
    from .star_runner_io import load_spacecraft_definition, upstream_product
    from .star_provenance import Provenance
    from .star_status import FALLBACK, evidence as star_evidence, finalize
    from .star_kpi_adapters import write_module_kpis
except ImportError:          # loaded outside the runners package
    from star_runner_io import load_spacecraft_definition, upstream_product
    from star_provenance import Provenance
    from star_status import FALLBACK, evidence as star_evidence, finalize
    from star_kpi_adapters import write_module_kpis
from pathlib import Path
from typing import Any, Callable

MODULE_ID = "END-019"
OUTPUT_DIRNAME = "output_components_thermal_analysis"
RESULTS_DIRNAME = "results_components_thermal_analysis"
MODULE_DIRNAME = "END019-ComponentsThermalAnalysis"
CUBESAT_MAX_MASS_KG = 24.0          # 12U, CubeSat Design Specification Rev. 14.1
CLASSES = ("1U", "3U", "6U", "12U")
RUNTIME_RELEASE = "R2026a"          # MATLAB release star_thermal.exe was compiled with
RUNTIME_HINT = ("star_thermal needs the MATLAB Runtime R2026a (version 26.1), which is not installed on this machine: install it "
                "(free, administrator rights: https://www.mathworks.com/products/compiler/mcr/index.html), or rebuild star_thermal "
                "with the MATLAB release installed here, or unset STAR_END019_EXECUTABLE to run the MATLAB sources (src/).")


def _star_root(star_root: str | None) -> Path:
    if star_root:
        return Path(star_root)
    return Path(__file__).resolve().parents[2]          # STAR/BackEnd/runners/end019_runner.py


def _requirement_texts(requirements: list[Any]) -> list[str]:
    return [str(r.get("text", "")) if isinstance(r, dict) else str(r) for r in requirements or []]


def _sentence(blob: str, match: re.Match) -> str:
    start = max(blob.rfind(". ", 0, match.start()), blob.rfind("; ", 0, match.start())) + 1
    end = blob.find(". ", match.end())
    return blob[start: end + 1 if end > 0 else len(blob)].strip()[:240]


def _from_requirements(texts: list[str]) -> tuple[dict[str, Any], dict[str, str], list[str], bool, bool]:
    """Values the requirements state (nothing is guessed). Returns params,
    evidence, out_of_scope reasons, whether the mission names a CubeSat and whether its payload is a SAR."""
    blob = re.sub(r"\s+", " ", " ".join(texts))
    low = blob.lower()
    params: dict[str, Any] = {}
    evidence: dict[str, str] = {}
    out_of_scope: list[str] = []
    if m := re.search(r"\b(1|3|6|12)\s*-?\s*u\b(?!\w)", low) or re.search(r"\b(1|3|6|12)\s*-?\s*unit\s+cubesat", low):
        params["form_factor"] = f"{m.group(1)}U"
        evidence["form_factor"] = _sentence(blob, m)
    if m := re.search(r"(?:mass|massa)[^.\d]{0,50}?(?:not exceeding|non superiore a|at most|max(?:imum)?|fino a|<=?)\s*(\d+(?:[.,]\d+)?)\s*kg", low) or \
            re.search(r"(?:not exceeding|at most|max(?:imum)?)\s*(\d+(?:[.,]\d+)?)\s*kg", low):
        mass = float(m.group(1).replace(",", "."))
        evidence["satellite_mass_kg"] = _sentence(blob, m)
        if mass > CUBESAT_MAX_MASS_KG:
            out_of_scope.append(f"satellite mass up to {mass:g} kg > {CUBESAT_MAX_MASS_KG:g} kg (12U): END-019 models CubeSats of 1U-12U only")
    is_cubesat = "cubesat" in low or "form_factor" in params
    is_sar = re.search(r"\bsar\b|synthetic aperture radar", low) is not None
    if is_sar and (m := re.search(r"\bsar\b[^.]{0,80}?(\d+(?:[.,]\d+)?)\s*w\b(?!h)", low)):
        params["sar_power_W"] = float(m.group(1).replace(",", "."))
        evidence["sar_power_W"] = _sentence(blob, m)
    deployable = re.search(r"deployable (?:solar )?(?:panel|array|wing)", low)
    body = re.search(r"body[- ]mounted (?:solar )?(?:panel|array|cell)", low)
    if deployable or body:
        params["panels"] = "both" if (deployable and body) else ("deployable" if deployable else "body")
        evidence["panels"] = _sentence(blob, deployable or body)
    return params, evidence, out_of_scope, is_cubesat, is_sar


def _approved_inputs(items: list[dict[str, Any]], reviewed: bool) -> dict[str, Any]:
    """END-019 values of the missing-information step. reviewed=True: values the user entered or
    edited; False: first guesses (registry defaults), which never override the requirements."""
    out: dict[str, Any] = {}
    for item in items or []:
        if str(item.get("needed_by_module_id", "")).upper() != MODULE_ID:
            continue
        is_default = item.get("source") == "module_registry_default" and not item.get("reviewed_by_user")
        if is_default == reviewed:
            continue
        name, value = item.get("parameter"), item.get("proposed_value")
        if value in (None, "", "TBD", "not available") or str(item.get("status")) in ("requires_user_input", "not_applicable"):
            continue
        if name == "form_factor":
            m = re.search(r"(1|3|6|12)", str(value))
            if m:
                out[name] = f"{m.group(1)}U"
        elif name in ("panels", "sar_source"):
            out[name] = str(value).strip().lower()
        elif name in ("sar_power_W", "sar_duty"):
            try:
                out[name] = float(str(value).replace(",", ".").split()[0])
            except (ValueError, IndexError):
                pass
    return out


def _stage_upstream(payload: dict[str, Any], staging: Path) -> tuple[list[str], list[str]]:
    """END-001 orbits and END-003 passes / attitude of this run (registry consumes), copied into one star_input_dir.
    Returns (staged satellite files, missing items)."""
    missing: list[str] = []
    sats = sorted(upstream_product(payload, "satellite_orbits", many=True))
    if not sats:
        missing.append("END-001 orbits (product satellite_orbits, satellite_XX.json) not found")
    passes = upstream_product(payload, "selected_pass_summary")
    if not passes:
        missing.append("END-003 selected_pass_summary.csv not found")
    # pass attitude: END-003 writes the body->ECI quaternion in its results folder
    # (output_attitude_propagation_ECI.csv) and the conjugate, for Unreal / END-007,
    # in output_attitude_propagation.csv; the model reads the first, or the second
    # conjugated when the first is missing.
    att_files = [f for f in (upstream_product(payload, "attitude_propagation_eci"), upstream_product(payload, "attitude_propagation_csv")) if f]
    if not att_files:
        missing.append("END-003 pass attitude (output_attitude_propagation[_ECI].csv) not found")
    if missing:
        return [], missing
    (staging / "output_constellation_optimizer").mkdir(parents=True, exist_ok=True)
    (staging / "output_attitude_propagation").mkdir(parents=True, exist_ok=True)
    for f in sats:
        shutil.copy2(f, staging / "output_constellation_optimizer" / f.name)
    for f in [passes, *att_files]:
        shutil.copy2(f, staging / "output_attitude_propagation" / f.name)
    return [f.name for f in sats], []


MODEL_P_INTERNAL_W = 7.0            # internal powers of the calibrated model (CTR 5 W + BAT 2 W)
BATTERY_DEFAULT_C = (0.0, 45.0)     # typical Li-ion charge range, when END-006 publishes no battery temperatures


def _apply_design(payload: dict[str, Any], sat: dict[str, Any] | None, config: dict[str, Any], provenance: dict[str, str],
                  approved: dict[str, Any], notes: list[str]) -> None:
    """Satellite, powers and design cases of the run (phase D, 2026-10-21): envelope, mass and solar faces of the END-006
    design; internal dissipation from END-004 power_design_cases.json (nominal for the window, hot = maximum, cold = idle);
    beta range of the mission life for the hot case (the model searches it for the hottest battery, 2026-10-22: the
    shortest eclipse is not always the hottest) and beta of the cold case (longest eclipse), from END-001
    eclipse_summary.json for every satellite; battery limits from the END-006 battery."""
    if sat:
        src = f"END-006 initial design of the run (spacecraft_definition.json)"
        if isinstance(sat.get("dims_m"), list) and len(sat["dims_m"]) == 3:
            config["dims_m"] = [float(v) for v in sat["dims_m"]]
            provenance["dims_m"] = src
        if sat.get("mass_kg"):
            config["mass_kg"] = float(sat["mass_kg"])
            provenance["mass_kg"] = src
        faces = (sat.get("solar_panels") or {}).get("body_faces") or []
        if faces and "panels" not in approved:
            config["solar_faces"] = list(faces)
            config["panels"] = "body"
            provenance["solar_faces"] = provenance["panels"] = f"{src}: body-mounted panels on {', '.join(faces)}"
    # internal dissipation (END-004)
    path = upstream_product(payload, "power_design_cases")
    cases = None
    if path and Path(path).is_file():
        try:
            cases = json.loads(Path(path).read_text(encoding="utf-8")).get("dissipation_W")
        except (OSError, ValueError):
            cases = None
    if isinstance(cases, dict) and all(isinstance(cases.get(k), (int, float)) for k in ("nominal", "hot", "cold")):
        p_nom, p_hot, p_cold = float(cases["nominal"]), float(cases["hot"]), float(cases["cold"])
        config["P_internal_W"] = round(p_nom, 4)
        provenance["P_internal_W"] = "END-004 power_design_cases.json (nominal: mean dissipation of the day)"
        power_src = "END-004 power_design_cases.json"
    else:
        p_nom = p_hot = p_cold = MODEL_P_INTERNAL_W
        provenance["P_internal_W"] = (f"model default {MODEL_P_INTERNAL_W:g} W (END-004 power_design_cases.json not available: "
                                      "END-004 is not in the workflow)")
        power_src = f"model default {MODEL_P_INTERNAL_W:g} W"
    # beta of the cases (END-001)
    idx, hot_lo, hot_hi, cold_b = [], [], [], []
    ecl_path = upstream_product(payload, "eclipse_summary")
    try:
        sats = json.loads(Path(ecl_path).read_text(encoding="utf-8")).get("satellites") if ecl_path else None
    except (OSError, ValueError):
        sats = None
    for s in sats if isinstance(sats, list) else []:
        try:
            idx.append(int(s["satellite_index"]))
            hot_lo.append(float(s["life"]["beta_min_deg"]))
            hot_hi.append(float(s["life"]["beta_max_deg"]))
            cold_b.append(float(s["cold_case"]["beta_deg"]))
        except (KeyError, TypeError, ValueError):
            idx, hot_lo, hot_hi, cold_b = [], [], [], []
            break
    hot = {"name": "hot", "P_internal_W": round(p_hot, 4)}
    cold = {"name": "cold", "P_internal_W": round(p_cold, 4)}
    if idx:
        hot.update({"satellite_index": idx, "beta_min_deg": hot_lo, "beta_max_deg": hot_hi})
        cold.update({"satellite_index": idx, "beta_deg": cold_b})
        provenance["cases"] = (f"END-001 eclipse_summary.json (hot: the beta of the mission life with the hottest battery, cold: longest eclipse); "
                               f"dissipation hot {p_hot:.2f} W / cold {p_cold:.2f} W from {power_src}")
    else:
        provenance["cases"] = ("beta of the window (END-001 eclipse_summary.json not available); "
                               f"dissipation hot {p_hot:.2f} W / cold {p_cold:.2f} W from {power_src}")
    config["cases"] = [hot, cold]
    # battery limits (END-006)
    # battery heater of the design (phase F4, H1 thermostat): verified by BackEnd/runners/matlab/end019_heater_cases.m
    heater = ((sat or {}).get("thermal_control") or {}).get("battery_heater") or {}
    if isinstance(heater.get("power_w"), (int, float)) and heater["power_w"] > 0:
        config["battery_heater"] = {"power_w": float(heater["power_w"])}
        if isinstance(heater.get("setpoint_c"), (int, float)):
            config["battery_heater"]["setpoint_c"] = float(heater["setpoint_c"])
        provenance["battery_heater"] = (f"END-006 design (thermal_control.battery_heater: {heater.get('component')}, "
                                        f"{float(heater['power_w']):g} W, {heater.get('source') or 'heater'})")
    temp = ((sat or {}).get("battery") or {}).get("temp_op_c")
    if isinstance(temp, list) and len(temp) == 2 and None not in temp:
        config["bat_min_C"], config["bat_max_C"] = float(temp[0]), float(temp[1])
        provenance["bat_min_C"] = provenance["bat_max_C"] = f"END-006 battery {(sat.get('battery') or {}).get('component')} (operating temperatures)"
    else:
        config["bat_min_C"], config["bat_max_C"] = BATTERY_DEFAULT_C
        provenance["bat_min_C"] = provenance["bat_max_C"] = ("default 0..45 degC, typical Li-ion charge range "
                                                             "(END-006 battery temperatures not published)")
        notes.append("Battery limits: END-006 publishes no operating temperatures for the battery, 0..45 degC assumed")


def _process_env() -> dict[str, str]:
    """Environment with the MATLAB Runtime R2026a first on PATH: its installer edits the system PATH, which a STAR
    started before the install does not see (STAR_END019_RUNTIME_DIR overrides the install folder)."""
    env = dict(os.environ)
    roots = [os.environ.get("STAR_END019_RUNTIME_DIR", "").strip()]
    roots += [str(Path(os.environ[v]) / "MATLAB" / "MATLAB Runtime" / RUNTIME_RELEASE)
              for v in ("ProgramW6432", "ProgramFiles") if os.environ.get(v)]
    for r in filter(None, roots):
        bin_dir = Path(r) / "runtime" / "win64"
        if bin_dir.is_dir():
            env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
            break
    return env


def _run_process(cmd: list[str], cwd: Path, log_path: Path, stop_event: Any, log: Callable[[str, str], None]) -> tuple[int | None, str]:
    with log_path.open("w", encoding="utf-8", errors="replace") as fh:
        proc = subprocess.Popen(cmd, cwd=str(cwd), stdout=fh, stderr=subprocess.STDOUT, env=_process_env(),
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        while proc.poll() is None:
            if stop_event is not None and stop_event.is_set():
                log("WARNING", "END-019 stopped by the user.")
                if sys.platform.startswith("win"):     # matlab -batch starts MATLAB.exe as a child
                    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                proc.terminate()
                break
            time.sleep(0.5)
        rc = proc.wait()
    return rc, log_path.read_text(encoding="utf-8", errors="replace")


def _constellation_evidence(path: Path) -> str:
    """Short evidence line from thermal_constellation_output.csv (its columns are the model's own)."""
    try:
        with path.open(newline="", encoding="utf-8-sig") as fh:
            rows = list(csv.DictReader(fh))
    except OSError:
        return ""
    if not rows:
        return ""
    cols = list(rows[0].keys())
    label_col = next((c for c in cols if re.search(r"label|name", c, re.I)), cols[0])
    flag_cols = [c for c in cols if re.search(r"flag|limit|viol|exceed", c, re.I) and not c.endswith("_C")]
    text = f"{len(rows)} satellite(s) analysed"
    for c in flag_cols:            # e.g. BAT_over_limit -> "BAT_over_limit on SAT-01, SAT-02"
        flagged = [r.get(label_col, "") for r in rows if str(r.get(c, "")).strip().lower() in ("1", "true", "yes", "si")]
        text += f"; {c} on " + (", ".join(flagged) if flagged else "none")

    def num(c: str, fun: Any) -> float | None:
        vals = []
        for r in rows:
            try:
                v = float(r.get(c, ""))
            except ValueError:
                continue
            if v == v:
                vals.append(v)
        return fun(vals) if vals else None
    hot, cold = num("hot_BAT_max_C", max), num("cold_BAT_min_C", min)
    lo, hi = num("BAT_min_limit_C", min), num("BAT_max_limit_C", max)
    if hot is not None and cold is not None:
        text += f"; battery design cases: hot max {hot:.1f} degC, cold min {cold:.1f} degC"
        if lo is not None and hi is not None:
            text += f" (limits {lo:g}..{hi:g} degC)"
    return text


def _heater_evidence(path: Path) -> str:
    """Short evidence line from heater_cases.json (end019_heater_cases.m)."""
    try:
        h = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    w = h.get("worst") or {}
    if h.get("status") != "completed" or not isinstance(w.get("needed_peak_W"), (int, float)):
        return f"battery heater: {h.get('reason') or h.get('status')}" if h.get("status") else ""
    text = (f"battery heater (cold case, setpoint {h.get('setpoint_C'):g} degC): needed peak {w['needed_peak_W']:.2f} W, "
            f"mean {w['needed_mean_W_cold']:.2f} W")
    if isinstance(w.get("battery_min_with_heater_C"), (int, float)):
        text += (f"; with the {((h.get('heater_in_design') or {}).get('power_W') or 0):g} W heater of the design the battery stays "
                 f"at >= {w['battery_min_with_heater_C']:.1f} degC")
    return text


def run_end019(input_file: str, output_dir: str, run_id: str | None = None,
               log_callback: Callable[[str, str], Any] | None = None, stop_event: Any = None,
               star_root: str | None = None, run_output_dir: str | None = None, modules_output_root: str | None = None,
               module_product_output_dir: str | None = None, module_results_dir: str | None = None, **_: Any) -> dict[str, Any]:
    def log(level: str, msg: str) -> None:
        if log_callback:
            log_callback(level, msg)

    module_root = Path(output_dir)
    product_dir = Path(module_product_output_dir) if module_product_output_dir else module_root / OUTPUT_DIRNAME
    results_dir = Path(module_results_dir) if module_results_dir else module_root / RESULTS_DIRNAME
    product_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)
    root = _star_root(star_root)
    started = datetime.now().isoformat()
    payload = json.loads(Path(input_file).read_text(encoding="utf-8"))

    # 1-2. domain and configuration: requirements, then values the user approved; first guesses only fill gaps
    texts = _requirement_texts(payload.get("requirements") or [])
    req_params, evidence, out_of_scope, is_cubesat, is_sar = _from_requirements(texts)
    first_guess = _approved_inputs(payload.get("resolved_inputs") or [], reviewed=False)
    approved = _approved_inputs(payload.get("resolved_inputs") or [], reviewed=True)
    config: dict[str, Any] = {}
    provenance: dict[str, str] = {}
    for source, values in (("first guess (registry default)", first_guess), ("requirements", req_params), ("approved by the user", approved)):
        for k, v in values.items():
            config[k] = v
            provenance[k] = source
    notes: list[str] = []
    # the satellite of the run (2026-10-17): the class of the END-006 initial design, the one every module uses;
    # only a class the user approved explicitly wins, a class written in the requirements is only reported
    sat = load_spacecraft_definition(payload)
    if sat and sat.get("form_factor") in CLASSES and "form_factor" not in approved:
        if req_params.get("form_factor") and req_params["form_factor"] != sat["form_factor"]:
            notes.append(f"The requirements state a {req_params['form_factor']} CubeSat; the END-006 design of the run is a "
                         f"{sat['form_factor']} (the class that meets the required performance), used here")
        config["form_factor"] = sat["form_factor"]
        provenance["form_factor"] = f"END-006 initial design of the run (spacecraft_definition.json, {sat.get('mass_kg', 0):.2f} kg)"
    if config.get("form_factor") not in CLASSES:
        config.pop("form_factor", None)
        provenance.pop("form_factor", None)
    # the domain is decided by what the requirements or the user state, never by a first guess
    stated_class = approved.get("form_factor") or req_params.get("form_factor") or (sat or {}).get("form_factor")
    if not out_of_scope and not stated_class:
        if not is_cubesat:
            out_of_scope.append("the mission names no CubeSat and no CubeSat class was approved: END-019 models CubeSats of 1U-12U only")
        elif "form_factor" in config:
            notes.append(f"CubeSat class not stated: first guess {config['form_factor']} (registry default)")
        else:
            notes.append("CubeSat class not stated: the model's default class is used")
    if is_sar:
        config["n_internal_nodes"] = 3
        provenance["n_internal_nodes"] = "requirements (SAR payload)"
        if "sar_source" not in config:
            config["sar_source"] = "passes"
            provenance["sar_source"] = "END-003 imaging passes of the run"
        if "sar_power_W" not in config:
            notes.append("SAR power not stated: the model's default SAR power is used")
    else:
        config["n_internal_nodes"] = 2
        provenance["n_internal_nodes"] = "no SAR payload in the requirements: central body and battery only"
        for k in ("sar_power_W", "sar_source", "sar_duty"):
            if config.pop(k, None) is not None:
                provenance.pop(k, None)
        notes.append("The third internal node of the model is a SAR payload: not modelled for this mission")
    _apply_design(payload, sat, config, provenance, approved, notes)
    if "panels" not in config:
        notes.append("Solar panel layout not stated: the model's default is used")

    info: dict[str, Any] = {"schema_version": 1, "module_id": MODULE_ID, "run_id": run_id, "generated_at": started,
                            "domain": "CubeSat 1U-12U; lumped-parameter model calibrated on in-orbit data of a 3U (WildtrackCube / SIMBA)",
                            "config": config, "provenance": provenance, "evidence": evidence, "notes": notes, "out_of_scope": out_of_scope}
    generated: list[str] = []

    def finish(status: str, message: str, **extra: Any) -> dict[str, Any]:
        # the class, the internal dissipation, the design-case betas and the battery limits drive the result; a fallback for
        # them is recorded (registry first guesses of the other settings are tuning)
        prov = Provenance(MODULE_ID)
        prov.add_origins({k: v for k, v in info.get("provenance", {}).items()
                          if k in ("form_factor", "P_internal_W", "cases", "bat_min_C")})
        status, severity = finalize(status, prov)
        if status == FALLBACK:
            message = star_evidence(MODULE_ID, status, prov, message)
        info.update({"status": status, "evidence_text": message, "fallback_severity": severity, **extra})
        path = results_dir / "thermal_run_info.json"
        path.write_text(json.dumps(info, indent=1, ensure_ascii=False), encoding="utf-8")
        generated.append(str(path))
        process = {"run_id": run_id, "status": status, "started_at": started, "completed_at": datetime.now().isoformat(),
                   "return_code": info.get("return_code"), "evidence": message}
        (module_root / "end019_process_result.json").write_text(json.dumps(process, indent=1, ensure_ascii=False), encoding="utf-8")
        log("EXECUTION" if status == "completed" else "WARNING", f"END-019 {status}: {message}")
        if status in ("completed", FALLBACK):
            write_module_kpis(MODULE_ID, module_root, run_id or "", log=log)
        return {"status": status, "fallback_severity": severity, "fallbacks": prov.fallbacks(), "provenance": prov.to_json(status, message),
                "generated_artifacts": generated, "evidence": message}

    if out_of_scope:
        info.update({"config": {}, "provenance": {}, "notes": []})      # nothing is configured for a mission outside the domain
        return finish("skipped_out_of_scope", "Mission out of scope for the CubeSat thermal model: " + "; ".join(out_of_scope))

    # 3. upstream products of this run
    staging = module_root / "star_input"
    if staging.exists():
        shutil.rmtree(staging)
    satellites, missing = _stage_upstream(payload, staging)
    if missing:
        return finish("failed", "Upstream products missing: " + "; ".join(missing) + ". END-019 needs END-001 and END-003 earlier in the workflow.")
    info["satellites"] = satellites

    # 4. the model
    cfg = {"star_input_dir": str(staging), "output_dir": str(product_dir), **config}
    cfg_path = module_root / "input_termico.json"
    cfg_path.write_text(json.dumps(cfg, indent=1), encoding="utf-8")
    log("EXECUTION", f"END-019 configuration: {json.dumps(config)}")
    exe_env = os.environ.get("STAR_END019_EXECUTABLE", "").strip()
    if exe_env:
        exe = Path(exe_env)
        if not exe.is_file():
            return finish("failed", f"STAR_END019_EXECUTABLE {exe} not found.")
        cmd = [str(exe), str(cfg_path)]
        info["engine"] = "executable (model as delivered, before the 2026-10-15 fixes)"
    else:
        src_dir = Path(os.environ.get("STAR_END019_MATLAB_SOURCE", "").strip() or root / MODULE_DIRNAME / "src")
        if not (src_dir / "star_thermal_main.m").is_file():
            return finish("failed", f"END-019 MATLAB sources not found: {src_dir / 'star_thermal_main.m'} (set STAR_END019_MATLAB_SOURCE).")
        matlab = os.environ.get("MATLAB_EXECUTABLE", "matlab")
        if not (Path(matlab).is_file() or shutil.which(matlab)):
            return finish("failed", f"MATLAB not found ('{matlab}'): END-019 runs its MATLAB sources (set MATLAB_EXECUTABLE).")
        src, cfg_m = str(src_dir).replace("'", "''"), str(cfg_path).replace("'", "''")
        # battery heater cases (phase F4): a separate .m outside the END-019 module, same MATLAB session
        ext = str(Path(__file__).resolve().parent / "matlab").replace("'", "''")
        cmd = [matlab, "-batch", f"addpath('{src}'); addpath('{ext}'); star_thermal_main('{cfg_m}'); end019_heater_cases('{cfg_m}');"]
        info["engine"] = f"MATLAB sources {src_dir} + BackEnd/runners/matlab/end019_heater_cases.m"
    log("EXECUTION", f"END-019 running {' '.join(cmd)}")
    rc, out = _run_process(cmd, module_root, module_root / "end019_process_log.txt", stop_event, log)
    info["command"] = cmd
    info["return_code"] = rc
    if stop_event is not None and stop_event.is_set():
        return finish("stopped", "END-019 stopped by the user.")
    if rc != 0:
        if exe_env and ("MATLAB Runtime" in out or "mclmcrrt" in out):
            return finish("failed", RUNTIME_HINT, process_output=out[-1500:])
        return finish("failed", f"END-019 model exited with code {rc}: {out.strip()[-600:]}", process_output=out[-1500:])

    # 5. products
    products = sorted(p.name for p in product_dir.iterdir() if p.is_file())
    generated.extend(str(product_dir / p) for p in products)
    constellation = product_dir / "thermal_constellation_output.csv"
    if not constellation.is_file():
        return finish("failed", "The END-019 model ended without thermal_constellation_output.csv.", products=products)
    evidence_text = _constellation_evidence(constellation) or f"{len(satellites)} satellite(s) analysed"
    heater_text = _heater_evidence(product_dir / "heater_cases.json")
    if heater_text:
        evidence_text += "; " + heater_text
    elif not exe_env:
        notes.append("heater_cases.json not written: battery heater sizing not available")
    # scalar settings only: the design cases are in thermal_run_info.json and in the evidence above
    shown = ", ".join(f"{k}={v}" for k, v in config.items() if not isinstance(v, (list, dict)))
    return finish("completed", f"{evidence_text} ({shown}).", products=products)

"""STAR runner for END-016 Collision Avoidance (2026-10-15): space-safety checks of the
constellation END-001 designed.

Inside STAR END-016 answers two design questions about the END-001 constellation of
the run (MATLAB, END016-CollisionAvoidance/lib/star_collision_main.m):
1. do the satellites of the constellation come close to each other? Every pair over
   the END-001 ephemeris window (satellite_NN_ephemeris.csv): time and distance of
   closest approach, miss components, relative speed, collision probability Pc with
   the declared position uncertainty and the largest Pc any uncertainty could give;
2. how long does each orbit last after the mission, and what does the disposal cost?
   Passive lifetime under drag (NRLMSISE-00) for the solar activity levels of the run
   mode, compliance with the 5-year (FCC) and 25-year (IADC) rules, perigee-lowering
   delta-v that brings it within each rule, drag make-up delta-v per year.

The runner
1. copies the END-001 products of this run (satellite_NN.json, satellite_NN_ephemeris.csv)
   into star_input/ and takes mass, drag area and drag coefficient from END-001's input
   of the run (the values END-001 used), else from the requirements, else defaults;
2. reads the mission lifetime and any disposal deadline from the requirements, and the
   values the user approved; every value records where it came from;
3. runs star_collision_main with matlab -batch (MATLAB_EXECUTABLE overrides the command);
4. writes collision_run_info.json (configuration, provenance, notes, status) for the
   results tab.
Run mode (star_runner_io.star_run_mode): test = mean solar activity only; full = low,
mean and high activity.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

try:
    from .star_runner_io import star_run_mode
except ImportError:
    from star_runner_io import star_run_mode

MODULE_ID = "END-016"
OUTPUT_DIRNAME = "output_collision_avoidance"
RESULTS_DIRNAME = "results_collision_avoidance"
MODULE_DIRNAME = "END016-CollisionAvoidance"
WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
         "twelve": 12, "fifteen": 15, "twenty": 20, "twenty-five": 25}
NUMBER = r"(\d+(?:[.,]\d+)?|" + "|".join(sorted(WORDS, key=len, reverse=True)) + r")"
DEFAULT_SIGMA_RTN_M = [50.0, 200.0, 50.0]
SOLAR_LEVELS = {"test": [140.0], "full": [70.0, 140.0, 220.0]}


def _star_root(star_root: str | None) -> Path:
    return Path(star_root) if star_root else Path(__file__).resolve().parents[2]


def _num(text: str) -> float | None:
    t = str(text).strip().lower()
    if t in WORDS:
        return float(WORDS[t])
    try:
        return float(t.replace(",", "."))
    except ValueError:
        return None


def _from_requirements(texts: list[str]) -> tuple[dict[str, Any], dict[str, str]]:
    """Mission lifetime, disposal deadlines, hard-body radius, mass and drag from the requirement texts."""
    out: dict[str, Any] = {}
    where: dict[str, str] = {}
    for i, text in enumerate(texts):
        low = text.lower()
        rid = f"requirement {i + 1}"
        m = re.search(r"(?:mission|operational|design)\s+(?:lifetime|life|duration)[^.;]{0,40}?" + NUMBER + r"\s*(?:years?|yrs?)\b", low)
        if m and _num(m.group(1)) is not None and "mission_lifetime_years" not in out:
            out["mission_lifetime_years"], where["mission_lifetime_years"] = _num(m.group(1)), rid
        for m in re.finditer(r"(?:dispos|de-?orbit|re-?ent|end[- ]of[- ]life|post[- ]mission|debris)[^.;]{0,120}?within\s+" + NUMBER + r"\s*years?", low):
            v = _num(m.group(1))
            if v:
                out.setdefault("disposal_rules_years", [])
                if v not in out["disposal_rules_years"]:
                    out["disposal_rules_years"].append(v)
                where["disposal_rules_years"] = rid
        m = re.search(r"hard[- ]body radius[^.;]{0,30}?(\d+(?:[.,]\d+)?)\s*(m|cm)\b", low)
        if m:
            v = float(m.group(1).replace(",", ".")) * (0.01 if m.group(2) == "cm" else 1.0)
            out["hard_body_radius_m"], where["hard_body_radius_m"] = v, rid
        m = re.search(r"mass\s+(?:not exceeding|of|below|up to|lower than|less than)\s+(\d+(?:[.,]\d+)?)\s*kg", low)
        if m and "mass_kg" not in out:
            out["mass_kg"], where["mass_kg"] = float(m.group(1).replace(",", ".")), rid
        m = re.search(r"drag (?:cross[- ]section|area) of\s+(\d+(?:[.,]\d+)?)\s*m", low)
        if m:
            out["drag_area_m2"], where["drag_area_m2"] = float(m.group(1).replace(",", ".")), rid
        m = re.search(r"drag coefficient of\s+(\d+(?:[.,]\d+)?)", low)
        if m:
            out["cd"], where["cd"] = float(m.group(1).replace(",", ".")), rid
    return out, where


def _approved_inputs(items: list[dict[str, Any]]) -> dict[str, Any]:
    """END-016 values the user entered or edited in the input-resolution step (first guesses are ignored)."""
    out: dict[str, Any] = {}
    for item in items or []:
        if str(item.get("needed_by_module_id", "")).upper() != MODULE_ID:
            continue
        if item.get("source") == "module_registry_default" and not item.get("reviewed_by_user"):
            continue
        name, value = item.get("parameter"), item.get("proposed_value")
        if value in (None, "", "TBD", "not available") or str(item.get("status")) in ("requires_user_input", "not_applicable"):
            continue
        nums = [float(x.replace(",", ".")) for x in re.findall(r"\d+(?:[.,]\d+)?", str(value))]
        if name == "position_sigma_rtn_m" and len(nums) >= 3:
            out[name] = nums[:3]
        elif name == "disposal_rules_years" and nums:
            out[name] = nums
        elif name in ("hard_body_radius_m", "mission_lifetime_years", "screening_km", "pc_threshold") and nums:
            out[name] = nums[0] if name != "pc_threshold" else float(str(value).strip())
    return out


def _end001_spacecraft(modules_output: Path) -> dict[str, float]:
    """Mass, drag area and drag coefficient END-001 used in this run (its runtime input)."""
    path = modules_output / "END-001" / "end001_runtime_input.json"
    try:
        sc = json.loads(path.read_text(encoding="utf-8")).get("SpacecraftProperties") or {}
    except (OSError, ValueError):
        return {}
    out = {}
    for key, name in (("Mass", "mass_kg"), ("ADrag", "drag_area_m2"), ("CD", "cd")):
        try:
            out[name] = float(sc[key])
        except (KeyError, TypeError, ValueError):
            pass
    return out


def _stage_upstream(modules_output: Path, staging: Path) -> tuple[list[str], str | None]:
    src = modules_output / "END-001" / "output_constellation_optimizer"
    sats = sorted(p for p in src.glob("satellite_*.json")) if src.is_dir() else []
    if not sats:
        return [], f"END-001 orbits (satellite_NN.json) not found in {src}: END-016 needs END-001 earlier in the workflow"
    missing = [p.name for p in sats if not (src / f"{p.stem}_ephemeris.csv").is_file()]
    if missing:
        return [], (f"END-001 ephemerides missing for {', '.join(missing)} (satellite_NN_ephemeris.csv, written by END-001 "
                    "since 2026-10-15): run END-001 again")
    staging.mkdir(parents=True, exist_ok=True)
    for p in sats:
        shutil.copy2(p, staging / p.name)
        shutil.copy2(src / f"{p.stem}_ephemeris.csv", staging / f"{p.stem}_ephemeris.csv")
    return [p.name for p in sats], None


def _run_process(cmd: list[str], cwd: Path, log_path: Path, stop_event: Any, log: Callable[[str, str], None]) -> tuple[int | None, str]:
    with log_path.open("w", encoding="utf-8", errors="replace") as fh:
        proc = subprocess.Popen(cmd, cwd=str(cwd), stdout=fh, stderr=subprocess.STDOUT,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        while proc.poll() is None:
            if stop_event is not None and stop_event.is_set():
                log("WARNING", "END-016 stopped by the user.")
                if sys.platform.startswith("win"):     # matlab -batch starts MATLAB.exe as a child
                    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                proc.terminate()
                break
            time.sleep(0.5)
        rc = proc.wait()
    return rc, log_path.read_text(encoding="utf-8", errors="replace")


def _years(v: Any) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "> 200 y" if str(v).lower() == "inf" else str(v)
    return "> 200 y" if f == float("inf") else f"{f:.1f} y"


def run_end016(input_file: str, output_dir: str, run_id: str | None = None,
               log_callback: Callable[[str, str], Any] | None = None, stop_event: Any = None,
               star_root: str | None = None, run_output_dir: str | None = None, modules_output_root: str | None = None,
               module_product_output_dir: str | None = None, module_results_dir: str | None = None,
               run_mode: str | None = None, **_: Any) -> dict[str, Any]:
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
    mode = star_run_mode({"run_mode": run_mode or payload.get("run_mode")})
    modules_output = Path(modules_output_root) if modules_output_root else (Path(run_output_dir) / "modules_output" if run_output_dir else module_root.parent)

    texts = [str(r.get("text", "")) if isinstance(r, dict) else str(r) for r in payload.get("requirements") or []]
    req, req_where = _from_requirements(texts)
    approved = _approved_inputs(payload.get("resolved_inputs") or [])
    sc_end001 = _end001_spacecraft(modules_output)

    config: dict[str, Any] = {}
    provenance: dict[str, str] = {}
    notes: list[str] = []

    def put(name: str, value: Any, origin: str) -> None:
        config[name] = value
        provenance[name] = origin

    defaults = {"mass_kg": 100.0, "drag_area_m2": 1.0, "cd": 2.2}
    spacecraft = {}
    for name in ("mass_kg", "drag_area_m2", "cd"):
        if name in sc_end001:
            spacecraft[name], provenance[f"spacecraft.{name}"] = sc_end001[name], "END-001 input of this run"
        elif name in req:
            spacecraft[name], provenance[f"spacecraft.{name}"] = req[name], req_where[name]
        else:
            spacecraft[name], provenance[f"spacecraft.{name}"] = defaults[name], "default (END-001 template)"
    config["spacecraft"] = spacecraft
    if "hard_body_radius_m" in approved:
        put("hard_body_radius_m", approved["hard_body_radius_m"], "approved by the user")
    elif "hard_body_radius_m" in req:
        put("hard_body_radius_m", req["hard_body_radius_m"], req_where["hard_body_radius_m"])
    else:
        put("hard_body_radius_m", round(2 * (spacecraft["drag_area_m2"] / 3.141592653589793) ** 0.5, 3),
            "derived: twice the radius of a disc with the drag area (both satellites)")
    if "position_sigma_rtn_m" in approved:
        put("position_sigma_rtn_m", approved["position_sigma_rtn_m"], "approved by the user")
    else:
        put("position_sigma_rtn_m", DEFAULT_SIGMA_RTN_M,
            "declared assumption: owner/operator GNSS ephemeris predicted ~1 day ahead (radial, in-track, cross-track 1-sigma)")
        notes.append("Pc uses a declared position uncertainty; Pc_max is the largest Pc any uncertainty could give")
    for name, default, origin in (("screening_km", 10.0, "default"), ("pc_threshold", 1e-4, "default (common manoeuvre threshold)")):
        put(name, approved.get(name, default), "approved by the user" if name in approved else origin)
    if "mission_lifetime_years" in approved:
        put("mission_lifetime_years", approved["mission_lifetime_years"], "approved by the user")
    elif "mission_lifetime_years" in req:
        put("mission_lifetime_years", req["mission_lifetime_years"], req_where["mission_lifetime_years"])
    else:
        notes.append("Mission lifetime not stated: orbit maintenance is not assessed")
    rules = sorted({int(round(r)) for r in [5, 25] + list(req.get("disposal_rules_years", [])) + list(approved.get("disposal_rules_years", [])) if r >= 1})
    put("disposal_rules_years", rules, "FCC 5-year and IADC 25-year rules" + (" + " + req_where["disposal_rules_years"] if "disposal_rules_years" in req else ""))
    put("solar_f107", SOLAR_LEVELS["full" if mode == "full" else "test"],
        f"run mode {mode}: " + ("low, mean and high solar activity" if mode == "full" else "mean solar activity only"))

    info: dict[str, Any] = {"schema_version": 1, "module_id": MODULE_ID, "run_id": run_id, "generated_at": started, "run_mode": mode,
                            "scope": "space-safety checks of the END-001 constellation: close approaches between its satellites; lifetime and disposal",
                            "config": config, "provenance": provenance, "notes": notes}
    generated: list[str] = []

    def finish(status: str, message: str, **extra: Any) -> dict[str, Any]:
        info.update({"status": status, "evidence_text": message, **extra})
        path = results_dir / "collision_run_info.json"
        path.write_text(json.dumps(info, indent=1, ensure_ascii=False), encoding="utf-8")
        generated.append(str(path))
        (module_root / "end016_process_result.json").write_text(json.dumps(
            {"run_id": run_id, "status": status, "started_at": started, "completed_at": datetime.now().isoformat(),
             "return_code": info.get("return_code"), "evidence": message}, indent=1, ensure_ascii=False), encoding="utf-8")
        log("EXECUTION" if status == "completed" else "WARNING", f"END-016 {status}: {message}")
        return {"status": status, "generated_artifacts": generated, "evidence": message}

    staging = module_root / "star_input"
    if staging.exists():
        shutil.rmtree(staging)
    satellites, problem = _stage_upstream(modules_output, staging)
    if problem:
        return finish("failed", problem)
    info["satellites"] = satellites

    cfg = {"star_input_dir": str(staging), "output_dir": str(product_dir), **config}
    cfg_path = module_root / "input_collision_avoidance.json"
    cfg_path.write_text(json.dumps(cfg, indent=1), encoding="utf-8")
    log("EXECUTION", f"END-016 configuration: {json.dumps(config)}")
    lib = Path(os.environ.get("STAR_END016_MATLAB_SOURCE", "").strip() or root / MODULE_DIRNAME / "lib")
    if not (lib / "star_collision_main.m").is_file():
        return finish("failed", f"END-016 MATLAB sources not found: {lib / 'star_collision_main.m'}")
    matlab = os.environ.get("MATLAB_EXECUTABLE", "matlab")
    if not (Path(matlab).is_file() or shutil.which(matlab)):
        return finish("failed", f"MATLAB not found ('{matlab}'): set MATLAB_EXECUTABLE.")
    src, cfg_m = str(lib).replace("'", "''"), str(cfg_path).replace("'", "''")
    cmd = [matlab, "-batch", f"addpath('{src}'); star_collision_main('{cfg_m}');"]
    log("EXECUTION", f"END-016 running {' '.join(cmd)}")
    rc, out = _run_process(cmd, module_root, module_root / "end016_process_log.txt", stop_event, log)
    info["command"], info["return_code"] = cmd, rc
    if stop_event is not None and stop_event.is_set():
        return finish("stopped", "END-016 stopped by the user.")
    summary_path = product_dir / "space_safety_summary.json"
    if rc != 0 or not summary_path.is_file():
        return finish("failed", f"END-016 model exited with code {rc}: {out.strip()[-600:]}", process_output=out[-1500:])
    generated.extend(str(p) for p in sorted(product_dir.iterdir()) if p.is_file())

    k = json.loads(summary_path.read_text(encoding="utf-8")).get("kpis", {})
    parts = [f"{len(satellites)} satellite(s)"]
    if k.get("n_pairs"):
        parts.append(f"minimum separation {float(k['min_separation_km']):.3f} km ({k.get('min_separation_pair')})")
        parts.append(f"{k.get('n_events_below_screening', 0)} close approach(es) below {config['screening_km']:g} km"
                     + (f", max Pc {float(k['max_pc']):.1e}" if k.get("n_events_below_screening") else ""))
    parts.append(f"passive lifetime {_years(k.get('passive_lifetime_years_mean_activity'))} at mean solar activity")
    for r in rules:
        key = f"complies_{int(r)}y_rule_mean_activity"
        if key in k:
            dv = k.get(f"disposal_dv_m_s_{int(r)}y_rule_mean_activity")
            parts.append(f"{int(r)}-year rule " + ("met" if k[key] else f"not met (disposal {float(dv):.1f} m/s)"))
    if k.get("orbit_maintenance_needed"):
        parts.append("the orbit decays before the end of the mission: orbit maintenance needed")
    return finish("completed", "; ".join(parts) + ".")

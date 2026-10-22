from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from runners.star_runner_io import (
    build_end003_config,
    coerce_bool,
    coerce_float,
    describe_pass,
    ensure_module_output_layout,
    input_value,
    load_end001_constellation,
    load_json,
    load_selected_passes,
    load_spacecraft_definition,
    merge_pass_selection_defaults,
    normalize_direct_module_outputs,
    upstream_product,
    write_json,
)
from runners.star_provenance import from_runtime_decisions
from runners.star_status import evidence as star_evidence, finalize
from runners.star_kpi_adapters import write_module_kpis

STAR_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_END003_DIR = STAR_ROOT / "END003-AttitudePropagation"
# STAR version of END-003 (2026-10-17): orbit from the END-001 ephemerides, no
# orbit propagation. The legacy star_attitude_propagation.m (internal propagation)
# is archived in END003-AttitudePropagation/_old/ (2026-10-17).
STAR_SCRIPT_NAME = "star_attitude_propagation_star.m"
ATTITUDE_MODES = ("nadir", "follow_site", "dynamics")
SPACECRAFT_NOTE = "uniform box of the class envelope, mean projected area as reference area"
# Centre of pressure from the centre of mass (2026-10-19): the uniform box puts both at the geometric centre, so the offset is the
# centre-of-gravity tolerance of the CubeSat Design Specification, about 20% of each side (2 cm on the 10 cm sides, 7 cm on the
# 34 cm side of a 3U): a conservative lever arm for SRP and drag, used unless the STAR input gives r_cp.
R_CP_FRACTION = 0.2
R_CP_NOTE = "r_cp = 20% of each side of the envelope (CubeSat Design Specification centre-of-gravity tolerance)"
LogCallback = Callable[[str, str], Any]


def _emit(cb: LogCallback | None, level: str, msg: str) -> None:
    if callable(cb):
        try: cb(level, msg)
        except Exception: pass


def _quote(path: Path | str) -> str:
    return str(path).replace("\\", "/").replace("'", "''")


def _duration(seconds: float) -> str:
    if seconds < 1: return f"{seconds*1000:.0f} ms"
    if seconds < 60: return f"{seconds:.2f} s"
    m, s = divmod(seconds, 60); return f"{int(m)} min {s:.1f} s"


def _collect(path: Path) -> list[str]:
    return [str(p) for p in sorted(path.rglob("*")) if p.is_file()] if path.exists() else []


def _find_dir() -> Path:
    env = os.environ.get("STAR_END003_DIR", "").strip()
    if env and Path(env).exists(): return Path(env)
    for p in [DEFAULT_END003_DIR, STAR_ROOT / "END003_AttitudePropagation", STAR_ROOT / "END003"]:
        if p.exists(): return p
    raise FileNotFoundError(f"END-003 folder not found. Expected {DEFAULT_END003_DIR}")


def _find_script(folder: Path) -> Path:
    script = folder / STAR_SCRIPT_NAME
    if script.exists(): return script
    raise FileNotFoundError(f"END-003 MATLAB function {STAR_SCRIPT_NAME} not found in {folder}")


def _end001_ephemerides(star_payload: dict[str, Any]) -> list[dict[str, Any]]:
    """satellite_NN_ephemeris.csv written by END-001 (product satellite_ephemerides)."""
    found = []
    for path in upstream_product(star_payload, "satellite_ephemerides", many=True):
        m = re.match(r"satellite_(\d+)_ephemeris\.csv$", path.name)
        if m:
            found.append({"satellite_index": int(m.group(1)), "file": str(path)})
    return sorted(found, key=lambda item: item["satellite_index"])


def _write_orbit_and_window(config: dict[str, Any], product_dir: Path, selected: dict[str, Any] | None) -> None:
    """Product attitude_orbit_window: elements of the satellite the imaging pass was selected on (the first satellite when there is
    no pass), epoch, propagation window, attitude mode and target site. END-004 and END-010 read it instead of
    end003_runtime_input.json (same key names, so the END-004 MATLAB reads it as its attitude configuration)."""
    orbit = ((selected or {}).get("imaging_pass") or {}).get("orbit") or config.get("orbit") or {}
    write_json(product_dir / "orbit_and_window.json", {
        "module_id": "END-003", "generated_at": datetime.now().isoformat(),
        "selected_satellite_index": ((selected or {}).get("imaging_pass") or {}).get("satellite_index"),
        "orbit": orbit, "sim_start_date": config.get("sim_start_date"), "sim_hours": config.get("sim_hours"),
        "sat": {"attitude_mode": (config.get("sat") or {}).get("attitude_mode")},
        "env": {"Re": (config.get("env") or {}).get("Re")},
        "target": config.get("target") or {},
    })


def _end001_ground_stations(star_payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Ground stations of the END-001 run (product ground_stations): END-003 computes the face illumination during their
    contacts for the END-004 solar generation (2026-10-19)."""
    path = upstream_product(star_payload, "ground_stations")
    if not path or not Path(path).exists():
        return []
    stations = (load_json(Path(path)) or {}).get("ground_stations") or []
    out = []
    for i, gs in enumerate(stations, 1):
        try:
            out.append({"name": str(gs.get("name") or f"GS {i}"), "lat": float(gs["lat"]), "lon": float(gs["lon"]),
                        "alt": float(gs.get("alt") or 0.0), "mask": float(gs["mask"] if gs.get("mask") is not None else 5.0)})   # 5 deg: END-001 default
        except (AttributeError, KeyError, TypeError, ValueError):
            continue
    return out


def _reviewed(star_payload: dict[str, Any], name: str) -> bool:
    """False for a registry first guess the user has not reviewed (as END-004 _user_input), True otherwise."""
    for item in star_payload.get("resolved_inputs") or []:
        if isinstance(item, dict) and item.get("parameter") == name:
            return not (item.get("source") in ("module_registry_default", "module_registry_required_input") and not item.get("reviewed_by_user"))
    return True


def _source(star_payload: dict[str, Any], name: str) -> str:
    return "STAR input" if _reviewed(star_payload, name) else "registry default (not reviewed by the user)"


def _apply_star_inputs(config: dict[str, Any], star_payload: dict[str, Any]) -> dict[str, Any]:
    """STAR inputs over the native template; returns the decisions (star_runtime.end003_inputs)."""
    report: dict[str, Any] = {}
    sat = config.setdefault("sat", {})
    mode = str(input_value(star_payload, "attitude_mode", "") or "").strip().lower()
    if mode in ATTITUDE_MODES:
        sat["attitude_mode"] = mode
        report["attitude_mode"] = {"value": mode, "source": _source(star_payload, "attitude_mode")}
    else:
        report["attitude_mode"] = {"value": sat.get("attitude_mode", "nadir"), "source": "template"}
    state = input_value(star_payload, "initial_attitude_state", None)
    if isinstance(state, dict):
        q0 = state.get("q0")
        if isinstance(q0, list) and len(q0) == 4:
            # registry: scalar first [w, x, y, z]; END-003: scalar last [x, y, z, w]
            sat["q0"] = [float(q0[1]), float(q0[2]), float(q0[3]), float(q0[0])]
        w0 = state.get("w0_rad_s", state.get("w0"))
        if isinstance(w0, list) and len(w0) == 3:
            sat["w0"] = [float(v) for v in w0]
        report["initial_attitude_state"] = {"q0_scalar_last": sat.get("q0"), "w0_rad_s": sat.get("w0"),
                                            "source": _source(star_payload, "initial_attitude_state")}
    # disturbance torques: only flags the user gave or reviewed switch a model off; an unreviewed registry first guess
    # keeps the template (gravity gradient, solar radiation pressure and drag on). Until 2026-10-19 the registry default
    # (srp and drag off) silently left the controller, the wheels and the magnetorquers with almost no disturbance.
    flags = input_value(star_payload, "environmental_flags", None) if _reviewed(star_payload, "environmental_flags") else None
    env_flags = config.setdefault("env", {}).setdefault("flags", {})
    if isinstance(flags, dict):
        for key in ("gg", "srp", "drag"):
            if key in flags:
                env_flags[key] = coerce_bool(flags.get(key), bool(env_flags.get(key, True)))
        report["environmental_flags"] = {"value": {k: env_flags.get(k) for k in ("gg", "srp", "drag")}, "source": "STAR input"}
    else:
        report["environmental_flags"] = {"value": {k: env_flags.get(k, True) for k in ("gg", "srp", "drag")},
                                         "source": "template (the registry default was not reviewed by the user)"}
    hours = coerce_float(input_value(star_payload, "simulation_duration_hours", None), 0.0)
    if hours > 0:
        config["sim_hours"] = hours
        report["simulation_duration_hours"] = {"value": hours, "source": "STAR input (limited to the END-001 ephemeris span)"}
    # mass, inertia and areas: the STAR input, otherwise the END-006 initial design (the satellite of every module)
    props = input_value(star_payload, "spacecraft_physical_properties", None)
    sat_def = load_spacecraft_definition(star_payload)
    if isinstance(props, dict) and props:
        for key in ("m", "A_ref", "Cr", "Cd", "Ix", "Iy", "Iz"):
            if props.get(key) is not None:
                sat[key] = coerce_float(props[key], float(sat.get(key, 0.0)))
        if isinstance(props.get("r_cp"), list) and len(props["r_cp"]) == 3:
            sat["r_cp"] = [float(v) for v in props["r_cp"]]
        report["spacecraft"] = {"value": {k: sat.get(k) for k in ("m", "A_ref", "Cr", "Cd", "Ix", "Iy", "Iz", "r_cp")}, "source": "STAR input"}
    elif sat_def:
        ix, iy, iz = sat_def["inertia_kg_m2"]
        sat.update({"m": sat_def["mass_kg"], "Ix": ix, "Iy": iy, "Iz": iz, "A_ref": sat_def["area_mean_projected_m2"],
                    "Cd": sat_def.get("cd", sat.get("Cd")), "Cr": sat_def.get("cr", sat.get("Cr"))})
        dims = sat_def.get("dims_m")
        if isinstance(dims, list) and len(dims) == 3:
            sat["r_cp"] = [R_CP_FRACTION * float(d) for d in dims]
        report["spacecraft"] = {"value": {k: sat.get(k) for k in ("m", "A_ref", "Cr", "Cd", "Ix", "Iy", "Iz", "r_cp")},
                                "source": f"END-006 initial design ({sat_def.get('form_factor')}, {SPACECRAFT_NOTE}; {R_CP_NOTE})"}
    else:
        report["spacecraft"] = {"value": {k: sat.get(k) for k in ("m", "A_ref", "Ix", "Iy", "Iz")}, "source": "template (no END-006 in the workflow)"}
    report["attitude_control"] = _apply_attitude_control(sat, sat_def)
    return report


def _apply_attitude_control(sat: dict[str, Any], sat_def: dict[str, Any] | None) -> dict[str, Any]:
    """Wheel limits, magnetorquer dipole and attitude knowledge of the PD control (sat.control) from the END-006 design
    (2026-10-19): momentum and maximum torque of the wheels (one per body axis), dipole per axis of the magnetorquers that
    dump them, knowledge error from the star tracker or from the pointing accuracy of the ADCS unit; the template values stay
    when the design does not give them."""
    control = sat.setdefault("control", {})
    ac = (sat_def or {}).get("attitude_control") or {}
    wheels = ac.get("wheels") or {}
    if wheels.get("momentum_nms") and wheels.get("max_torque_nm"):
        control["wheel_momentum_Nms"] = float(wheels["momentum_nms"])
        control["wheel_torque_Nm"] = float(wheels["max_torque_nm"])
        kind = "reaction wheel" if wheels.get("source") == "reaction_wheel" else "wheels of the ADCS unit"
        control["wheels_source"] = f"END-006 {wheels.get('name') or wheels.get('component')} ({kind}, one per body axis)"
    else:
        control.setdefault("wheels_source", "END-003 template" + (" (the END-006 design gives no wheel data)" if sat_def else ""))
    tracker = ac.get("star_tracker") or {}
    if tracker.get("accuracy_cross_arcsec"):
        sigma = float(tracker["accuracy_cross_arcsec"]) / 3600.0 / (3.0 if str(tracker.get("accuracy_basis")) == "3-sigma" else 1.0)
        control["attitude_knowledge_deg"] = sigma
        control["knowledge_source"] = f"END-006 star tracker {tracker.get('component')} (cross-axis accuracy, 1 sigma)"
    elif ac.get("pointing_accuracy_deg"):
        control["attitude_knowledge_deg"] = float(ac["pointing_accuracy_deg"])
        control["knowledge_source"] = f"END-006 ADCS unit {ac.get('adcs_unit')} (declared pointing accuracy as 1-sigma knowledge error)"
    else:
        control.setdefault("knowledge_source", "END-003 template")
    mtq = ac.get("magnetorquers") or {}
    if mtq.get("dipole_am2") and int(mtq.get("axes") or 0) >= 3:
        control["magnetorquer_dipole_Am2"] = float(mtq["dipole_am2"])
        kind = "magnetorquer" if mtq.get("source") == "magnetorquer" else "magnetorquers of the ADCS unit"
        control["magnetorquer_source"] = f"END-006 {mtq.get('name') or mtq.get('component')} ({kind}, dipole per body axis)"
    # otherwise END-003 sizes the dipole with the END-006 rule (a full wheel dumped in one orbit)
    return {"value": {k: control.get(k) for k in ("enabled", "wheel_momentum_Nms", "wheel_torque_Nm", "attitude_knowledge_deg",
                                                  "magnetorquer_dipole_Am2")},
            "wheels_source": control.get("wheels_source"), "knowledge_source": control.get("knowledge_source"),
            "magnetorquer_source": control.get("magnetorquer_source", "END-003: END-006 sizing rule (dipole that dumps a full wheel in one orbit)")}


def _terminate(proc: subprocess.Popen, cb: LogCallback | None) -> None:
    if proc.poll() is not None: return
    _emit(cb, "EXECUTION", f"Stop requested. Terminating END-003 MATLAB process tree. PID={proc.pid}")
    if sys.platform.startswith("win"):
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        proc.terminate(); proc.wait(timeout=8)
    except Exception:
        try: proc.kill(); proc.wait(timeout=8)
        except Exception: pass


def _reader(proc: subprocess.Popen, q: queue.Queue[str | None]) -> None:
    try:
        assert proc.stdout is not None
        for line in proc.stdout: q.put(line)
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
                status = "stopped"; _terminate(proc, cb); rc = proc.poll(); break
            try: item = q.get(timeout=0.2)
            except queue.Empty: item = "__NO_LINE__"
            if item is None:
                stdout_done = True
            elif item != "__NO_LINE__":
                f.write(item); f.flush()
                if item.rstrip(): _emit(cb, "END-003", item.rstrip())
            rc = proc.poll()
            if rc is not None and stdout_done:
                status = "completed" if rc == 0 else "failed"; break
        while True:
            try: item = q.get_nowait()
            except queue.Empty: break
            if item:
                f.write(item); f.flush()
                if item.rstrip(): _emit(cb, "END-003", item.rstrip())
    return status, rc


def run_end003(
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
    output_path = Path(output_dir); output_path.mkdir(parents=True, exist_ok=True)
    product_dir, results_dir = ensure_module_output_layout(output_path, "END-003")
    if module_product_output_dir:
        product_dir = Path(module_product_output_dir); product_dir.mkdir(parents=True, exist_ok=True)
    if module_results_dir:
        results_dir = Path(module_results_dir); results_dir.mkdir(parents=True, exist_ok=True)
    star_payload = load_json(input_path)

    end001_csv = upstream_product(star_payload, "constellation_output")
    config = build_end003_config(star_payload)
    if end001_csv:
        config.setdefault("star_runtime", {})["end001_output_csv"] = str(end001_csv)

    # END-003 screens every satellite of the END-001 constellation and selects
    # the imaging pass (END-007) and the night light-curve pass (END-010).
    constellation, constellation_epoch = load_end001_constellation(end001_csv)
    if constellation:
        config["constellation"] = constellation
        if constellation_epoch and str(config.get("sim_start_date", "")).strip() != constellation_epoch:
            # RAAN / true anomaly are defined at END-001's epoch: propagate from there.
            _emit(log_callback, "EXECUTION", f"END-003: sim_start_date aligned to the END-001 epoch {constellation_epoch} (was {config.get('sim_start_date')}).")
            config["sim_start_date"] = constellation_epoch
        _emit(log_callback, "EXECUTION", f"END-003: {len(constellation)} satellite(s) loaded from END-001 for pass selection.")
    process_info_path = output_path / "end003_process_result.json"
    # The STAR version of END-003 takes the orbits from END-001 and does not propagate them.
    ephemerides = _end001_ephemerides(star_payload)
    if not ephemerides:
        reason = ("END-003 needs the END-001 ephemerides (satellite_NN_ephemeris.csv next to constellation_optimizer_output.csv): "
                  "run END-001 in the same workflow first." + ("" if end001_csv else " No END-001 constellation CSV was found upstream."))
        _emit(log_callback, "ERROR", reason)
        write_json(process_info_path, {"run_id": run_id, "status": "failed", "reason": reason})
        return {"status": "failed", "evidence": reason, "generated_artifacts": _collect(output_path)}
    config["end001_ephemeris"] = ephemerides
    # The passes are chosen by END-001 (2026-10-17): imaging pass over the AOI and
    # first night pass from the observatory; END-003 computes the attitude on them.
    pass_selection = upstream_product(star_payload, "pass_selection")
    if not pass_selection or not pass_selection.exists():
        reason = ("END-003 needs the passes selected by END-001 (product pass_selection, pass_selection.json): "
                  "run END-001 in the same workflow first.")
        _emit(log_callback, "ERROR", reason)
        write_json(process_info_path, {"run_id": run_id, "status": "failed", "reason": reason})
        return {"status": "failed", "evidence": reason, "generated_artifacts": _collect(output_path)}
    config["end001_pass_selection"] = str(pass_selection)
    stations = _end001_ground_stations(star_payload)
    if stations:
        config["ground_stations"] = stations
    config.pop("target_selection", None)
    if constellation:
        first = constellation[0]
        config["orbit"] = {k: first[k] for k in ("alt_perigee_m", "alt_apogee_m", "inclination_deg", "raan_deg", "omega_deg", "nu_deg")}
    config.setdefault("env", {})["Re"] = 6378137.0          # reference of the END-001 altitudes (WGS84)
    decisions = _apply_star_inputs(config, star_payload)
    config.setdefault("star_runtime", {})["end003_inputs"] = decisions
    config["star_runtime"]["orbit_source"] = "END-001 ephemeris (no orbit propagation in END-003)"
    config["pass_selection"] = merge_pass_selection_defaults(config.get("pass_selection"))
    config_path = output_path / "end003_runtime_input.json"
    write_json(config_path, config)
    _emit(log_callback, "EXECUTION", f"END-003: orbits from {len(ephemerides)} END-001 ephemeris file(s); attitude mode "
          f"{config['sat'].get('attitude_mode')} ({decisions['attitude_mode']['source']}); passes selected by END-001 "
          f"({pass_selection.name}).")

    folder = _find_dir()
    script = _find_script(folder)
    stdout_path = output_path / "matlab_stdout.txt"
    stderr_path = output_path / "matlab_stderr.txt"
    invocation_path = output_path / "end003_runner_invocation.json"
    started_at = datetime.now().isoformat(); started_perf = time.perf_counter()
    matlab = os.environ.get("MATLAB_EXECUTABLE", "matlab")
    command = f"cd('{_quote(folder)}'); {script.stem}('{_quote(config_path)}', '{_quote(output_path)}');"
    write_json(invocation_path, {"run_id": run_id, "started_at": started_at, "star_input_file": str(input_path), "runtime_input_file": str(config_path), "matlab_function": str(script), "output_dir": str(output_path), "product_output_dir": str(product_dir), "results_output_dir": str(results_dir), "end001_output_csv": str(end001_csv) if end001_csv else None, "matlab_command": command})

    if stop_event is not None and stop_event.is_set():
        write_json(process_info_path, {"run_id": run_id, "status": "stopped", "reason": "Stop requested before MATLAB launch."})
        return {"status": "stopped", "evidence": "END-003 stopped before MATLAB launch.", "generated_artifacts": _collect(output_path)}

    env = os.environ.copy()
    env.update({
        "STAR_END003_INPUT_FILE": str(config_path),
        "STAR_END003_OUTPUT_DIR": str(output_path),
        "STAR_END003_PRODUCT_OUTPUT_DIR": str(product_dir),
        "STAR_END003_RESULTS_DIR": str(results_dir),
        "STAR_MODULE_OUTPUT_DIR": str(output_path),
        "STAR_MODULE_PRODUCT_OUTPUT_DIR": str(product_dir),
        "STAR_MODULE_RESULTS_DIR": str(results_dir),
        "STAR_MODULE_INPUT_FILE": str(input_path),
    })
    if end001_csv:
        env["STAR_END001_OUTPUT_CSV"] = str(end001_csv)
        env["STAR_CONSTELLATION_OPTIMIZER_OUTPUT_CSV"] = str(end001_csv)

    _emit(log_callback, "EXECUTION", f"END-003 Attitude Propagation started. MATLAB: {matlab}")
    _emit(log_callback, "EXECUTION", f"END-003 runtime config: {config_path}")
    _emit(log_callback, "EXECUTION", f"END-003 output directory: {output_path}")
    proc = subprocess.Popen([matlab, "-batch", command], cwd=str(folder), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform.startswith("win") else 0)
    _emit(log_callback, "EXECUTION", f"END-003 MATLAB process started with PID={proc.pid}.")
    status, rc = _run_process(proc, stdout_path, log_callback, stop_event)
    stderr_path.write_text("", encoding="utf-8")
    duration = time.perf_counter() - started_perf

    if status == "failed":
        reason = f"MATLAB END-003 failed with return code {rc}. See {stdout_path}."
        _emit(log_callback, "ERROR", reason)

    normalize_direct_module_outputs(output_path, product_dir, results_dir, keep_names={"end003_runner_invocation.json", "end003_runtime_input.json", "star_attitude_propagation_runtime.m", "matlab_stdout.txt", "matlab_stderr.txt", "end003_process_result.json", "upstream_artifacts.json"}, log_callback=log_callback, module_label="END-003")
    artifacts = _collect(output_path)
    write_json(process_info_path, {"run_id": run_id, "started_at": started_at, "completed_at": datetime.now().isoformat(), "duration_seconds": round(duration, 3), "duration_human": _duration(duration), "return_code": rc, "status": status, "stdout_file": str(stdout_path), "stderr_file": str(stderr_path), "pid": proc.pid})
    _emit(log_callback, "EXECUTION", f"END-003 finished with status={status}. Execution time: {_duration(duration)} ({duration:.2f} s).")
    if status == "completed":
        _write_orbit_and_window(config, product_dir, load_selected_passes(None, product_dir / "output_attitude_propagation.csv"))
        selected = load_selected_passes(None, product_dir / "output_attitude_propagation.csv")
        if selected:
            _emit(log_callback, "EXECUTION", "END-003 selected imaging pass (END-007, daylight): " + describe_pass(selected.get("imaging_pass")))
            _emit(log_callback, "EXECUTION", "END-003 selected light-curve pass (END-010, night): " + describe_pass(selected.get("lightcurve_pass")))
        else:
            _emit(log_callback, "WARNING", "END-003 did not publish selected_passes.json.")
    if status == "stopped":
        return {"status": "stopped", "evidence": "END-003 stopped by user request.", "generated_artifacts": artifacts, "return_code": rc}
    if status != "completed":
        return {"status": "failed", "evidence": f"END-003 MATLAB attitude propagation failed. See {stdout_path}.", "generated_artifacts": artifacts, "return_code": rc}
    write_module_kpis("END-003", output_path, run_id, log=lambda lvl, msg: _emit(log_callback, lvl, msg))
    prov = from_runtime_decisions("END-003", config, "end003_inputs")
    final_status, severity = finalize(status, prov)
    n_ecl = len(ephemerides)
    facts = (f"END-003 attitude propagation ({config['sat'].get('attitude_mode')}) on {n_ecl} END-001 ephemeris file(s), "
             f"passes from END-001 pass_selection; mass/inertia from {decisions['spacecraft']['source'].split(' (')[0]}")
    return {"status": final_status, "fallback_severity": severity, "fallbacks": prov.fallbacks(), "provenance": prov.to_json(final_status),
            "evidence": star_evidence("END-003", final_status, prov, facts), "generated_artifacts": artifacts, "return_code": rc}

from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from runners.star_runner_io import (
    build_end010_config,
    describe_pass,
    ensure_module_output_layout,
    find_upstream_artifact,
    load_json,
    load_selected_passes,
    normalize_direct_module_outputs,
    write_json,
)

STAR_ROOT = Path(__file__).resolve().parents[2]
END010_DIR = STAR_ROOT / "END010-ReflectanceDetermination"
END010_SCRIPT = END010_DIR / "star_reflectance_determination.m"
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



def _prepare_runtime_script(source: Path, runtime: Path, config: Path, output_folder: Path) -> None:
    text = source.read_text(encoding="utf-8", errors="replace")
    text = re.sub(r"set\(0,\s*DefaultFigureVisible\s*,\s*off\s*\);", "set(0, 'DefaultFigureVisible', 'off');", text)
    text = re.sub(r"(?m)^\s*file_input\s*=\s*.*?;\s*$", f"file_input = '{_quote(config)}';", text, count=1)
    text = re.sub(r"(?m)^\s*path_output\s*=\s*.*?;\s*$", f"path_output = '{_quote(output_folder)}';", text, count=1)
    runtime.parent.mkdir(parents=True, exist_ok=True)
    runtime.write_text(text, encoding="utf-8")

def _terminate(proc: subprocess.Popen, cb: LogCallback | None) -> None:
    if proc.poll() is not None: return
    _emit(cb, "EXECUTION", f"Stop requested. Terminating END-010 MATLAB process tree. PID={proc.pid}")
    if sys.platform.startswith("win"):
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        proc.terminate(); proc.wait(timeout=8)
    except Exception:
        try: proc.kill(); proc.wait(timeout=8)
        except Exception: pass


def _run_process(proc: subprocess.Popen, stdout_path: Path, cb: LogCallback | None, stop_event: threading.Event | None) -> tuple[str, int | None]:
    status, rc = "running", None
    assert proc.stdout is not None
    with stdout_path.open("w", encoding="utf-8", errors="replace") as f:
        while True:
            if stop_event is not None and stop_event.is_set():
                status = "stopped"; _terminate(proc, cb); rc = proc.poll(); break
            line = proc.stdout.readline()
            if line:
                f.write(line); f.flush()
                if line.rstrip(): _emit(cb, "END-010", line.rstrip())
                continue
            rc = proc.poll()
            if rc is not None:
                status = "completed" if rc == 0 else "failed"; break
            time.sleep(0.2)
        try: rest = proc.stdout.read() or ""
        except Exception: rest = ""
        if rest:
            f.write(rest); f.flush()
            for line in rest.splitlines():
                if line.strip(): _emit(cb, "END-010", line.strip())
    return status, rc


def run_end010(
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
    product_dir, results_dir = ensure_module_output_layout(output_path, "END-010")
    if module_product_output_dir:
        product_dir = Path(module_product_output_dir); product_dir.mkdir(parents=True, exist_ok=True)
    if module_results_dir:
        results_dir = Path(module_results_dir); results_dir.mkdir(parents=True, exist_ok=True)
    star_payload = load_json(input_path)
    root = Path(star_root) if star_root else STAR_ROOT
    # END-003 exports three CSV flavors of the same pass: output_attitude_propagation_ECI.csv
    # (true right-handed ECI, X/Y/Z as propagated), output_attitude_propagation_Unity.csv
    # (Unity left-handed Y-up axes), and output_attitude_propagation.csv (Unreal Engine
    # left-handed Z-up axes, Y negated in the legacy END-003 -- see the "MULTI-ENGINE CSV EXPORT"
    # section of END003-AttitudePropagation/_old/star_attitude_propagation.m; the STAR version keeps
    # the ECI position). END-010's MATLAB pipeline reads eci_x/y/z_km as plain ECI and
    # does its own Unity-axis conversion internally, so it must consume the _ECI file --
    # consuming the base-name file (the Unreal-flavored, Y-flipped one) silently corrupts
    # every downstream geometry/visibility computation (elevation, range, phase angle).
    end003_csv = (
        find_upstream_artifact(star_payload, ["output_attitude_propagation_eci.csv"], [".csv"])
        or find_upstream_artifact(star_payload, ["output_attitude_propagation_eci"], [".csv"])
        or find_upstream_artifact(star_payload, ["output_attitude_propagation.csv"], [".csv"])
        or find_upstream_artifact(star_payload, ["output_attitude_propagation"], [".csv"])
        or find_upstream_artifact(star_payload, ["attitude"], [".csv"])
    )
    end001_csv = find_upstream_artifact(star_payload, ["constellation_optimizer_output"], [".csv"]) or find_upstream_artifact(star_payload, ["constellation"], [".csv"])
    # END-003 publishes a dedicated night pass visible from the light-curve
    # observer (Matera): when available it replaces the daylight imaging pass
    # above as END-010's ephemeris (a light curve needs a dark observer and a
    # sunlit satellite, the opposite of the END-007 imaging geometry).
    selected_passes = load_selected_passes(star_payload, end003_csv)
    lightcurve_pass = (selected_passes or {}).get("lightcurve_pass") or {}
    if lightcurve_pass.get("found"):
        _emit(log_callback, "EXECUTION", "END-010 will simulate the END-003 selected night pass: " + describe_pass(lightcurve_pass))
    elif selected_passes is not None:
        _emit(log_callback, "WARNING", "END-010: END-003 found no sunlit night pass for the observer; using the END-003 imaging pass ephemeris instead.")
    config_path = output_path / "end010_runtime_input.json"
    write_json(config_path, build_end010_config(star_payload, product_dir, results_dir, end003_csv, root, selected_passes))
    stdout_path = output_path / "matlab_stdout.txt"
    stderr_path = output_path / "matlab_stderr.txt"
    process_info_path = output_path / "end010_process_result.json"
    runtime_script = output_path / "star_reflectance_determination_runtime.m"
    invocation_path = output_path / "end010_runner_invocation.json"
    started_at = datetime.now().isoformat(); started_perf = time.perf_counter()
    matlab = os.environ.get("MATLAB_EXECUTABLE", "matlab")

    if not END010_SCRIPT.exists():
        reason = f"END-010 MATLAB script not found: {END010_SCRIPT}"
        write_json(process_info_path, {"run_id": run_id, "status": "failed", "reason": reason})
        return {"status": "failed", "evidence": reason, "generated_artifacts": _collect(output_path)}

    _prepare_runtime_script(END010_SCRIPT, runtime_script, config_path, output_path)
    command = f"cd('{_quote(END010_DIR)}'); run('{_quote(runtime_script)}');"
    write_json(invocation_path, {"run_id": run_id, "started_at": started_at, "star_input_file": str(input_path), "runtime_input_file": str(config_path), "runtime_matlab_file": str(runtime_script), "output_dir": str(output_path), "product_output_dir": str(product_dir), "results_output_dir": str(results_dir), "end003_output_csv": str(end003_csv) if end003_csv else None, "end001_output_csv": str(end001_csv) if end001_csv else None, "matlab_command": command})
    if stop_event is not None and stop_event.is_set():
        write_json(process_info_path, {"run_id": run_id, "status": "stopped", "reason": "Stop requested before MATLAB launch."})
        return {"status": "stopped", "evidence": "END-010 stopped before MATLAB launch.", "generated_artifacts": _collect(output_path)}

    env = os.environ.copy()
    env.update({
        "STAR_END010_INPUT_FILE": str(config_path),
        "STAR_END010_OUTPUT_DIR": str(output_path),
        "STAR_END010_PRODUCT_OUTPUT_DIR": str(product_dir),
        "STAR_END010_RESULTS_DIR": str(results_dir),
        # END-010 must load MATLAB helper functions and data from the real
        # module installation folder, not from the per-run output folder where
        # the temporary runtime script is written.  The MATLAB file reads this
        # variable before adding lib/, lib/data, lib/sgp4 and BuildAqua to path.
        "STAR_END010_MAIN_FOLDER": str(END010_DIR),
        "STAR_MODULE_OUTPUT_DIR": str(output_path),
        "STAR_MODULE_PRODUCT_OUTPUT_DIR": str(product_dir),
        "STAR_MODULE_RESULTS_DIR": str(results_dir),
        "STAR_MODULE_INPUT_FILE": str(input_path),
    })
    if end003_csv:
        env["STAR_END003_OUTPUT_CSV"] = str(end003_csv)
        env["STAR_ATTITUDE_PROPAGATION_OUTPUT_CSV"] = str(end003_csv)
    if end001_csv:
        env["STAR_END001_OUTPUT_CSV"] = str(end001_csv)
        env["STAR_CONSTELLATION_OPTIMIZER_OUTPUT_CSV"] = str(end001_csv)

    _emit(log_callback, "EXECUTION", f"END-010 Reflectance Determination started. MATLAB: {matlab}")
    _emit(log_callback, "EXECUTION", f"END-010 runtime config: {config_path}")
    _emit(log_callback, "EXECUTION", f"END-010 output directory: {output_path}")
    proc = subprocess.Popen([matlab, "-batch", command], cwd=str(END010_DIR), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform.startswith("win") else 0)
    _emit(log_callback, "EXECUTION", f"END-010 MATLAB process started with PID={proc.pid}.")
    status, rc = _run_process(proc, stdout_path, log_callback, stop_event)
    stderr_path.write_text("", encoding="utf-8")
    duration = time.perf_counter() - started_perf

    if status == "failed":
        reason = f"MATLAB END-010 failed with return code {rc}. See {stdout_path}."
        _emit(log_callback, "ERROR", reason)

    normalize_direct_module_outputs(output_path, product_dir, results_dir, keep_names={"end010_runner_invocation.json", "end010_runtime_input.json", "star_reflectance_determination_runtime.m", "matlab_stdout.txt", "matlab_stderr.txt", "end010_process_result.json", "upstream_artifacts.json"}, log_callback=log_callback, module_label="END-010")
    artifacts = _collect(output_path)
    write_json(process_info_path, {"run_id": run_id, "started_at": started_at, "completed_at": datetime.now().isoformat(), "duration_seconds": round(duration, 3), "duration_human": _duration(duration), "return_code": rc, "status": status, "stdout_file": str(stdout_path), "stderr_file": str(stderr_path), "pid": proc.pid})
    _emit(log_callback, "EXECUTION", f"END-010 finished with status={status}. Execution time: {_duration(duration)} ({duration:.2f} s).")
    if status == "stopped":
        return {"status": "stopped", "evidence": "END-010 stopped by user request.", "generated_artifacts": artifacts, "return_code": rc}
    if status != "completed":
        return {"status": "failed", "evidence": f"END-010 MATLAB reflectance determination failed. See {stdout_path}.", "generated_artifacts": artifacts, "return_code": rc}
    return {"status": "completed", "evidence": "END-010 MATLAB reflectance determination executed successfully.", "generated_artifacts": artifacts, "return_code": rc}

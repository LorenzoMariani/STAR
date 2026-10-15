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
    describe_pass,
    ensure_module_output_layout,
    find_upstream_artifact,
    load_end001_constellation,
    load_json,
    load_selected_passes,
    merge_pass_selection_defaults,
    normalize_direct_module_outputs,
    write_json,
)

STAR_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_END003_DIR = STAR_ROOT / "END003-AttitudePropagation"
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
    env = os.environ.get("STAR_END003_SCRIPT", "").strip()
    if env and Path(env).exists(): return Path(env)
    for p in [folder / "star_attitude_propagation.m", folder / "star_attitude_propagator.m"]:
        if p.exists(): return p
    hits = sorted(folder.rglob("*attitude*propagation*.m"))
    if hits: return hits[0]
    raise FileNotFoundError(f"END-003 MATLAB script not found in {folder}")


def _prepare_runtime_script(source: Path, runtime: Path, config: Path, output_folder: Path) -> None:
    text = source.read_text(encoding="utf-8", errors="replace")
    text = re.sub(r"set\(0,\s*DefaultFigureVisible\s*,\s*off\s*\);", "set(0, 'DefaultFigureVisible', 'off');", text)
    if "DefaultFigureVisible" not in text:
        text = re.sub(r"(?m)^(\s*clear\s*;\s*clc\s*;\s*close all\s*;\s*)$", r"\1\nset(0, 'DefaultFigureVisible', 'off');", text, count=1)
    text = re.sub(r"(?m)^\s*file_input\s*=\s*.*?;\s*$", f"file_input = '{_quote(config)}';", text, count=1)
    text = re.sub(r"(?m)^\s*path_output\s*=\s*.*?;\s*$", f"path_output = '{_quote(output_folder)}';", text, count=1)
    text = re.sub(r"\bsaveas\s*\(", "star_save_png(", text)
    if "function star_save_png(" not in text:
        text += """

function star_save_png(fig_handle, file_path)
    try
        drawnow;
        exportgraphics(fig_handle, file_path, 'Resolution', 200);
    catch
        try
            print(fig_handle, file_path, '-dpng', '-r200');
        catch save_error
            warning('STAR:PNGSaveFailed', 'Could not save PNG %s: %s', file_path, save_error.message);
        end
    end
end
"""
    runtime.parent.mkdir(parents=True, exist_ok=True)
    runtime.write_text(text, encoding="utf-8")


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

    end001_csv = find_upstream_artifact(star_payload, ["constellation_optimizer_output"], [".csv"]) or find_upstream_artifact(star_payload, ["constellation"], [".csv"])
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
    else:
        _emit(log_callback, "WARNING", "END-003: no END-001 constellation CSV found; screening only the orbit of the END-003 input template.")
    config["pass_selection"] = merge_pass_selection_defaults(config.get("pass_selection"))
    config_path = output_path / "end003_runtime_input.json"
    write_json(config_path, config)

    folder = _find_dir()
    script = _find_script(folder)
    runtime_script = output_path / "star_attitude_propagation_runtime.m"
    stdout_path = output_path / "matlab_stdout.txt"
    stderr_path = output_path / "matlab_stderr.txt"
    process_info_path = output_path / "end003_process_result.json"
    invocation_path = output_path / "end003_runner_invocation.json"
    started_at = datetime.now().isoformat(); started_perf = time.perf_counter()
    matlab = os.environ.get("MATLAB_EXECUTABLE", "matlab")
    _prepare_runtime_script(script, runtime_script, config_path, output_path)
    command = f"cd('{_quote(folder)}'); run('{_quote(runtime_script)}');"
    write_json(invocation_path, {"run_id": run_id, "started_at": started_at, "star_input_file": str(input_path), "runtime_input_file": str(config_path), "runtime_matlab_file": str(runtime_script), "output_dir": str(output_path), "product_output_dir": str(product_dir), "results_output_dir": str(results_dir), "end001_output_csv": str(end001_csv) if end001_csv else None, "matlab_command": command})

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
    return {"status": "completed", "evidence": "END-003 MATLAB attitude propagation executed successfully and generated output_attitude_propagation.csv.", "generated_artifacts": artifacts, "return_code": rc}

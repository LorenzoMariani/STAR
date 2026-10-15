from __future__ import annotations

import json
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
    build_end001_config,
    ensure_module_output_layout,
    load_json,
    move_result_files_from_product,
    normalize_direct_module_outputs,
    write_json,
)

STAR_ROOT = Path(__file__).resolve().parents[2]
END001_DIR = STAR_ROOT / "END001-ConstellationOptimizer"
END001_SCRIPT = END001_DIR / "lib" / "star_constellation_optimizer.m"   # in lib/ since 2026-10-15
LogCallback = Callable[[str, str], Any]


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
    m, s = divmod(seconds, 60)
    return f"{int(m)} min {s:.1f} s"


def _collect(path: Path) -> list[str]:
    return [str(p) for p in sorted(path.rglob("*")) if p.is_file()] if path.exists() else []


def _prepare_runtime_script(source: Path, runtime: Path, config: Path, output_folder: Path) -> None:
    text = source.read_text(encoding="utf-8", errors="replace")
    text = re.sub(r"set\(0,\s*DefaultFigureVisible\s*,\s*off\s*\);", "set(0, 'DefaultFigureVisible', 'off');", text)
    if "DefaultFigureVisible" not in text:
        text = re.sub(r"(?m)^(\s*clear\s*;\s*clc\s*;\s*close all\s*;\s*)$", r"\1\nset(0, 'DefaultFigureVisible', 'off');", text, count=1)
    text = re.sub(r"(?m)^\s*file_input\s*=\s*.*?;\s*$", f"file_input = '{_quote(config)}';", text, count=1)
    text = re.sub(r"(?m)^\s*path_output\s*=\s*.*?;\s*$", f"path_output = '{_quote(output_folder)}';", text, count=1)
    runtime.parent.mkdir(parents=True, exist_ok=True)
    runtime.write_text(text, encoding="utf-8")


def _terminate(proc: subprocess.Popen, cb: LogCallback | None) -> None:
    if proc.poll() is not None:
        return
    _emit(cb, "EXECUTION", f"Stop requested. Terminating END-001 MATLAB process tree. PID={proc.pid}")
    if sys.platform.startswith("win"):
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        proc.terminate()
        proc.wait(timeout=8)
    except Exception:
        try:
            proc.kill(); proc.wait(timeout=8)
        except Exception:
            pass


def _run_process(proc: subprocess.Popen, stdout_path: Path, cb: LogCallback | None, stop_event: threading.Event | None) -> tuple[str, int | None]:
    status = "running"
    rc: int | None = None
    assert proc.stdout is not None
    with stdout_path.open("w", encoding="utf-8", errors="replace") as f:
        while True:
            if stop_event is not None and stop_event.is_set():
                status = "stopped"
                _terminate(proc, cb)
                rc = proc.poll()
                break
            line = proc.stdout.readline()
            if line:
                f.write(line); f.flush()
                clean = line.rstrip()
                if clean:
                    _emit(cb, "END-001", clean)
                continue
            rc = proc.poll()
            if rc is not None:
                status = "completed" if rc == 0 else "failed"
                break
            time.sleep(0.2)
        try:
            rest = proc.stdout.read() or ""
        except Exception:
            rest = ""
        if rest:
            f.write(rest); f.flush()
            for line in rest.splitlines():
                if line.strip():
                    _emit(cb, "END-001", line.strip())
    return status, rc


def run_end001(
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
    product_dir, results_dir = ensure_module_output_layout(output_path, "END-001")
    if module_product_output_dir:
        product_dir = Path(module_product_output_dir); product_dir.mkdir(parents=True, exist_ok=True)
    if module_results_dir:
        results_dir = Path(module_results_dir); results_dir.mkdir(parents=True, exist_ok=True)

    star_payload = load_json(input_path)
    config_path = output_path / "end001_runtime_input.json"
    write_json(config_path, build_end001_config(star_payload))
    runtime_script = output_path / "star_constellation_optimizer_runtime.m"
    stdout_path = output_path / "matlab_stdout.txt"
    stderr_path = output_path / "matlab_stderr.txt"
    process_info_path = output_path / "end001_process_result.json"
    invocation_path = output_path / "end001_runner_invocation.json"
    started_at = datetime.now().isoformat()
    started_perf = time.perf_counter()
    matlab = os.environ.get("MATLAB_EXECUTABLE", "matlab")

    if not END001_SCRIPT.exists():
        reason = f"END-001 MATLAB script not found: {END001_SCRIPT}"
        write_json(process_info_path, {"run_id": run_id, "status": "failed", "reason": reason, "started_at": started_at, "completed_at": datetime.now().isoformat()})
        return {"status": "failed", "evidence": reason, "generated_artifacts": _collect(output_path)}

    _prepare_runtime_script(END001_SCRIPT, runtime_script, config_path, product_dir)
    command = f"cd('{_quote(END001_DIR)}'); run('{_quote(runtime_script)}');"
    write_json(invocation_path, {
        "run_id": run_id,
        "started_at": started_at,
        "star_input_file": str(input_path),
        "runtime_input_file": str(config_path),
        "runtime_matlab_file": str(runtime_script),
        "output_dir": str(output_path),
        "product_output_dir": str(product_dir),
        "results_output_dir": str(results_dir),
        "matlab_command": command,
    })

    if stop_event is not None and stop_event.is_set():
        write_json(process_info_path, {"run_id": run_id, "status": "stopped", "reason": "Stop requested before MATLAB launch."})
        return {"status": "stopped", "evidence": "END-001 stopped before MATLAB launch.", "generated_artifacts": _collect(output_path)}

    env = os.environ.copy()
    env.update({
        "STAR_END001_INPUT_FILE": str(config_path),
        "STAR_END001_OUTPUT_DIR": str(output_path),
        "STAR_END001_PRODUCT_OUTPUT_DIR": str(product_dir),
        "STAR_END001_RESULTS_DIR": str(results_dir),
        # END-001 must load MATLAB helper functions (lib/, lib/FUNCTIONS/...)
        # from the real module installation folder, not from the per-run
        # output folder where the temporary runtime script is written.
        "STAR_END001_MAIN_FOLDER": str(END001_DIR),
        "STAR_MODULE_OUTPUT_DIR": str(output_path),
        "STAR_MODULE_PRODUCT_OUTPUT_DIR": str(product_dir),
        "STAR_MODULE_RESULTS_DIR": str(results_dir),
        "STAR_MODULE_INPUT_FILE": str(input_path),
    })
    if modules_output_root or star_payload.get("modules_output_root"):
        env["STAR_MODULES_OUTPUT_ROOT"] = str(modules_output_root or star_payload.get("modules_output_root"))

    _emit(log_callback, "EXECUTION", f"END-001 Constellation Optimizer started. MATLAB: {matlab}")
    _emit(log_callback, "EXECUTION", f"END-001 runtime config: {config_path}")
    _emit(log_callback, "EXECUTION", f"END-001 product output folder: {product_dir}")
    proc = subprocess.Popen([matlab, "-batch", command], cwd=str(END001_DIR), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform.startswith("win") else 0)
    _emit(log_callback, "EXECUTION", f"END-001 MATLAB process started with PID={proc.pid}.")
    status, rc = _run_process(proc, stdout_path, log_callback, stop_event)
    stderr_path.write_text("", encoding="utf-8")
    duration = time.perf_counter() - started_perf

    move_result_files_from_product(product_dir, results_dir)
    if status == "completed":
        csv_path = product_dir / "constellation_optimizer_output.csv"
        if not csv_path.exists():
            status = "failed"
            _emit(log_callback, "ERROR", f"END-001 completed but did not generate required CSV: {csv_path}")
    elif status == "failed":
        reason = f"MATLAB END-001 failed with return code {rc}. See {stdout_path}."
        _emit(log_callback, "ERROR", reason)

    normalize_direct_module_outputs(output_path, product_dir, results_dir, keep_names={"end001_runner_invocation.json", "end001_runtime_input.json", "star_constellation_optimizer_runtime.m", "matlab_stdout.txt", "matlab_stderr.txt", "end001_process_result.json"}, log_callback=log_callback, module_label="END-001")
    artifacts = _collect(output_path)
    completed_at = datetime.now().isoformat()
    write_json(process_info_path, {"run_id": run_id, "started_at": started_at, "completed_at": completed_at, "duration_seconds": round(duration, 3), "duration_human": _duration(duration), "return_code": rc, "status": status, "stdout_file": str(stdout_path), "stderr_file": str(stderr_path), "pid": proc.pid})
    _emit(log_callback, "EXECUTION", f"END-001 finished with status={status}. Execution time: {_duration(duration)} ({duration:.2f} s).")

    if status == "stopped":
        return {"status": "stopped", "evidence": "END-001 stopped by user request.", "generated_artifacts": artifacts, "return_code": rc}
    if status != "completed":
        return {"status": "failed", "evidence": f"END-001 MATLAB constellation optimizer failed. See {stdout_path}.", "generated_artifacts": artifacts, "return_code": rc}
    return {"status": "completed", "evidence": "END-001 MATLAB constellation optimizer executed successfully and generated constellation_optimizer_output.csv.", "generated_artifacts": artifacts, "return_code": rc}

from __future__ import annotations

import json
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
    ensure_module_output_layout,
    find_upstream_artifact,
    load_json,
    make_runtime_input_copy,
    normalize_direct_module_outputs,
    write_json,
)

STAR_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_END004_DIR = STAR_ROOT / "END004-PowerBudget"
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
    write_json(runtime_input, runtime_data)

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

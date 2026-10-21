"""
Runner adapter for STAR END-007 Synthetic Data Generation.

This runner connects STAR to the real END-007 simulation launcher located in:

    END007-SyntheticDataGeneration/run_simulation.py

The END-007 script is treated as the source of truth for simulation inputs.
CSV paths, FOV and Unreal paths are expected to be defined directly inside
run_simulation.py unless that script is later extended to accept them as
arguments.

Supported STAR runtime features:
- detailed technical-log messages through log_callback(level, message);
- cooperative Stop Execution through stop_event;
- process termination for Unreal if the user presses Stop while Unreal is still
  running;
- artifact traceability in the STAR run output folder.

Important:
- To avoid Unreal's external log window, run_simulation.py should launch Unreal
  without the -log flag and should use -stdout -FullStdOutLogOutput -UTF8Output.
- This runner can read process stdout/stderr only if run_simulation.py creates
  the subprocess with stdout=subprocess.PIPE and stderr redirected or piped.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import os
import re
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
    describe_pass,
    ensure_module_output_layout,
    upstream_product,
    load_selected_passes,
    normalize_direct_module_outputs,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Exact project structure expected for END-007.
# END007_DIR = PROJECT_ROOT / "external_modules" / "END007-SyntheticDataGeneration"
END007_DIR = PROJECT_ROOT / "END007-SyntheticDataGeneration"
END007_SCRIPT = END007_DIR / "run_simulation.py"

LogCallback = Callable[[str, str], Any]


# ---------------------------------------------------------------------------
# General helpers
# ---------------------------------------------------------------------------
def _emit(log_callback: LogCallback | None, level: str, message: str) -> None:
    """Safely emit one line to STAR's technical log."""
    if log_callback is None:
        return
    try:
        log_callback(level, message)
    except Exception:
        # Logging must never break module execution.
        pass


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=4), encoding="utf-8")


def _safe_relative(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return str(path)


def _classify_unreal_log_line(line: str) -> str:
    lowered = line.lower()
    if "fatal error" in lowered or "assertion failed" in lowered:
        return "ERROR"
    if " error:" in lowered or lowered.startswith("error:") or "logwindows: error" in lowered:
        return "ERROR"
    if " warning:" in lowered or "warning:" in lowered:
        return "WARNING"
    if "logblueprintusermessages" in lowered:
        return "UNREAL"
    return "UNREAL"


def _format_duration(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    if seconds < 1.0:
        return f"{seconds * 1000:.0f} ms"
    if seconds < 60.0:
        return f"{seconds:.2f} s"
    minutes, remaining = divmod(seconds, 60.0)
    if minutes < 60.0:
        return f"{int(minutes)} min {remaining:.1f} s"
    hours, minutes = divmod(minutes, 60.0)
    return f"{int(hours)} h {int(minutes)} min {remaining:.1f} s"


# ---------------------------------------------------------------------------
# END-007 script loading and invocation
# ---------------------------------------------------------------------------


def _matlab_like_quote(path: Path | str) -> str:
    return str(path).replace("\\", "/").replace("'", "''")

def _python_path_literal(path: Path | str) -> str:
    """Return a Python string literal safe for Windows paths in runtime copies."""
    return repr(str(path).replace("\\", "/"))


def _prepare_runtime_run_simulation(source_script: Path, runtime_script: Path, attitude_csv: Path | None, product_output_dir: Path, results_output_dir: Path) -> Path:
    """Create a runtime copy of run_simulation.py with STAR run paths injected.

    Some legacy versions of END-007 keep the attitude CSV path as a literal string
    inside run_simulation.py, so overriding module.CSV_INPUT after import is not
    sufficient. This runtime copy rewrites the common assignment patterns and any
    old STAR/Output/output_attitude_propagation literal.
    """
    text = source_script.read_text(encoding="utf-8", errors="replace")
    if attitude_csv is not None:
        csv_literal = _python_path_literal(attitude_csv)
        # Replace common global assignment patterns.
        patterns = [
            r"(?m)^\s*CSV_INPUT\s*=\s*.*$",
            r"(?m)^\s*CSV_PATH\s*=\s*.*$",
            r"(?m)^\s*INPUT_CSV\s*=\s*.*$",
            r"(?m)^\s*ATTITUDE_CSV\s*=\s*.*$",
        ]
        replacement_lines = {
            "CSV_INPUT": f"CSV_INPUT = Path({csv_literal})",
            "CSV_PATH": f"CSV_PATH = Path({csv_literal})",
            "INPUT_CSV": f"INPUT_CSV = Path({csv_literal})",
            "ATTITUDE_CSV": f"ATTITUDE_CSV = Path({csv_literal})",
        }
        for pattern in patterns:
            name = pattern.split('^\\s*')[1].split('\\s*')[0]
            text, n = re.subn(pattern, replacement_lines.get(name, f"{name} = Path({csv_literal})"), text, count=1)
        # Replace the historical hardcoded path wherever it appears as a string.
        text = re.sub(
            r"C:\\\\Users\\\\s5oss\\\\Desktop\\\\software_s5lab\\\\STAR\\\\Output\\\\output_attitude_propagation\\\\output_attitude_propagation\.csv",
            str(attitude_csv).replace('\\', '/'),
            text,
        )
        text = re.sub(
            r"C:/Users/s5oss/Desktop/software_s5lab/STAR/Output/output_attitude_propagation/output_attitude_propagation\.csv",
            str(attitude_csv).replace('\\', '/'),
            text,
        )
    out_literal = _python_path_literal(product_output_dir)
    text = re.sub(r"(?m)^\s*OUTPUT_DIR\s*=\s*.*$", f"OUTPUT_DIR = Path({out_literal})", text, count=1)

    # PROJECT_DIR must point at the real END-007 module installation (where the
    # .uproject actually lives), not at the per-run output folder where this
    # runtime copy is written, and not at any stale hardcoded dev-machine path.
    project_dir_literal = _python_path_literal(END007_DIR / "Unreal" / "EarthSim")
    text = re.sub(r"(?m)^\s*PROJECT_DIR\s*=\s*.*$", f"PROJECT_DIR = Path({project_dir_literal})", text, count=1)
    banner = (
        "# STAR runtime copy generated by end007_runner.py\n"
        "import os as _star_os\n"
        f"_star_os.environ['STAR_END007_PRODUCT_OUTPUT_DIR'] = {repr(str(product_output_dir))}\n"
        f"_star_os.environ['STAR_END007_RESULTS_DIR'] = {repr(str(results_output_dir))}\n"
    )
    runtime_script.parent.mkdir(parents=True, exist_ok=True)
    runtime_script.write_text(banner + "\n" + text, encoding="utf-8")
    return runtime_script

def _find_end007_script() -> Path:
    if END007_SCRIPT.exists():
        return END007_SCRIPT
    raise FileNotFoundError(
        "END-007 run_simulation.py not found at the expected path: "
        f"{END007_SCRIPT}"
    )


def _load_simulation_module(script_path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("star_end007_run_simulation", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load END-007 script from: {script_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _function_accepts_keyword(function: Any, keyword: str) -> bool:
    try:
        signature = inspect.signature(function)
    except (TypeError, ValueError):
        return False

    if keyword in signature.parameters:
        return True

    return any(
        parameter.kind == parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )


def _call_run_simulation(
    simulation_module: Any,
    log_callback: LogCallback | None = None,
    stop_event: threading.Event | None = None,
    extra_kwargs: dict[str, Any] | None = None,
) -> Any:
    if not hasattr(simulation_module, "run_simulation"):
        raise AttributeError("END-007 script does not define run_simulation().")

    run_simulation = simulation_module.run_simulation
    csv_input = getattr(simulation_module, "CSV_INPUT", None)
    fov_deg = getattr(simulation_module, "FOV_DEG", None)

    signature = inspect.signature(run_simulation)
    positional_parameters = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind
        in (parameter.POSITIONAL_ONLY, parameter.POSITIONAL_OR_KEYWORD)
    ]
    positional_count = len(positional_parameters)

    args: list[Any] = []
    if positional_count >= 1:
        if csv_input in (None, ""):
            raise ValueError(
                "run_simulation() requires a CSV path but CSV_INPUT is not defined "
                "in the END-007 script."
            )
        args.append(csv_input)

    if positional_count >= 2 and fov_deg not in (None, ""):
        args.append(float(fov_deg))

    kwargs: dict[str, Any] = {}
    if _function_accepts_keyword(run_simulation, "log_callback"):
        kwargs["log_callback"] = log_callback
    if _function_accepts_keyword(run_simulation, "stop_event"):
        kwargs["stop_event"] = stop_event
    for key, value in (extra_kwargs or {}).items():
        if _function_accepts_keyword(run_simulation, key):
            kwargs[key] = value

    return run_simulation(*args, **kwargs)


def _archive_config_if_available(simulation_module: Any, log_callback: LogCallback | None = None) -> None:
    archive_config = getattr(simulation_module, "archive_config", None)
    if not callable(archive_config):
        return

    _emit(log_callback, "EXECUTION", "Archiving END-007 autostart/config file.")
    try:
        archive_config()
    except shutil.SameFileError as exc:
        # Non-fatal: the config is already in the target folder.
        _emit(log_callback, "EXECUTION", f"END-007 config already archived; continuing. Details: {exc}")
    except FileNotFoundError as exc:
        # Non-fatal: Unreal/run_simulation may already have moved or deleted it.
        _emit(log_callback, "WARNING", f"END-007 config file not found during archive; continuing. Details: {exc}")


def _copy_script_outputs(
    simulation_module: Any,
    output_dir: Path,
    log_callback: LogCallback | None = None,
) -> list[str]:
    """Copy known outputs produced by run_simulation.py into STAR's product folder.

    Important:
    In the STAR runtime copy, run_simulation.py often has OUTPUT_DIR rewritten to
    the same folder used as product_output_dir. In that case copying would try to
    copy each file onto itself and Python raises SameFileError. Treat files that
    are already in destination_dir as generated artifacts and do not copy them.
    """
    generated: list[str] = []
    module_output_dir = Path(getattr(simulation_module, "OUTPUT_DIR", ""))

    if not module_output_dir.exists() or not module_output_dir.is_dir():
        _emit(
            log_callback,
            "WARNING",
            f"END-007 OUTPUT_DIR not found or not a folder: {module_output_dir}",
        )
        return generated

    destination_dir = Path(output_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)

    try:
        same_directory = module_output_dir.resolve() == destination_dir.resolve()
    except OSError:
        same_directory = False

    for source_path in sorted(module_output_dir.iterdir()):
        if not source_path.is_file():
            continue

        destination_path = destination_dir / source_path.name

        try:
            source_resolved = source_path.resolve()
            destination_resolved = destination_path.resolve()
        except OSError:
            source_resolved = source_path
            destination_resolved = destination_path

        if same_directory or source_resolved == destination_resolved:
            generated.append(str(source_path))
            _emit(
                log_callback,
                "EXECUTION",
                f"END-007 output already in product folder: {source_path.name}",
            )
            continue

        try:
            shutil.copy2(source_path, destination_path)
        except shutil.SameFileError:
            generated.append(str(destination_path))
            _emit(
                log_callback,
                "EXECUTION",
                f"END-007 output already copied: {source_path.name}",
            )
            continue

        generated.append(str(destination_path))
        _emit(log_callback, "EXECUTION", f"Copied END-007 output: {source_path.name}")

    if not generated:
        _emit(log_callback, "WARNING", f"No file outputs found in END-007 OUTPUT_DIR: {module_output_dir}")

    return generated


# ---------------------------------------------------------------------------
# Process handling, log streaming and stop support
# ---------------------------------------------------------------------------
def _reader_thread(
    stream: Any,
    stream_name: str,
    output_queue: queue.Queue[tuple[str, str]],
) -> None:
    try:
        for raw_line in iter(stream.readline, ""):
            if not raw_line:
                break
            output_queue.put((stream_name, raw_line.rstrip()))
    except Exception as exc:
        output_queue.put((stream_name, f"[reader error] {exc}"))
    finally:
        try:
            stream.close()
        except Exception:
            pass


def _start_process_log_readers(process: Any) -> queue.Queue[tuple[str, str]]:
    output_queue: queue.Queue[tuple[str, str]] = queue.Queue()

    stdout = getattr(process, "stdout", None)
    stderr = getattr(process, "stderr", None)

    if stdout is not None:
        threading.Thread(
            target=_reader_thread,
            args=(stdout, "stdout", output_queue),
            name="END007StdoutReader",
            daemon=True,
        ).start()

    if stderr is not None and stderr is not stdout:
        threading.Thread(
            target=_reader_thread,
            args=(stderr, "stderr", output_queue),
            name="END007StderrReader",
            daemon=True,
        ).start()

    return output_queue


def _terminate_process_tree(process: Any, log_callback: LogCallback | None = None) -> None:
    """Terminate Unreal as reliably as possible after a STAR stop request."""
    if process is None or not hasattr(process, "poll"):
        return

    if process.poll() is not None:
        return

    pid = getattr(process, "pid", None)
    _emit(log_callback, "EXECUTION", f"Stop requested. Terminating END-007 process tree. PID={pid}")

    if sys.platform.startswith("win") and pid is not None:
        # /T kills child processes; /F forces termination if graceful shutdown fails.
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception as exc:
            _emit(log_callback, "WARNING", f"taskkill failed for END-007 process: {exc}")

    try:
        process.terminate()
    except Exception:
        pass

    try:
        process.wait(timeout=10)
    except Exception:
        try:
            process.kill()
            process.wait(timeout=10)
        except Exception as exc:
            _emit(log_callback, "WARNING", f"Could not kill END-007 process cleanly: {exc}")


def _wait_for_process_with_stop_and_logs(
    process: Any,
    unreal_log_path: Path,
    log_callback: LogCallback | None = None,
    stop_event: threading.Event | None = None,
) -> tuple[str, int | None]:
    """
    Wait for the external END-007/Unreal process while:
    - forwarding process log lines to STAR's technical log when stdout/stderr is piped;
    - checking stop_event regularly;
    - saving all streamed lines into unreal_log_path.
    """
    if not hasattr(process, "poll"):
        return "completed_without_process_handle", None

    output_queue = _start_process_log_readers(process)
    status = "running"
    return_code: int | None = None
    last_heartbeat = time.monotonic()

    with unreal_log_path.open("w", encoding="utf-8", errors="replace") as log_file:
        while True:
            while True:
                try:
                    stream_name, line = output_queue.get_nowait()
                except queue.Empty:
                    break

                if not line:
                    continue

                log_file.write(line + "\n")
                log_file.flush()

                level = _classify_unreal_log_line(line)
                _emit(log_callback, level, line)

            if stop_event is not None and stop_event.is_set():
                status = "stopped"
                _terminate_process_tree(process, log_callback=log_callback)
                return_code = process.poll()
                break

            return_code = process.poll()
            if return_code is not None:
                status = "completed" if return_code == 0 else "failed"
                break

            # If stdout is not piped, still provide sparse heartbeat logs.
            if getattr(process, "stdout", None) is None and time.monotonic() - last_heartbeat > 15:
                _emit(log_callback, "EXECUTION", "END-007 / Unreal is still running...")
                last_heartbeat = time.monotonic()

            time.sleep(0.2)

        # Drain any final lines produced just before process termination.
        drain_deadline = time.monotonic() + 2.0
        while time.monotonic() < drain_deadline:
            try:
                _stream_name, line = output_queue.get_nowait()
            except queue.Empty:
                break
            if line:
                log_file.write(line + "\n")
                level = _classify_unreal_log_line(line)
                _emit(log_callback, level, line)

    return status, return_code


# ---------------------------------------------------------------------------
# STAR entry point
# ---------------------------------------------------------------------------
def run_end007(
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
    """
    STAR execution entry point for END-007.

    app_webview.py calls this function as:
        run_end007(
            input_file=<STAR generated JSON>,
            output_dir=<module output dir>,
            run_id=<run id>,
            log_callback=<optional STAR logger>,
            stop_event=<optional threading.Event>
        )

    The STAR input JSON is kept for traceability. Simulation inputs are still
    read directly from END007-SyntheticDataGeneration/run_simulation.py.
    """
    input_path = Path(input_file)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    product_output_dir, results_output_dir = ensure_module_output_layout(output_path, "END-007")
    if module_product_output_dir:
        product_output_dir = Path(module_product_output_dir); product_output_dir.mkdir(parents=True, exist_ok=True)
    if module_results_dir:
        results_output_dir = Path(module_results_dir); results_output_dir.mkdir(parents=True, exist_ok=True)

    script_path = _find_end007_script()

    _emit(log_callback, "EXECUTION", "END-007 Synthetic Data Generation runner started.")
    _emit(log_callback, "EXECUTION", f"STAR module input file: {input_path}")
    _emit(log_callback, "EXECUTION", f"STAR module output folder: {output_path}")
    _emit(log_callback, "EXECUTION", f"END-007 launcher script: {script_path}")

    star_payload = _load_json(input_path)

    # Cartella RUN corrente della simulazione STAR.
    # Normalmente output_path = RUN_.../modules_output/END-007, quindi parents[1] e' RUN_...
    if run_output_dir:
        star_run_dir = Path(run_output_dir).resolve()
    elif star_payload.get("run_output_dir"):
        star_run_dir = Path(str(star_payload["run_output_dir"])).resolve()
    else:
        star_run_dir = None
        for candidate in [output_path, input_path, Path(star_output_root) if star_output_root else None]:
            if candidate is None:
                continue
            for parent in [Path(candidate).resolve(), *Path(candidate).resolve().parents]:
                if parent.name.startswith("RUN_"):
                    star_run_dir = parent
                    break
            if star_run_dir is not None:
                break

    if star_run_dir is None:
        raise RuntimeError(
            f"END-007 cannot determine STAR run directory from output_path={output_path} input_path={input_path}"
        )

    modules_output_root_path = star_run_dir / "modules_output"

    end003_csv = upstream_product(star_payload, "attitude_propagation_csv")

    # END-003 selects the satellite and the daylight pass END-007 has to render.
    # Record it next to the images so the run is self-describing.
    selected_passes = load_selected_passes(star_payload, end003_csv)
    imaging_pass = (selected_passes or {}).get("imaging_pass") or None
    if imaging_pass:
        _emit(log_callback, "EXECUTION", "END-007 will simulate the END-003 selected pass: " + describe_pass(imaging_pass))
        try:
            _write_json(product_output_dir / "simulated_pass.json", {
                "run_id": run_id,
                "source": (selected_passes or {}).get("_source_path"),
                "attitude_csv": str(end003_csv) if end003_csv is not None else None,
                "imaging_pass": imaging_pass,
            })
        except Exception as exc:
            _emit(log_callback, "WARNING", f"END-007 could not write simulated_pass.json: {exc}")
    else:
        _emit(log_callback, "WARNING", "END-007: END-003 selected_passes.json not found; simulating the raw END-003 CSV.")

    # Expose STAR folders to run_simulation.py if it supports environment-based configuration.
    import os
    os.environ["STAR_RUN_OUTPUT_DIR"] = str(star_run_dir)
    os.environ["STAR_MODULES_OUTPUT_ROOT"] = str(modules_output_root_path)
    os.environ["STAR_END007_OUTPUT_DIR"] = str(output_path)
    os.environ["STAR_END007_PRODUCT_OUTPUT_DIR"] = str(product_output_dir)
    os.environ["STAR_END007_RESULTS_DIR"] = str(results_output_dir)
    os.environ["STAR_MODULE_OUTPUT_DIR"] = str(output_path)
    os.environ["STAR_MODULE_PRODUCT_OUTPUT_DIR"] = str(product_output_dir)
    os.environ["STAR_MODULE_RESULTS_DIR"] = str(results_output_dir)
    os.environ["STAR_MODULE_INPUT_FILE"] = str(input_path)
    if end003_csv is not None:
        os.environ["STAR_END003_OUTPUT_CSV"] = str(end003_csv)
        os.environ["STAR_ATTITUDE_PROPAGATION_OUTPUT_CSV"] = str(end003_csv)

    runtime_script_path = output_path / "run_simulation_runtime.py"
    script_to_load = _prepare_runtime_run_simulation(
        source_script=script_path,
        runtime_script=runtime_script_path,
        attitude_csv=end003_csv,
        product_output_dir=product_output_dir,
        results_output_dir=results_output_dir,
    )
    simulation_module = _load_simulation_module(script_to_load)

    # Override legacy constants in run_simulation.py so it reads the current
    # STAR run artifacts instead of the historical STAR/Output folder.
    if end003_csv is not None:
        for attr in ["CSV_INPUT", "CSV_PATH", "INPUT_CSV", "ATTITUDE_CSV"]:
            try:
                setattr(simulation_module, attr, Path(end003_csv))
            except Exception:
                pass
    try:
        setattr(simulation_module, "OUTPUT_DIR", product_output_dir)
    except Exception:
        pass

    invocation = {
        "run_id": run_id,
        "generated_at": datetime.now().isoformat(),
        "star_input_file": str(input_path),
        "end007_script": str(script_path),
        "runtime_script": str(script_to_load),
        "input_source": "constants_defined_in_run_simulation_py",
        "csv_input": str(getattr(simulation_module, "CSV_INPUT", "")),
        "fov_deg": getattr(simulation_module, "FOV_DEG", None),
        "unreal_editor_exe": str(getattr(simulation_module, "UNREAL_EDITOR_EXE", "")),
        "uproject": str(getattr(simulation_module, "UPROJECT", "")),
        "star_payload_keys": sorted(star_payload.keys()),
        "output_dir": str(output_path),
        "product_output_dir": str(product_output_dir),
        "results_output_dir": str(results_output_dir),
        "star_run_dir": str(star_run_dir),
        "end003_output_csv": str(end003_csv) if end003_csv is not None else None,
        "selected_imaging_pass": imaging_pass,
        "modules_output_root": str(modules_output_root or star_payload.get("modules_output_root", "")),
        "module_output_dir_from_star_input": str(star_payload.get("module_output_dir", "")),
        "upstream_artifacts": star_payload.get("upstream_artifacts", []),
        "upstream_artifacts_absolute": star_payload.get("upstream_artifacts_absolute", []),
        "supports_log_callback": _function_accepts_keyword(
            getattr(simulation_module, "run_simulation", None), "log_callback"
        ) if hasattr(simulation_module, "run_simulation") else False,
        "supports_stop_event": _function_accepts_keyword(
            getattr(simulation_module, "run_simulation", None), "stop_event"
        ) if hasattr(simulation_module, "run_simulation") else False,
    }
    invocation_path = output_path / "end007_runner_invocation.json"
    upstream_artifacts_path = output_path / "upstream_artifacts.json"
    _write_json(
        upstream_artifacts_path,
        {
            "run_id": run_id,
            "module_output_dir": str(output_path),
            "module_product_output_dir": str(product_output_dir),
            "module_results_dir": str(results_output_dir),
            "end003_output_csv": str(end003_csv) if end003_csv is not None else None,
            "modules_output_root": str(modules_output_root_path),
            "star_run_dir": str(star_run_dir),
            "upstream_artifacts": star_payload.get("upstream_artifacts", []),
            "upstream_artifacts_absolute": star_payload.get("upstream_artifacts_absolute", []),
        },
    )
    if "env" in locals():
        env["STAR_UPSTREAM_ARTIFACTS_FILE"] = str(upstream_artifacts_path)
    _write_json(invocation_path, invocation)
    _emit(log_callback, "SYSTEM", f"END-007 invocation saved: {invocation_path}")

    if stop_event is not None and stop_event.is_set():
        _emit(log_callback, "EXECUTION", "END-007 was stopped before Unreal launch.")
        stopped_path = output_path / "end007_process_result.json"
        _write_json(
            stopped_path,
            {
                "started_at": None,
                "completed_at": datetime.now().isoformat(),
                "status": "stopped",
                "pid": None,
                "return_code": None,
                "waited_for_completion": False,
                "reason": "Stop requested before launch.",
            },
        )
        return {
            "status": "stopped",
            "evidence": "END-007 execution was stopped before Unreal was launched.",
            "generated_artifacts": [str(invocation_path), str(stopped_path)],
            "process_id": None,
            "end007_script": str(script_path),
        "runtime_script": str(script_to_load),
        }

    generated_artifacts = [str(invocation_path)]
    started_at = datetime.now().isoformat()
    started_perf = time.perf_counter()
    process = None

    try:
        _emit(log_callback, "EXECUTION", "Launching END-007 run_simulation.py.")
        process = _call_run_simulation(
            simulation_module,
            log_callback=log_callback,
            stop_event=stop_event,
            extra_kwargs={
                "output_dir": str(output_path),
                "module_output_dir": str(output_path),
                "product_output_dir": str(product_output_dir),
                "results_dir": str(results_output_dir),
                "run_id": run_id,
                "star_input_file": str(input_path),
                "run_output_dir": str(star_run_dir),
                "modules_output_root": str(modules_output_root_path),
                "attitude_csv": str(end003_csv) if end003_csv is not None else None,
            },
        )
    except Exception as exc:
        _emit(log_callback, "ERROR", f"END-007 run_simulation.py failed during launch: {exc}")
        process_info_path = output_path / "end007_process_result.json"
        _write_json(
            process_info_path,
            {
                "started_at": started_at,
                "completed_at": datetime.now().isoformat(),
                "status": "failed",
                "pid": None,
                "return_code": None,
                "waited_for_completion": False,
                "error": str(exc),
            },
        )
        generated_artifacts.append(str(process_info_path))
        raise

    process_info = {
        "started_at": started_at,
        "completed_at": None,
        "status": "launched",
        "pid": getattr(process, "pid", None),
        "return_code": None,
        "waited_for_completion": False,
        "stdout_was_piped": getattr(process, "stdout", None) is not None,
        "stderr_was_piped": getattr(process, "stderr", None) is not None,
    }

    _emit(log_callback, "EXECUTION", f"END-007 process launched. PID={process_info['pid']}")

    unreal_log_path = results_output_dir / "end007_unreal_runtime.log"

    if hasattr(process, "poll"):
        process_info["waited_for_completion"] = True
        process_info["status"] = "running"

        if getattr(process, "stdout", None) is None:
            _emit(
                log_callback,
                "WARNING",
                "END-007 process stdout is not piped. STAR can stop the process, "
                "but detailed Unreal logs will appear only if run_simulation.py uses "
                "stdout=subprocess.PIPE and removes the Unreal -log flag.",
            )

        status, return_code = _wait_for_process_with_stop_and_logs(
            process=process,
            unreal_log_path=unreal_log_path,
            log_callback=log_callback,
            stop_event=stop_event,
        )

        process_info["completed_at"] = datetime.now().isoformat()
        process_info["return_code"] = return_code
        process_info["status"] = status
        generated_artifacts.append(str(unreal_log_path))

        if status != "stopped":
            _archive_config_if_available(simulation_module, log_callback=log_callback)
            generated_artifacts.extend(_copy_script_outputs(simulation_module, product_output_dir, log_callback=log_callback))
        else:
            _emit(log_callback, "EXECUTION", "Skipping END-007 output copy because execution was stopped.")

    elif hasattr(process, "wait"):
        # Fallback for Popen-like objects that do not expose poll().
        process_info["waited_for_completion"] = True
        process_info["status"] = "running"
        _emit(log_callback, "WARNING", "END-007 process does not expose poll(); stop responsiveness is limited.")
        return_code = process.wait()
        process_info["completed_at"] = datetime.now().isoformat()
        process_info["return_code"] = return_code
        process_info["status"] = "completed" if return_code in (0, None) else "failed"
        _archive_config_if_available(simulation_module, log_callback=log_callback)
        generated_artifacts.extend(_copy_script_outputs(simulation_module, product_output_dir, log_callback=log_callback))

    else:
        process_info["status"] = "completed_without_process_handle"
        process_info["completed_at"] = datetime.now().isoformat()
        _emit(log_callback, "WARNING", "END-007 script did not return a process handle.")
        generated_artifacts.extend(_copy_script_outputs(simulation_module, product_output_dir, log_callback=log_callback))

    duration = time.perf_counter() - started_perf
    process_info["duration_seconds"] = round(duration, 3)
    process_info["duration_human"] = _format_duration(duration)

    normalize_direct_module_outputs(
        module_root=output_path,
        product_dir=product_output_dir,
        results_dir=results_output_dir,
        keep_names={
            "end007_runner_invocation.json",
            "upstream_artifacts.json",
            "end007_process_result.json",
            "run_simulation_runtime.py",
        },
        log_callback=log_callback,
        module_label="END-007",
    )

    process_info_path = output_path / "end007_process_result.json"
    _write_json(process_info_path, process_info)
    generated_artifacts.append(str(process_info_path))

    status = str(process_info["status"])

    if status == "stopped":
        _emit(log_callback, "EXECUTION", f"END-007 Synthetic Data Generation stopped by user. Execution time: {_format_duration(duration)} ({duration:.2f} s).")
        return {
            "status": "stopped",
            "evidence": "END-007 simulation was stopped by user request from STAR.",
            "generated_artifacts": generated_artifacts,
            "process_id": getattr(process, "pid", None),
            "end007_script": str(script_path),
        "runtime_script": str(script_to_load),
        }

    if status not in {"completed", "completed_without_process_handle"}:
        message = f"END-007 simulation process terminated with status={status}, return_code={process_info.get('return_code')}."
        _emit(log_callback, "ERROR", message)
        raise RuntimeError(message)

    _emit(log_callback, "EXECUTION", f"END-007 Synthetic Data Generation completed successfully. Execution time: {_format_duration(duration)} ({duration:.2f} s).")

    return {
        "status": "completed",
        "evidence": "END-007 run_simulation.py launched and completed through the STAR runner.",
        "generated_artifacts": generated_artifacts,
        "process_id": getattr(process, "pid", None),
        "end007_script": str(script_path),
        "runtime_script": str(script_to_load),
    }

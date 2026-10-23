"""END-008 -> STAR: running the executable and reading its output.

``run_exe`` calls battery_monitoring.exe as the delivery documents (exit 0 = done, 1 = input errors, 2 = calculation error,
last stdout line ``OUTPUT: <path>``). ``read_output`` uses ``load`` of plot_battery_monitoring.py (imported by path), then
``summarize`` / ``kpis`` / ``frontend_data`` give the STAR products and ``write_png`` draws the official mission figure
(``figure_mission``). Nothing here imports STAR; KPI ids are global ids ``END-008.<key>`` to be added to the STAR catalogue.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
VENDOR_DIR = HERE.parent
PLOTTER = "plot_battery_monitoring.py"
EXE = "battery_monitoring.exe"
EXIT_MEANING = {0: "completed", 1: "errors in the input file", 2: "error in the calculation"}
FRONTEND_MAX_POINTS = 600


def run_exe(input_path: str | Path, vendor_dir: str | Path = VENDOR_DIR, timeout_s: float = 1800,
            stop_event: Any = None) -> dict[str, Any]:
    """Runs the executable on input_path (cwd = its folder, so the output lands next to it). ``stop_event`` (an object with
    ``is_set()``) kills the process: the result has ``stopped`` True."""
    exe = Path(vendor_dir) / EXE
    if not exe.is_file():
        return {"returncode": None, "ok": False, "output_path": None, "seconds": 0.0, "stopped": False,
                "message": "executable not found: {}".format(exe), "stdout": "", "stderr": ""}
    t0 = time.time()
    proc = subprocess.Popen([str(exe), str(input_path), "--quiet"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            cwd=str(Path(input_path).resolve().parent), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    reason = ""
    while True:
        try:
            stdout, stderr = proc.communicate(timeout=0.5)
            break
        except subprocess.TimeoutExpired:
            if stop_event is not None and stop_event.is_set():
                reason = "stopped by the user"
            elif time.time() - t0 > timeout_s:
                reason = "timeout after {:.0f} s".format(timeout_s)
            if reason:
                proc.kill()
                stdout, stderr = proc.communicate()
                return {"returncode": None, "ok": False, "output_path": None, "seconds": round(time.time() - t0, 2),
                        "stopped": reason.startswith("stopped"), "message": reason, "stdout": stdout or "", "stderr": stderr or ""}
    lines = stdout.strip().splitlines()
    out = lines[-1][len("OUTPUT: "):].strip() if lines and lines[-1].startswith("OUTPUT: ") else None
    ok = proc.returncode == 0 and out is not None
    msg = EXIT_MEANING.get(proc.returncode, "exit code {}".format(proc.returncode))
    if proc.returncode != 0:
        msg += ": " + (stderr.strip() or stdout.strip())[:500]
    return {"returncode": proc.returncode, "ok": ok, "output_path": out, "seconds": round(time.time() - t0, 2), "stopped": False,
            "message": msg, "stdout": stdout, "stderr": stderr}


def load_plotter(vendor_dir: str | Path = VENDOR_DIR):
    path = Path(vendor_dir) / PLOTTER
    if not path.is_file():
        raise FileNotFoundError("END-008 plot script not found: {}".format(path))
    spec = importlib.util.spec_from_file_location("end008_plot_battery_monitoring", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read_output(path: str | Path, vendor_dir: str | Path = VENDOR_DIR):
    """(summary dict, per-orbit DataFrame, time series dict) of an output file or folder."""
    return load_plotter(vendor_dir).load(path)


def write_png(summary, orbits, series, png_path: str | Path, vendor_dir: str | Path = VENDOR_DIR) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    load_plotter(vendor_dir).figure_mission(summary, orbits, series)
    fig = plt.gcf()
    Path(png_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(png_path), dpi=110)
    plt.close(fig)
    return Path(png_path)


def law_domain_outside_fraction(summary: dict[str, Any]) -> float:
    """Largest fraction of orbits whose degradation-law variable is outside the law's domain (the battery temperature
    outside its domain counts 1.0, orbits beyond the cycles of the data too)."""
    dom = summary.get("degradation_law_domain") or {}
    worst = 0.0
    for key, d in dom.items():
        if not isinstance(d, dict):
            continue
        if "fraction_of_orbits_outside" in d:
            worst = max(worst, float(d["fraction_of_orbits_outside"] or 0.0))
        elif d.get("outside") is True:
            worst = 1.0
        elif d.get("beyond") is True:
            worst = max(worst, 1.0)
    return round(worst, 6)


def summarize(summary: dict[str, Any], orbits, run: dict[str, Any] | None = None) -> dict[str, Any]:
    """battery_health_summary.json: the exe summary reduced to what STAR shows, plus the per-mode balance."""
    soh = summary["SOH_end_of_mission"]
    eol = summary["end_of_life"]
    out = {
        "mission": summary.get("mission"), "orbits": summary.get("orbits"), "orbits_per_day": summary.get("orbits_per_day"),
        "pack_energy_Wh": summary.get("pack_energy_Wh"), "pack_nominal_voltage_V": summary.get("pack_nominal_voltage_V"),
        "degradation_model": summary.get("degradation_model"),
        "soh_end_of_mission": soh.get("median"), "soh_p05": soh.get("p05"), "soh_p95": soh.get("p95"),
        "eol_threshold_soh": eol.get("SOH_threshold"), "eol_reached": bool(eol.get("reached")),
        "eol_sigma_points": "{} of {}".format(eol.get("sigma_points_reaching_it"), eol.get("of")),
        "soc_min_mission": summary.get("SOC_min_mission"), "orbits_below_soc_min": summary.get("orbits_below_SOC_min"),
        "orbits_soc_zero": summary.get("orbits_SOC_zero"),
        "law_domain_outside_fraction": law_domain_outside_fraction(summary),
        "input_warnings": list(summary.get("input_warnings") or []),
        "modes": summary.get("modes") or {},
        "degradation_law_domain": summary.get("degradation_law_domain") or {},
    }
    if len(orbits):
        out["soc_min_overall"] = float(orbits["SOC_min"].min())
        out["soc_max_overall"] = float(orbits["SOC_max"].max())
    if run:
        out["run"] = {k: run.get(k) for k in ("returncode", "seconds", "message")}
    return out


def kpis(summ: dict[str, Any]) -> list[dict[str, Any]]:
    """KPI rows (global ids END-008.<key>) in the unit of the STAR catalogue."""
    def row(key, name, value, unit, category="mission_compliance"):
        return {"id": "END-008." + key, "name": name, "value": value, "unit": unit, "category": category,
                "source": {"product": "battery_health_summary", "field": key}}
    pct = lambda v: None if v is None else round(100.0 * float(v), 3)
    return [
        row("soh_end_of_mission", "Battery state of health at the end of the mission (median)", pct(summ["soh_end_of_mission"]), "%"),
        row("soh_p05", "Battery state of health at the end of the mission (5th percentile)", pct(summ["soh_p05"]), "%"),
        row("eol_reached", "Battery end of life reached within the mission", summ["eol_reached"], "bool"),
        row("soc_min_mission", "Lowest battery state of charge of the mission", pct(summ["soc_min_mission"]), "%"),
        row("orbits_below_soc_min", "Orbits with the state of charge below its minimum", summ["orbits_below_soc_min"], "-"),
        row("law_domain_outside_fraction", "Orbits outside the domain of the degradation law", pct(summ["law_domain_outside_fraction"]),
            "%", "run_validity"),
    ]


def _decimate(n: int, limit: int = FRONTEND_MAX_POINTS) -> list[int]:
    if n <= limit:
        return list(range(n))
    step = (n - 1) / (limit - 1)
    return sorted({int(round(i * step)) for i in range(limit)})


def frontend_data(summary: dict[str, Any], orbits, summ: dict[str, Any]) -> dict[str, Any]:
    """Data of the results tab: per-orbit curves decimated to at most FRONTEND_MAX_POINTS points."""
    idx = _decimate(len(orbits))
    cols = ["t_years", "SOH", "SOH_p05", "SOH_p95", "SOC_min", "SOC_max", "load_energy_Wh", "solar_energy_Wh", "discharge_energy_Wh"]
    curves = {c: [round(float(orbits[c].iloc[i]), 6) for i in idx] for c in cols if c in orbits}
    return {"module_id": "END-008", "summary": {k: v for k, v in summ.items() if k != "degradation_law_domain"},
            "degradation_law_domain": summ.get("degradation_law_domain"), "curves": curves, "points": len(idx),
            "orbits_total": len(orbits)}


def write_frontend_js(data: dict[str, Any], path: str | Path) -> Path:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("window.batteryHealthData = " + json.dumps(data, separators=(",", ":")) + ";\n", "utf-8")
    return Path(path)


def orbits_csv(orbits, path: str | Path) -> Path:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    orbits.to_csv(str(path), index=False)
    return Path(path)

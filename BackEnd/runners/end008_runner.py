"""STAR runner for END-008 Battery Health Monitoring (2026-10-23).

END-008 is a vendor black box (END008-BatteryHealthMonitoring: battery_monitoring.exe, power_budget_to_input.py,
plot_battery_monitoring.py; not in git). The STAR code that drives it is END008-BatteryHealthMonitoring/star_integration;
this runner only reads the upstream products, chooses the STAR settings with their provenance and calls it:

1. reads the END-004 power_budget_summary.json, the END-006 spacecraft_definition.json and, when END-019 ran, its
   thermal_summary_SAT-*.json (registry ``consumes``);
2. writes power_budget.xlsx in the END-008 layout (star_end008_power_budget) and input.json with the official converter and a
   STAR base (star_end008_input): Test = 1 year with a 120 s step, Full = the mission lifetime of the requirements with a 60 s
   step; cell and pack from Input/input_battery_health_monitoring.json (assumptions: END-006 publishes only the battery
   energy); battery temperature = the END-019 mean, else 20 degC;
3. runs battery_monitoring.exe input.json --quiet (exit 0 = completed, 1 = input errors, 2 = calculation error);
4. writes battery_health_summary.json, battery_orbits.csv, the mission figure, the frontend data and kpis.json.

The orchestrator runs END-008 once, after the CEF design loop (registry ``cef_loop: after_loop``).
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

try:
    from .star_runner_io import load_spacecraft_definition, star_run_mode, upstream_product
    from .star_provenance import Provenance
    from .star_status import COMPLETED, FAILED, FALLBACK, SKIP_BLOCKED, STOPPED, evidence as star_evidence, finalize
    from .star_kpi_adapters import write_module_kpis
    from . import star_text_rules
except ImportError:          # loaded outside the runners package
    from star_runner_io import load_spacecraft_definition, star_run_mode, upstream_product
    from star_provenance import Provenance
    from star_status import COMPLETED, FAILED, FALLBACK, SKIP_BLOCKED, STOPPED, evidence as star_evidence, finalize
    from star_kpi_adapters import write_module_kpis
    import star_text_rules

MODULE_ID = "END-008"
OUTPUT_DIRNAME = "output_battery_health_monitoring"
RESULTS_DIRNAME = "results_battery_health_monitoring"
MODULE_DIRNAME = "END008-BatteryHealthMonitoring"
TEMPLATE_NAME = "input_battery_health_monitoring.json"
OUTPUT_NAME = "battery_monitoring_output.json"
TIMEOUT_S = {"test": 600, "full": 3600}


def _star_root(star_root: str | None) -> Path:
    return Path(star_root) if star_root else Path(__file__).resolve().parents[2]


def _integration(vendor: Path):
    """The three star_integration modules (imported from the vendor folder)."""
    pkg = str(vendor / "star_integration")
    if pkg not in sys.path:
        sys.path.insert(0, pkg)
    import star_end008_input as inp            # noqa: PLC0415
    import star_end008_output as out           # noqa: PLC0415
    import star_end008_power_budget as pb      # noqa: PLC0415
    return inp, out, pb


def _read_json(path: Path | None) -> dict[str, Any] | None:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _lifetime(requirements: list[Any], inp: Any) -> tuple[float | None, str]:
    """Mission lifetime [years] of the requirements: the shared STAR rule (star_text_rules), else the END-008 pattern."""
    reqs = [r for r in requirements or [] if isinstance(r, dict)]
    found = star_text_rules.mission_parameters(reqs).get("lifetime_years")
    if found and found[0]:
        return float(found[0]), f"requirement {found[1]} (mission lifetime)"
    years = inp.mission_lifetime_years([str(r.get("text", "")) for r in reqs])
    return (years, "requirements (mission lifetime)") if years else (None, "")


def run_end008(input_file: str, output_dir: str, run_id: str | None = None,
               log_callback: Callable[[str, str], Any] | None = None, stop_event: Any = None,
               star_root: str | None = None, module_product_output_dir: str | None = None,
               module_results_dir: str | None = None, **_: Any) -> dict[str, Any]:
    def log(level: str, msg: str) -> None:
        if log_callback:
            log_callback(level, msg)

    module_root = Path(output_dir)
    product_dir = Path(module_product_output_dir) if module_product_output_dir else module_root / OUTPUT_DIRNAME
    results_dir = Path(module_results_dir) if module_results_dir else module_root / RESULTS_DIRNAME
    product_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)
    root = _star_root(star_root)
    vendor = root / MODULE_DIRNAME
    started = datetime.now().isoformat()
    payload = json.loads(Path(input_file).read_text(encoding="utf-8"))
    prov = Provenance(MODULE_ID)
    generated: list[str] = []

    def finish(status: str, message: str) -> dict[str, Any]:
        status, severity = finalize(status, prov)
        if status == FALLBACK:
            message = star_evidence(MODULE_ID, status, prov, message)
        process = {"run_id": run_id, "status": status, "started_at": started, "completed_at": datetime.now().isoformat(),
                   "evidence": message}
        (module_root / "end008_process_result.json").write_text(json.dumps(process, indent=1, ensure_ascii=False), encoding="utf-8")
        log("EXECUTION" if status == COMPLETED else "WARNING", f"END-008 {status}: {message}")
        if status in (COMPLETED, FALLBACK):
            write_module_kpis(MODULE_ID, module_root, run_id or "", log=log)
        return {"status": status, "fallback_severity": severity, "fallbacks": prov.fallbacks(),
                "provenance": prov.to_json(status, message), "generated_artifacts": generated, "evidence": message}

    # 1. the delivery (not in git) and the upstream products
    exe = vendor / "battery_monitoring.exe"
    if not exe.is_file():
        return finish(SKIP_BLOCKED, f"battery_monitoring.exe not found in {vendor}: the END-008 delivery is not in git, copy it "
                                    "into that folder to run END-008")
    try:
        inp, out, pb = _integration(vendor)
    except Exception as exc:                                       # noqa: BLE001 (a missing pandas / openpyxl)
        return finish(FAILED, f"END-008 integration package not importable: {type(exc).__name__}: {exc}")
    budget_path = upstream_product(payload, "power_budget_summary")
    budget = _read_json(budget_path)
    if not budget or not isinstance(budget.get("input_config"), dict):
        return finish(FAILED, f"END-004 power_budget_summary.json missing or without input_config ({budget_path})")
    prov.record("power_budget", Path(budget_path).name, "END-004 power budget of the run (input_config)")
    sat = load_spacecraft_definition(payload)
    thermal = [t for t in (_read_json(p) for p in upstream_product(payload, "thermal_summary", many=True)) if t]

    # 2. STAR settings
    mode = star_run_mode(payload)
    template_path = root / "Input" / TEMPLATE_NAME
    template = inp.load_template(template_path)
    lifetime, life_source = _lifetime(payload.get("requirements") or [], inp)
    temperature, temp_source = inp.battery_temperature_C(thermal)
    battery_wh = float((budget["input_config"].get("battery") or {}).get("capacity_Wh") or 0.0)
    if battery_wh <= 0:
        return finish(FAILED, "the END-004 power budget has no battery capacity")
    sat_wh = ((sat or {}).get("battery") or {}).get("capacity_wh")
    notes: list[str] = []
    if sat_wh is not None and abs(float(sat_wh) - battery_wh) > 0.01:
        notes.append(f"battery of the END-006 design {float(sat_wh):g} Wh, END-004 power budget {battery_wh:g} Wh: the power "
                     "budget one is simulated (its loads and depth of discharge go with it)")
    base, base_prov = inp.build_base(template, run_mode=mode, mission_name=f"STAR {run_id or ''}".strip(), battery_wh=battery_wh,
                                     lifetime_years=lifetime, temperature_C=temperature if thermal else None,
                                     datasheet=((sat or {}).get("battery") or {}).get("battery_data"))
    tpl_src = f"template {template_path.name}" if template_path.is_file() else "template defaults of star_integration"
    for key, value, why in base_prov:
        from_datasheet = str(why).startswith("datasheet")
        if key in ("cell", "pack.cells_in_parallel") and from_datasheet:
            prov.record(key, value, f"END-006 battery {((sat or {}).get('battery') or {}).get('component')}, {why}")
        elif key == "cell":
            prov.record("cell", value, tpl_src, kind="fallback", severity="minor", reason="assumption: " + why)
        elif key == "pack.cells_in_parallel":
            prov.record(key, value, f"{tpl_src} cell and the battery energy", kind="fallback", severity="minor",
                        reason="assumption: " + why)
        elif key == "pack.temperature_C":
            prov.record(key, value, temp_source)
        elif key == "mission.duration_years":
            source = why if mode == "test" else (life_source or "default 5 years: no mission lifetime in the requirements")
            prov.record(key, value, source)
        else:
            prov.record(key, value, why)
    prov.record("battery_capacity_Wh", battery_wh, "END-004 power budget (battery of the design it used)")
    if ((((sat or {}).get("battery") or {}).get("battery_data") or {}).get("cells_in_series")):
        prov.record("pack.cells_in_series", base["pack"]["cells_in_series"],
                    f"END-006 battery {sat['battery'].get('component')} datasheet (battery_data)")
    else:
        prov.record("pack.cells_in_series", base["pack"]["cells_in_series"], tpl_src, kind="fallback", severity="minor",
                    reason="assumption of the template: the battery datasheet does not publish the pack configuration")
    log("EXECUTION", f"END-008 {mode} run: {base['mission']['duration_years']:g} year(s), step {base['simulation']['time_step_s']:g} s, "
                     f"pack {base['pack']['cells_in_series']}S{base['pack']['cells_in_parallel']}P, {base['pack']['temperature_C']:g} degC")

    # 3. power budget workbook and input.json (official converter)
    xlsx = product_dir / "power_budget.xlsx"
    input_path = product_dir / "input.json"
    try:
        values = pb.write_power_budget_xlsx(budget, xlsx)
        generated.append(str(xlsx))
        cfg, conv_notes = inp.write_input(xlsx, base, input_path, vendor)
        generated.append(str(input_path))
    except Exception as exc:                                       # noqa: BLE001
        return finish(FAILED, f"END-008 input not built: {type(exc).__name__}: {exc}")
    for n in values.get("notes") or []:
        prov.record("power_budget_format", None, "END-004 power budget", reason=n)
    notes += list(values.get("notes") or [])

    # 4. the executable
    log("EXECUTION", f"END-008 running {exe.name} {input_path.name} --quiet")
    run = out.run_exe(input_path, vendor, timeout_s=TIMEOUT_S[mode], stop_event=stop_event)
    if run.get("stopped"):
        return finish(STOPPED, "END-008 stopped by the user.")
    if not run["ok"]:
        return finish(FAILED, f"battery_monitoring.exe: {run['message']}")
    out_path = Path(run["output_path"])
    out_path = out_path if out_path.is_absolute() else input_path.parent / out_path
    target = product_dir / OUTPUT_NAME
    if out_path.resolve() != target.resolve():
        shutil.copy2(out_path, target)
    generated.append(str(target))

    # 5. products
    try:
        s, orbits, series = out.read_output(target, vendor)
        summ = out.summarize(s, orbits, run)
        summ.update({"run_mode": mode, "settings": {
            "duration_years": base["mission"]["duration_years"], "time_step_s": base["simulation"]["time_step_s"],
            "battery_capacity_Wh": battery_wh, "cell": base["cell"].get("name"), "cells_in_series": base["pack"]["cells_in_series"],
            "cells_in_parallel": base["pack"]["cells_in_parallel"], "temperature_C": base["pack"]["temperature_C"],
            "temperature_source": temp_source, "SOC_min": base["pack"].get("SOC_min"), "SOC_max": base["pack"].get("SOC_max")},
            "notes": notes, "converter_notes": conv_notes, "provenance": prov.entries})
        (product_dir / "battery_health_summary.json").write_text(json.dumps(summ, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
        generated.append(str(out.orbits_csv(orbits, product_dir / "battery_orbits.csv")))
        generated.append(str(out.write_frontend_js(out.frontend_data(s, orbits, summ), results_dir / "battery_health_data.js")))
        generated.append(str(out.write_png(s, orbits, series, results_dir / "01_battery_monitoring.png", vendor)))
        generated.insert(0, str(product_dir / "battery_health_summary.json"))
    except Exception as exc:                                       # noqa: BLE001
        return finish(FAILED, f"END-008 output not read: {type(exc).__name__}: {exc}")
    for n in conv_notes:
        log("EXECUTION", f"END-008 converter: {n}")

    pct = lambda v: f"{100 * float(v):.1f} %" if v is not None else "n/a"       # noqa: E731
    years = base["mission"]["duration_years"]
    text = (f"SOH at the end of the {years:g}-year mission {pct(summ['soh_end_of_mission'])} (5th percentile {pct(summ['soh_p05'])}), "
            f"end of life (SOH {pct(summ['eol_threshold_soh'])}) {'reached' if summ['eol_reached'] else 'not reached'}; "
            f"lowest SOC {pct(summ['soc_min_mission'])}, {summ['orbits_below_soc_min']} orbit(s) below the SOC minimum; "
            f"{pct(summ['law_domain_outside_fraction'])} of the orbits outside the domain of the degradation law "
            f"({base['pack']['cells_in_series']}S{base['pack']['cells_in_parallel']}P, {base['pack']['temperature_C']:g} degC, "
            f"exe {run['seconds']:.0f} s)")
    return finish(COMPLETED, text)

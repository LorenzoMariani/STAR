"""STAR requirement compliance and KPI summary (2026-10-17).

After the workflow, every requirement with a number STAR can read (runners/star_text_rules.py) is compared with the
KPI of the module that computes it; END-019's own per-requirement checks are added. Each requirement gets
met / not met / not verifiable (with the reason), and the KPIs of every module are collected in one table.
Files: <run>/compliance/compliance.json and compliance_data.js (window.starComplianceData, read by the results tab).
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from . import star_text_rules as R
except ImportError:
    import star_text_rules as R


def _load(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _first(root: Path, pattern: str) -> Path | None:
    hits = sorted(p for p in root.glob(pattern) if "_initial" not in p.name and "_copy" not in p.name)
    return hits[0] if hits else None


def _kpi_by_name(kpis: list, name: str) -> Any:
    for k in kpis or []:
        if str(k.get("name", "")).lower() == name.lower():
            return k.get("value")
    return None


def collect_kpis(modules_root: Path) -> dict[str, dict[str, Any]]:
    """Normalised KPIs of the modules that ran: {module: {metric: value, "_source": file}}."""
    out: dict[str, dict[str, Any]] = {}
    p = _first(modules_root, "END-001/*/coverage_summary.json")
    d = _load(p) if p else None
    if d:
        k = d.get("kpis") or []
        out["END-001"] = {
            "_source": str(p), "fitness_engine": d.get("fitness_engine_used"), "fallback": d.get("surrogate_fallback_reason"),
            "orbit_type": d.get("orbit_type"), "run_mode": d.get("star_run_mode"),
            "max_revisit_h": _kpi_by_name(k, "Maximum Revisit Time"), "p90_revisit_h": _kpi_by_name(k, "P90 Revisit Time"),
            "mean_revisit_h": _kpi_by_name(k, "Mean Revisit Time"), "max_latency_h": _kpi_by_name(k, "Maximum Latency"),
            "gs_access_h": _kpi_by_name(k, "Average Ground Station Access Time"), "aoi_covered_pct": _kpi_by_name(k, "Percent AOI Covered"),
            "n_satellites": _kpi_by_name(k, "Number of Satellites"), "n_planes": _kpi_by_name(k, "Number of Planes"),
            "altitude_km": _kpi_by_name(k, "Altitude"), "inclination_deg": _kpi_by_name(k, "Inclination"),
        }
    p = _first(modules_root, "END-004/*/power_budget_summary.json")
    d = _load(p) if p else None
    if d:
        flown = [m for m in d.get("mode_summaries", []) if (m.get("orbits_per_day") or 0) > 0]
        out["END-004"] = {"_source": str(p), "daily_balance_Wh": (d.get("analysis") or {}).get("daily_balance_Wh"),
                          "max_dod_pct": 100 * max((m.get("orbital_DoD") or 0) for m in flown) if flown else None,
                          "generation_per_orbit_Wh": flown[0].get("power_generated_per_orbit_Wh") if flown else None,
                          "peak_power_W": max((m.get("peak_power_W") or 0) for m in flown) if flown else None}
    p = _first(modules_root, "END-016/*/space_safety_summary.json")
    d = _load(p) if p else None
    if d:
        k = d.get("kpis") or {}
        out["END-016"] = {"_source": str(p), **{key: k.get(key) for key in (
            "min_separation_km", "n_events_below_screening", "n_events_below_1km", "passive_lifetime_years_mean_activity",
            "complies_5y_rule_mean_activity", "disposal_dv_m_s_5y_rule_mean_activity", "complies_25y_rule_mean_activity",
            "disposal_dv_m_s_25y_rule_mean_activity", "orbit_maintenance_needed")}}
    files = sorted((modules_root / "END-018").glob("*/thermal_summary_SAT-*.json"))
    if files:
        bat_max, bat_min, ctr_max, over = [], [], [], []
        for f in files:
            t = _load(f) or {}
            pk = t.get("peaks") or {}
            nodes = t.get("nodes") or {}
            if pk.get("BAT_max_C") is not None:
                bat_max.append(pk["BAT_max_C"])
            if isinstance(nodes.get("BAT"), dict) and nodes["BAT"].get("min_C") is not None:
                bat_min.append(nodes["BAT"]["min_C"])
            if pk.get("CTR_max_C") is not None:
                ctr_max.append(pk["CTR_max_C"])
            over += [k for k, v in (t.get("violations") or {}).items() if v]
        out["END-018"] = {"_source": str(files[0].parent), "battery_max_C": max(bat_max) if bat_max else None,
                          "battery_min_C": min(bat_min) if bat_min else None, "central_body_max_C": max(ctr_max) if ctr_max else None,
                          "limits_exceeded": sorted(set(over)), "n_satellites": len(files)}
    p = _first(modules_root, "END-010/*/reflectance_summary.json")
    d = _load(p) if p else None
    if d:
        k = d.get("kpis") or []
        out["END-010"] = {"_source": str(p), "observatory": d.get("observatory"),
                          "peak_magnitude": _kpi_by_name(k, "Peak Apparent Visual Magnitude (Est.)"),
                          "limiting_magnitude": _kpi_by_name(k, "Site Limiting Visual Magnitude"),
                          "max_elevation_deg": _kpi_by_name(k, "Max Elevation"), "pass_duration_s": _kpi_by_name(k, "Pass Duration")}
    p = _first(modules_root, "END-003/*/attitude_summary.json")
    d = _load(p) if p else None
    if d:
        k = d.get("kpis") or []
        out["END-003"] = {"_source": str(p), "eclipse_pct": _kpi_by_name(k, "Eclipse Fraction"),
                          "imaging_pass_found": _kpi_by_name(k, "Ground Station Pass Found"),
                          "night_pass_found": _kpi_by_name(k, "Night Light-Curve Pass Found"),
                          "max_body_rate_deg_s": _kpi_by_name(k, "Max Body Rate During Imaging Pass")}
    p = modules_root / "END-019" / "output_component_selector" / "component_selector_results.json"
    d = _load(p)
    if d:
        res = d.get("result") or {}
        mission = res.get("mission") or {}
        sc = d.get("spacecraft") or {}
        out["END-019"] = {"_source": str(p), "phase": d.get("phase"), "status": d.get("status"),
                          "class_u": mission.get("chosen_class_u") or (res.get("cubesat") or {}).get("form_factor_u"),
                          "mass_kg": (res.get("totals") or {}).get("mass_kg"),
                          "mass_limit_kg": (res.get("totals") or {}).get("mass_limit_kg"),
                          "checks": mission.get("requirements") or [], "unmet": mission.get("unmet") or [],
                          "subsystems": sorted({str(s.get("id") or s.get("subsystem") or "") for s in res.get("subsystems") or []} - {""}),
                          "propulsion": any("propulsion" in str(s.get("id") or s.get("subsystem") or "") and s.get("selected")
                                            for s in res.get("subsystems") or []),
                          "spacecraft_mass_kg": sc.get("mass_kg")}
    return out


KPI_ROWS = [
    ("END-001", "n_satellites", "Satellites", "-"), ("END-001", "n_planes", "Orbital planes", "-"),
    ("END-001", "altitude_km", "Altitude", "km"), ("END-001", "inclination_deg", "Inclination", "deg"),
    ("END-001", "max_revisit_h", "Maximum revisit time", "h"), ("END-001", "p90_revisit_h", "90th percentile revisit time", "h"),
    ("END-001", "mean_revisit_h", "Mean revisit time", "h"), ("END-001", "max_latency_h", "Maximum data latency", "h"),
    ("END-001", "gs_access_h", "Average ground-station access", "h"), ("END-001", "aoi_covered_pct", "Area of interest covered", "%"),
    ("END-001", "fitness_engine", "Fitness engine used", "-"),
    ("END-003", "eclipse_pct", "Eclipse fraction", "%"), ("END-003", "max_body_rate_deg_s", "Max body rate (imaging pass)", "deg/s"),
    ("END-004", "daily_balance_Wh", "Daily energy balance", "Wh"), ("END-004", "max_dod_pct", "Max depth of discharge per orbit", "%"),
    ("END-004", "generation_per_orbit_Wh", "Generation per orbit", "Wh"),
    ("END-010", "peak_magnitude", "Peak apparent magnitude", "mag"), ("END-010", "observatory", "Observatory", "-"),
    ("END-016", "min_separation_km", "Minimum separation between satellites", "km"),
    ("END-016", "n_events_below_screening", "Close approaches below screening", "-"),
    ("END-016", "passive_lifetime_years_mean_activity", "Passive orbital lifetime", "years"),
    ("END-016", "disposal_dv_m_s_5y_rule_mean_activity", "Disposal delta-v (5-year rule)", "m/s"),
    ("END-018", "battery_max_C", "Battery max temperature", "C"), ("END-018", "battery_min_C", "Battery min temperature", "C"),
    ("END-018", "central_body_max_C", "Central body max temperature", "C"),
    ("END-019", "class_u", "CubeSat class", "U"), ("END-019", "mass_kg", "Satellite mass", "kg"),
]


def kpi_table(kpis: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for module, key, name, unit in KPI_ROWS:
        v = (kpis.get(module) or {}).get(key)
        if v is not None:
            rows.append({"module": module, "name": name, "value": round(v, 4) if isinstance(v, float) else v, "unit": unit})
    return rows


def _check(module: str, metric: str, op: str, threshold: Any, unit: str, kpis: dict, label: str, value_key: str | None = None) -> dict[str, Any]:
    data = kpis.get(module)
    c = {"module": module, "metric": label, "operator": op, "threshold": threshold, "unit": unit}
    if data is None:
        return {**c, "value": None, "status": "not_verifiable", "reason": f"{module} did not run in this workflow"}
    v = data.get(value_key or metric)
    if v is None:
        return {**c, "value": None, "status": "not_verifiable", "reason": f"{module} did not report {label.lower()}"}
    if isinstance(v, str) and v.strip().lower().lstrip("+") in ("inf", "infinity"):
        v = float("inf")                                       # e.g. END-016 lifetime of an orbit that does not decay
    if isinstance(v, str) and op in ("<=", ">=", "in"):
        import re
        m = re.match(r"\s*([<>])=?\s*(-?\d+(?:\.\d+)?)", v)     # e.g. END-016 lifetime "> 200": a bound, not a value
        if not m:
            return {**c, "value": v, "status": "not_verifiable", "reason": f"{module} reported '{v}'"}
        bound, side = float(m.group(2)), m.group(1)
        if op in ("<=", ">=") and ((op == "<=" and side == ">" and bound >= threshold) or (op == ">=" and side == "<" and bound <= threshold)):
            return {**c, "value": v, "status": "not_met", "reason": ""}
        if op in ("<=", ">=") and ((op == "<=" and side == "<" and bound <= threshold) or (op == ">=" and side == ">" and bound >= threshold)):
            return {**c, "value": v, "status": "met", "reason": ""}
        return {**c, "value": v, "status": "not_verifiable", "reason": f"{module} reported only a bound ({v})"}
    if op == "<=":
        ok = v <= threshold + 1e-9
    elif op == ">=":
        ok = v >= threshold - 1e-9
    elif op == "==":
        ok = v == threshold
    elif op == "in":
        ok = threshold[0] - 1e-9 <= v <= threshold[1] + 1e-9
    else:
        ok = bool(v)
    return {**c, "value": round(v, 4) if isinstance(v, float) else v, "status": "met" if ok else "not_met", "reason": ""}


def check_requirement(req: dict[str, Any], kpis: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rid, text = str(req.get("id", "REQ")), str(req.get("text", ""))
    p = {k: v[0] for k, v in R.mission_parameters([(rid, text)]).items()}
    checks: list[dict[str, Any]] = []
    for key, label in (("revisit_max_h", "Maximum revisit time"), ("revisit_mean_h", "Mean revisit time"),
                       ("revisit_p90_h", "90th percentile revisit time"), ("latency_h", "Maximum data latency")):
        if key in p:
            metric = {"revisit_max_h": "max_revisit_h", "revisit_mean_h": "mean_revisit_h", "revisit_p90_h": "p90_revisit_h",
                      "latency_h": "max_latency_h"}[key]
            checks.append(_check("END-001", metric, "<=", round(p[key], 4), "h", kpis, label))
    if "sats_max" in p:
        checks.append(_check("END-001", "n_satellites", "<=", p["sats_max"], "-", kpis, "Number of satellites"))
    if "sats_min" in p and p.get("sats_min") != p.get("sats_max"):
        checks.append(_check("END-001", "n_satellites", ">=", p["sats_min"], "-", kpis, "Number of satellites"))
    if p.get("single"):
        checks.append(_check("END-001", "n_satellites", "==", 1, "-", kpis, "Number of satellites"))
    if "planes" in p:
        checks.append(_check("END-001", "n_planes", "==", p["planes"], "-", kpis, "Number of orbital planes"))
    if "alt" in p:
        lo, hi = p["alt"]
        if lo is not None and hi is not None and lo == hi:
            lo, hi = lo - 25, hi + 25
        checks.append(_check("END-001", "altitude_km", "in", [lo if lo is not None else 0, hi if hi is not None else 1e9], "km", kpis, "Altitude"))
    if "incl" in p:
        checks.append(_check("END-001", "inclination_deg", "in", [p["incl"] - 0.5, p["incl"] + 0.5], "deg", kpis, "Inclination"))
    if "mass" in p:
        checks.append(_check("END-019", "mass_kg", "<=", p["mass"][0], "kg", kpis, "Satellite mass"))
    if "class_u" in p:
        c = _check("END-019", "class_u", "in", [min(p["class_u"]), max(p["class_u"])], "U", kpis, "CubeSat class")
        if c["status"] == "not_met":
            c["reason"] = "END-019 chooses the smallest class whose components meet the performance requirements (stated class only reported)"
        checks.append(c)
    if "dod_max_pct" in p:
        checks.append(_check("END-004", "max_dod_pct", "<=", p["dod_max_pct"], "%", kpis, "Depth of discharge per orbit"))
    if p.get("energy_balance_positive"):
        checks.append(_check("END-004", "daily_balance_Wh", ">=", 0, "Wh", kpis, "Daily energy balance"))
    if "magnitude_min" in p:
        checks.append(_check("END-010", "peak_magnitude", ">=", p["magnitude_min"], "mag", kpis, "Peak apparent magnitude (fainter = larger)"))
    if p.get("separation_check"):
        checks.append(_check("END-016", "n_events_below_screening", "==", 0, "-", kpis, "Close approaches below the screening distance"))
    if "reentry_years" in p:
        c = _check("END-016", "passive_lifetime_years_mean_activity", "<=", p["reentry_years"], "years", kpis, "Passive orbital lifetime")
        if c["status"] == "not_met":
            dv = [x for x in (kpis.get("END-019") or {}).get("checks", []) if "delta-v" in str(x.get("what", "")).lower() and x.get("status") == "met"]
            if dv:
                c.update({"status": "met", "reason": "disposal manoeuvre: " + str(dv[0].get("what"))})
            else:
                c["reason"] = "the orbit decays too slowly: a disposal manoeuvre is needed"
        checks.append(c)
    if "lifetime_years" in p and "reentry_years" not in p:
        checks.append(_check("END-016", "passive_lifetime_years_mean_activity", ">=", p["lifetime_years"], "years", kpis,
                             "Passive orbital lifetime vs mission lifetime"))
    if "temp_range_c" in p:
        tr = p["temp_range_c"]
        if tr["item"] == "battery":
            checks.append(_check("END-018", "battery_max_C", "<=", tr["max"], "C", kpis, "Battery max temperature"))
            checks.append(_check("END-018", "battery_min_C", ">=", tr["min"], "C", kpis, "Battery min temperature"))
        else:
            checks.append({"module": "END-018", "metric": f"{tr['item']} temperature", "operator": "in", "threshold": [tr["min"], tr["max"]],
                           "unit": "C", "value": None, "status": "not_verifiable",
                           "reason": "END-018 models the faces, panels, central body, battery and SAR payload nodes"})
    low = R.norm(text)
    if p.get("orbit") == "SSORGT" and "END-001" in kpis:
        checks.append(_check("END-001", "orbit_type", "==", "SSORGT", "", kpis, "Sun-synchronous orbit"))
    # reference passes: daylight imaging pass and night pass of END-001 / END-003
    if R.has_any(low, ("daylight", "in daylight", "di giorno", "diurno")) and R.has_any(low, ("image", "imaging", "acquire", "immagine", "acquisire")):
        checks.append(_check("END-003", "imaging_pass_found", "==", True, "", kpis, "Daylight imaging pass found"))
    if R.has_any(low, ("at night", "night pass", "di notte", "notturno")) and R.has_any(low, ("cross the sky", "visible", "light curve", "observ",
                                                                                            "illuminated", "visibile", "curva di luce")):
        checks.append(_check("END-003", "night_pass_found", "==", True, "", kpis, "Night pass visible from the observatory found"))
    if R.has_any(low, ("battery temperature", "temperatura della batteria")) and R.has_any(low, ("limit", "limits", "limite", "limiti")):
        data = kpis.get("END-018")
        if data is None:
            checks.append({"module": "END-018", "metric": "Battery temperature limit", "operator": "", "threshold": None, "unit": "", "value": None,
                           "status": "not_verifiable", "reason": "END-018 did not run in this workflow"})
        else:
            over = [v for v in data.get("limits_exceeded", []) if v.startswith("BAT")]
            checks.append({"module": "END-018", "metric": "Battery temperature limit", "operator": "", "threshold": None, "unit": "C",
                           "value": data.get("battery_max_C"), "status": "not_met" if over else "met",
                           "reason": "limit exceeded on at least one satellite" if over else ""})
    # an analysis the call asks for: met when the module that makes it produced its results
    if R.has_any(low, ("shall be assessed", "shall be provided", "shall provide evidence", "evidence of", "shall be computed", "shall be simulated",
                       "shall be estimated", "shall be analysed", "shall be analyzed", "shall be verified", "shall be evaluated",
                       "dovra essere fornito", "dovra essere fornita", "dovranno essere forniti", "dovranno essere fornite", "dovra essere valutato", "dovra essere valutata", "dovranno essere valutati", "dovranno essere valutate", "dovra essere calcolato", "dovra essere calcolata", "dovranno essere calcolati", "dovranno essere calcolate", "dovra essere simulato", "dovra essere simulata", "dovranno essere simulati", "dovranno essere simulate", "dovra essere stimato", "dovra essere stimata", "dovranno essere stimati", "dovranno essere stimate", "dovra essere analizzato", "dovra essere analizzata", "dovranno essere analizzati", "dovranno essere analizzate", "dovra essere verificato", "dovra essere verificata", "dovranno essere verificati", "dovranno essere verificate")):
        named = list(R.modules_requested(text))
        specific = [m for m in named if m in ("END-004", "END-007", "END-010", "END-016", "END-018")]
        for module_id in (specific or named):     # the module that makes the analysis, not the generic orbit / CubeSat ones
            if module_id in kpis and not any(c["module"] == module_id for c in checks):
                checks.append({"module": module_id, "metric": "Analysis produced", "operator": "", "threshold": None, "unit": "", "value": True,
                               "status": "met", "reason": f"{module_id} produced its results"})
    for x in (kpis.get("END-019") or {}).get("checks", []):
        if (x.get("requirement") or {}).get("id") == rid:
            st = str(x.get("status", "")).replace("-", "_")
            checks.append({"module": "END-019", "metric": str(x.get("what", "")), "operator": "", "threshold": None, "unit": "",
                           "value": None, "status": st if st in ("met", "not_met", "not_verifiable") else "not_verifiable",
                           "reason": str(x.get("message", ""))})
    statuses = [c["status"] for c in checks]
    applied = [k for k in ("adrag", "cd", "start") if k in p] or \
        (["objective"] if R.has_any(low, ("minimise the revisit", "minimize the revisit", "maximise the coverage", "maximize the coverage",
                                          "minimizzare il tempo di rivisita", "massimizzare la copertura")) else [])
    if not checks and applied:
        status = "applied"
        reason = ("an objective END-001 optimises (revisit, coverage)" if applied == ["objective"]
                  else "used as an input of the modules (" + ", ".join({"adrag": "drag area", "cd": "drag coefficient", "start": "start epoch"}[k] for k in applied) + ")")
    elif not checks:
        status, reason = "not_verifiable", "no quantity STAR computes is stated in this requirement"
    elif "not_met" in statuses:
        status, reason = "not_met", ""
    elif all(s == "met" for s in statuses):
        status, reason = "met", ""
    elif "met" in statuses:
        status, reason = "partially_verified", "some checks could not be verified"
    else:
        status, reason = "not_verifiable", "; ".join(sorted({c["reason"] for c in checks if c.get("reason")}))[:300]
    return {"id": rid, "text": text, "status": status, "reason": reason, "checks": checks}


def _clean(obj: Any) -> Any:
    """inf / nan are not valid JSON for the results page: written as text."""
    import math
    if isinstance(obj, float) and (math.isinf(obj) or math.isnan(obj)):
        return "inf" if obj > 0 else "-inf" if math.isinf(obj) else "nan"
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    return obj


def build(run_path: str | Path, requirements: list[dict[str, Any]], run_mode: str = "test", workflow: list | None = None) -> dict[str, Any]:
    run_path = Path(run_path)
    kpis = collect_kpis(run_path / "modules_output")
    rows = [check_requirement(r, kpis) for r in requirements or [] if isinstance(r, dict) and r.get("text")]
    counts = {s: sum(1 for r in rows if r["status"] == s) for s in ("met", "not_met", "partially_verified", "applied", "not_verifiable")}
    data = {
        "generated_at": datetime.now().isoformat(),
        "run_mode": run_mode,
        "note": ("Test mode: every module ran with its fastest settings, the values are not meaningful." if run_mode != "full" else ""),
        "modules_run": sorted(kpis),
        "workflow": [s.get("module_id") for s in (workflow or [])],
        "counts": counts,
        "requirements": rows,
        "kpis": kpi_table(kpis),
        "sources": {m: v.get("_source") for m, v in kpis.items()},
    }
    data = _clean(data)
    out = run_path / "compliance"
    out.mkdir(parents=True, exist_ok=True)
    (out / "compliance.json").write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    (out / "compliance_data.js").write_text("window.starComplianceData = " + json.dumps(data, ensure_ascii=False, default=str) + ";\n", encoding="utf-8")
    return data

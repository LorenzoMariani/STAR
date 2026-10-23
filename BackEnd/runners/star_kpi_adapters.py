"""KPI adapters (phase E, step E2): one pure function per module turns the module's own products into the common KPI list.

``adapt_end0XX(module_root, run_ctx=None) -> list[kpi]`` reads only files under ``modules_output/<END-xxx>/`` (never MATLAB
code, never another module's products) and returns entries built with ``star_kpis.kpi``. The runners call
``write_module_kpis`` at the end of their run; compliance calls ``adapt`` / ``build_document`` to rebuild the KPIs of a run
that has no kpis.json yet. This file holds the logic that was ``star_compliance.collect_kpis``, so nothing the old
compliance read is lost.

``run_ctx`` is an optional dict (``run_id``); END-006 takes ``phase`` ("initial" | "final") as an argument.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable

try:
    from . import star_kpis as K
except ImportError:
    import star_kpis as K

Ctx = dict[str, Any] | None


# --------------------------------------------------------------------------- reading helpers
def _load(path: Path | None) -> dict | None:
    if path is None:
        return None
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _first(root: Path, pattern: str) -> Path | None:
    hits = sorted(p for p in Path(root).glob(pattern) if p.is_file() and "_initial" not in p.name and "_copy" not in p.name)
    return hits[0] if hits else None


def _num(v: Any) -> float | None:
    if isinstance(v, bool) or v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and abs(f) != float("inf") else None


def _get(d: Any, path: str) -> Any:
    for part in path.split("."):
        d = d.get(part) if isinstance(d, dict) else None
    return d


def _by_name(kpis: list | None) -> dict[str, dict[str, Any]]:
    return {str(k.get("name", "")).lower(): k for k in kpis or [] if isinstance(k, dict)}


def _assessment_of(k: dict[str, Any], unit: str) -> dict[str, Any] | None:
    """The module's own verdict on one of its KPIs (meets_requirement, threshold_ok / threshold_bad)."""
    meets, ok, bad = k.get("meets_requirement"), _num(k.get("threshold_ok")), _num(k.get("threshold_bad"))
    if meets is None and ok is None:
        return None
    source = str(k.get("threshold_source") or "")
    source = source if source in K.THRESHOLD_SOURCES else "module_default"
    if ok is None:
        return K.assessment(meets, "==", True, "bool", source, note="module flag; its threshold is not published")
    op = "<=" if bad is None or ok <= bad else ">="
    return K.assessment(meets, op, ok, unit, source, note="module threshold (ok limit)" + (f", bad limit {bad:g}" if bad is not None else ""))


def _native(module_id: str, product: str, kpis: list | None, skip: tuple[str, ...] = (), context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Catalogue entries of the module whose ``native`` name is in the module's own KPI list (END-001 / 003 / 010)."""
    names = _by_name(kpis)
    out = []
    for key, e in K.CATALOGUE.items():
        if not key.startswith(module_id + ".") or "{" in key or not e.get("native") or e.get("product") != product or key in skip:
            continue
        k = names.get(str(e["native"]).lower())
        if k is None or k.get("value") is None:
            continue
        unit = K.norm_unit(e["unit"])
        out.append(K.kpi(key, k["value"], native_id=k.get("id"), context=context, assessment=_assessment_of(k, unit)))
    return out


def _add(out: list, kpi_id: str, value: Any, **kw: Any) -> None:
    """Append a KPI when it has a value (a module that did not report it gives none, as compliance reads it)."""
    if value is not None:
        out.append(K.kpi(kpi_id, value, **kw))


# --------------------------------------------------------------------------- END-001 constellation optimizer
def adapt_end001(module_root: str | Path, run_ctx: Ctx = None) -> list[dict[str, Any]]:
    root = Path(module_root)
    p = _first(root, "*/coverage_summary.json")
    d = _load(p)
    if not d:
        return []
    out = _native("END-001", "coverage_summary", d.get("kpis"), skip=("END-001.fitness_engine",))
    otype, requested = str(d.get("orbit_type") or ""), str(d.get("orbit_type_requested") or "")
    # the family END-001 chose ("Auto" when the call names no orbit type)
    family = ("Sun-synchronous (SSO-RGT)" if otype == "SSORGT" else "Walker delta (inclined RGT)" if otype.startswith("RGT") else otype or "-")
    _add(out, "END-001.orbit_type", d.get("orbit_type"), context={"family": family, "chosen_by_end001": requested.lower() == "auto"})
    _add(out, "END-001.orbit_type_requested", d.get("orbit_type_requested"))
    _add(out, "END-001.fitness_engine", d.get("fitness_engine_used"),
         context={"fallback_reason": d.get("surrogate_fallback_reason") or "", "run_mode": d.get("star_run_mode") or "",
                  "requested": d.get("fitness_engine_requested") or ""})
    ecl = _load(_first(root, "*/eclipse_summary.json")) or {}
    env = ecl.get("life_envelope") or {}
    _add(out, "END-001.mission_life_years", ecl.get("mission_life_years"))
    _add(out, "END-001.eclipse_max_life_min", env.get("eclipse_max_min"))
    _add(out, "END-001.eclipse_min_life_min", env.get("eclipse_min_min"))
    _add(out, "END-001.abs_beta_max_life_deg", env.get("abs_beta_max_deg"))
    ops = (_load(_first(root, "*/operations_summary.json")) or {}).get("constellation_mean") or {}
    for key, field in (("orbits_per_day", "orbits_per_day"), ("imaging_s_per_day", "imaging_s_per_day"),
                       ("imaging_orbits_per_day", "imaging_orbits_per_day"), ("contact_s_per_day", "contact_s_per_day"),
                       ("contact_orbits_per_day", "contact_orbits_per_day")):
        _add(out, f"END-001.{key}", ops.get(field), context={"scope": "constellation mean"})
    gs = (_load(_first(root, "*/ground_stations.json")) or {}).get("ground_stations")
    if isinstance(gs, list):
        _add(out, "END-001.n_ground_stations", len(gs), context={"names": [str(g.get("name", "")) for g in gs if isinstance(g, dict)]})
    return out


# --------------------------------------------------------------------------- END-003 attitude propagation
def adapt_end003(module_root: str | Path, run_ctx: Ctx = None) -> list[dict[str, Any]]:
    d = _load(_first(Path(module_root), "*/attitude_summary.json"))
    if not d:
        return []
    k = d.get("kpis") or []
    out = _native("END-003", "attitude_summary", k)
    sat = _by_name(k).get("imaging pass satellite index", {}).get("value")
    for e in out:      # the imaging pass numbers belong to one satellite of the constellation
        if e["id"] in ("END-003.max_pointing_error_deg", "END-003.mean_pointing_error_deg", "END-003.max_body_rate_deg_s",
                       "END-003.peak_elevation_deg") and isinstance(sat, (int, float)):
            e["context"] = {"scope": "imaging pass", "satellite": f"SAT-{int(sat):02d}"}
    _add(out, "END-003.attitude_mode", d.get("attitude_mode"))
    out += end003_absolute(d)
    return out


def end003_absolute(d: dict[str, Any]) -> list[dict[str, Any]]:
    """IF-003-006: peak wheel momentum, control torque and magnetorquer dipole in physical units. The module's own absolute value
    when attitude_control writes it, otherwise the % KPI x the capacity of the wheels / magnetorquers END-003 used."""
    names = _by_name(d.get("kpis"))
    ac = d.get("attitude_control") or {}
    out: list[dict[str, Any]] = []
    for kpi_id, native, own, cap_key, src_key in (
            ("END-003.peak_wheel_momentum_Nms", "peak wheel momentum", "peak_wheel_momentum_Nms", "wheel_momentum_Nms", "wheels_source"),
            ("END-003.peak_control_torque_Nm", "peak control torque", "peak_control_torque_Nm", "wheel_torque_Nm", "wheels_source"),
            ("END-003.peak_mtq_dipole_Am2", "peak magnetorquer dipole", "peak_mtq_dipole_Am2", "magnetorquer_dipole_Am2", "magnetorquer_source")):
        value, how = _num(ac.get(own)), "module value"
        pct, cap = _num(names.get(native, {}).get("value")), _num(ac.get(cap_key))
        if value is None and pct is not None and cap is not None:
            value, how = pct / 100.0 * cap, f"{pct:.4g} % of {cap:g}"
        _add(out, kpi_id, value, context={"derived_from": how, "capacity_used": cap, "design_used": str(ac.get(src_key) or "")})
    return out


# --------------------------------------------------------------------------- END-004 power budget
def adapt_end004(module_root: str | Path, run_ctx: Ctx = None) -> list[dict[str, Any]]:
    root = Path(module_root)
    p = _first(root, "*/power_budget_summary.json")
    d = _load(p)
    if not d:
        return []
    out: list[dict[str, Any]] = []
    flown = [m for m in d.get("mode_summaries", []) if (m.get("orbits_per_day") or 0) > 0]
    n_flown = sum(float(m.get("orbits_per_day") or 0) for m in flown)
    _add(out, "END-004.daily_balance_Wh", _get(d, "analysis.daily_balance_Wh"), context={"case": "nominal"})
    # generation per mode (attitude of each mode): the mean over the orbits of the day
    if flown:
        _add(out, "END-004.generation_per_orbit_Wh",
             sum(float(m.get("orbits_per_day") or 0) * float(m.get("power_generated_per_orbit_Wh") or 0) for m in flown) / n_flown,
             context={"scope": "mean over the orbits of the day"})
        _add(out, "END-004.peak_power_W", max((m.get("peak_power_W") or 0) for m in flown), context={"scope": "flown modes"})
    _add(out, "END-004.design_margin_pct", None if d.get("analysis", {}).get("margin_fraction") is None
         else 100 * float(d["analysis"]["margin_fraction"]))
    nominal_dod = 100 * max((m.get("orbital_DoD") or 0) for m in flown) if flown else None
    cases = _load(p.parent / "power_design_cases.json")
    # phase D: the depth of discharge checked is the battery worst case (longest eclipse over the mission life, generation
    # reduced by the shorter sunlight); the nominal one stays as a KPI. Without the design-case file (older runs) the
    # nominal one is the only value, as compliance read it then.
    if cases and _num(cases.get("worst_dod_pct")) is not None:
        wc = cases.get("battery_worst_case") or {}
        limit = _num(cases.get("dod_limit_pct"))
        ctx = {"case": "worst", "eclipse_source": wc.get("eclipse_source") or ""}
        a = None if limit is None else K.assessment(cases.get("battery_within_dod_limit"), "<=", limit, "%", "requirement",
                                                    note="depth of discharge limit stated in the requirements")
        _add(out, "END-004.worst_dod_pct", cases["worst_dod_pct"], context=ctx, assessment=a)
        _add(out, "END-004.nominal_dod_pct", _get(cases, "nominal.max_dod_pct"), context={"case": "nominal"})
        _add(out, "END-004.worst_daily_balance_Wh", wc.get("daily_balance_Wh"), context=ctx)
        _add(out, "END-004.worst_eclipse_min", wc.get("eclipse_min"), context=ctx)
        _add(out, "END-004.nominal_eclipse_min", _get(cases, "orbit.eclipse_min"), context={"case": "nominal"})
        _add(out, "END-004.orbit_period_min", _get(cases, "orbit.period_min"))
        _add(out, "END-004.battery_capacity_Wh", cases.get("battery_capacity_Wh"))
        for case in ("hot", "cold", "nominal"):
            _add(out, f"END-004.dissipation_{case}_W", _get(cases, f"dissipation_W.{case}"), context={"case": case})
        bh = cases.get("battery_heater") or {}          # phase F4: the battery heater energy of the worst (cold) case
        _add(out, "END-004.heater_energy_per_orbit_Wh", bh.get("energy_per_orbit_Wh", 0.0),
             context={"case": "worst", "component": bh.get("component") or "", "mean_w_cold": bh.get("mean_w_cold")})
    else:
        _add(out, "END-004.worst_dod_pct", nominal_dod, context={"case": "nominal", "note": "power_design_cases.json not available: nominal eclipse"})
        _add(out, "END-004.nominal_dod_pct", nominal_dod, context={"case": "nominal"})
        _add(out, "END-004.battery_capacity_Wh", _get(d, "input_config.battery.capacity_Wh"))
        _add(out, "END-004.orbit_period_min", _get(d, "input_config.orbit.period_min"))
        _add(out, "END-004.nominal_eclipse_min", _get(d, "input_config.orbit.eclipse_min"), context={"case": "nominal"})
    return out


# --------------------------------------------------------------------------- END-006 component selector
def design_components(results: dict[str, Any] | None) -> dict[str, str]:
    """{slot: component id} of a component_selector_results.json (the slots with a selected component)."""
    out: dict[str, str] = {}
    for s in ((results or {}).get("result") or {}).get("subsystems") or []:
        sel = s.get("selected")
        slot = s.get("id") or s.get("subsystem")
        if slot and isinstance(sel, dict) and sel.get("id"):
            out[str(slot)] = str(sel["id"])
    # the battery heater (IF-019-006) is chosen after the search: an integrated one is named so that switching it on is a change
    h = (((results or {}).get("result") or {}).get("mission") or {}).get("battery_heater") or {}
    if h.get("component"):
        out["battery_heater"] = str(h["component"]) if h.get("source") == "separate" else f"{h['component']}:integrated_heater"
    return out


def design_signature(components: dict[str, str]) -> str:
    """Hash of the slot -> component choice: the same signature means the same components (CEF-COMPONENTS)."""
    text = "\n".join(f"{slot}={components[slot]}" for slot in sorted(components))
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def adapt_end006(module_root: str | Path, run_ctx: Ctx = None, phase: str = "final") -> list[dict[str, Any]]:
    """phase 'final' reads the final design products, 'initial' the *_initial ones (the satellite the other modules use)."""
    base = Path(module_root) / "output_component_selector"
    sfx = "_initial" if phase == "initial" else ""
    d = _load(base / f"component_selector_results{sfx}.json")
    if not d:
        return []
    sd = _load(base / ("spacecraft_definition.json" if phase == "initial" else "spacecraft_definition_final.json")) or d.get("spacecraft") or {}
    res = d.get("result") or {}
    mission = res.get("mission") or {}
    totals = res.get("totals") or {}
    ctx = {"phase": phase}
    out: list[dict[str, Any]] = []
    _add(out, "END-006.class_u", sd.get("class_u") or mission.get("chosen_class_u") or _get(res, "cubesat.form_factor_u"), context=ctx)
    _add(out, "END-006.stated_class_u", _get(mission, "stated_class.class_u"), context=ctx)
    components = design_components(d)
    if components:
        _add(out, "END-006.design_signature", design_signature(components), context={**ctx, "components": components})
    mass = _num(totals.get("mass_kg"))
    lim = mission.get("mass_limit") or {}
    mass_a = None
    if mass is not None and _num(lim.get("kg")) is not None:
        rid = (lim.get("requirement") or {}).get("id")
        mass_a = K.assessment(mass <= float(lim["kg"]) + 1e-9, "<=", lim["kg"], "kg", "requirement" if rid else "module_default",
                              [rid] if rid else [], note="mass limit of the requirement" if rid else "mass limit of the class")
    _add(out, "END-006.mass_kg", mass, context=ctx, assessment=mass_a)
    _add(out, "END-006.mass_limit_kg", totals.get("mass_limit_kg"), context=ctx)
    vol, vol_lim = _num(totals.get("volume_m3")), _num(totals.get("volume_limit_m3"))
    _add(out, "END-006.volume_used_pct", 100 * vol / vol_lim if vol is not None and vol_lim else None, context=ctx)
    dv = mission.get("dv") or {}
    _add(out, "END-006.dv_capacity_m_s", dv.get("given_m_s"), context={**ctx, "source": dv.get("source") or ""})
    _add(out, "END-006.dv_need_m_s", dv.get("dv_m_s"), context={**ctx, "source": dv.get("source") or ""})
    _add(out, "END-006.battery_capacity_Wh", sd.get("battery_wh"), context=ctx)
    _add(out, "END-006.battery_need_Wh", _get(mission, "battery.need_wh"), context=ctx)
    _add(out, "END-006.pointing_accuracy_deg", _get(sd, "attitude_control.pointing_accuracy_deg"), context=ctx)
    ws = mission.get("wheel_sizing") or {}      # IF-003-006: capacity / END-003 need of the chosen wheels
    for key, need, cap in (("momentum_ratio", "need_momentum_nms", "capacity_momentum_nms"), ("torque_ratio", "need_torque_nm", "capacity_torque_nm")):
        _add(out, f"END-006.wheel_{key}", ws.get(key), context={**ctx, "component": ws.get("component") or "", "need": ws.get(need),
                                                                "capacity": ws.get(cap), "design_factor": ws.get("design_factor")})
    bh = mission.get("battery_heater") or {}       # IF-019-006: heater sized on the END-019 cold case
    if bh:
        hctx = {**ctx, "component": bh.get("component") or "", "source": bh.get("source") or "", "status": bh.get("status") or "",
                "need_peak_w": bh.get("need_peak_w"), "required_w": bh.get("required_w"), "why": bh.get("why") or ""}
        _add(out, "END-006.battery_heater_W", bh.get("power_w") if bh.get("component") else 0.0, context=hctx,
             assessment=None if bh.get("required_w") is None else K.assessment(
                 bh.get("status") == "met", ">=", round(float(bh["required_w"]), 4), "W", "module_default",
                 note=f"{bh.get('design_factor')} x the END-019 cold-case peak"))
        tc = bh.get("temperature_check") or {}
        if tc:
            out.append(K.kpi("END-006.check_battery_temperature", tc.get("met"), context={**ctx, **{k: v for k, v in tc.items() if k != "met"}},
                             assessment=K.assessment(tc.get("met"), "==", True, "bool", "module_default", note=str(tc.get("what") or ""))))
    _add(out, "END-006.solar_peak_power_W", _get(sd, "solar_panels.total_peak_w"), context=ctx)
    _add(out, "END-006.declared_peak_power_W", totals.get("power_w_declared_peak"), context=ctx)
    _add(out, "END-006.drag_area_m2", sd.get("area_mean_projected_m2"), context=ctx)
    _add(out, "END-006.drag_coefficient", sd.get("cd"), context=ctx)
    subsystems = res.get("subsystems") or []
    _add(out, "END-006.has_propulsion", any("propulsion" in str(s.get("id") or s.get("subsystem") or "") and bool(s.get("selected"))
                                          for s in subsystems), context=ctx)
    n_sub, n_cov = _num(totals.get("n_subsystems")), _num(totals.get("n_covered"))
    _add(out, "END-006.subsystems_covered_pct", 100 * n_cov / n_sub if n_sub else None, context=ctx)
    # END-006 selects only among catalogued components: true when every subsystem has one
    _add(out, "END-006.components_from_catalogue", bool(res.get("ok")) and n_sub is not None and n_cov == n_sub, context=ctx,
         source={"product": "component_selector_results", "field": "result.ok and n_covered == n_subsystems"})
    _add(out, "END-006.unmet_requirements", len(mission.get("unmet") or []), context={**ctx, "unmet": list(mission.get("unmet") or [])})
    # one boolean per requirement check of END-006 (assessment names the requirement: compliance reads it generically)
    seen: dict[str, int] = {}
    for x in mission.get("requirements") or []:
        base_key = K.check_key(x.get("slot"), x.get("what"))
        seen[base_key] = seen.get(base_key, 0) + 1
        key = base_key if seen[base_key] == 1 else f"{base_key}_{seen[base_key]}"
        status = str(x.get("status", "")).replace("-", "_")
        meets = True if status == "met" else False if status == "not_met" else None
        req = (x.get("requirement") or {}).get("id")
        _add(out, f"END-006.{key}", meets, name=str(x.get("what") or key), unit="bool", category="evidence",
             context={**ctx, "slot": x.get("slot") or "design", "status": status},
             source={"product": f"component_selector_results{sfx}", "field": "result.mission.requirements[]"},
             assessment=K.assessment(meets, "==", True, "bool", "requirement" if req else "module_default", [req] if req else [],
                                     note=str(x.get("message") or "")))
        if meets is None:                       # not_verifiable: the check exists, its value does not
            out.append(K.kpi(f"END-006.{key}", None, name=str(x.get("what") or key), unit="bool", category="evidence",
                             context={**ctx, "slot": x.get("slot") or "design", "status": status}, assessment=K.assessment(
                                 None, "==", True, "bool", "requirement" if req else "module_default", [req] if req else [],
                                 note=str(x.get("message") or ""))))
    return out


def adapt_end006_initial(module_root: str | Path, run_ctx: Ctx = None) -> list[dict[str, Any]]:
    return adapt_end006(module_root, run_ctx, phase="initial")


def adapt_end006_final(module_root: str | Path, run_ctx: Ctx = None) -> list[dict[str, Any]]:
    return adapt_end006(module_root, run_ctx, phase="final")


# --------------------------------------------------------------------------- END-007 synthetic data generation
def adapt_end007(module_root: str | Path, run_ctx: Ctx = None) -> list[dict[str, Any]]:
    root = Path(module_root)
    sim = _load(_first(root, "*/simulated_pass.json"))
    images = [p for p in root.glob("*/*.png") if p.is_file() and not p.parent.name.startswith("results_")]
    if sim is None and not images and not root.exists():
        return []
    out: list[dict[str, Any]] = []
    sat = _get(sim or {}, "imaging_pass.satellite_index")
    _add(out, "END-007.imaging_pass_simulated", bool(sim and sim.get("imaging_pass")),
         context={"satellite": f"SAT-{int(sat):02d}"} if isinstance(sat, (int, float)) else {})
    _add(out, "END-007.images_produced", len(images))
    return out


# --------------------------------------------------------------------------- END-010 reflectance determination
def adapt_end010(module_root: str | Path, run_ctx: Ctx = None) -> list[dict[str, Any]]:
    d = _load(_first(Path(module_root), "*/reflectance_summary.json"))
    if not d:
        return []
    out = _native("END-010", "reflectance_summary", d.get("kpis"))
    limiting = _by_name(d.get("kpis")).get("site limiting visual magnitude", {})
    for e in out:
        if e["id"] == "END-010.peak_magnitude" and e["assessment"]:
            # the module's flag: the peak magnitude is brighter than the site limit; informative, not a requirement
            e["assessment"] = K.assessment(e["assessment"]["meets"], "<=", limiting.get("value"), "mag", "module_default",
                                           note="module flag: peak magnitude brighter than the site limiting magnitude")
    _add(out, "END-010.observatory", d.get("observatory"))
    return out


# --------------------------------------------------------------------------- END-016 space safety
def adapt_end016(module_root: str | Path, run_ctx: Ctx = None) -> list[dict[str, Any]]:
    d = _load(_first(Path(module_root), "*/space_safety_summary.json"))
    if not d:
        return []
    k, cfg = d.get("kpis") or {}, d.get("config") or {}
    out: list[dict[str, Any]] = []
    for key, field in (("n_pairs", "n_pairs"), ("min_separation_km", "min_separation_km"),
                       ("n_events_below_screening", "n_events_below_screening"), ("n_events_below_1km", "n_events_below_1km"),
                       ("events_per_day", "events_per_day"), ("max_pc", "max_pc"),
                       ("n_events_above_pc_threshold", "n_events_above_pc_threshold"),
                       ("passive_lifetime_years", "passive_lifetime_years_mean_activity"),
                       ("passive_lifetime_min_years", "passive_lifetime_years_min"),
                       ("passive_lifetime_max_years", "passive_lifetime_years_max"),
                       ("drag_makeup_dv_m_s_per_year", "drag_makeup_dv_m_s_per_year_mean_activity"),
                       ("orbit_maintenance_needed", "orbit_maintenance_needed")):
        ctx = {"solar_activity": "mean"} if "lifetime" in key or "drag" in key else {}
        if key == "min_separation_km" and k.get("min_separation_pair"):
            ctx = {"pair": k["min_separation_pair"]}
        _add(out, f"END-016.{key}", k.get(field), context=ctx)
    # disposal rules: one pair of KPIs per rule the module evaluated (5 and 25 years today)
    for key in sorted(k):
        m = re.match(r"^complies_(\d+)y_rule_mean_activity$", key)
        if m:
            n = m.group(1)
            _add(out, f"END-016.complies_{n}y_rule", k.get(key), context={"solar_activity": "mean"})
            _add(out, f"END-016.disposal_dv_{n}y_m_s", k.get(f"disposal_dv_m_s_{n}y_rule_mean_activity"), context={"solar_activity": "mean"})
    _add(out, "END-016.screening_km", cfg.get("screening_km"))
    _add(out, "END-016.mass_used_kg", cfg.get("mass_kg"))
    _add(out, "END-016.drag_area_used_m2", cfg.get("drag_area_m2"))
    return out


# --------------------------------------------------------------------------- END-019 components thermal analysis
def adapt_end019(module_root: str | Path, run_ctx: Ctx = None) -> list[dict[str, Any]]:
    root = Path(module_root)
    files = sorted(root.glob("*/thermal_summary_SAT-*.json"))
    if not files:
        return []
    # candidates[kpi] = [(value, case, satellite)]: the window run plus the hot and cold design cases of every satellite
    cand: dict[str, list[tuple[float, str, str]]] = {}
    over: set[str] = set()
    limits: dict[str, Any] = {}
    betas: dict[str, tuple[float, float]] = {}                # hot beta of the hottest battery, cold eclipse of the coldest
    solar: dict[str, list[tuple[float, str]]] = {"max": [], "min": []}

    def add(key: str, value: Any, case: str, sat: str) -> None:
        v = _num(value)
        if v is not None:
            cand.setdefault(key, []).append((v, case, sat))

    for f in files:
        t = _load(f) or {}
        sat = str(t.get("satellite_label") or re.sub(r"^thermal_summary_|\.json$", "", f.name))
        nodes, pk, dc = t.get("nodes") or {}, t.get("peaks") or {}, t.get("design_cases") or {}
        limits = limits or (t.get("limits") or {})
        bat, ctr = nodes.get("BAT") or {}, nodes.get("CTR") or {}
        add("bat_max", bat.get("max_C") if bat.get("max_C") is not None else pk.get("BAT_max_C"), "window", sat)
        add("bat_min", bat.get("min_C"), "window", sat)
        add("ctr_max", ctr.get("max_C") if ctr.get("max_C") is not None else pk.get("CTR_max_C"), "window", sat)
        add("ctr_min", ctr.get("min_C"), "window", sat)
        add("sar_max", (nodes.get("SAR") or {}).get("max_C"), "window", sat)
        sp = t.get("solar_panels") or {}
        add("sp_max", sp.get("max_C"), "window", sat)
        add("sp_min", sp.get("min_C"), "window", sat)
        for n in ("pX", "mX", "pY", "mY", "pZ", "mZ"):
            add("face_max", (nodes.get(n) or {}).get("max_C"), "window", sat)
            add("face_min", (nodes.get(n) or {}).get("min_C"), "window", sat)
        # phase D: the hot and cold design cases over the mission life bound the battery and the central body
        for case in ("hot", "cold"):
            c = dc.get(case) or {}
            cn = c.get("nodes") or {}
            if case == "hot":
                add("bat_max", (cn.get("BAT") or {}).get("max_C"), "hot", sat)
                add("ctr_max", (cn.get("CTR") or {}).get("max_C"), "hot", sat)
            else:
                add("bat_min", (cn.get("BAT") or {}).get("min_C"), "cold", sat)
                add("ctr_min", (cn.get("CTR") or {}).get("min_C"), "cold", sat)
            for n in ("pX", "mX", "pY", "mY", "pZ", "mZ"):
                add("face_max", (cn.get(n) or {}).get("max_C"), case, sat)
                add("face_min", (cn.get(n) or {}).get("min_C"), case, sat)
            if case == "hot" and _num(c.get("beta_deg")) is not None and _num((cn.get("BAT") or {}).get("max_C")) is not None:
                if "hot" not in betas or cn["BAT"]["max_C"] > betas["hot"][1]:
                    betas["hot"] = (float(c["beta_deg"]), float(cn["BAT"]["max_C"]))
            if case == "cold" and _num(c.get("eclipse_min")) is not None and _num((cn.get("BAT") or {}).get("min_C")) is not None:
                if "cold" not in betas or cn["BAT"]["min_C"] < betas["cold"][1]:
                    betas["cold"] = (float(c["eclipse_min"]), float(cn["BAT"]["min_C"]))
        over |= {kk for kk, v in (t.get("violations") or {}).items() if v}

    # limits used: the run info says whether the battery limits are a datasheet value or the END-019 default
    info = _load(_first(root, "*/thermal_run_info.json")) or {}
    prov = info.get("provenance") or {}
    cfg = info.get("config") or {}

    def bat_source(name: str) -> str:
        text = str(prov.get(name) or "").lower()
        return "module_default" if not text or text.startswith("default") else "component"

    bat_min = _num(cfg.get("bat_min_C")) if _num(cfg.get("bat_min_C")) is not None else _num(limits.get("BAT_min"))
    bat_max = _num(cfg.get("bat_max_C")) if _num(cfg.get("bat_max_C")) is not None else _num(limits.get("BAT"))
    src_min, src_max = bat_source("bat_min_C"), bat_source("bat_max_C")
    note_min = str(prov.get("bat_min_C") or "")
    note_max = str(prov.get("bat_max_C") or "")

    def worst(key: str, high: bool) -> tuple[float, dict[str, Any]] | None:
        items = cand.get(key)
        if not items:
            return None
        v, case, sat = max(items) if high else min(items)
        return v, {"case": case, "satellite": sat, "scope": f"worst of {len(files)} satellite(s), window and design cases"}

    out: list[dict[str, Any]] = []

    def put(kpi_id: str, key: str, high: bool, assess: dict[str, Any] | None = None) -> None:
        w = worst(key, high)
        if w:
            out.append(K.kpi(kpi_id, w[0], context=w[1], assessment=assess))

    def limit_assessment(key: str, high: bool, limit: float | None, source: str, note: str) -> dict[str, Any] | None:
        w = worst(key, high)
        if w is None or limit is None:
            return None
        meets = w[0] <= limit + 1e-9 if high else w[0] >= limit - 1e-9
        return K.assessment(meets, "<=" if high else ">=", limit, "C", source, note=note)

    # battery heater (phase F4, heater_cases.json of end019_heater_cases.m): the minimum with the heater of the design
    # replaces the unheated one; the hot side does not change (the heater only raises the minimum)
    heat = _load(_first(root, "*/heater_cases.json")) or {}
    hw = (heat.get("worst") or {}) if heat.get("status") == "completed" else {}
    no_heater = worst("bat_min", False)
    with_heater = _num(hw.get("battery_min_with_heater_C"))
    put("END-019.battery_max_C", "bat_max", True, limit_assessment("bat_max", True, bat_max, src_max, note_max))
    if with_heater is not None:
        heater_w = _num((heat.get("heater_in_design") or {}).get("power_W"))
        meets = with_heater >= bat_min - 1e-9 if bat_min is not None else None
        out.append(K.kpi("END-019.battery_min_C", with_heater,
                         context={"case": "cold case and window with the heater of the design", "heater_W": heater_w,
                                  "satellite": hw.get("satellite_label") or "", "scope": f"worst of {len(files)} satellite(s)"},
                         assessment=None if meets is None else K.assessment(meets, ">=", bat_min, "C", src_min, note=note_min)))
    else:
        put("END-019.battery_min_C", "bat_min", False, limit_assessment("bat_min", False, bat_min, src_min, note_min))
    if no_heater:
        _add(out, "END-019.battery_min_no_heater_C", no_heater[0], context=no_heater[1])
    if hw:
        hctx = {"setpoint_C": heat.get("setpoint_C"), "satellite": hw.get("satellite_label") or "", "case": "cold"}
        _add(out, "END-019.heater_needed_peak_W", hw.get("needed_peak_W"), context={**hctx, "rule": "ideal thermostat"})
        _add(out, "END-019.heater_needed_mean_W_cold", hw.get("needed_mean_W_cold"), context={**hctx, "rule": "ideal thermostat"})
        _add(out, "END-019.heater_duty_cold_pct", hw.get("duty_cold_pct"),
             context={**hctx, "rule": "bang-bang with the heater of the design" if with_heater is not None else "ideal thermostat on-fraction"})
        _add(out, "END-019.heater_in_design_W", _num((heat.get("heater_in_design") or {}).get("power_W")) or 0.0, context=hctx)
    put("END-019.central_body_max_C", "ctr_max", True, limit_assessment("ctr_max", True, _num(limits.get("CTR")), "module_default", "END-019 default limit"))
    put("END-019.central_body_min_C", "ctr_min", False)
    put("END-019.solar_panel_max_C", "sp_max", True)
    put("END-019.solar_panel_min_C", "sp_min", False)
    put("END-019.face_max_C", "face_max", True)
    put("END-019.face_min_C", "face_min", False)
    put("END-019.sar_max_C", "sar_max", True, limit_assessment("sar_max", True, _num(limits.get("SAR")), "module_default", "END-019 default limit"))
    _add(out, "END-019.battery_limit_min_C", bat_min, context={"source": note_min})
    _add(out, "END-019.battery_limit_max_C", bat_max, context={"source": note_max})
    _add(out, "END-019.limits_violated", bool(over), context={"violations": sorted(over)})
    if "hot" in betas:
        _add(out, "END-019.hot_case_beta_deg", betas["hot"][0], context={"case": "hot", "battery_max_C": betas["hot"][1]})
    if "cold" in betas:
        _add(out, "END-019.cold_case_eclipse_min", betas["cold"][0], context={"case": "cold", "battery_min_C": betas["cold"][1]})
    _add(out, "END-019.n_satellites", len(files))
    return out


# --------------------------------------------------------------------------- dispatch and files
ADAPTERS: dict[str, Callable[..., list[dict[str, Any]]]] = {
    "END-001": adapt_end001, "END-003": adapt_end003, "END-004": adapt_end004, "END-006/initial": adapt_end006_initial,
    "END-006/final": adapt_end006_final, "END-007": adapt_end007, "END-010": adapt_end010, "END-016": adapt_end016,
    "END-019": adapt_end019,
}


def adapt(module_id: str, module_root: str | Path, phase: str = "", run_ctx: Ctx = None) -> list[dict[str, Any]]:
    """KPIs of one node ('END-006' needs its phase)."""
    node = f"{module_id}/{phase}" if phase else module_id
    if node not in ADAPTERS and module_id == "END-006":
        node = "END-006/final"
    fn = ADAPTERS.get(node)
    return fn(module_root, run_ctx) if fn else []


def build_document(module_id: str, module_root: str | Path, phase: str = "", run_id: str = "") -> dict[str, Any]:
    """The kpis.json document of a node, from its products on disk."""
    phase = phase if module_id == "END-006" else ""
    return K.document(module_id, adapt(module_id, module_root, phase, {"run_id": run_id}), phase=phase, run_id=run_id)


def write_module_kpis(module_id: str, module_root: str | Path, run_id: str = "", phase: str = "",
                      log: Callable[[str, str], Any] | None = None) -> Path | None:
    """Write <module_root>/kpis.json (kpis_initial.json for END-006's initial node) at the end of a run.
    A KPI problem never fails the module: it is logged and the file is not written (the registry product check reports it)."""
    try:
        doc = build_document(module_id, module_root, phase, run_id)
        return K.write(module_root, doc)
    except Exception as exc:                      # noqa: BLE001
        if log:
            log("WARNING", f"{module_id}: kpis.json not written ({type(exc).__name__}: {exc})")
        return None

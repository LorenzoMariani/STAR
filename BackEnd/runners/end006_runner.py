"""STAR runner for END-006 Satellite Design Component Selector.

Called by the orchestrator (FrontEnd/star_frontend_v5.py -> StarApi.call_module_runner_or_placeholder) as
`runners.end006_runner.run_end006(input_file=..., output_dir=..., ...)`. Place this file in BackEnd/runners/.

The selector package (star_component_selector) is located through, in order:
  1. the STAR_COMPONENT_SELECTOR_ROOT environment variable;
  2. STAR/END006-ComponentSelector/star_component_selector (the module folder inside STAR, like the other
     END0XX modules), or a folder named `star_component_selector` next to or above this file, the STAR root
     or the run folder.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

try:
    from .star_runner_io import upstream_product
    from .star_kpi_adapters import write_module_kpis
except ImportError:          # loaded outside the runners package
    from star_runner_io import upstream_product
    from star_kpi_adapters import write_module_kpis

MODULE_ID = "END-006"
OUTPUT_DIRNAME = "output_component_selector"
RESULTS_DIRNAME = "results_component_selector"
SELECTOR_DIRNAME = "star_component_selector"
# the only input of the selector: the CubeSat class (1, 3, 6 or 12 U)
INPUT_ALIASES: dict[str, str] = {}


def _find_selector_root(extra: list[str | Path]) -> Path:
    candidates: list[Path] = []
    env = os.environ.get("STAR_COMPONENT_SELECTOR_ROOT", "").strip()
    if env:
        candidates.append(Path(env).expanduser())
    here = Path(__file__).resolve()
    for base in [here, *[Path(p).resolve() for p in extra if p]]:
        for parent in [base, *base.parents]:
            candidates.append(parent / "END006-ComponentSelector" / SELECTOR_DIRNAME)   # module folder inside STAR
            candidates.append(parent / SELECTOR_DIRNAME)
            candidates.append(parent.parent / SELECTOR_DIRNAME)
    for c in candidates:
        if (c / "star_selector" / "api.py").is_file():
            return c.resolve()
    raise FileNotFoundError(
        f"{SELECTOR_DIRNAME} not found. Set STAR_COMPONENT_SELECTOR_ROOT to the folder that contains star_selector/ and data/catalog.json.")


def _number(value: Any) -> float | None:
    try:
        return float(str(value).replace(",", ".").split()[0])
    except (ValueError, IndexError):
        return None


def _approved_inputs(items: list[dict[str, Any]], defaults_only: bool | None = None) -> dict[str, Any]:
    """Values resolved in the missing-information step for END-006 (field proposed_value); empty values are ignored.

    defaults_only=True keeps only first-guess values (source module_registry_default, not edited by the user): they must not override what
    the requirements say; False keeps only values the user provided or edited; None keeps all."""
    out: dict[str, Any] = {}
    for item in items or []:
        if str(item.get("needed_by_module_id", "")).upper() != MODULE_ID:
            continue
        is_default = item.get("source") == "module_registry_default" and not item.get("reviewed_by_user")
        if defaults_only is not None and is_default != defaults_only:
            continue
        name = INPUT_ALIASES.get(item.get("parameter"), item.get("parameter"))
        if name != "form_factor_u":
            continue
        value = item.get("proposed_value")
        if value in (None, "", "TBD", "not available") or str(item.get("status")) in ("requires_user_input", "not_applicable"):
            continue
        num = _number(value)
        if num is not None and int(num) in (1, 3, 6, 12):
            out[name] = int(num)
    return out


# Satellite shared by the STAR modules (2026-10-17): END-006 runs first (initial design, step 0 of the
# workflow) and writes spacecraft_definition.json, which END-001, END-003, END-004, END-010, END-016 and
# END-019 use; at the end of the workflow it runs again with their results (final design).
SPACECRAFT_FILE = "spacecraft_definition.json"
PANEL_FACE_MM = {"1U": (100.0, 100.0), "2U": (100.0, 227.0), "3U": (100.0, 340.5), "6U": (226.3, 366.0), "12U": (226.3, 366.0)}
CD_DEFAULT, CR_DEFAULT = 2.2, 1.2


def spacecraft_definition(result: dict[str, Any], phase: str, run_id: str | None) -> dict[str, Any]:
    """The satellite of the design for the other modules: class and envelope, mass, inertia and areas of the uniform box,
    solar panels on the body faces, battery, declared powers of the subsystems."""
    cs = result.get("cubesat") or {}
    env = [float(v) for v in (cs.get("envelope_mm") or (100.0, 100.0, 340.5))]
    a, b, c = (v / 1000.0 for v in env)
    totals = result.get("totals") or {}
    mass = float(totals.get("mass_kg") or 0.0)
    # by design slot (comms_s, comms_uhf, antenna_s, ...): the keys of breakdown.power_w
    chosen = {s.get("id") or s.get("subsystem"): s["selected"] for s in result.get("subsystems", []) if s.get("selected")}
    faces = {"+X": (b, c), "-X": (b, c), "+Y": (a, c), "-Y": (a, c), "+Z": (a, b), "-Z": (a, b)}
    panel = chosen.get("solar_panel") or {}
    pspecs = panel.get("specs") or {}
    face_type = str(pspecs.get("face") or "")
    n_panels = int((((chosen.get("structure") or {}).get("specs") or {}).get("panel_faces") or {}).get(face_type, 0) or 0)
    body_faces: list[str] = []
    if face_type in PANEL_FACE_MM and n_panels:
        pw, ph = PANEL_FACE_MM[face_type]
        def mismatch(dims: tuple[float, float]) -> float:
            s = sorted(d * 1000.0 for d in dims)
            return abs(s[0] - pw) / pw + abs(s[1] - ph) / ph
        order = ["+X", "-X", "+Y", "-Y", "+Z", "-Z"]
        body_faces = sorted(faces, key=lambda k: (round(mismatch(faces[k]), 3), order.index(k)))[:n_panels]
    peak = pspecs.get("peak_power_w")
    battery = ((result.get("mission") or {}).get("battery") or {}).get("integrated_wh")
    if battery is None:
        battery = ((chosen.get("battery") or {}).get("specs") or {}).get("capacity_wh")
    if battery is None:
        battery = ((chosen.get("eps") or {}).get("specs") or {}).get("integrated_battery_wh")
    # operating temperatures of the battery (END-019 limits, phase D): the battery pack, else the EPS with the integrated battery
    cell = chosen.get("battery") or (chosen.get("eps") if ((chosen.get("eps") or {}).get("specs") or {}).get("integrated_battery_wh") else None) or {}
    temp = cell.get("temp_op_c")
    temp = [float(temp[0]), float(temp[1])] if isinstance(temp, (list, tuple)) and len(temp) == 2 and None not in temp else None
    components = {k: v.get("id") for k, v in chosen.items()}
    heater = thermal_control((result.get("mission") or {}).get("battery_heater"))
    if heater and heater["battery_heater"].get("component"):
        bh = heater["battery_heater"]
        # an integrated heater is part of the battery, named so that switching it on changes the design signature
        components["battery_heater"] = bh["component"] if bh.get("source") == "separate" else f"{bh['component']}:integrated_heater"
    return {
        "schema_version": 1, "module_id": MODULE_ID, "phase": phase, "run_id": run_id, "generated_at": datetime.now().isoformat(),
        "class_u": cs.get("class_u"), "form_factor": f"{cs.get('class_u')}U", "envelope_mm": env, "dims_m": [a, b, c],
        "mass_kg": mass,
        "inertia_kg_m2": [mass / 12.0 * (b * b + c * c), mass / 12.0 * (a * a + c * c), mass / 12.0 * (a * a + b * b)],
        "inertia_model": "uniform box of the class envelope with the mass of the selected components",
        "face_areas_m2": {"x": b * c, "y": a * c, "z": a * b},
        "area_mean_projected_m2": (a * b + b * c + c * a) / 2.0,
        "cd": CD_DEFAULT, "cr": CR_DEFAULT,
        "solar_panels": {"component": panel.get("id"), "name": panel.get("name"), "face_type": face_type or None,
                         "peak_power_w_per_panel": peak, "n_panels": n_panels, "body_faces": body_faces,
                         "total_peak_w": (float(peak) * n_panels) if peak is not None and n_panels else None},
        "battery_wh": battery,
        "battery": {"component": cell.get("id"), "capacity_wh": battery, "temp_op_c": temp},
        "consumers_declared_peak_w": (result.get("breakdown") or {}).get("power_w") or {},
        "radios": {k: {"component": v.get("id"), "band": (v.get("specs") or {}).get("band"),
                       "has_receiver": (v.get("specs") or {}).get("has_receiver"),
                       "power_w_idle": (v.get("specs") or {}).get("power_w_idle"),
                       "power_w_tx": (v.get("specs") or {}).get("power_w_tx")}
                   for k, v in chosen.items() if str(k).startswith("comms")},
        "power_unknown": totals.get("power_unknown") or [],
        "attitude_control": attitude_control(chosen),
        "components": components,
        "thermal_control": heater,
        "conventions": "body frame: +Z payload boresight (nadir), long axis of the envelope along Z; envelope X x Y x Z; "
                       "Cd and Cr are STAR defaults; area_mean_projected = surface / 4 (orientation average)",
    }


def thermal_control(heater: dict[str, Any] | None) -> dict[str, Any] | None:
    """Thermal control of the design (phase F4, IF-019-006): the battery heater chosen from the END-019 cold-case sizing, with the
    thermostat setpoint END-019 used and the orbit-mean power of the cold case (END-004 counts its energy in the cold case,
    END-019 verifies it). None without END-019 in the run (or when no heater is needed)."""
    if not heater or not heater.get("component"):
        return None
    return {"battery_heater": {"component": heater["component"], "name": heater.get("name"), "source": heater.get("source"),
                               "power_w": heater.get("power_w"), "setpoint_c": heater.get("setpoint_c"),
                               "mean_w_cold": heater.get("mean_w_cold"), "duty_cold": heater.get("duty_cold"),
                               "mass_kg": heater.get("mass_kg"), "bus_voltage_v": heater.get("bus_voltage_v"),
                               "rule": f"thermostat at the setpoint; power >= {heater.get('design_factor')} x the END-019 cold-case peak "
                                       f"({heater.get('need_peak_w')} W)"}}


def attitude_control(chosen: dict[str, Any]) -> dict[str, Any]:
    """Actuators and attitude knowledge of the design for the END-003 attitude control (2026-10-19): the reaction wheels (the
    selected wheel, otherwise the wheels integrated in the ADCS unit), one per body axis, with the momentum and the maximum
    torque of each wheel as the vendor declares them; the magnetorquers that dump the wheel momentum (the selected
    magnetorquer, otherwise those of the ADCS unit), dipole per body axis; the pointing accuracy of the ADCS unit and the
    star tracker accuracy."""
    def num(specs: dict[str, Any], key: str) -> float | None:
        v = (specs or {}).get(key)
        return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None

    wheels = None
    rw, adcs = chosen.get("reaction_wheel"), chosen.get("adcs")
    if rw and num(rw.get("specs"), "momentum_mnms") and num(rw.get("specs"), "max_torque_mnm"):
        wheels = {"source": "reaction_wheel", "component": rw.get("id"), "name": rw.get("name"), "quantity": rw.get("quantity"),
                  "momentum_nms": num(rw["specs"], "momentum_mnms") / 1000.0, "max_torque_nm": num(rw["specs"], "max_torque_mnm") / 1000.0}
    elif adcs and num(adcs.get("specs"), "wheel_momentum_mnms") and num(adcs.get("specs"), "wheel_max_torque_mnm"):
        wheels = {"source": "adcs", "component": adcs.get("id"), "name": adcs.get("name"), "quantity": 3,
                  "momentum_nms": num(adcs["specs"], "wheel_momentum_mnms") / 1000.0,
                  "max_torque_nm": num(adcs["specs"], "wheel_max_torque_mnm") / 1000.0}
    magnetorquers = None
    mtq = chosen.get("magnetorquer")
    if mtq and num(mtq.get("specs"), "magnetic_moment_am2"):
        # a three-axis board, or single-axis rods: one per body axis when the design has three of them
        axes = int(num(mtq["specs"], "axes") or 1) * int(mtq.get("quantity") or 1)
        magnetorquers = {"source": "magnetorquer", "component": mtq.get("id"), "name": mtq.get("name"), "axes": min(axes, 3),
                         "dipole_am2": num(mtq["specs"], "magnetic_moment_am2")}
    elif adcs and num(adcs.get("specs"), "magnetorquer_dipole_am2"):
        magnetorquers = {"source": "adcs", "component": adcs.get("id"), "name": adcs.get("name"), "axes": 3,
                         "dipole_am2": num(adcs["specs"], "magnetorquer_dipole_am2")}
    st = chosen.get("star_tracker")
    tracker = None
    if st and num(st.get("specs"), "accuracy_cross_arcsec"):
        tracker = {"component": st.get("id"), "accuracy_cross_arcsec": num(st["specs"], "accuracy_cross_arcsec"),
                   "accuracy_roll_arcsec": num(st["specs"], "accuracy_roll_arcsec"), "accuracy_basis": st["specs"].get("accuracy_basis")}
    return {"wheels": wheels, "magnetorquers": magnetorquers, "adcs_unit": adcs.get("id") if adcs else None,
            "pointing_accuracy_deg": num(adcs.get("specs"), "pointing_accuracy_deg") if adcs else None, "star_tracker": tracker,
            "note": "wheels: one per body axis, momentum and maximum torque of each wheel; magnetorquers: dipole per body axis "
                    "(vendor values, END-006 catalog); null when the design has no such data"}


def design_changes(initial: dict[str, Any] | None, final: dict[str, Any]) -> list[str]:
    """What the final design changes with respect to the initial one the modules used."""
    if not initial:
        return []
    out = []
    if initial.get("class_u") != final.get("class_u"):
        out.append(f"class {initial.get('class_u')}U -> {final.get('class_u')}U")
    mi, mf = float(initial.get("mass_kg") or 0), float(final.get("mass_kg") or 0)
    if abs(mf - mi) > 1e-6:
        out.append(f"mass {mi:.3f} -> {mf:.3f} kg")
    ci, cf = initial.get("components") or {}, final.get("components") or {}
    for sub in sorted(set(ci) | set(cf)):
        if ci.get(sub) != cf.get(sub):
            out.append(f"{sub}: {ci.get(sub) or 'none'} -> {cf.get(sub) or 'none'}")
    if initial.get("battery_wh") != final.get("battery_wh"):
        out.append(f"battery {initial.get('battery_wh')} -> {final.get('battery_wh')} Wh")
    return out


def mission_context(payload: dict[str, Any]) -> dict[str, Any]:
    """Products of the same run that the final design uses when they are there (registry consumes of END-006/final): the orbit
    altitudes of END-001 (GSD and swath of the imagers), the END-004 power budget (energy the battery gives in an orbit ->
    battery capacity) and the END-016 space-safety summary (disposal delta-v -> propulsion)."""
    ctx: dict[str, Any] = {}
    alts = []
    for p in upstream_product(payload, "satellite_orbits", many=True):
        try:
            orbit = json.loads(p.read_text(encoding="utf-8")).get("orbit") or {}
            alts.append((float(orbit["alt_perigee_m"]) + float(orbit["alt_apogee_m"])) / 2000.0)
        except (OSError, ValueError, KeyError, TypeError):
            continue
    if alts:
        ctx["altitude_km"] = [min(alts), max(alts)]
        ctx["altitude_source"] = f"END-001 of this run ({len(alts)} satellite orbits)"
    for key, path in (("end004", upstream_product(payload, "power_budget_summary")),
                      ("end016", upstream_product(payload, "space_safety_summary"))):
        if path and path.is_file():
            try:
                ctx[key] = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
    end003 = end003_peaks(upstream_product(payload, "kpis_end003"), upstream_product(payload, "spacecraft_definition"))
    if end003:
        ctx["end003"] = end003
    end019 = end019_heater(upstream_product(payload, "kpis_end019"))
    if end019:
        ctx["end019"] = end019
    return ctx


def end019_heater(kpis_path: Path | None) -> dict[str, Any] | None:
    """IF-019-006: the END-019 battery temperatures and the cold-case heater sizing (kpis_end019). None without END-019."""
    if not kpis_path or not kpis_path.is_file():
        return None
    try:
        kpis = {k.get("id"): k for k in json.loads(kpis_path.read_text(encoding="utf-8")).get("kpis") or []}
    except (OSError, ValueError, AttributeError):
        return None

    def val(key: str) -> float | None:
        return _number((kpis.get(f"END-019.{key}") or {}).get("value"))
    if val("battery_min_C") is None and val("battery_max_C") is None:
        return None
    return {"needed_peak_w": val("heater_needed_peak_W"), "needed_mean_w_cold": val("heater_needed_mean_W_cold"),
            "setpoint_c": ((kpis.get("END-019.heater_needed_peak_W") or {}).get("context") or {}).get("setpoint_C"),
            "battery_min_c": val("battery_min_C"), "battery_max_c": val("battery_max_C"), "limit_min_c": val("battery_limit_min_C"),
            "limit_max_c": val("battery_limit_max_C"), "battery_min_no_heater_c": val("battery_min_no_heater_C"),
            "heater_in_design_w": val("heater_in_design_W"), "source": "END-019 of this run (kpis_end019)"}


def end003_peaks(kpis_path: Path | None, design_path: Path | None) -> dict[str, Any] | None:
    """IF-003-006: the END-003 peaks the wheels are sized on (kpis_end003): momentum = max(peak angular momentum, peak wheel
    momentum), peak control torque; the largest principal inertia of the design END-003 used (spacecraft_definition) for the
    slew momentum. None without END-003 (today's rule: wheels declared for the class)."""
    if not kpis_path or not kpis_path.is_file():
        return None
    try:
        values = {k.get("id"): k.get("value") for k in json.loads(kpis_path.read_text(encoding="utf-8")).get("kpis") or []}
    except (OSError, ValueError, AttributeError):
        return None
    moms = [v for v in (_number(values.get("END-003.peak_momentum_Nms")), _number(values.get("END-003.peak_wheel_momentum_Nms"))) if v is not None]
    torque = _number(values.get("END-003.peak_control_torque_Nm"))
    if not moms or torque is None:
        return None
    out: dict[str, Any] = {"peak_momentum_nms": max(moms), "peak_torque_nm": torque, "source": "END-003 of this run (kpis_end003)"}
    try:
        inertia = json.loads(design_path.read_text(encoding="utf-8")).get("inertia_kg_m2") if design_path and design_path.is_file() else None
        out["inertia_max_kgm2"] = max(float(x) for x in inertia) if inertia else None
    except (OSError, ValueError, TypeError):
        pass
    return out


def run_end006(input_file: str, output_dir: str, run_id: str | None = None,
               log_callback: Callable[[str, str], Any] | None = None, stop_event: Any = None,
               star_root: str | None = None, run_output_dir: str | None = None,
               module_product_output_dir: str | None = None, module_results_dir: str | None = None, **_: Any) -> dict[str, Any]:
    def log(level: str, msg: str) -> None:
        if log_callback:
            log_callback(level, msg)

    module_root = Path(output_dir)
    product_dir = Path(module_product_output_dir) if module_product_output_dir else module_root / OUTPUT_DIRNAME
    results_dir = Path(module_results_dir) if module_results_dir else module_root / RESULTS_DIRNAME
    product_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)

    selector_root = _find_selector_root([star_root or "", run_output_dir or "", output_dir])
    if str(selector_root) not in sys.path:
        sys.path.insert(0, str(selector_root))
    from star_selector.api import (SelectorService, bom_rows, dumps, power_handoff,  # noqa: PLC0415
                                   requirements_to_params)

    payload = json.loads(Path(input_file).read_text(encoding="utf-8"))
    requirements = payload.get("requirements") or []
    # initial design (step 0, before the other modules) or final design (end of the workflow, with their results)
    phase = "initial" if str((payload.get("workflow_step") or {}).get("phase") or "").lower() == "initial" else "final"
    sfx = "_initial" if phase == "initial" else ""

    # 1. defaults of the module; 2. requirements; 3. approved inputs (first guesses never override the requirements)
    defaults_path = None
    for base in [Path(__file__).resolve(), Path(star_root or "."), Path(run_output_dir or ".")]:
        for parent in [base, *base.parents]:
            cand = parent / "Input" / "input_component_selector.json"
            if cand.is_file():
                defaults_path = cand
                break
        if defaults_path:
            break
    params: dict[str, Any] = {}
    if defaults_path:
        params = {k: v for k, v in json.loads(defaults_path.read_text(encoding="utf-8")).items() if k == "form_factor_u"}
        log("EXECUTION", f"END-006 defaults loaded from {defaults_path}")
    mapping = requirements_to_params(requirements)
    first_guess = _approved_inputs(payload.get("resolved_inputs") or [], defaults_only=True)
    params.update(first_guess)
    params.update({k: v for k, v in mapping["params"].items() if v is not None})
    approved = _approved_inputs(payload.get("resolved_inputs") or [], defaults_only=False)
    params.update(approved)
    # the CubeSat class: the smallest that carries the subsystems the mission needs (since 2026-10-15); a class the user
    # chose in the input-resolution step wins; a class written in the requirements is only reported
    forced = approved.get("form_factor_u")
    notes = [n for n in mapping["notes"] if "CubeSat class not stated" not in n]
    if forced:
        notes.append(f"CubeSat class chosen by the user: {forced}U")
    context = mission_context(payload) if phase == "final" else {}
    used = [k for k in ("altitude_km", "end003", "end004", "end016", "end019") if k in context]
    log("EXECUTION", f"END-006 {phase} design; class chosen by the user: {forced or 'no'}; products of this run used: {', '.join(used) or 'none'}")

    service = SelectorService()
    generated: list[str] = []
    started = datetime.now().isoformat()

    def write(path: Path, text: str) -> None:
        path.write_text(text, encoding="utf-8")
        generated.append(str(path))

    out_of_scope = mapping["out_of_scope"]
    # Inside STAR the domain check has already accepted the mission as a CubeSat one (2026-10-17): a maximum mass above
    # 24 kg ("mass not exceeding 100 kg") is met by any CubeSat, so it is a note, not a reason to skip.
    upper_mass = [m for m in out_of_scope if m.startswith("satellite mass up to")]
    if upper_mass:
        out_of_scope = [m for m in out_of_scope if m not in upper_mass]
        notes = list(notes) + [m.split(":")[0] + ": the request sets only a maximum, met by a CubeSat (STAR domain: CubeSat up to 24 kg)"
                               for m in upper_mass]
    result: dict[str, Any]
    if out_of_scope:
        result = {"ok": True, "error": None, "within_limits": False, "subsystems": [], "messages": out_of_scope}
        status, evidence = "skipped_out_of_scope", "Mission out of scope for the CubeSat selector: " + "; ".join(out_of_scope)
    else:
        result = service.design({"requirements": requirements, "context": context, "form_factor_u": forced}, with_images=True)
        mission = result["mission"]
        units = result["cubesat"]["class_u"]
        params["form_factor_u"] = units
        notes += mission["notes"]
        t = result["totals"]
        uncovered = [s["label"] for s in result["subsystems"] if not s["selected"]]
        status = "completed"
        how = "chosen by the user" if forced else "the smallest class that meets the performance the mission asks for"
        evidence = (f"{units}U CubeSat ({how}): {t['n_covered']} of {t['n_subsystems']} subsystems the mission needs; mass {t['mass_kg']:.3f} of "
                    f"{t['mass_limit_kg']:g} kg, volume {t['volume_m3']:.3e} of {t['volume_limit_m3']:.3e} m3; {len(mission['extras'])} subsystem(s) not required"
                    + ("" if result["within_limits"] else "; the subsystems together exceed the limits of the class")
                    + (f"; no component fits for: {', '.join(uncovered)}" if uncovered else "")
                    + (f"; {len(mission['unmet'])} requirement(s) not met: " + " ".join(mission["unmet"]).rstrip(".") if mission["unmet"] else "; requirements met") + ".")

    record = {"schema_version": 2, "module_id": MODULE_ID, "run_id": run_id, "generated_at": started, "status": status, "evidence": evidence,
              "phase": phase, "params": params, "notes": notes, "out_of_scope": out_of_scope, "requirements_mapping": mapping, "result": result}
    if status == "completed":
        sc = spacecraft_definition(result, phase, run_id)
        record["spacecraft"] = sc
        if phase == "initial":
            # the satellite every module of the workflow uses
            sc["design_iteration"] = 0
            write(product_dir / SPACECRAFT_FILE, dumps(sc))
            record["evidence"] = evidence = "Initial design, used by the other modules: " + evidence
        else:
            initial_path = upstream_product(payload, "spacecraft_definition") or product_dir / SPACECRAFT_FILE
            initial = json.loads(initial_path.read_text(encoding="utf-8")) if initial_path.is_file() else None
            changes = design_changes(initial, sc)
            used_iteration = int((initial or {}).get("design_iteration") or 0)
            record["initial_spacecraft"] = initial
            record["design_changes"] = changes
            # D(k): relative to the design the modules used in this iteration, D(k-1) (the initial design in the first pass)
            write(product_dir / "spacecraft_definition_final.json",
                  dumps({**sc, "design_iteration": used_iteration + 1, "used_design_iteration": used_iteration,
                         "changes_from_used_design": changes}))
            if initial is None:
                note = "no initial design in this run: the other modules did not use an END-006 satellite"
            elif changes:
                note = "the final design differs from the initial one the modules used: " + "; ".join(changes)
            else:
                note = "same satellite as the initial design the modules used"
            record["evidence"] = evidence = f"Final design ({note}): " + evidence
    write(product_dir / f"component_selector_results{sfx}.json", dumps(record))
    write(product_dir / f"component_selector_requirements_mapping{sfx}.json", dumps({"requirements": requirements, **mapping, "approved_inputs": approved}))
    if status == "completed":
        rows = bom_rows(result)
        if rows:
            with (product_dir / f"component_selector_bom{sfx}.csv").open("w", newline="", encoding="utf-8-sig") as fh:
                writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(rows)
            generated.append(str(product_dir / f"component_selector_bom{sfx}.csv"))
        write(product_dir / f"component_selector_power_handoff{sfx}.json", dumps(power_handoff(result)))

    # frontend payload and self-contained report (the GUI in view-only mode reads window.componentSelectorData;
    # the initial design goes to window.componentSelectorDataInitial, shown in the "Initial design" tab)
    var = "componentSelectorDataInitial" if phase == "initial" else "componentSelectorData"
    data = {**record}
    write(results_dir / f"component_selector_data{sfx}.js", f"window.{var} = " + dumps(data) + ";\n")
    gui_html = Path(__file__).resolve().parents[2] / "FrontEnd" / "web" / "modules" / "end006_results.html"   # the END-006 tab (only copy of the GUI)
    if gui_html.is_file():
        page = gui_html.read_text(encoding="utf-8")
        embedded = "<script>window.componentSelectorData = " + dumps(data).replace("</", "<\\/") + ";</script>\n"
        write(results_dir / f"component_selector_report{sfx}.html", page.replace("<script>\n(() => {", embedded + "<script>\n(() => {", 1))
    log("EXECUTION", f"END-006 {status}: {evidence}")
    if status == "completed":      # kpis_initial.json for the initial design, kpis.json for the final one
        write_module_kpis(MODULE_ID, module_root, run_id or "", phase, log=log)
    return {"status": status, "generated_artifacts": generated, "evidence": evidence}

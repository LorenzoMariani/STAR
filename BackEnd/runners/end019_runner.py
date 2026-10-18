"""STAR runner for END-019 Satellite Design Component Selector.

Called by the orchestrator (FrontEnd/star_frontend_v3.py -> StarApi.call_module_runner_or_placeholder) as
`runners.end019_runner.run_end019(input_file=..., output_dir=..., ...)`. Place this file in BackEnd/runners/.

The selector package (star_component_selector) is located through, in order:
  1. the STAR_COMPONENT_SELECTOR_ROOT environment variable;
  2. STAR/END019-ComponentSelector/star_component_selector (the module folder inside STAR, like the other
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

MODULE_ID = "END-019"
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
            candidates.append(parent / "END019-ComponentSelector" / SELECTOR_DIRNAME)   # module folder inside STAR
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
    """Values resolved in the missing-information step for END-019 (field proposed_value); empty values are ignored.

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


# Satellite shared by the STAR modules (2026-10-17): END-019 runs first (initial design, step 0 of the
# workflow) and writes spacecraft_definition.json, which END-001, END-003, END-004, END-010, END-016 and
# END-018 use; at the end of the workflow it runs again with their results (final design).
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
        "consumers_declared_peak_w": (result.get("breakdown") or {}).get("power_w") or {},
        "radios": {k: {"component": v.get("id"), "band": (v.get("specs") or {}).get("band"),
                       "has_receiver": (v.get("specs") or {}).get("has_receiver"),
                       "power_w_idle": (v.get("specs") or {}).get("power_w_idle"),
                       "power_w_tx": (v.get("specs") or {}).get("power_w_tx")}
                   for k, v in chosen.items() if str(k).startswith("comms")},
        "power_unknown": totals.get("power_unknown") or [],
        "components": {k: v.get("id") for k, v in chosen.items()},
        "conventions": "body frame: +Z payload boresight (nadir), long axis of the envelope along Z; envelope X x Y x Z; "
                       "Cd and Cr are STAR defaults; area_mean_projected = surface / 4 (orientation average)",
    }


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


def mission_context(modules_output: Path | None) -> dict[str, Any]:
    """Products of the same run that END-019 uses when they are there: the orbit altitudes of END-001 (GSD and swath of the imagers),
    the END-004 power budget (energy the battery gives in an orbit -> battery capacity) and the END-016 space-safety summary
    (disposal delta-v -> propulsion)."""
    ctx: dict[str, Any] = {}
    if not modules_output:
        return ctx
    alts = []
    for p in sorted((modules_output / "END-001" / "output_constellation_optimizer").glob("satellite_*.json")):
        try:
            orbit = json.loads(p.read_text(encoding="utf-8")).get("orbit") or {}
            alts.append((float(orbit["alt_perigee_m"]) + float(orbit["alt_apogee_m"])) / 2000.0)
        except (OSError, ValueError, KeyError, TypeError):
            continue
    if alts:
        ctx["altitude_km"] = [min(alts), max(alts)]
        ctx["altitude_source"] = f"END-001 of this run ({len(alts)} satellite orbits)"
    for key, path in (("end004", modules_output / "END-004" / "output_power_budget" / "power_budget_summary.json"),
                      ("end016", modules_output / "END-016" / "output_collision_avoidance" / "space_safety_summary.json")):
        if path.is_file():
            try:
                ctx[key] = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
    return ctx


def run_end019(input_file: str, output_dir: str, run_id: str | None = None,
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
        log("EXECUTION", f"END-019 defaults loaded from {defaults_path}")
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
    context = mission_context(Path(output_dir).resolve().parent) if phase == "final" else {}
    used = [k for k in ("altitude_km", "end004", "end016") if k in context]
    log("EXECUTION", f"END-019 {phase} design; class chosen by the user: {forced or 'no'}; products of this run used: {', '.join(used) or 'none'}")

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
        status, evidence = "skipped", "Mission out of scope for the CubeSat selector: " + "; ".join(out_of_scope)
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
            write(product_dir / SPACECRAFT_FILE, dumps(sc))
            record["evidence"] = evidence = "Initial design, used by the other modules: " + evidence
        else:
            initial_path = product_dir / SPACECRAFT_FILE
            initial = json.loads(initial_path.read_text(encoding="utf-8")) if initial_path.is_file() else None
            changes = design_changes(initial, sc)
            record["initial_spacecraft"] = initial
            record["design_changes"] = changes
            write(product_dir / "spacecraft_definition_final.json", dumps({**sc, "changes_from_initial": changes}))
            if initial is None:
                note = "no initial design in this run: the other modules did not use an END-019 satellite"
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
    gui_html = Path(__file__).resolve().parents[2] / "FrontEnd" / "web" / "modules" / "end019_results.html"   # the END-019 tab (only copy of the GUI)
    if gui_html.is_file():
        page = gui_html.read_text(encoding="utf-8")
        embedded = "<script>window.componentSelectorData = " + dumps(data).replace("</", "<\\/") + ";</script>\n"
        write(results_dir / f"component_selector_report{sfx}.html", page.replace("<script>\n(() => {", embedded + "<script>\n(() => {", 1))
    log("EXECUTION", f"END-019 {status}: {evidence}")
    return {"status": status, "generated_artifacts": generated, "evidence": evidence}

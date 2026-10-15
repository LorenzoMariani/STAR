"""STAR runner for END-019 Satellite Design Component Selector.

Called by the orchestrator (FrontEnd/star_frontend_v2.py -> StarApi.call_module_runner_or_placeholder) as
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
    params.setdefault("form_factor_u", 6)
    notes = list(mapping["notes"])
    if "form_factor_u" not in mapping["params"] and "form_factor_u" not in approved:
        notes.append(f"CubeSat class not specified in the requirements or edited by the user: {params['form_factor_u']:g}U (first guess) used")
    log("EXECUTION", f"END-019 parameters: {json.dumps(params, ensure_ascii=False)}")

    service = SelectorService()
    generated: list[str] = []
    started = datetime.now().isoformat()

    def write(path: Path, text: str) -> None:
        path.write_text(text, encoding="utf-8")
        generated.append(str(path))

    out_of_scope = mapping["out_of_scope"]
    result: dict[str, Any]
    if out_of_scope:
        result = {"ok": True, "error": None, "within_limits": False, "subsystems": [], "messages": out_of_scope}
        status, evidence = "skipped", "Mission out of scope for the CubeSat selector: " + "; ".join(out_of_scope)
    else:
        result = service.select({"form_factor_u": int(params["form_factor_u"])}, with_images=True)
        t = result["totals"]
        uncovered = [s["label"] for s in result["subsystems"] if not s["selected"]]
        status = "completed"
        evidence = (f"{t['n_covered']} of {t['n_subsystems']} subsystems with a component that fits a {int(params['form_factor_u'])}U; mass {t['mass_kg']:.3f} of "
                    f"{t['mass_limit_kg']:g} kg, volume {t['volume_m3']:.3e} of {t['volume_limit_m3']:.3e} m3"
                    + ("" if result["within_limits"] else "; the subsystems together exceed the limits of the class")
                    + (f"; no component fits for: {', '.join(uncovered)}" if uncovered else "") + ".")

    record = {"schema_version": 2, "module_id": MODULE_ID, "run_id": run_id, "generated_at": started, "status": status, "evidence": evidence,
              "params": params, "notes": notes, "out_of_scope": out_of_scope, "requirements_mapping": mapping, "result": result}
    write(product_dir / "component_selector_results.json", dumps(record))
    write(product_dir / "component_selector_requirements_mapping.json", dumps({"requirements": requirements, **mapping, "approved_inputs": approved}))
    if status == "completed":
        rows = bom_rows(result)
        if rows:
            with (product_dir / "component_selector_bom.csv").open("w", newline="", encoding="utf-8-sig") as fh:
                writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(rows)
            generated.append(str(product_dir / "component_selector_bom.csv"))
        write(product_dir / "component_selector_power_handoff.json", dumps(power_handoff(result)))

    # frontend payload and self-contained report (the GUI in view-only mode reads window.componentSelectorData)
    data = {**record}
    write(results_dir / "component_selector_data.js", "window.componentSelectorData = " + dumps(data) + ";\n")
    gui_html = selector_root / "gui" / "component_selector.html"
    if gui_html.is_file():
        page = gui_html.read_text(encoding="utf-8")
        embedded = "<script>window.componentSelectorData = " + dumps(data).replace("</", "<\\/") + ";</script>\n"
        write(results_dir / "component_selector_report.html", page.replace("<script>\n(() => {", embedded + "<script>\n(() => {", 1))
    log("EXECUTION", f"END-019 {status}: {evidence}")
    return {"status": status, "generated_artifacts": generated, "evidence": evidence}

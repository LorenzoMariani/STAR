"""STAR smoke test (2026-10-15): the whole STAR pipeline, headless, in a few minutes.

It drives the same StarApi as the window (FrontEnd/star_frontend_v5.py), step by
step as the user does: new run, reviewed requirements, rule-based mission
planning, approved workflow, resolved and approved module inputs, execution
in the chosen run mode (default 'test': every module with its fastest
settings, results not meaningful), then a table with the status and the time
of every module. END-007 (Unreal, always in full) is left out unless asked.

    python FrontEnd/star_smoke_test.py                      # test mode, v7 proposal, no END-007
    python FrontEnd/star_smoke_test.py --proposal Input/.../Mission_Proposal_v6.txt --requirements Input/.../Mission_Proposal_v6_requirements.json
    python FrontEnd/star_smoke_test.py --mode full --level 1 --with-end007
    python FrontEnd/star_smoke_test.py --proposal Input/.../Mission_Proposal_v5.txt --requirements none

The run is written under Output/ (RUN_SMOKETEST_<timestamp>) and can be opened
in the results workspace. Exit code 0 when every module completed or was
skipped on purpose (out of its domain), 1 otherwise.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
STAR_ROOT = HERE.parent
SAMPLES = STAR_ROOT / "Input" / "input_base_knowledge" / "sample_inputs"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(STAR_ROOT / "BackEnd"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mode", default="test", choices=["test", "full"], help="STAR run mode (default test)")
    ap.add_argument("--level", type=int, default=3, choices=[1, 2, 3, 4, 5], help="accuracy level of a full run (default 3)")
    ap.add_argument("--proposal", default=str(SAMPLES / "Mission_Proposal_v7.txt"), help="mission request document (.txt or .docx)")
    ap.add_argument("--requirements", default=str(SAMPLES / "Mission_Proposal_v7_requirements.json"),
                    help="JSON with the reviewed requirements, or 'none' for the rule-based extraction of the document")
    ap.add_argument("--with-end007", action="store_true", help="keep END-007 (Unreal, always in full) in the workflow")
    ap.add_argument("--add", nargs="*", default=[], metavar="END-XXX",
                    help="modules added to the planned workflow, as a user edit of the review (e.g. --add END-008)")
    args = ap.parse_args()

    import star_frontend_v5 as fe  # noqa: PLC0415  (the window module; no window is opened)

    api = fe.StarApi()
    api.add_log = lambda kind, msg: print(f"[{kind}] {msg}"[:240], flush=True) if kind in ("ERROR", "WARNING") else None
    t_start = time.time()
    source = Path(args.proposal)

    # 1. run and document (what upload_document does after the file dialog)
    api.create_run_folder(f"RUN_SMOKETEST_{datetime.now():%Y%m%d_%H%M%S}")
    api.reset_run_state_after_new_upload()
    destination = api.current_run_path / "input" / source.name
    shutil.copy2(source, destination)
    api.uploaded_text = api.read_document_text(source)
    api.input_document_filename = source.name
    api.input_document_original_path = str(source)
    api.input_document_saved_relative_path = destination.relative_to(api.current_run_path).as_posix()
    api.input_document_saved_absolute_path = str(destination)

    # 2. requirements
    if args.requirements.lower() == "none":
        reqs = api.rule_based_requirement_extraction(api.uploaded_text)
    else:
        reqs = json.loads(Path(args.requirements).read_text(encoding="utf-8"))["requirements"]
    reqs = [{"status": "extracted", "source": "mission_request_document", **r} for r in reqs]
    check(api.save_reviewed_requirements(reqs), "save requirements")

    # 3. planning (rule-based, the LLM-free path) and approval
    check(api.propose_workflow("Rule-based MVP"), "mission planning")
    workflow = [dict(s) for s in api.workflow_steps if args.with_end007 or s.get("module_id") != "END-007"]
    planned = {s.get("module_id") for s in workflow}
    for module_id in (m.upper() for m in args.add):
        if module_id not in planned:
            module = api.get_module_by_id(module_id)
            check({"ok": bool(module), "error": f"{module_id} not in the registry"}, f"add {module_id}")
            workflow.append(api.build_workflow_step_for_module(module))
    if [s.get("module_id") for s in workflow] != [s.get("module_id") for s in api.workflow_steps]:
        check(api.save_reviewed_workflow(workflow), "reviewed workflow (END-007 left out, --add modules)")
    check(api.approve_workflow(), "approve workflow")

    # 4. module inputs (registry first guesses) and approval
    check(api.analyze_missing_information("Registry-driven MVP"), "resolve module inputs")
    check(api.approve_missing_information(), "approve module inputs")

    # 5. execution
    modes = api.set_run_mode(args.mode, args.level)
    check(modes, "run mode")
    plan = [s.get("module_id") for s in api.workflow_steps]
    est = modes["estimates"]["full"][str(args.level)] if args.mode == "full" else modes["estimates"]["test"]
    print(f"Run {api.current_run_id}: mode {api.run_mode_label()}, workflow {plan}, estimated {est['total_s']} s", flush=True)
    result = api.execute_workflow()
    rows = result.get("execution_results") or api.execution_results or []
    print(f"\n{'module':8s} {'status':10s} {'time':>8s} {'est.':>7s}  evidence")
    bad = 0
    for r in rows:
        mid = r.get("module_id", "?")
        status = str(r.get("status", "?"))
        try:
            secs = (datetime.fromisoformat(str(r["completed_at"])) - datetime.fromisoformat(str(r["started_at"]))).total_seconds()
        except (KeyError, ValueError, TypeError):
            secs = None
        ok = status in ("completed", "completed_with_fallback", "skipped_out_of_scope")
        bad += not ok
        print(f"{mid:8s} {status:24s} {(f'{float(secs):.0f} s' if secs is not None else '-'):>8s} "
              f"{str(round(est['per_module'].get(mid, 0))) + ' s':>7s}  {str(r.get('evidence', ''))[:150]}")
    bad += check_products(api, rows)
    bad += check_convergence(api)
    print(f"\n{'PASS' if not bad and rows else 'FAIL'}: {len(rows)} module(s), {bad} not completed or inconsistent, total {time.time() - t_start:.0f} s; run folder {api.current_run_path}")
    return 0 if not bad and rows else 1


def check_products(api, rows) -> int:
    """Phase B: the products the registry promises are in the run, every module received only what it consumes, the workflow
    graph is saved; writes tests/fixtures/smoke_products_manifest.json (files under modules_output) for the CI contract test."""
    problems: list[str] = []
    run = api.current_run_path
    modules_output = run / "modules_output"
    graph = api.workflow_graph_of_steps(api.workflow_steps)
    completed = {r.get("node") or r.get("module_id") for r in rows if r.get("status") in ("completed", "completed_with_fallback")}
    for node_id in graph.node_ids:
        if node_id in completed or (graph.node(node_id).phase is None and graph.node(node_id).module_id in completed):
            for product in graph.missing_outputs(node_id, modules_output):
                problems.append(f"{node_id}: guaranteed product {product} missing from the run")
    prov_path = run / "star_provenance.json"
    if not prov_path.is_file():
        problems.append("star_provenance.json not written")
    else:
        prov = json.loads(prov_path.read_text(encoding="utf-8"))
        in_prov = {m.get("node") for m in prov.get("modules", [])}
        for r in rows:
            if (r.get("node") or r.get("module_id")) not in in_prov:
                problems.append(f"{r.get('node') or r.get('module_id')}: missing from star_provenance.json")
        for m in prov.get("modules", []):
            if m.get("status") == "failed" or not m.get("evidence"):
                problems.append(f"{m.get('node')}: provenance status {m.get('status')} / empty evidence")
            if m.get("status") == "completed_with_fallback":
                print(f"  fallback {m.get('fallback_severity')}: {m.get('node')} - " + "; ".join(f['item'] for f in m.get("fallbacks", [])))
    if not (run / "planning" / "workflow_graph.json").is_file():
        problems.append("planning/workflow_graph.json not written")
    for path in sorted((run / "module_inputs").glob("STEP_*_input.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        step = payload.get("workflow_step") or {}
        module_id = str(step.get("module_id", "")).upper()
        node_id = f"{module_id}/{step['phase']}" if step.get("phase") in ("initial", "final") else module_id
        if node_id not in graph.node_ids:
            continue
        consumed = {str(c.get("product")) for c in graph.node(node_id).consumes}
        if set(payload.get("upstream_products") or {}) != consumed:
            problems.append(f"{path.name}: upstream_products {sorted(payload.get('upstream_products') or {})} != consumed {sorted(consumed)}")
    manifest = {"generated_from": run.name, "files": {
        m.name: sorted(p.relative_to(m).as_posix() for p in m.rglob("*") if p.is_file())
        for m in sorted(modules_output.iterdir()) if m.is_dir()}}
    target = STAR_ROOT / "tests" / "fixtures" / "smoke_products_manifest.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    for line in problems:
        print(f"[PRODUCTS] {line}", flush=True)
    print(f"[PRODUCTS] {len(problems)} problem(s); manifest {target}", flush=True)
    return len(problems)


def check_convergence(api) -> int:
    """Phase F7: the design loop ends converged (or not_converged on CEF-BATTERY only) within 3 iterations, every criterion passes, the iterations are archived, END-001
    ran once, END-010 ran only if its trigger fired, REQ-020 is met. A failure prints the failing criteria and their values."""
    problems: list[str] = []
    run = api.current_run_path
    path = run / "convergence.json"
    if not path.is_file():
        print("[CEF] convergence.json not written", flush=True)
        return 1
    conv = json.loads(path.read_text(encoding="utf-8"))
    iterations = conv.get("iterations") or []
    # accepted outcome (2026-10-23): no catalogued heater covers the cold-case battery, so the loop may end not_converged
    # with CEF-BATTERY as the only failing criterion; anything else failing is a regression
    converged = conv.get("status") == "converged"
    if not converged and conv.get("status") != "not_converged":
        problems.append(f"status {conv.get('status')} (expected converged or not_converged): {conv.get('reason')}")
    if not converged and sorted(conv.get("failing_criteria") or []) != ["CEF-BATTERY"]:
        problems.append(f"failing criteria {conv.get('failing_criteria')} (expected only CEF-BATTERY)")
    if int(conv.get("iterations_run") or 0) > 3 or len(iterations) != int(conv.get("iterations_run") or 0):
        problems.append(f"iterations_run {conv.get('iterations_run')} / {len(iterations)} recorded (max 3)")
    for it in iterations[-1:]:
        for c in it.get("criteria", []):
            if c.get("status") not in ("pass", "not_applicable") and (converged or c.get("id") != "CEF-BATTERY"):
                problems.append(f"iteration {it['k']} {c.get('id')} {c.get('status')}: {c.get('reason') or c.get('values')} (threshold {c.get('threshold')})")
    for it in iterations:
        if not (run / "cef" / f"iteration_{int(it['k']):02d}").is_dir():
            problems.append(f"cef/iteration_{int(it['k']):02d} missing")
    # END-001 is fixed: one entry in the results/provenance, and never in a loop iteration
    prov = json.loads((run / "star_provenance.json").read_text(encoding="utf-8")) if (run / "star_provenance.json").is_file() else {}
    n001 = sum(1 for m in prov.get("modules", []) if m.get("node") == "END-001")
    if n001 != 1:
        problems.append(f"END-001 recorded {n001} times (expected once)")
    if any(n.get("node") == "END-001" for it in iterations for n in it.get("nodes", [])):
        problems.append("END-001 re-run inside the loop")
    # END-010 follows its trigger: re-run exactly when fired
    for post in conv.get("post_loop_nodes") or []:
        runs = sum(1 for m in prov.get("modules", []) if m.get("node") == post.get("node"))
        expected = 1 + (1 if post.get("fired") else 0)
        if runs != expected:
            problems.append(f"{post.get('node')} recorded {runs} times, trigger fired={post.get('fired')} (expected {expected})")
    comp_path = run / "compliance" / "compliance.json"
    comp = json.loads(comp_path.read_text(encoding="utf-8")) if comp_path.is_file() else {}
    reqs = comp.get("requirements") or comp.get("items") or []
    req20 = next((r for r in reqs if str(r.get("id") or r.get("requirement_id")) == "REQ-020"), None)
    want20 = "met" if converged else "not_met"
    if not req20 or req20.get("status") != want20:
        problems.append(f"REQ-020 {None if not req20 else req20.get('status')} (expected {want20}): {None if not req20 else req20.get('reason')}")
    for line in problems:
        print(f"[CEF] {line}", flush=True)
    print(f"[CEF] {conv.get('status')} after {conv.get('iterations_run')} iteration(s); {len(problems)} problem(s)", flush=True)
    return len(problems)


def check(result: dict, step: str) -> None:
    if not isinstance(result, dict) or not result.get("ok", True):
        raise SystemExit(f"Smoke test stopped at '{step}': {result.get('error') if isinstance(result, dict) else result}")


if __name__ == "__main__":
    sys.exit(main())

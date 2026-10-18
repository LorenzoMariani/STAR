"""STAR smoke test (2026-10-15): the whole STAR pipeline, headless, in a few minutes.

It drives the same StarApi as the window (FrontEnd/star_frontend_v4.py), step by
step as the user does: new run, reviewed requirements, rule-based mission
planning, approved workflow, resolved and approved module inputs, execution
in the chosen run mode (default 'test': every module with its fastest
settings, results not meaningful), then a table with the status and the time
of every module. END-007 (Unreal, always in full) is left out unless asked.

    python FrontEnd/star_smoke_test.py                      # test mode, v6 proposal, no END-007
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
    ap.add_argument("--proposal", default=str(SAMPLES / "Mission_Proposal_v6.txt"), help="mission request document (.txt or .docx)")
    ap.add_argument("--requirements", default=str(SAMPLES / "Mission_Proposal_v6_requirements.json"),
                    help="JSON with the reviewed requirements, or 'none' for the rule-based extraction of the document")
    ap.add_argument("--with-end007", action="store_true", help="keep END-007 (Unreal, always in full) in the workflow")
    args = ap.parse_args()

    import star_frontend_v4 as fe  # noqa: PLC0415  (the window module; no window is opened)

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
    if len(workflow) != len(api.workflow_steps):
        check(api.save_reviewed_workflow(workflow), "workflow without END-007")
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
        ok = status in ("completed", "skipped")
        bad += not ok
        print(f"{mid:8s} {status:10s} {(f'{float(secs):.0f} s' if secs is not None else '-'):>8s} "
              f"{str(round(est['per_module'].get(mid, 0))) + ' s':>7s}  {str(r.get('evidence', ''))[:150]}")
    print(f"\n{'PASS' if not bad and rows else 'FAIL'}: {len(rows)} module(s), {bad} not completed, total {time.time() - t_start:.0f} s; run folder {api.current_run_path}")
    return 0 if not bad and rows else 1


def check(result: dict, step: str) -> None:
    if not isinstance(result, dict) or not result.get("ok", True):
        raise SystemExit(f"Smoke test stopped at '{step}': {result.get('error') if isinstance(result, dict) else result}")


if __name__ == "__main__":
    sys.exit(main())

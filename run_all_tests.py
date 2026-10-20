"""Run every STAR test suite and print one summary (2026-10-19).

    python run_all_tests.py                    all the suites
    python run_all_tests.py END-003 END-006    only these
    python run_all_tests.py --list             the suites and where they are
    python run_all_tests.py SMOKE              the whole pipeline (FrontEnd/star_smoke_test.py), only when named

MATLAB suites (matlab.unittest, all in one MATLAB session):
    END-001  tests/test_end001_constellation.m   (END-001 is a git submodule: its STAR tests stay in this repository)
    END-003  END003-AttitudePropagation/tests
    END-004  END004-PowerBudget/tests
Python suites (unittest):
    END-006  END006-ComponentSelector/star_component_selector/tests

Run only when named (2026-10-20):
    SMOKE    FrontEnd/star_smoke_test.py   the whole STAR pipeline headless in test mode (Mission_Proposal_v7, without
             END-007), 4 to 7 minutes; needs MATLAB, pywebview and the module data and builds of the STAR PC (END-010:
             lib/data/DE440.mat and the Unity build)

MATLAB is MATLAB_EXECUTABLE, otherwise matlab on the PATH, otherwise the newest C:/Program Files/MATLAB/R*/bin/matlab.exe.
Exit code 0 only when every selected suite ran and passed (a suite that could not run counts as a failure).
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

STAR_ROOT = Path(__file__).resolve().parent
SUITES = [
    {"id": "END-001", "kind": "matlab", "path": "tests/test_end001_constellation.m"},
    {"id": "END-003", "kind": "matlab", "path": "END003-AttitudePropagation/tests"},
    {"id": "END-004", "kind": "matlab", "path": "END004-PowerBudget/tests"},
    {"id": "END-006", "kind": "python", "path": "END006-ComponentSelector/star_component_selector",
     "args": ["-m", "unittest", "discover", "-s", "tests", "-t", "."]},
]
# not in the default run: python run_all_tests.py SMOKE
OPTIONAL_SUITES = [
    {"id": "SMOKE", "kind": "script", "path": "FrontEnd/star_smoke_test.py"},
]

MATLAB_SCRIPT = r"""
suites = {%(paths)s};
names = {%(names)s};
out = struct('suite', {}, 'passed', {}, 'failed', {}, 'incomplete', {}, 'seconds', {}, 'not_passed', {});
for i = 1:numel(suites)
    fprintf('\n===== %%s: %%s =====\n', names{i}, suites{i});
    t0 = tic;
    try
        res = runtests(suites{i});
        np = {res(~[res.Passed]).Name};
        out(end+1) = struct('suite', names{i}, 'passed', nnz([res.Passed]), 'failed', nnz([res.Failed]), ...
            'incomplete', nnz([res.Incomplete]), 'seconds', toc(t0), 'not_passed', {np}); %%#ok<SAGROW>
    catch err
        out(end+1) = struct('suite', names{i}, 'passed', 0, 'failed', 1, 'incomplete', 0, 'seconds', toc(t0), ...
            'not_passed', {{['suite error: ' err.message]}}); %%#ok<SAGROW>
    end
    close all force;
end
fid = fopen('%(json)s', 'w');
fprintf(fid, '%%s', jsonencode(out));
fclose(fid);
"""


def find_matlab() -> str | None:
    """As the STAR runners: MATLAB_EXECUTABLE, then matlab on the PATH, then the newest Windows install."""
    exe = os.environ.get("MATLAB_EXECUTABLE", "").strip()
    if exe and (Path(exe).is_file() or shutil.which(exe)):
        return exe
    if shutil.which("matlab"):
        return "matlab"
    installs = sorted(glob.glob("C:/Program Files/MATLAB/R*/bin/matlab.exe"))
    return installs[-1] if installs else None


def matlab_literal(text: str) -> str:
    return "'" + text.replace("\\", "/").replace("'", "''") + "'"


def run_matlab(suites: list[dict]) -> list[dict]:
    """All the MATLAB suites in one session; MATLAB's output goes to the console."""
    exe = find_matlab()
    if exe is None:
        return [{"suite": s["id"], "status": "NOT RUN", "detail": "MATLAB not found (set MATLAB_EXECUTABLE)"} for s in suites]
    with tempfile.TemporaryDirectory() as tmp:
        result_json = Path(tmp) / "results.json"
        script = Path(tmp) / "star_run_matlab_suites.m"
        script.write_text(MATLAB_SCRIPT % {
            "paths": ", ".join(matlab_literal(str(STAR_ROOT / s["path"])) for s in suites),
            "names": ", ".join(matlab_literal(s["id"]) for s in suites),
            "json": str(result_json).replace("\\", "/").replace("'", "''"),
        }, encoding="utf-8")
        command = f"cd({matlab_literal(str(STAR_ROOT))}); run({matlab_literal(str(script))});"
        proc = subprocess.run([exe, "-batch", command], cwd=STAR_ROOT)
        if not result_json.is_file():
            return [{"suite": s["id"], "status": "NOT RUN", "detail": f"MATLAB ended with code {proc.returncode} before the results"}
                    for s in suites]
        data = json.loads(result_json.read_text(encoding="utf-8"))
    rows = []
    for r in data if isinstance(data, list) else [data]:
        not_passed = r.get("not_passed") or []
        if isinstance(not_passed, str):
            not_passed = [not_passed]
        status = "PASS" if r["failed"] == 0 and r["incomplete"] == 0 else ("FAIL" if r["failed"] else "INCOMPLETE")
        rows.append({"suite": r["suite"], "status": status, "seconds": r["seconds"],
                     "detail": f"{r['passed']} passed, {r['failed']} failed, {r['incomplete']} incomplete",
                     "not_passed": not_passed})
    return rows


def run_python(suite: dict) -> dict:
    print(f"\n===== {suite['id']}: {suite['path']} =====", flush=True)
    t0 = time.perf_counter()
    proc = subprocess.run([sys.executable, *suite["args"]], cwd=STAR_ROOT / suite["path"], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    seconds = time.perf_counter() - t0
    text = proc.stdout + proc.stderr
    ran = re.search(r"Ran (\d+) tests?", text)
    tail = re.search(r"^(OK.*|FAILED.*)$", text, re.MULTILINE)
    failed = re.findall(r"^(?:FAIL|ERROR): (\S+)", text, re.MULTILINE)
    print(text if proc.returncode else (tail.group(1) if tail else text[-2000:]), flush=True)
    return {"suite": suite["id"], "status": "PASS" if proc.returncode == 0 else "FAIL", "seconds": seconds,
            "detail": f"{ran.group(1) if ran else '?'} tests, {tail.group(1) if tail else 'no unittest summary'}",
            "not_passed": failed}


def run_script(suite: dict) -> dict:
    """A script with its own report (the pipeline smoke test): output shown while it runs, exit code 0 = pass."""
    print(f"\n===== {suite['id']}: {suite['path']} =====", flush=True)
    t0 = time.perf_counter()
    proc = subprocess.Popen([sys.executable, suite["path"], *suite.get("args", [])], cwd=STAR_ROOT, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                            env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    lines = []
    for line in proc.stdout:
        print(line, end="", flush=True)
        lines.append(line.rstrip("\n"))
    proc.wait()
    seconds = time.perf_counter() - t0
    # star_smoke_test.py: a table "module status time est. evidence" and a last line "PASS: ..." / "FAIL: ...",
    # or "Smoke test stopped at '<step>': ..." before the execution
    tail = next((x for x in reversed(lines) if re.match(r"(PASS|FAIL): |Smoke test stopped", x)), None)
    head = next((i for i, x in enumerate(lines) if re.match(r"module\s+status\s", x)), len(lines))
    not_passed = [f"{m.group(1)} {m.group(2)}" for x in lines[head + 1:]
                  if (m := re.match(r"(END-\d{3})\s+(\S+)\s", x)) and m.group(2) not in ("completed", "skipped")]
    return {"suite": suite["id"], "status": "PASS" if proc.returncode == 0 else "FAIL", "seconds": seconds,
            "detail": tail.split("; run folder")[0] if tail else f"ended with code {proc.returncode}, no report",
            "not_passed": not_passed}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the STAR test suites (MATLAB and Python) and print a summary.")
    parser.add_argument("suites", nargs="*", help="suite ids to run (default: all but SMOKE), e.g. END-003 END-006")
    parser.add_argument("--list", action="store_true", help="list the suites and exit")
    args = parser.parse_args()
    known = SUITES + OPTIONAL_SUITES
    if args.list:
        for s in known:
            print(f"{s['id']:8} {s['kind']:7} {s['path']}" + ("   (only when named)" if s in OPTIONAL_SUITES else ""))
        return 0
    wanted = [x.upper() for x in args.suites]
    unknown = [x for x in wanted if x not in {s["id"] for s in known}]
    if unknown:
        parser.error(f"unknown suite(s) {', '.join(unknown)}; known: {', '.join(s['id'] for s in known)}")
    chosen = [s for s in known if s["id"] in wanted] if wanted else SUITES

    t0 = time.perf_counter()
    rows = []
    matlab_suites = [s for s in chosen if s["kind"] == "matlab"]
    if matlab_suites:
        rows += run_matlab(matlab_suites)
    rows += [run_python(s) for s in chosen if s["kind"] == "python"]
    rows += [run_script(s) for s in chosen if s["kind"] == "script"]
    order = {s["id"]: i for i, s in enumerate(known)}
    rows.sort(key=lambda r: order[r["suite"]])

    print("\n" + "=" * 78)
    print(f"{'suite':8} {'result':11} {'time':>8}  details")
    for r in rows:
        secs = f"{r['seconds']:.0f} s" if "seconds" in r else "-"
        print(f"{r['suite']:8} {r['status']:11} {secs:>8}  {r['detail']}")
        for name in r.get("not_passed") or []:
            print(f"{'':30}- {name}")
    ok = all(r["status"] == "PASS" for r in rows)
    print("=" * 78)
    print(f"{'ALL SUITES PASSED' if ok else 'SOME SUITES DID NOT PASS'} in {time.perf_counter() - t0:.0f} s")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

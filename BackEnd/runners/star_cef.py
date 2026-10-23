"""STAR CEF loop controller (phase F, 2026-10-23): the design loop between the modules and END-006's final design.

Pure Python (PyYAML + the other ``runners`` modules), testable without the app: the orchestrator passes a ``run_node`` callback.

Iteration 1 is the ordinary workflow, run by the orchestrator. ``CefLoop.run`` then takes over::

    evaluate the criteria of iteration k and archive it  ->  converged?  -> post-loop nodes, end
                                                          ->  k == max    -> not_converged, end
                                                          ->  stalled?    -> stalled, end
                                                          ->  promote D(k) over spacecraft_definition, re-run the loop nodes

D(k) is the design END-006/final produced in iteration k; the modules of iteration k+1 use it as their ``spacecraft_definition``
(the registry ``feeds_back_to`` edge). The node sets come from the workflow graph (``loop_nodes`` / ``post_loop_nodes``), the
criteria from ``Input/input_base_knowledge/config/cef_loop.yaml`` (global KPI ids, thresholds in the syntax of
requirement_kpi_rules.yaml), the post-loop triggers from the registry ``cef_loop.rerun_on``.

Files in the run folder: ``convergence.json`` (rewritten after every step) and ``cef/iteration_0k/`` (the design used and the
one produced, the process results and the declared products of the nodes run in the iteration; html and image products are
left out, nothing is deleted). ``convergence.json.status``: converged | not_converged | stalled | interrupted | stopped |
not_applicable (``running`` while the loop is working). Not converged is an outcome, not an error.
"""
from __future__ import annotations

import hashlib
import json
import math
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import yaml

try:
    from . import star_kpis as K
    from . import star_status
    from .star_runner_io import design_fingerprint
except ImportError:                      # imported as a top-level module (runners folder on sys.path)
    import star_kpis as K
    import star_status
    from star_runner_io import design_fingerprint

CONFIG_PATH = Path(__file__).resolve().parents[2] / "Input" / "input_base_knowledge" / "config" / "cef_loop.yaml"

CONVERGED, NOT_CONVERGED, STALLED = "converged", "not_converged", "stalled"
INTERRUPTED, STOPPED, NOT_APPLICABLE, RUNNING = "interrupted", "stopped", "not_applicable", "running"
PASS, FAIL, N_A, NOT_EVALUABLE = "pass", "fail", "not_applicable", "not_evaluable"

ARCHIVE_SKIP_FORMATS = ("html", "image")      # reports with images: a few MB per iteration instead of about 100
ARCHIVE_MAX_BYTES = 25_000_000
VOLATILE_KEYS = {"generated_at", "run_id", "design_iteration", "promoted_from", "_source_path", "changes_from_initial",
                 "changes_from_used_design", "timestamp"}
EPS = 1e-9


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    data = yaml.safe_load(Path(path or CONFIG_PATH).read_text(encoding="utf-8")) or {}
    data.setdefault("max_iterations", 3)
    data.setdefault("stall_mass_rel", 0.001)
    data.setdefault("criteria", [])
    return data


def kpi_module(kpi_id: str) -> str:
    return str(kpi_id).split(".", 1)[0]


def kpi_node(kpi_id: str) -> str:
    """Workflow node of a KPI id: END-006's KPIs of the loop come from its final node."""
    module = kpi_module(kpi_id)
    return f"{module}/final" if module == "END-006" else module


def criteria_nodes(config: dict[str, Any]) -> list[str]:
    """Nodes whose KPIs the criteria read (used to choose the loop nodes)."""
    out: list[str] = []
    for c in config.get("criteria", []):
        for chk in _all_checks(c):
            for kid in _check_kpis(chk):
                node = kpi_node(kid)
                if node not in out:
                    out.append(node)
    return out


def _all_checks(criterion: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(x) for x in (criterion.get("checks") or [])]


def _check_kpis(check: dict[str, Any]) -> list[str]:
    ids = [check["kpi"]] if check.get("kpi") else []
    thr = check.get("threshold")
    if isinstance(thr, dict):
        ids += [thr[k] for k in ("kpi", "kpi_limit") if thr.get(k)]
    ref = check.get("ref")
    if isinstance(ref, dict) and ref.get("kpi"):
        ids.append(ref["kpi"])
    return [str(i) for i in ids]


# --------------------------------------------------------------------------- criteria (pure functions)
def _number(v: Any) -> float | None:
    if isinstance(v, bool) or v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def _value_of(kpis: dict[str, Any], kpi_id: str) -> Any:
    entry = kpis.get(kpi_id)
    return entry.get("value") if isinstance(entry, dict) else entry


def _limit_of(kpis: dict[str, Any], kpi_id: str) -> Any:
    entry = kpis.get(kpi_id)
    a = entry.get("assessment") if isinstance(entry, dict) else None
    return a.get("threshold") if isinstance(a, dict) else None


def _fmt(v: Any) -> str:
    n = _number(v)
    return f"{n:.6g}" if n is not None else str(v)


def _na(reason: str) -> dict[str, Any]:
    return {"status": N_A, "reason": reason}


def _missing(kpi_id: str, failed: dict[str, str], inactive: dict[str, str], check: dict[str, Any], what: str = "") -> dict[str, Any]:
    """A KPI is not there: not applicable (module not in the workflow / out of scope, or if_missing), else not evaluable."""
    module = kpi_module(kpi_id)
    if module in failed:
        return {"status": NOT_EVALUABLE, "reason": f"{module} {failed[module]}"}
    if module in inactive:
        return _na(f"{module} {inactive[module]}")
    if check.get("if_missing") == N_A:
        return _na(f"{kpi_id} not produced")
    return {"status": NOT_EVALUABLE, "reason": f"{what or kpi_id} missing"}


def evaluate_check(check: dict[str, Any], kpis: dict[str, Any], used: dict[str, Any], failed: dict[str, str] | None = None,
                   inactive: dict[str, str] | None = None) -> dict[str, Any]:
    """One check of a criterion on the KPIs of the iteration (``kpis``) and of the design used (``used``).
    Returns {status, label, kpi, value, threshold, ref, margin, reason}."""
    failed, inactive = failed or {}, inactive or {}
    kid, op = str(check["kpi"]), str(check.get("op", "<="))
    out: dict[str, Any] = {"kpi": kid, "label": check.get("label") or kid, "op": op, "value": _value_of(kpis, kid),
                           "threshold": None, "ref": None, "margin": None, "status": NOT_EVALUABLE, "reason": ""}
    value = out["value"]
    if kid not in kpis or value is None or kpi_module(kid) in failed:
        out.update(_missing(kid, failed, inactive, check))
        return out
    ref_spec, thr_spec = check.get("ref"), check.get("threshold")

    # reference value (rel_le and ==)
    ref = None
    if ref_spec is not None:
        if ref_spec == "used":
            ref = _value_of(used, kid)
            if ref is None:
                out.update(reason=f"the design used has no {kid}")
                return out
        elif isinstance(ref_spec, dict) and ref_spec.get("kpi"):
            ref = _value_of(kpis, str(ref_spec["kpi"]))
            if ref is None:
                out.update(_missing(str(ref_spec["kpi"]), failed, inactive, check))
                return out
        out["ref"] = ref

    # threshold
    thr: Any = thr_spec
    if isinstance(thr_spec, dict):
        if thr_spec.get("kpi"):
            base = _value_of(kpis, str(thr_spec["kpi"]))
            if _number(base) is None:
                out.update(_missing(str(thr_spec["kpi"]), failed, inactive, check))
                return out
            thr = _number(base) * float(thr_spec.get("factor", 1.0))
        elif thr_spec.get("kpi_limit"):
            limit = _limit_of(kpis, str(thr_spec["kpi_limit"]))
            if _number(limit) is None:
                if check.get("if_no_limit") == N_A:
                    out.update(_na(f"{thr_spec['kpi_limit']} has no limit to check against"))
                else:
                    out.update(reason=f"no limit published for {thr_spec['kpi_limit']}")
                return out
            thr = _number(limit)
    out["threshold"] = thr

    if op == "==":
        expected = ref if ref_spec is not None else thr
        a, b = _number(value), _number(expected)
        same = (abs(a - b) <= EPS * max(1.0, abs(b)) if a is not None and b is not None else value == expected)
        out.update(status=PASS if same else FAIL, threshold=expected,
                   reason="" if same else f"{out['label']}: {_fmt(value)} != {_fmt(expected)}")
        return out

    v = _number(value)
    if v is None:
        out["reason"] = f"{kid} is not a number ({value!r})"
        return out
    if op == "rel_le":
        r, band = _number(ref), _number(thr)
        if r is None or band is None:
            out["reason"] = f"{kid}: reference or band is not a number"
            return out
        limit = band * abs(r)
        diff = abs(v - r)
        ok = diff <= limit + EPS * max(1.0, abs(r))
        out.update(status=PASS if ok else FAIL, threshold=band, margin=limit - diff,
                   reason="" if ok else f"{out['label']}: {_fmt(v)} differs from {_fmt(r)} by {100 * diff / abs(r) if r else float('inf'):.3g} % (> {100 * band:.3g} %)")
        return out
    t = _number(thr)
    if t is None:
        out["reason"] = f"threshold of {kid} is not a number ({thr!r})"
        return out
    tol = EPS * max(1.0, abs(t))
    ok = {"<=": v <= t + tol, ">=": v >= t - tol, "<": v < t - tol, ">": v > t + tol}.get(op)
    if ok is None:
        out["reason"] = f"unknown operator {op!r}"
        return out
    out.update(status=PASS if ok else FAIL, margin=(t - v) if op in ("<=", "<") else (v - t),
               reason="" if ok else f"{out['label']}: {_fmt(v)} not {op} {_fmt(t)}")
    return out


def evaluate_criteria(config: dict[str, Any], kpis: dict[str, Any], used: dict[str, Any], failed: dict[str, str] | None = None,
                      inactive: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Status of every criterion: {id, name, status, values{kpi: v}, threshold{kpi: t}, margin{kpi: m}, reason, checks[]}.

    ``failed``: module id -> why its KPIs cannot be trusted ("failed"): the checks on them are not_evaluable.
    ``inactive``: module id -> why it is not in the loop ("is not in the workflow"): the checks on it are not_applicable."""
    failed, inactive = failed or {}, inactive or {}
    out = []
    for c in config.get("criteria", []):
        rec: dict[str, Any] = {"id": c["id"], "name": c.get("name", ""), "status": PASS, "values": {}, "threshold": {}, "margin": {},
                               "reason": "", "checks": []}
        applies = c.get("applies_if")
        if applies:
            cond = evaluate_check({"kpi": applies["kpi"], "op": applies.get("op", ">"), "threshold": applies.get("threshold"),
                                   "label": applies["kpi"], "if_missing": N_A}, kpis, used, failed, inactive)
            if cond["status"] != PASS:
                rec.update(status=N_A, reason=cond["reason"] or f"does not apply: {applies['kpi']} {applies.get('op', '>')} {applies.get('threshold')} is false")
                out.append(rec)
                continue
        results = [evaluate_check(chk, kpis, used, failed, inactive) for chk in _all_checks(c)]
        rec["checks"] = results
        for chk, r in zip(_all_checks(c), results):
            for kid in _check_kpis(chk):
                if kid in kpis:
                    rec["values"][kid] = _value_of(kpis, kid)
            if r["threshold"] is not None:
                rec["threshold"][r["kpi"]] = r["threshold"]
            if r["margin"] is not None:
                rec["margin"][r["kpi"]] = r["margin"]
        statuses = [r["status"] for r in results]
        if FAIL in statuses:
            rec["status"] = FAIL
        elif NOT_EVALUABLE in statuses:
            rec["status"] = NOT_EVALUABLE
        elif results and all(s == N_A for s in statuses):
            rec["status"] = N_A
        rec["reason"] = "; ".join(r["reason"] for r in results if r["reason"] and r["status"] in (FAIL, NOT_EVALUABLE)) \
            or ("; ".join(r["reason"] for r in results if r["reason"]) if rec["status"] == N_A else "")
        out.append(rec)
    return out


def criteria_ok(criteria: list[dict[str, Any]]) -> bool:
    return bool(criteria) and all(c["status"] in (PASS, N_A) for c in criteria)


# --------------------------------------------------------------------------- helpers on designs and files
def _get_path(data: Any, path: str) -> Any:
    cur = data
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _read_json(path: Path | None) -> dict[str, Any] | None:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _strip(data: Any) -> Any:
    if isinstance(data, dict):
        return {k: _strip(v) for k, v in data.items() if k not in VOLATILE_KEYS}
    if isinstance(data, list):
        return [_strip(v) for v in data]
    return data


def _digest(data: Any) -> str:
    return hashlib.sha1(json.dumps(data, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


class CefLoop:
    """The design loop. ``run_node(node_id, iteration)`` runs one node in the orchestrator and returns its result dict
    (``status`` and, for the log, ``evidence`` / ``duration_seconds``); it must return status ``stopped`` when the user stopped."""

    def __init__(self, graph: Any, config: dict[str, Any], modules_root: str | Path, run_dir: str | Path,
                 run_node: Callable[[str, int], dict[str, Any]], log: Callable[[str, str], None] | None = None,
                 stop_event: Any = None, run_id: str = "") -> None:
        self.graph, self.config = graph, config
        self.modules_root, self.run_dir = Path(modules_root), Path(run_dir)
        self.run_node, self._log, self.stop_event, self.run_id = run_node, log or (lambda level, msg: None), stop_event, run_id
        self.max_iterations = max(1, int(config.get("max_iterations", 3)))
        self.crit_nodes = criteria_nodes(config)
        edges = graph.feedback_edges()
        self.edge = edges[0] if edges else None                     # (producer node, produced product, fed-back product)
        self.loop_nodes = graph.loop_nodes(self.crit_nodes) if self.edge else []
        self.post_nodes = graph.post_loop_nodes(self.crit_nodes) if self.edge else []
        self.fixed_nodes = graph.fixed_nodes()
        self.cef_dir = self.run_dir / "cef"
        self.state: dict[str, Any] = {}
        self._d0: dict[str, Any] | None = None                      # the design of iteration 1, as a dict
        self._used_design: dict[str, Any] | None = None             # the design the modules of the current iteration must use
        self._stale: list[str] = []
        self._used_kpis: dict[str, Any] = {}
        self._produced_design: dict[str, Any] | None = None
        self._baseline: dict[tuple, str] = {}
        self._consumed_baseline: dict[tuple, str] = {}

    # ------------------------------------------------------------------ small helpers
    def log(self, level: str, message: str) -> None:
        self._log(level, message)

    def stopped(self) -> bool:
        return bool(self.stop_event is not None and self.stop_event.is_set())

    def _design_path(self, product: str) -> Path | None:
        found = self.graph.find_product(product, self.modules_root)
        return found[0] if found else None

    def _module_kpis(self, node_id: str) -> dict[str, Any]:
        node = self.graph.node(node_id)
        doc = K.load_doc(self.modules_root / node.module_id / K.file_name(node.phase or ""))
        return {k["id"]: k for k in (doc or {}).get("kpis", []) if isinstance(k, dict) and k.get("id")}

    def _run_kpis(self, excluded_modules: set[str]) -> dict[str, Any]:
        return {k: v for k, v in K.load_run(self.modules_root.parent).items() if v.get("module_id") not in excluded_modules}

    def _fingerprint(self, product: str, keys: list[str] | None, design: dict[str, Any] | None = None) -> str:
        """Fingerprint of a product (the values of ``keys`` for a JSON design, else the stripped content of its files)."""
        if design is not None:
            return _digest({k: _get_path(design, k) for k in keys} if keys else _strip(design))
        files = self.graph.find_product(product, self.modules_root)
        parts = []
        for path in files:
            doc = _read_json(path) if path.suffix.lower() == ".json" else None
            if doc is not None:
                parts.append((path.name, {k: _get_path(doc, k) for k in keys} if keys else _strip(doc)))
            else:
                try:
                    parts.append((path.name, hashlib.sha1(path.read_bytes()).hexdigest()))
                except OSError:
                    parts.append((path.name, "unreadable"))
        return _digest(parts)

    def _changed_keys(self, keys: list[str], old: dict[str, Any] | None, new: dict[str, Any] | None) -> list[str]:
        return [k for k in keys if _get_path(old or {}, k) != _get_path(new or {}, k)]

    # ------------------------------------------------------------------ archive
    def _iter_dir(self, k: int) -> Path:
        return self.cef_dir / f"iteration_{k:02d}"

    def _copy_products(self, node_ids: list[str], dest_root: Path) -> list[str]:
        copied: list[str] = []
        for node_id in node_ids:
            for item in self.graph.node(node_id).produces:
                if str(item.get("format", "")).lower() in ARCHIVE_SKIP_FORMATS:
                    continue
                for src in self.graph.find_product(str(item.get("product")), self.modules_root):
                    try:
                        if src.stat().st_size > ARCHIVE_MAX_BYTES:
                            continue
                        rel = src.relative_to(self.modules_root)
                        dst = dest_root / "modules_output" / rel
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src, dst)
                        copied.append(str(rel).replace("\\", "/"))
                    except (OSError, ValueError):
                        continue
        return copied

    def _archive(self, k: int, ran_nodes: list[str], results: dict[str, dict[str, Any]]) -> list[str]:
        d = self._iter_dir(k)
        d.mkdir(parents=True, exist_ok=True)
        files = self._copy_products(ran_nodes, d)
        produced = self._design_path(self.edge[1]) if self.edge else None
        if produced:
            shutil.copy2(produced, d / "spacecraft_definition_produced.json")
        slim = {n: {key: r.get(key) for key in ("status", "evidence", "duration_seconds", "started_at", "completed_at", "node", "iteration")}
                for n, r in results.items()}
        (d / "process_results.json").write_text(json.dumps(slim, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
        return files

    def _snapshot_used(self, k: int) -> dict[str, Any] | None:
        """Copy of the design the modules of iteration k are about to use."""
        path = self._design_path(self.edge[2]) if self.edge else None
        if not path:
            return None
        d = self._iter_dir(k)
        d.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, d / "spacecraft_definition_used.json")
        return _read_json(path)

    def promote(self, k: int) -> bool:
        """Copy the design produced in iteration k over the fed-back product, stamped with the iteration."""
        src = self._design_path(self.edge[1])
        dst = self._design_path(self.edge[2])
        design = _read_json(src)
        if not design or dst is None:
            return False
        design["design_iteration"] = k
        design["promoted_from"] = self.edge[0]
        dst.write_text(json.dumps(design, indent=2, ensure_ascii=False), encoding="utf-8")
        return True

    # ------------------------------------------------------------------ the loop
    def _design_block(self, source: str, kpis: dict[str, Any]) -> dict[str, Any]:
        sig = kpis.get("END-006.design_signature") or {}
        return {"source": source, "signature": sig.get("value"), "mass_kg": _value_of(kpis, "END-006.mass_kg"),
                "components": (sig.get("context") or {}).get("components") or {}}

    @staticmethod
    def _diff(used: dict[str, Any], produced: dict[str, Any]) -> list[str]:
        changes = []
        a, b = used.get("components") or {}, produced.get("components") or {}
        for slot in sorted(set(a) | set(b)):
            if a.get(slot) != b.get(slot):
                changes.append(f"{slot}: {a.get(slot, 'none')} -> {b.get(slot, 'none')}")
        ma, mb = _number(used.get("mass_kg")), _number(produced.get("mass_kg"))
        if ma is not None and mb is not None and abs(ma - mb) > 1e-6:
            changes.append(f"mass {ma:.4g} -> {mb:.4g} kg")
        return changes

    def _write(self) -> None:
        self.state["generated_at"] = datetime.now().isoformat(timespec="seconds")
        try:
            (self.run_dir / "convergence.json").write_text(json.dumps(self.state, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        except OSError as exc:
            self.log("WARNING", f"convergence.json not saved: {exc}")

    def _finish(self, status: str, reason: str) -> dict[str, Any]:
        self.state["status"], self.state["reason"] = status, reason
        self.state["failing_criteria"] = [c["id"] for c in (self.state["iterations"][-1]["criteria"] if self.state["iterations"] else [])
                                          if c["status"] in (FAIL, NOT_EVALUABLE)] if status != CONVERGED else []
        self._write()
        level = "SYSTEM" if status in (CONVERGED, NOT_APPLICABLE) else "WARNING"
        self.log(level, f"Design loop {status}: {reason}")
        return self.state

    def _initial_state(self) -> dict[str, Any]:
        post = []
        for n in self.post_nodes:
            node = self.graph.node(n)
            rules = self.graph.registry.cef_loop(node.module_id)["rerun_on"]
            post.append({"node": n, "trigger": rules or "any consumed product changed", "fired": None})
        return {"schema_version": 1, "run_id": self.run_id, "status": RUNNING, "max_iterations": self.max_iterations,
                "iterations_run": 0, "converged_at": None, "loop_nodes": self.loop_nodes, "post_loop_nodes": post,
                "fixed_modules": [self.graph.node(n).module_id for n in self.fixed_nodes],
                "feedback": {"produced": self.edge[1], "fed_back_to": self.edge[2], "producer": self.edge[0]} if self.edge else None,
                "criteria_def": [{"id": c["id"], "name": c.get("name", "")} for c in self.config.get("criteria", [])],
                "iterations": [], "failing_criteria": [], "reason": "", "warnings": []}

    def run(self, first_pass: dict[str, dict[str, Any]]) -> dict[str, Any]:
        """``first_pass``: node id -> result of iteration 1 (the ordinary workflow, already executed)."""
        self.state = self._initial_state()
        if self.edge is None:
            return self._finish(NOT_APPLICABLE, "the workflow has no feedback edge (END-006 final design is not in the workflow)")
        producer = self.edge[0]
        first = first_pass.get(producer)
        if not first or not star_status.is_success(first.get("status")):
            return self._finish(NOT_APPLICABLE, f"{producer} did not complete in the first pass "
                                                f"({(first or {}).get('status', 'not run')}): no final design to feed back")
        if not [n for n in self.loop_nodes if n != producer]:
            return self._finish(NOT_APPLICABLE, "no module of the workflow uses the satellite design: nothing to iterate")

        self._d0 = self._used_design = self._snapshot_used(1)
        self._used_kpis = self._module_kpis(self.graph.registry.producer_of(self.edge[2]) or "")
        used_source = "initial design"
        for n in self.post_nodes:                                     # what the post-loop nodes used = the state after the first pass
            for rule in self._rules_of(n):
                self._baseline[(n, rule["product"])] = self._fingerprint(rule["product"], rule.get("keys"), self._d0 if rule["product"] == self.edge[2] else None)
        self._consumed_baseline = {(n, str(c.get("product"))): self._fingerprint(str(c.get("product")), None, self._d0 if str(c.get("product")) == self.edge[2] else None)
                                   for n in self.post_nodes for c in self.graph.node(n).consumes}

        k = 1
        results = {n: first_pass[n] for n in self.loop_nodes if n in first_pass}
        archive_nodes = [n for n in ([self.graph.registry.producer_of(self.edge[2])] + self.loop_nodes) if n and n in first_pass]
        final_status, final_reason = None, ""
        while True:
            self._record_iteration(k, used_source, archive_nodes, results)
            record = self.state["iterations"][-1]
            self.state["iterations_run"] = k
            bad = [n for n in self.loop_nodes if n in results and results[n].get("status") in (star_status.FAILED, star_status.SKIP_BLOCKED, star_status.STOPPED)]
            missing = [n for n in self.loop_nodes if n not in results]
            if self.stopped() or any(results[n].get("status") == star_status.STOPPED for n in bad):
                return self._finish(STOPPED, f"stopped by the user during iteration {k}")
            if bad or missing:
                n = (bad or missing)[0]
                why = results[n].get("evidence", "") if n in results else "not run"
                return self._finish(INTERRUPTED, f"{n} {results[n].get('status') if n in results else 'not run'} in iteration {k}: {str(why)[:200]}")
            if self._stale:
                return self._finish(INTERRUPTED, f"iteration {k}: " + "; ".join(self._stale) + " (stale read of the satellite design, results not valid)")
            if criteria_ok(record["criteria"]):
                self.state["converged_at"] = k
                final_status, final_reason = CONVERGED, f"all criteria met at iteration {k}"
                break
            failing = [c["id"] for c in record["criteria"] if c["status"] in (FAIL, NOT_EVALUABLE)]
            if k >= self.max_iterations:
                final_status, final_reason = NOT_CONVERGED, f"criteria still failing after {k} iteration(s): {', '.join(failing)}"
                break
            if self._stalled(record):
                final_status = STALLED
                final_reason = (f"the design produced equals the design used (signature and mass) but {', '.join(failing)} still fail: "
                                "the runs are deterministic, another iteration would give the same result")
                break
            if not self.promote(k):
                return self._finish(INTERRUPTED, f"the design of iteration {k} could not be promoted")
            self.log("EXECUTION", f"Design loop: iteration {k} not converged ({', '.join(failing)}); design D{k} promoted, iteration {k + 1}/{self.max_iterations}.")
            k += 1
            self._used_kpis = self._module_kpis(producer)
            used_source = f"final design of iteration {k - 1}"
            self._used_design = self._snapshot_used(k)
            results = {}
            archive_nodes = list(self.loop_nodes)
            self._run_iteration_nodes(k, results)
            self._write()
        if final_status in (CONVERGED, NOT_CONVERGED, STALLED):
            self._produced_design = _read_json(self._design_path(self.edge[1]))
            interrupted = self._post_loop(k)
            if interrupted:
                return self._finish(STOPPED, interrupted)
        return self._finish(final_status, final_reason)

    def _run_iteration_nodes(self, k: int, results: dict[str, dict[str, Any]]) -> None:
        for node_id in self.loop_nodes:
            if self.stopped():
                return
            self.log("EXECUTION", f"Design loop iteration {k}/{self.max_iterations}: {node_id}.")
            result = self.run_node(node_id, k)
            results[node_id] = result
            status = result.get("status")
            if not star_status.is_success(status) and status != star_status.SKIP_SCOPE:
                return                                                # the loop ends as interrupted / stopped

    def _check_design_used(self, k: int, results: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """Every node of iteration k must have loaded D(k-1): the iteration stamp and the signature of the design the controller
        put in place. ``design_used`` is filled by the orchestrator from load_spacecraft_definition; a node without it (it does
        not read the satellite) is 'not_recorded'. A mismatch is a stale read: the iteration is not valid."""
        want_iter = k - 1
        want_sig = design_fingerprint(self._used_design) if self._used_design else None
        checks: dict[str, dict[str, Any]] = {}
        self._stale = []
        for node_id, r in results.items():
            used = r.get("design_used") or []
            if not used:
                checks[node_id] = {"status": "not_recorded"}
                continue
            wrong = [u for u in used if int(u.get("design_iteration") or 0) != want_iter or (want_sig and u.get("signature") != want_sig)]
            checks[node_id] = {"status": "mismatch" if wrong else "ok", "used": used, "expected_iteration": want_iter}
            if wrong:
                got = ", ".join(f"design {u.get('design_iteration')}" for u in wrong)
                msg = f"{node_id} used {got} instead of D{want_iter}"
                self._stale.append(msg)
                self.state["warnings"].append(f"iteration {k}: {msg}")
                self.log("WARNING", f"Design loop iteration {k}: {msg}")
        return checks

    def _record_iteration(self, k: int, used_source: str, archive_nodes: list[str], results: dict[str, dict[str, Any]]) -> None:
        """Evaluate the criteria of iteration k, archive it and append it to convergence.json."""
        failed = {self.graph.node(n).module_id: str(r.get("status")) for n, r in results.items()
                  if r.get("status") in (star_status.FAILED, star_status.SKIP_BLOCKED, star_status.STOPPED)}
        inactive = {m: "is not in the workflow" for m in
                    {kpi_module(i) for c in self.config.get("criteria", []) for chk in _all_checks(c) for i in _check_kpis(chk)}
                    if not any(self.graph.node(n).module_id == m for n in self.graph.node_ids)}
        inactive.update({self.graph.node(n).module_id: "was skipped (out of scope)" for n, r in results.items()
                         if r.get("status") == star_status.SKIP_SCOPE})
        checks = self._check_design_used(k, results)
        kpis = self._run_kpis(set(failed))
        criteria = evaluate_criteria(self.config, kpis, self._used_kpis, failed, inactive)
        evolution = []
        for item in self.config.get("evolution_kpis") or []:
            kid = item["kpi"]
            e = kpis.get(kid)
            if e is not None and _number(e.get("value")) is not None:
                evolution.append({"kpi": kid, "label": item.get("label", kid), "value": _number(e.get("value")), "unit": e.get("unit", "")})
        used = self._design_block(used_source, self._used_kpis)
        produced = self._design_block(f"{self.edge[0]} of iteration {k}", kpis)
        produced["changes"] = self._diff(used, produced)
        record = {"k": k, "design_used": {x: used[x] for x in ("source", "signature", "mass_kg")},
                  "design_produced": {x: produced[x] for x in ("signature", "mass_kg", "changes")},
                  "components_used": used["components"], "components_produced": produced["components"],
                  "nodes": [{"node": n, "status": r.get("status"), "duration_s": r.get("duration_seconds"),
                             "design_check": checks.get(n, {}).get("status"), "design_used": r.get("design_used")} for n, r in results.items()],
                  "criteria": criteria, "evolution": evolution, "archive": self._archive(k, archive_nodes, results)}
        self.state["iterations"].append(record)
        for c in criteria:
            if c["status"] in (FAIL, NOT_EVALUABLE):
                self.log("WARNING", f"Design loop iteration {k}: {c['id']} {c['status']}: {c['reason']}")
        self._write()

    def _stalled(self, record: dict[str, Any]) -> bool:
        used, produced = record["design_used"], record["design_produced"]
        if not used.get("signature") or used.get("signature") != produced.get("signature"):
            return False
        a, b = _number(used.get("mass_kg")), _number(produced.get("mass_kg"))
        return a is not None and b is not None and abs(a - b) <= float(self.config.get("stall_mass_rel", 0.001)) * abs(a)

    # ------------------------------------------------------------------ post-loop nodes and warnings
    def _rules_of(self, node_id: str) -> list[dict[str, Any]]:
        node = self.graph.node(node_id)
        rules = self.graph.registry.cef_loop(node.module_id)["rerun_on"]
        if rules:
            return [dict(r) for r in rules]
        return [{"product": str(c.get("product")), "keys": None} for c in node.consumes]

    def _current_fp(self, rule: dict[str, Any]) -> str:
        design = self._produced_design if rule["product"] == self.edge[2] else None
        return self._fingerprint(rule["product"], rule.get("keys"), design)

    def _post_loop(self, k: int) -> str:
        """Run the post-loop nodes whose trigger fired. Returns a text when the user stopped the run, else ''."""
        triggers = {t["node"]: t for t in self.state["post_loop_nodes"]}
        fired_nodes: list[str] = []
        for n in self.post_nodes:
            t = triggers[n]
            changed = []
            for rule in self._rules_of(n):
                key = (n, rule["product"])
                before = self._baseline.get(key)
                if before is None:
                    before = self._fingerprint(rule["product"], rule.get("keys"), self._d0 if rule["product"] == self.edge[2] else None)
                if self._current_fp(rule) != before:
                    keys = rule.get("keys")
                    changed.append({"product": rule["product"], "keys": self._changed_keys(keys, self._d0, self._produced_design) if keys else None})
            t["fired"], t["changed"] = bool(changed), changed
            if changed:
                fired_nodes.append(n)
            else:
                rule_products = {r["product"] for r in self._rules_of(n)}
                moved = [str(c.get("product")) for c in self.graph.node(n).consumes if str(c.get("product")) not in rule_products
                         and self._fingerprint(str(c.get("product")), None, self._produced_design if str(c.get("product")) == self.edge[2] else None)
                         != self._consumed_baseline.get((n, str(c.get("product"))))]
                if moved:
                    self.state["warnings"].append(f"{n} not re-run (trigger not fired): it keeps the {', '.join(moved)} of iteration 1")
        for node_id in self.fixed_nodes:
            for c in self.graph.node(node_id).consumes:
                if c.get("uses") and str(c.get("product")) == self.edge[2]:
                    diff = self._changed_keys([str(u) for u in c["uses"]], self._d0, self._produced_design)
                    if diff:
                        self.state["warnings"].append(f"{node_id} was not re-run (cef_loop: fixed): its results used the "
                                                      f"{', '.join(diff)} of the design of iteration 1, which changed in the final design")
        for w in self.state["warnings"]:
            self.log("WARNING", f"Design loop: {w}")
        self._write()
        if not fired_nodes:
            return ""
        promoted = self.promote(k)                                     # the post-loop nodes use the final satellite
        self.state["final_design_promoted"] = promoted
        self.log("EXECUTION", f"Design loop: post-loop nodes {', '.join(fired_nodes)} re-run on the final design.")
        before_dir = self.cef_dir / "post_loop_before"
        self._copy_products(fired_nodes, before_dir)
        for n in fired_nodes:
            if self.stopped():
                return f"stopped by the user before {n} (post-loop)"
            result = self.run_node(n, k)
            triggers[n]["status"] = result.get("status")
            if result.get("status") == star_status.STOPPED:
                return f"stopped by the user during {n} (post-loop)"
            if not star_status.is_success(result.get("status")):
                self.state["warnings"].append(f"{n} post-loop re-run {result.get('status')}: {str(result.get('evidence', ''))[:160]}")
                self.log("WARNING", f"Design loop: {self.state['warnings'][-1]}")
        self._write()
        return ""

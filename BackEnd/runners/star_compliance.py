"""STAR requirement compliance (phase E, 2026-10-22): a generic engine over the common KPIs.

After the workflow, the KPIs of every module (``kpis.json``, ``star_kpis``; rebuilt by ``star_kpi_adapters`` for a run that has
none) are compared with the requirements through the table of rules ``config/requirement_kpi_rules.yaml``. The rules and
the evaluation semantics are described in the header of that file. Nothing here knows a module: a new check is a new rule.

For each requirement the engine builds the rows ``requirement x check`` (the per-run map ``requirement_kpi_map.json``,
also written at planning time with the thresholds that do not depend on a run), evaluates them and gives the status
met / not_met / evidence_provided / partially_verified / applied / not_verifiable. A failed check carries the violating
value as evidence ("battery min -36.8 C (cold case, SAT-03) < 0 C ...").

Files: <run>/compliance/compliance.json, compliance_data.js (window.starComplianceData, read by the results tab),
requirement_kpi_map.json, traceability.json / traceability.csv (star_traceability).
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from . import star_text_rules as R
    from . import star_kpis as K
    from . import star_kpi_adapters as A
except ImportError:
    import star_text_rules as R
    import star_kpis as K
    import star_kpi_adapters as A

RULES_PATH = Path(__file__).resolve().parents[2] / "Input" / "input_base_knowledge" / "config" / "requirement_kpi_rules.yaml"
STATUSES = ("met", "not_met", "evidence_provided", "partially_verified", "applied", "not_verifiable")
_RULES_CACHE: dict[str, Any] = {}


def _load(path: Path) -> dict | None:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def load_rules(path: str | Path | None = None) -> dict[str, Any]:
    """The parsed requirement_kpi_rules.yaml (cached by modification time)."""
    import yaml
    p = Path(path or RULES_PATH)
    key = f"{p}:{p.stat().st_mtime_ns}"
    if key not in _RULES_CACHE:
        _RULES_CACHE.clear()
        _RULES_CACHE[key] = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return _RULES_CACHE[key]


# --------------------------------------------------------------------------- KPIs of a run
def run_kpis(run_path: str | Path) -> dict[str, dict[str, Any]]:
    """{kpi_id: entry} of the run: every kpis.json, and the adapters for a module that has none (runs older than phase E)."""
    run_path = Path(run_path)
    kpis = K.load_run(run_path)
    have = {e.get("module_id") for e in kpis.values()}
    root = run_path / "modules_output"
    for mdir in sorted(p for p in root.glob("END-*") if p.is_dir()):
        mid = mdir.name
        if mid in have:
            continue
        phases = ("final", "initial") if mid == "END-006" else ("",)
        for phase in phases:
            doc = A.build_document(mid, mdir, phase, run_path.name)
            if doc.get("kpis"):
                for k in doc["kpis"]:
                    kpis[k["id"]] = {**k, "module_id": mid, "node": doc.get("node"), "_file": f"{mdir.name} (rebuilt from the module products)"}
                break
    return kpis


# --------------------------------------------------------------------------- the plan of a requirement (rules -> rows)
def _fmt(v: Any) -> str:
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        return f"{v:.4g}"
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_fmt(x) for x in v) + "]"
    return str(v)


def _unit(u: Any) -> str:
    u = str(u or "")
    return {"C": "°C", "-": "", "bool": ""}.get(u, u)


def _param_value(ref: Any, p: dict[str, Any], key: str | None) -> Any:
    """'$param', '$param.field', '$param[i]' of the rule's parameter; anything else is a constant."""
    if not (isinstance(ref, str) and ref.startswith("$param")):
        return ref
    v = p.get(key) if key else None
    rest = ref[len("$param"):]
    if v is None or not rest:
        return v
    if rest.startswith(".") and isinstance(v, dict):
        return v.get(rest[1:])
    m = re.match(r"^\[(\d+)\]$", rest)
    if m and isinstance(v, (list, tuple)) and int(m.group(1)) < len(v):
        return v[int(m.group(1))]
    return None


def _range(spec: dict[str, Any], p: dict[str, Any], key: str | None) -> list[float] | None:
    v = _param_value(spec.get("param_range"), p, key)
    if v is None:
        return None
    t = float(spec.get("tolerance") or 0)
    if isinstance(v, (int, float)):
        return [v - t, v + t]
    items = list(v)
    default = spec.get("default")
    if default and len(items) == 2:
        lo = items[0] if items[0] is not None else default[0]
        hi = items[1] if items[1] is not None else default[1]
    else:
        vals = [x for x in items if x is not None]
        if not vals:
            return None
        lo, hi = min(vals), max(vals)
    if lo == hi and spec.get("widen_if_point"):
        lo, hi = lo - float(spec["widen_if_point"]), hi + float(spec["widen_if_point"])
    return [lo, hi]


def _threshold(spec: Any, p: dict[str, Any], key: str | None) -> tuple[Any, str]:
    """(threshold, source): a number / list from the requirement text, a constant, or a dict {kpi} / {kpi_limit} to resolve later."""
    if isinstance(spec, dict) and "param_range" in spec:
        return _range(spec, p, key), "requirement"
    if isinstance(spec, dict) and "kpi" in spec:
        pv = p.get(key) if key else None
        kid = str(spec["kpi"]).replace("{param}", str(int(pv)) if isinstance(pv, (int, float)) else "{param}")
        return {"kpi": kid}, "kpi"
    if isinstance(spec, dict) and "kpi_limit" in spec:
        return {"kpi_limit": spec["kpi_limit"]}, "module_limit"
    if isinstance(spec, str) and spec.startswith("$param"):
        return _param_value(spec, p, key), "requirement"
    return spec, "rule"


def _fires(rule: dict[str, Any], p: dict[str, Any], low: str, is_evidence: bool) -> bool:
    key = rule.get("param")
    if key is not None and key not in p:
        return False
    if rule.get("param_any") and not any(k in p for k in rule["param_any"]):
        return False
    if rule.get("unless_param") and rule["unless_param"] in p:
        return False
    if rule.get("unless_equal_param") and key in p and p.get(key) == p.get(rule["unless_equal_param"]):
        return False
    for field, want in (rule.get("where") or {}).items():
        if not (isinstance(p.get(key), dict) and p[key].get(field) == want):
            return False
    for field, want in (rule.get("where_not") or {}).items():
        if isinstance(p.get(key), dict) and p[key].get(field) == want:
            return False
    if rule.get("match") and not all(R.has_any(low, g) for g in rule["match"]):
        return False
    if rule.get("unless_match") and all(R.has_any(low, g) for g in rule["unless_match"]):
        return False
    if rule.get("evidence") and not is_evidence:
        return False
    if rule.get("unless_evidence") and is_evidence:
        return False
    return True


def _check_row(rule: dict[str, Any], c: dict[str, Any], p: dict[str, Any], group: str) -> dict[str, Any]:
    thr, src = _threshold(c.get("threshold"), p, rule.get("param"))
    kid = str(c["kpi"])
    return {"rule": rule["id"], "kind": "check", "group": group, "kpi_id": kid, "module": kid.split(".")[0], "operator": c.get("op", "<="),
            "threshold": thr, "threshold_source": src, "unit": K.norm_unit(c.get("unit", "-")), "label": c.get("label") or kid,
            "note_not_met": rule.get("note_not_met", "")}


def plan_requirement(req: dict[str, Any], rules: dict[str, Any]) -> dict[str, Any]:
    """The rules that fire on a requirement and the rows they give (no run data needed)."""
    rid, text = str(req.get("id", "REQ")), str(req.get("text", ""))
    p = {k: v[0] for k, v in R.mission_parameters([(rid, text)]).items()}
    low = R.norm(text)
    is_evidence = R.has_any(low, [str(x) for x in rules.get("evidence_phrases") or []])
    rows: list[dict[str, Any]] = []
    status_rules: list[dict[str, Any]] = []
    fired: list[str] = []
    for rule in rules.get("rules") or []:
        if not _fires(rule, p, low, is_evidence):
            continue
        fired.append(rule["id"])
        for c in rule.get("checks") or []:
            rows.append(_check_row(rule, c, p, "all"))
        for i, branch in enumerate(rule.get("any_of") or []):
            for c in branch:
                rows.append(_check_row(rule, c, p, f"any_of[{i}]"))
        for kid in rule.get("kpis") or []:
            rows.append({"rule": rule["id"], "kind": "evidence", "group": "evidence", "kpi_id": kid, "module": kid.split(".")[0],
                         "operator": "", "threshold": None, "threshold_source": "", "unit": "", "label": kid, "note_not_met": ""})
        if rule.get("module_checks"):
            rows.append({"rule": rule["id"], "kind": "module", "group": "module", "kpi_id": None, "module": rule["module_checks"],
                         "operator": "", "threshold": None, "threshold_source": "component", "unit": "", "label": "", "note_not_met": ""})
        if rule.get("status"):
            status_rules.append({"rule": rule["id"], "status": rule["status"], "reason": rule.get("reason", "")})
    # the same kpi / operator / threshold is kept once, the rule's first
    seen: set[str] = set()
    unique = []
    for r in rows:
        k = json.dumps([r["kind"], r["group"] if r["group"].startswith("any_of") else "", r["kpi_id"], r["operator"], r["threshold"]], default=str)
        if r["kind"] != "module" and k in seen:
            continue
        seen.add(k)
        unique.append(r)
    return {"id": rid, "text": text, "parameters": p, "is_evidence": is_evidence, "rules": fired, "rows": unique, "status_rules": status_rules}


# --------------------------------------------------------------------------- evaluation
def _ctx_text(entry: dict[str, Any]) -> str:
    c = entry.get("context") or {}
    parts = []
    if c.get("case"):
        parts.append(f"{c['case']} case")
    if c.get("satellite"):
        parts.append(str(c["satellite"]))
    return f" ({', '.join(parts)})" if parts else ""


_NEG = {"<=": ">", ">=": "<", "==": "!=", "<": ">=", ">": "<="}


def _compare(v: Any, op: str, thr: Any) -> str:
    """'met' | 'not_met' | 'unverifiable' (a bound such as '> 200' decides only when it settles the comparison)."""
    if isinstance(v, str) and v.strip().lower().lstrip("+") in ("inf", "infinity"):
        v = float("inf")                                       # e.g. END-016 lifetime of an orbit that does not decay
    if isinstance(v, str) and op in ("<=", ">=", "in"):
        m = re.match(r"\s*([<>])=?\s*(-?\d+(?:\.\d+)?)", v)     # e.g. END-016 lifetime "> 200": a bound, not a value
        if not m or not isinstance(thr, (int, float)):
            return "unverifiable"
        bound, side = float(m.group(2)), m.group(1)
        if (op == "<=" and side == ">" and bound >= thr) or (op == ">=" and side == "<" and bound <= thr):
            return "not_met"
        if (op == "<=" and side == "<" and bound <= thr) or (op == ">=" and side == ">" and bound >= thr):
            return "met"
        return "unverifiable"
    try:
        if op == "<=":
            ok = v <= thr + 1e-9
        elif op == ">=":
            ok = v >= thr - 1e-9
        elif op == "<":
            ok = v < thr
        elif op == ">":
            ok = v > thr
        elif op == "in":
            ok = thr[0] - 1e-9 <= v <= thr[1] + 1e-9
        elif isinstance(v, str) and isinstance(thr, str):
            t = thr.strip().lower()
            ok = v.strip().lower().startswith("rgt") if t.startswith("rgt") else v.strip().lower() == t
        else:
            ok = v == thr
    except TypeError:
        return "unverifiable"
    return "met" if ok else "not_met"


def _resolve(row: dict[str, Any], kpis: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Row with a concrete threshold: {kpi} -> that KPI's value, {kpi_limit} -> the limit the module used and its source."""
    r = dict(row)
    thr = r["threshold"]
    if isinstance(thr, dict) and "kpi" in thr:
        e = kpis.get(thr["kpi"])
        r["threshold"] = e.get("value") if e else None
        r["threshold_ref"] = thr["kpi"]
        r["threshold_source"] = "kpi"
    elif isinstance(thr, dict) and "kpi_limit" in thr:
        e = kpis.get(thr["kpi_limit"])
        a = (e or {}).get("assessment") or {}
        r["threshold"] = a.get("threshold")
        r["threshold_ref"] = thr["kpi_limit"]
        r["threshold_source"] = a.get("threshold_source") or "module_limit"
        r["threshold_note"] = a.get("note") or ""
    return r


def _evaluate(row: dict[str, Any], kpis: dict[str, dict[str, Any]], modules_run: set[str]) -> dict[str, Any]:
    r = _resolve(row, kpis)
    module, label, unit = r["module"], r["label"], _unit(r["unit"])
    c = {"module": module, "metric": label, "operator": r["operator"], "threshold": r["threshold"], "unit": r["unit"], "kpi_id": r["kpi_id"],
         "rule": r["rule"], "group": r["group"], "threshold_source": r["threshold_source"], "value": None, "status": "not_verifiable",
         "reason": "", "evidence": ""}
    e = kpis.get(r["kpi_id"])
    if module not in modules_run:
        c["reason"] = c["evidence"] = f"{module} did not run in this workflow"
        return c
    if e is None or e.get("value") is None:
        c["reason"] = c["evidence"] = f"{module} did not report {label.lower()}"
        return c
    if r["threshold"] is None:
        what = r.get("threshold_ref") or "its threshold"
        c["value"] = e["value"]
        c["reason"] = c["evidence"] = f"{label}: no value for {what}" + (" (the module reported no limit)" if r["threshold_source"] not in ("kpi", "requirement") else "")
        return c
    v = e["value"]
    res = _compare(v, r["operator"], r["threshold"])
    c["value"] = round(v, 4) if isinstance(v, float) else v
    shown = f"{_fmt(v)}{(' ' + unit) if unit else ''}{_ctx_text(e)}"
    lim = _fmt(r["threshold"]) + ((" " + unit) if unit else "")
    if res == "unverifiable":
        c["reason"] = c["evidence"] = f"{label}: the module reported '{v}', not a value that settles {r['operator']} {lim}"
        return c
    c["status"] = res
    if res == "met":
        c["evidence"] = f"{label}: {shown} {r['operator']} {lim}"
        return c
    sym = "outside" if r["operator"] == "in" else _NEG.get(r["operator"], "!=")
    src = ""
    if r.get("threshold_ref") and r["threshold_source"] not in ("kpi",):
        note = r.get("threshold_note") or ""
        src = f" ({r['threshold_source'].replace('_', ' ')} limit{': ' + note if note else ''})"
    c["evidence"] = f"{label}: {shown} {sym} {lim}{src}"
    c["reason"] = c["evidence"] + (f". {r['note_not_met']}" if r.get("note_not_met") else "")
    return c


def _module_checks(rid: str, module: str, kpis: dict[str, dict[str, Any]], modules_run: set[str]) -> list[dict[str, Any]]:
    """The module's own checks that name the requirement (assessment.requirement_ids, threshold_source requirement / component)."""
    out = []
    for kid, e in kpis.items():
        a = e.get("assessment") or {}
        if module and e.get("module_id") != module:
            continue
        if rid in (a.get("requirement_ids") or []) and a.get("threshold_source") in ("requirement", "component"):
            out.append({"rule": f"M-{e.get('module_id')}", "kind": "module", "group": "module", "kpi_id": kid, "module": e.get("module_id"),
                        "operator": a.get("operator") or "", "threshold": a.get("threshold"), "threshold_source": a.get("threshold_source"),
                        "unit": a.get("unit") or e.get("unit") or "", "label": e.get("name") or kid, "note_not_met": ""})
    return out


def _evaluate_module(row: dict[str, Any], kpis: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """A check the module made itself: meets true / false / null, its message as evidence."""
    e = kpis[row["kpi_id"]]
    a = e.get("assessment") or {}
    meets = a.get("meets")
    note = str(a.get("note") or "")
    c = {"module": row["module"], "metric": row["label"], "operator": row["operator"] if row["operator"] != "==" or not isinstance(a.get("threshold"), bool) else "",
         "threshold": None if isinstance(a.get("threshold"), bool) else a.get("threshold"), "unit": row["unit"] if row["unit"] != "bool" else "",
         "kpi_id": row["kpi_id"], "rule": row["rule"], "group": "module", "threshold_source": row["threshold_source"],
         "value": e.get("value"), "status": "met" if meets is True else "not_met" if meets is False else "not_verifiable",
         "reason": note if meets is not True else "", "evidence": f"{row['label']}: {note}" if note else row["label"]}
    return c


def check_requirement(req: dict[str, Any], kpis: dict[str, dict[str, Any]], rules: dict[str, Any] | None = None,
                      plan: dict[str, Any] | None = None) -> dict[str, Any]:
    rules = rules or load_rules()
    plan = plan or plan_requirement(req, rules)
    rid = plan["id"]
    modules_run = {e.get("module_id") for e in kpis.values()}
    rows = list(plan["rows"])
    module_rows: list[dict[str, Any]] = []
    for r in [x for x in rows if x["kind"] == "module"]:
        mine = _module_checks(rid, r["module"], kpis, modules_run)
        if mine:
            module_rows += mine
        elif r["module"] not in modules_run:
            module_rows.append({**r, "kind": "module_missing"})
    # module checks that name the requirement, rule or not
    named = {x["kpi_id"] for x in module_rows if x["kind"] == "module"}
    module_rows += [x for x in _module_checks(rid, "", kpis, modules_run) if x["kpi_id"] not in named]
    rows = [x for x in rows if x["kind"] != "module"] + module_rows

    checks: list[dict[str, Any]] = []
    units: dict[str, list[dict[str, Any]]] = {}            # evaluation unit -> its checks (an any_of rule is one unit)
    evidence_kpis: list[dict[str, Any]] = []
    seen: set[tuple] = set()
    for r in rows:
        if r["kind"] == "evidence":
            e = kpis.get(r["kpi_id"])
            evidence_kpis.append({"kpi_id": r["kpi_id"], "module": r["module"], "rule": r["rule"], "present": bool(e and e.get("value") is not None),
                                  "name": (e or {}).get("name") or r["kpi_id"], "value": (e or {}).get("value"), "unit": (e or {}).get("unit", ""),
                                  "context": (e or {}).get("context", {})})
            continue
        if r["kind"] == "module_missing":
            msg = f"{r['module']} did not run in this workflow"
            c = {"module": r["module"], "metric": f"{r['module']} checks", "operator": "", "threshold": None, "unit": "", "kpi_id": None, "rule": r["rule"],
                 "group": "module", "threshold_source": "component", "value": None, "status": "not_verifiable", "reason": msg, "evidence": msg}
        else:
            thr = r["threshold"]
            sig = (r["kpi_id"], r["operator"], float(thr) if isinstance(thr, (int, float)) and not isinstance(thr, bool) else json.dumps(thr, default=str),
                   r["group"].startswith("any_of"))
            if sig in seen:                                 # the same kpi / operator / threshold is kept once, the rule's first
                continue
            seen.add(sig)
            c = _evaluate_module(r, kpis) if r["kind"] == "module" else _evaluate(r, kpis, modules_run)
        checks.append(c)
        units.setdefault(f"any:{r['rule']}" if r["group"].startswith("any_of") else f"all:{len(checks)}", []).append(c)

    unit_status: list[tuple[str, list[dict[str, Any]]]] = []
    for key, cs in units.items():
        if key.startswith("any:"):
            branches: dict[str, list[dict[str, Any]]] = {}
            for c in cs:
                branches.setdefault(c["group"], []).append(c)
            bs = ["met" if all(c["status"] == "met" for c in b) else "not_met" if any(c["status"] == "not_met" for c in b) else "not_verifiable"
                  for b in branches.values()]
            st = "met" if "met" in bs else "not_met" if all(s == "not_met" for s in bs) else "not_verifiable"
        else:
            st = cs[0]["status"]
        unit_status.append((st, cs))

    statuses = [s for s, _ in unit_status]
    reason = ""
    ev_missing = [e for e in evidence_kpis if not e["present"]]
    if "not_met" in statuses:
        status = "not_met"
        bad = []
        for s, cs in unit_status:
            if s != "not_met":
                continue
            if cs[0]["group"].startswith("any_of"):
                bad.append("none of the alternatives is met: " + "; ".join(c["evidence"] for c in cs)
                           + next((f". {r['note_not_met']}" for r in rows if r.get("rule") == cs[0]["rule"] and r.get("note_not_met")), ""))
            else:
                bad.append(cs[0]["reason"] or cs[0]["evidence"])
        reason = " | ".join(dict.fromkeys(bad))
    elif statuses:
        if all(s == "met" for s in statuses):
            status = "met" if not ev_missing else "partially_verified"
            if ev_missing:
                reason = "not reported: " + ", ".join(e["kpi_id"] for e in ev_missing[:6])
        elif "met" in statuses:
            status = "partially_verified"
            reason = "some checks could not be verified: " + "; ".join(dict.fromkeys(c["reason"] for _, cs in unit_status for c in cs if c["status"] == "not_verifiable" and c["reason"]))[:300]
        else:
            status = "not_verifiable"
            reason = "; ".join(dict.fromkeys(c["reason"] for _, cs in unit_status for c in cs if c["reason"]))[:300]
    elif evidence_kpis:
        present = [e for e in evidence_kpis if e["present"]]
        if not ev_missing:
            status, reason = "evidence_provided", "the analysis the requirement asks for is in the results of " + ", ".join(sorted({e["module"] for e in evidence_kpis})) + " (no threshold to verify)"
        elif present:
            status, reason = "partially_verified", "evidence from " + ", ".join(sorted({e["module"] for e in present})) + "; not reported: " + ", ".join(e["kpi_id"] for e in ev_missing[:6])
        else:
            status = "not_verifiable"
            reason = ", ".join(sorted({e["module"] for e in evidence_kpis})) + " did not run in this workflow or reported none of the evidence"
    elif plan["status_rules"]:
        applied = [s for s in plan["status_rules"] if s["status"] == "applied"]
        if applied:
            status = "applied"
            reason = "; ".join(dict.fromkeys(s["reason"] for s in applied if s["reason"]))
        else:
            status = "not_verifiable"
            reason = "; ".join(dict.fromkeys(s["reason"] for s in plan["status_rules"] if s["reason"]))
    elif plan["rules"]:
        status, reason = "not_verifiable", "the modules reported no check for this requirement"
    else:
        status, reason = "not_verifiable", "no quantity STAR computes is stated in this requirement"
    return {"id": rid, "text": plan["text"], "status": status, "reason": reason, "rules": plan["rules"], "checks": checks,
            "evidence_kpis": evidence_kpis}


# --------------------------------------------------------------------------- per-run map requirement x check
def map_rows(plans: list[dict[str, Any]], kpis: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """requirement_kpi_map rows: req_id, rule, kpi_id, module, operator, threshold, threshold_source, unit, group.
    With the KPIs of a run the thresholds that come from another KPI are resolved and the module checks are listed."""
    out = []
    for pl in plans:
        for r in pl["rows"]:
            if r["kind"] == "module" and kpis is not None:
                continue
            if kpis is not None and r["kind"] == "check":
                r = _resolve(r, kpis)
            out.append({"req_id": pl["id"], "rule": r["rule"], "kpi_id": r["kpi_id"] or f"{r['module']}.<module checks naming the requirement>",
                        "module": r["module"], "operator": r["operator"], "threshold": r["threshold"],
                        "threshold_source": r["threshold_source"], "unit": r["unit"], "group": r["group"]})
        if kpis is not None:
            for r in _module_checks(pl["id"], "", kpis, set()):
                out.append({"req_id": pl["id"], "rule": r["rule"], "kpi_id": r["kpi_id"], "module": r["module"], "operator": r["operator"],
                            "threshold": r["threshold"], "threshold_source": r["threshold_source"], "unit": r["unit"], "group": "module"})
    return out


def build_map(requirements: list[dict[str, Any]], kpis: dict[str, dict[str, Any]] | None = None, rules: dict[str, Any] | None = None) -> dict[str, Any]:
    rules = rules or load_rules()
    plans = [plan_requirement(r, rules) for r in requirements or [] if isinstance(r, dict) and r.get("text")]
    return _clean({"schema_version": 1, "generated_at": datetime.now().isoformat(timespec="seconds"), "rules_file": RULES_PATH.name,
                   "stage": "planning" if kpis is None else "run", "read_only": True,
                   "rows": map_rows(plans, kpis),
                   "requirements": [{"id": p["id"], "parameters": p["parameters"], "rules": p["rules"]} for p in plans],
                   "no_kpi": [p["id"] for p in plans if not any(r["kind"] != "module" or True for r in p["rows"]) and not p["status_rules"]]})


def write_map(path: str | Path, requirements: list[dict[str, Any]], kpis: dict[str, dict[str, Any]] | None = None) -> Path:
    """Write requirement_kpi_map.json (the planning version when no run KPIs are given)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build_map(requirements, kpis), indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- KPI table, fallbacks, build
def kpi_table(kpis: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for kid, e in kpis.items():
        if e.get("value") is None or ".check_" in kid:
            continue
        v = e["value"]
        rows.append({"id": kid, "module": e.get("module_id"), "name": e.get("name"), "value": round(v, 4) if isinstance(v, float) else v,
                     "unit": _unit(e.get("unit")) if e.get("unit") not in ("C", "U", "bool", "-") else e.get("unit"),
                     "category": e.get("category"), "native_id": e.get("native_id"), "context": e.get("context") or {},
                     "node": e.get("node")})
    return rows


def module_assessments(kpis: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """The modules' own verdicts. Those with a threshold the module chose (auto, module_default) are informative only."""
    out = []
    for kid, e in kpis.items():
        a = e.get("assessment")
        if not a:
            continue
        out.append({"kpi_id": kid, "module": e.get("module_id"), "name": e.get("name"), "value": e.get("value"), "unit": e.get("unit"),
                    "meets": a.get("meets"), "operator": a.get("operator"), "threshold": a.get("threshold"),
                    "threshold_source": a.get("threshold_source"), "requirement_ids": a.get("requirement_ids") or [], "note": a.get("note") or "",
                    "informative": a.get("threshold_source") in ("auto", "module_default")})
    return out


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


def critical_fallbacks(run_path: Path) -> dict[str, list[str]]:
    """{module: [items]} of the modules that completed with a critical fallback (star_provenance.json of the run)."""
    data = _load(run_path / "star_provenance.json") or {}
    out: dict[str, list[str]] = {}
    for m in data.get("modules", []):
        if m.get("status") == "completed_with_fallback" and m.get("fallback_severity") == "critical":
            out.setdefault(str(m.get("module_id")), []).extend(str(f.get("item")) for f in m.get("fallbacks", []))
    return out


def apply_fallbacks(rows: list[dict[str, Any]], fallbacks: dict[str, list[str]]) -> None:
    """A 'met' or 'evidence_provided' verdict computed from a module that used a critical fallback is only partially verified."""
    for r in rows:
        if r["status"] not in ("met", "evidence_provided"):
            continue
        used = sorted({c["module"] for c in r["checks"] if c["module"] in fallbacks} |
                      {e["module"] for e in r.get("evidence_kpis", []) if e["module"] in fallbacks})
        if used:
            r["status"] = "partially_verified"
            r["reason"] = "; ".join(f"{m} used a critical fallback ({', '.join(fallbacks[m][:3])})" for m in used)


def build(run_path: str | Path, requirements: list[dict[str, Any]], run_mode: str = "test", workflow: list | None = None,
          write: bool = True, out_dir: str | Path | None = None) -> dict[str, Any]:
    """Compliance of a run: compliance.json (+ _data.js), requirement_kpi_map.json, traceability.json / .csv in <run>/compliance
    (or out_dir, to recompute a finished run without touching it)."""
    run_path = Path(run_path)
    out = Path(out_dir) if out_dir else run_path / "compliance"
    rules = load_rules()
    kpis = run_kpis(run_path)
    reqs = [r for r in requirements or [] if isinstance(r, dict) and r.get("text")]
    plans = [plan_requirement(r, rules) for r in reqs]
    rows = [check_requirement(r, kpis, rules, pl) for r, pl in zip(reqs, plans)]
    fallbacks = critical_fallbacks(run_path)
    apply_fallbacks(rows, fallbacks)
    counts = {s: sum(1 for r in rows if r["status"] == s) for s in STATUSES}
    modules_run = sorted({e.get("module_id") for e in kpis.values() if e.get("module_id")})
    data = {
        "generated_at": datetime.now().isoformat(),
        "run_mode": run_mode,
        "note": ("Test mode: every module ran with its fastest settings, the values are not meaningful." if run_mode != "full" else ""),
        "modules_run": modules_run,
        "workflow": [s.get("module_id") for s in (workflow or [])],
        "counts": counts,
        "requirements": rows,
        "module_assessments": module_assessments(kpis),
        "kpis": kpi_table(kpis),
        "sources": {m: next((e.get("_file") for e in kpis.values() if e.get("module_id") == m), None) for m in modules_run},
    }
    try:
        from . import star_traceability as T
    except ImportError:
        import star_traceability as T
    trace = T.build(run_path, rows, build_map(reqs, kpis, rules), kpis, write=write, out_dir=out)
    data["traceability"] = {"gaps": trace["gaps"], "file": "compliance/traceability.json"}
    data = _clean(data)
    if write:
        out.mkdir(parents=True, exist_ok=True)
        (out / "compliance.json").write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        (out / "compliance_data.js").write_text("window.starComplianceData = " + json.dumps(data, ensure_ascii=False, default=str) + ";\n", encoding="utf-8")
        (out / "requirement_kpi_map.json").write_text(json.dumps(build_map(reqs, kpis, rules), indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return data

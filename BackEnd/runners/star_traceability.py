"""STAR traceability matrix (phase E, step E4, 2026-10-22).

Built by ``star_compliance.build`` from the requirement rows, the per-run requirement->KPI map and the KPIs of the run.
Files in <run>/compliance:

- ``traceability.json``: per requirement the chain requirement -> rule -> KPI -> product file -> module node -> module
  status / fallbacks (``star_provenance.json``); the matrix requirements x workflow nodes (cell = KPI ids and worst status);
  the gaps (requirements with no KPI, mission-compliance KPIs linked to no requirement).
- ``traceability.csv``: one row per requirement-KPI link, for export.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

try:
    from . import star_kpis as K
except ImportError:
    import star_kpis as K

REGISTRY_DIR = Path(__file__).resolve().parents[2] / "Input" / "input_base_knowledge" / "registry"
# worst first: what a cell of the matrix shows when several links meet in it
_SEVERITY = ("not_met", "not_verifiable", "partially_verified", "evidence_provided", "met")


def _load(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def _registry():
    try:
        try:
            from . import star_workflow_graph as G
        except ImportError:
            import star_workflow_graph as G
        return G.Registry.load(REGISTRY_DIR)
    except Exception:
        return None


def _product_file(registry: Any, kpi: dict[str, Any]) -> str:
    """Registry path of the product the KPI comes from ('' when the registry does not list it)."""
    product = (kpi.get("source") or {}).get("product") or ""
    if kpi.get("node") == "END-006/initial":
        product = K.END006_INITIAL_PRODUCTS.get(product, product)
    spec = registry.produce_spec(product) if registry and product else None
    return f"{kpi.get('module_id')}/{spec.get('path')}" if spec else ""


def _link_status(check: dict[str, Any] | None, evidence: dict[str, Any] | None) -> str:
    if check is not None:
        return check.get("status", "not_verifiable")
    if evidence is not None:
        return "evidence_provided" if evidence.get("present") else "not_verifiable"
    return "not_verifiable"


def build(run_path: str | Path, rows: list[dict[str, Any]], kpi_map: dict[str, Any], kpis: dict[str, dict[str, Any]],
          write: bool = True, out_dir: str | Path | None = None) -> dict[str, Any]:
    run_path = Path(run_path)
    registry = _registry()
    prov = {m.get("node") or m.get("module_id"): m for m in (_load(run_path / "star_provenance.json") or {}).get("modules", [])}
    by_req = {r["id"]: r for r in rows}

    def module_state(node: str | None, module: str | None) -> tuple[str, list[str]]:
        m = prov.get(node) or prov.get(module) or {}
        return str(m.get("status") or ""), [str(f.get("item")) for f in m.get("fallbacks", [])]

    chain: list[dict[str, Any]] = []
    linked: set[str] = set()
    for r in rows:
        links = []
        for c in r["checks"]:
            e = kpis.get(c.get("kpi_id") or "")
            links.append((c.get("kpi_id"), c.get("rule"), c.get("group"), c, None, e))
        for ev in r.get("evidence_kpis", []):
            links.append((ev["kpi_id"], ev["rule"], "evidence", None, ev, kpis.get(ev["kpi_id"])))
        for kid, rule, group, check, ev, e in links:
            if kid:
                linked.add(kid)
            node = (e or {}).get("node") or (kid or "").split(".")[0]
            module = (e or {}).get("module_id") or (check or ev or {}).get("module")
            mstatus, fb = module_state(node, module)
            chain.append({
                "req_id": r["id"], "req_status": r["status"], "rule": rule, "group": group, "kpi_id": kid,
                "kpi_name": (e or {}).get("name") or (check or {}).get("metric") or kid or "",
                "value": (e or {}).get("value", (check or {}).get("value")), "unit": (e or {}).get("unit", ""),
                "operator": (check or {}).get("operator", ""), "threshold": (check or {}).get("threshold"),
                "threshold_source": (check or {}).get("threshold_source", ""), "link_status": _link_status(check, ev),
                "evidence": (check or {}).get("evidence", ""), "module": module, "node": node,
                "product": ((e or {}).get("source") or {}).get("product", ""), "product_file": _product_file(registry, e or {}),
                "module_status": mstatus, "fallbacks": fb})
    # matrix requirements x nodes
    nodes = sorted({c["node"] for c in chain if c["node"]})
    matrix: dict[str, dict[str, Any]] = {}
    for c in chain:
        if not c["node"]:
            continue
        cell = matrix.setdefault(c["req_id"], {}).setdefault(c["node"], {"kpis": [], "status": "met"})
        if c["kpi_id"] and c["kpi_id"] not in cell["kpis"]:
            cell["kpis"].append(c["kpi_id"])
        st = c["link_status"]
        if c["group"].startswith("any_of") and c["req_status"] == "met" and st == "not_met":
            st = "met"                       # an alternative that failed while another one is met
        if _SEVERITY.index(st) < _SEVERITY.index(cell["status"]) if st in _SEVERITY else False:
            cell["status"] = st
        if c["fallbacks"] and c["module_status"] == "completed_with_fallback" and cell["status"] in ("met", "evidence_provided"):
            cell["status"] = "partially_verified" if _critical(prov, c["node"]) else cell["status"]
    no_kpi = [r["id"] for r in rows if r["id"] not in {c["req_id"] for c in chain if c["kpi_id"]}]
    unlinked = [{"kpi_id": kid, "name": e.get("name"), "module": e.get("module_id"), "value": e.get("value"), "unit": e.get("unit")}
                for kid, e in sorted(kpis.items()) if e.get("category") == "mission_compliance" and kid not in linked and e.get("value") is not None]
    out = {"schema_version": 1, "generated_at": K.datetime.now().isoformat(timespec="seconds"), "run_id": run_path.name,
           "nodes": nodes, "matrix": matrix, "chain": chain,
           "gaps": {"requirements_without_kpi": [{"req_id": i, "status": by_req[i]["status"], "reason": by_req[i]["reason"]} for i in no_kpi],
                    "kpis_without_requirement": unlinked}}
    if write:
        d = Path(out_dir) if out_dir else run_path / "compliance"
        d.mkdir(parents=True, exist_ok=True)
        (d / "traceability.json").write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        cols = ["req_id", "req_status", "rule", "group", "kpi_id", "kpi_name", "value", "unit", "operator", "threshold", "threshold_source",
                "link_status", "evidence", "module", "node", "product", "product_file", "module_status", "fallbacks"]
        with open(d / "traceability.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for c in chain:
                w.writerow({**c, "threshold": json.dumps(c["threshold"]) if isinstance(c["threshold"], (list, dict)) else c["threshold"],
                            "fallbacks": "; ".join(c["fallbacks"])})
            for i in no_kpi:                                           # a requirement with no link still has a row (a gap)
                w.writerow({"req_id": i, "req_status": by_req[i]["status"], "link_status": "gap: no KPI is linked"})
    return out


def _critical(prov: dict[str, Any], node: str | None) -> bool:
    return (prov.get(node) or {}).get("fallback_severity") == "critical"

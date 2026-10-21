"""Provenance of a module run (phase C): where each input value comes from and which ones are fallbacks.

Runners already record decisions as {"value", "source"} (END-003/END-004 `endXXX_inputs`) or as a name -> origin dict
(END-016/END-019 `provenance`); the adapters below turn them into entries. A source that starts with "template", "default",
"registry default" or "first guess", or says "not available" / "not found" / "not published", is a fallback.
Severity: critical when the substituted value drives a requirement or KPI (CRITICAL_ITEMS), otherwise minor.
"""
from __future__ import annotations

import json
from typing import Any

FALLBACK_MARKERS = ("template", "default", "registry default", "first guess", "not available", "not found", "not published",
                    "no end-006", "not reviewed")

# items whose fallback changes the result of the module (matched as prefix of the item name)
CRITICAL_ITEMS: dict[str, tuple[str, ...]] = {
    "END-001": ("ground_stations", "orbit"),
    "END-003": ("spacecraft",),
    "END-004": ("orbit", "duty_cycles", "satellite", "power_generated_per_orbit_Wh", "battery_capacity_Wh", "subsystems"),
    "END-010": ("attitude",),
    "END-016": ("spacecraft.",),
    "END-019": ("form_factor",),
}


def is_fallback_source(source: Any) -> bool:
    s = str(source or "").strip().lower()
    return bool(s) and any(s.startswith(m) or m in s for m in FALLBACK_MARKERS)


class Provenance:
    def __init__(self, module_id: str) -> None:
        self.module_id = module_id
        self.entries: list[dict[str, Any]] = []

    def record(self, item: str, value: Any, source: str, kind: str | None = None, severity: str | None = None,
               reason: str = "") -> None:
        kind = kind or ("fallback" if is_fallback_source(source) else "input")
        if kind == "fallback" and severity is None:
            crit = CRITICAL_ITEMS.get(self.module_id, ())
            severity = "critical" if any(item == c or item.startswith(c) for c in crit) else "minor"
        self.entries.append({"item": item, "value": _short(value), "source": str(source), "kind": kind,
                             "severity": severity if kind == "fallback" else None, "reason": reason})

    def fallbacks(self) -> list[dict[str, Any]]:
        return [e for e in self.entries if e["kind"] == "fallback"]

    def worst_severity(self) -> str | None:
        fb = self.fallbacks()
        if not fb:
            return None
        return "critical" if any(e["severity"] == "critical" for e in fb) else "minor"

    def add_decisions(self, decisions: Any, prefix: str = "") -> None:
        """Walk a decisions dict: entries {"value", "source"} (or nested ones) become records."""
        if not isinstance(decisions, dict):
            return
        for name, d in decisions.items():
            if not isinstance(d, dict):
                continue
            if "source" in d:
                self.record(prefix + name, d.get("value"), d["source"])
            elif not any(k.endswith("_source") for k in d):
                self.add_decisions(d, prefix + name + ".")
            # sub-sources of a decision ("wheels_source": "END-003 template"): one entry each
            for key, source in d.items():
                if key.endswith("_source") and isinstance(source, str):
                    self.record(f"{prefix}{name}.{key[:-len('_source')]}", None, source)

    def add_origins(self, origins: Any, values: Any = None) -> None:
        """Flat name -> origin dict (END-016 / END-019 `provenance`)."""
        if not isinstance(origins, dict):
            return
        for name, source in origins.items():
            self.record(name, (values or {}).get(name) if isinstance(values, dict) else None, str(source))

    def to_json(self, status: str = "", evidence: str = "") -> dict[str, Any]:
        return {"module_id": self.module_id, "status": status, "fallback_severity": self.worst_severity(),
                "evidence": evidence, "entries": self.entries, "fallbacks": self.fallbacks()}


def _short(value: Any, limit: int = 200) -> Any:
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        text = str(value)
    return value if len(text) <= limit else text[:limit] + "..."


def from_runtime_decisions(module_id: str, runtime_data: dict[str, Any], key: str) -> Provenance:
    """Provenance from `star_runtime.<key>` of a runner's runtime input (END-003: end003_inputs, END-004: end004_inputs)."""
    prov = Provenance(module_id)
    prov.add_decisions(((runtime_data or {}).get("star_runtime") or {}).get(key))
    return prov

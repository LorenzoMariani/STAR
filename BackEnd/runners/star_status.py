"""Execution statuses of a STAR module run (phase C): one definition used by the runners, the orchestrator and the tests.

completed                a real run with every input from its producer or from the user
completed_with_fallback  a real run that used a fallback for an OPTIONAL input (severity critical | minor)
failed                   the run raised an error or a REQUIRED input is missing (no fallback for required inputs)
stopped                  the user stopped it
skipped_out_of_scope     the runner decided the mission is outside the module's domain (not an error)
skipped_blocked          not launched: the module cannot run here or an upstream module it requires did not produce its data
"""
from __future__ import annotations

from typing import Any

COMPLETED = "completed"
FALLBACK = "completed_with_fallback"
FAILED = "failed"
STOPPED = "stopped"
SKIP_SCOPE = "skipped_out_of_scope"
SKIP_BLOCKED = "skipped_blocked"

EXECUTION_STATUSES = [COMPLETED, FALLBACK, FAILED, STOPPED, SKIP_SCOPE, SKIP_BLOCKED]
SUCCESS = {COMPLETED, FALLBACK}


def normalize(status: Any) -> str:
    """Legacy plain 'skipped' (runner decision) is the out-of-scope skip."""
    s = str(status or "").strip().lower()
    return SKIP_SCOPE if s == "skipped" else s


def is_skipped(status: Any) -> bool:
    return normalize(status) in (SKIP_SCOPE, SKIP_BLOCKED)


def is_success(status: Any) -> bool:
    return normalize(status) in SUCCESS


def ui_status(status: Any, severity: str | None = None) -> str:
    """Module card status of the execution page: Completed / Fallback (critical) / Skipped / Error / Stopped."""
    s = normalize(status)
    if s == COMPLETED:
        return "Completed"
    if s == FALLBACK:
        return "Fallback" if severity == "critical" else "Completed"
    if is_skipped(s):
        return "Skipped"
    if s == STOPPED:
        return "Stopped"
    return "Error"


def finalize(status: str, provenance: Any) -> tuple[str, str | None]:
    """(status, severity): a 'completed' run that used fallbacks becomes completed_with_fallback; other statuses are kept."""
    if normalize(status) == COMPLETED and provenance is not None and provenance.fallbacks():
        return FALLBACK, provenance.worst_severity()
    return normalize(status), None


def fallback_sentence(provenance: Any, limit: int = 4) -> str:
    """'Fallbacks (critical): item (reason); ...' computed from the provenance, '' without fallbacks."""
    fb = provenance.fallbacks() if provenance is not None else []
    if not fb:
        return ""
    shown = "; ".join(f"{f['item']} ({f['source']})" for f in fb[:limit])
    more = f"; +{len(fb) - limit} more" if len(fb) > limit else ""
    return f"Fallbacks ({provenance.worst_severity()}): {shown}{more}."


def evidence(module: str, status: str, provenance: Any = None, facts: str = "", reason: str = "") -> str:
    """Evidence text computed from the run: what was done (facts), the fallbacks, or why it was not run."""
    s = normalize(status)
    if is_skipped(s):
        return f"{module} not run: {reason}." if reason else f"{module} not run."
    if s == FAILED:
        return f"{module} failed: {reason}." if reason else f"{module} failed."
    if s == STOPPED:
        return f"{module} stopped by user request."
    parts = [facts.strip().rstrip(".") + "." if facts.strip() else f"{module} completed."]
    fb = fallback_sentence(provenance)
    if fb:
        parts.append(fb)
    return " ".join(parts)

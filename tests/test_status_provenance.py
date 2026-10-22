"""Phase C: execution statuses, provenance and computed evidence (BackEnd/runners/star_status.py, star_provenance.py)."""
import sys
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "BackEnd"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from runners import star_status as ss                                    # noqa: E402
from runners.star_provenance import Provenance, from_runtime_decisions   # noqa: E402


class TestStatus(unittest.TestCase):
    def test_legacy_skipped_is_out_of_scope(self):
        self.assertEqual(ss.normalize("skipped"), ss.SKIP_SCOPE)
        self.assertTrue(ss.is_skipped("skipped"))
        self.assertTrue(ss.is_skipped(ss.SKIP_BLOCKED))
        self.assertFalse(ss.is_skipped(ss.FAILED))

    def test_ui_status_skipped_is_not_error(self):
        self.assertEqual(ss.ui_status(ss.SKIP_SCOPE), "Skipped")
        self.assertEqual(ss.ui_status("skipped"), "Skipped")
        self.assertEqual(ss.ui_status(ss.SKIP_BLOCKED), "Skipped")
        self.assertEqual(ss.ui_status(ss.FAILED), "Error")
        self.assertEqual(ss.ui_status(ss.STOPPED), "Stopped")
        self.assertEqual(ss.ui_status(ss.COMPLETED), "Completed")
        self.assertEqual(ss.ui_status(ss.FALLBACK, "critical"), "Fallback")
        self.assertEqual(ss.ui_status(ss.FALLBACK, "minor"), "Completed")

    def test_success_does_not_block_downstream(self):
        self.assertTrue(ss.is_success(ss.COMPLETED))
        self.assertTrue(ss.is_success(ss.FALLBACK))
        for s in (ss.FAILED, ss.STOPPED, ss.SKIP_SCOPE, ss.SKIP_BLOCKED):
            self.assertFalse(ss.is_success(s))

    def test_finalize_upgrades_only_completed(self):
        clean, dirty = Provenance("END-004"), Provenance("END-004")
        clean.record("orbit", 1, "END-001 orbit of the satellite selected by END-003")
        dirty.record("duty_cycles", None, "template (END-001 operations_summary.json not available)")
        self.assertEqual(ss.finalize("completed", clean), (ss.COMPLETED, None))
        self.assertEqual(ss.finalize("completed", dirty), (ss.FALLBACK, "critical"))
        self.assertEqual(ss.finalize("failed", dirty), (ss.FAILED, None))
        self.assertEqual(ss.finalize("stopped", dirty), (ss.STOPPED, None))

    def test_evidence_is_computed(self):
        dirty = Provenance("END-004")
        dirty.record("duty_cycles", None, "template (END-001 operations_summary.json not available)")
        text = ss.evidence("END-004", ss.FALLBACK, dirty, "Power budget from END-003")
        self.assertIn("Power budget from END-003.", text)
        self.assertIn("Fallbacks (critical): duty_cycles", text)
        self.assertEqual(ss.evidence("END-006", ss.SKIP_SCOPE, reason="mission names no CubeSat"), "END-006 not run: mission names no CubeSat.")
        self.assertIn("failed", ss.evidence("END-004", ss.FAILED, reason="missing x"))


class TestProvenance(unittest.TestCase):
    def test_severity_by_item(self):
        p = Provenance("END-004")
        p.record("orbit", None, "template (END-003/END-001 products not found)")
        p.record("mode_orbits_per_day", None, "default")
        p.record("battery_capacity_Wh", 10, "END-006 initial design")
        self.assertEqual([e["severity"] for e in p.fallbacks()], ["critical", "minor"])
        self.assertEqual(p.worst_severity(), "critical")

    def test_decisions_adapter(self):
        runtime = {"star_runtime": {"end003_inputs": {
            "attitude_mode": {"value": "nadir", "source": "template"},
            "spacecraft": {"value": {"m": 4}, "source": "END-006 initial design (3U)"},
            "attitude_control": {"value": {}, "wheels_source": "END-003 template", "knowledge_source": "END-003 template"}}}}
        p = from_runtime_decisions("END-003", runtime, "end003_inputs")
        items = {e["item"]: e for e in p.entries}
        self.assertEqual(items["attitude_mode"]["kind"], "fallback")
        self.assertEqual(items["attitude_mode"]["severity"], "minor")
        self.assertEqual(items["spacecraft"]["kind"], "input")
        self.assertEqual(items["attitude_control.wheels"]["kind"], "fallback")

    def test_origins_adapter_spacecraft_defaults_are_critical(self):
        p = Provenance("END-016")
        p.add_origins({"spacecraft.mass_kg": "default (END-001 template)", "spacecraft.cd": "END-006 initial design (spacecraft_definition.json)"})
        self.assertEqual([(f["item"], f["severity"]) for f in p.fallbacks()], [("spacecraft.mass_kg", "critical")])

    def test_no_fallbacks(self):
        p = Provenance("END-001")
        p.record("ground_stations", 2, "END-001 runtime input")
        self.assertEqual(p.fallbacks(), [])
        self.assertIsNone(p.worst_severity())
        self.assertEqual(p.to_json("completed")["fallbacks"], [])


class TestComplianceFallback(unittest.TestCase):
    def test_met_with_critical_fallback_is_partially_verified(self):
        from runners import star_compliance as sc
        rows = [{"id": "R1", "status": "met", "reason": "", "checks": [{"module": "END-004"}]},
                {"id": "R2", "status": "met", "reason": "", "checks": [{"module": "END-001"}]},
                {"id": "R3", "status": "not_met", "reason": "", "checks": [{"module": "END-004"}]},
                {"id": "R4", "status": "evidence_provided", "reason": "", "checks": [], "evidence_kpis": [{"module": "END-004", "kpi_id": "END-004.worst_dod_pct"}]},
                {"id": "R5", "status": "evidence_provided", "reason": "", "checks": [], "evidence_kpis": [{"module": "END-001", "kpi_id": "END-001.n_satellites"}]}]
        sc.apply_fallbacks(rows, {"END-004": ["duty_cycles"]})
        self.assertEqual([r["status"] for r in rows], ["partially_verified", "met", "not_met", "partially_verified", "evidence_provided"])
        self.assertIn("END-004 used a critical fallback (duty_cycles)", rows[0]["reason"])
        self.assertIn("END-004 used a critical fallback (duty_cycles)", rows[3]["reason"])


if __name__ == "__main__":
    unittest.main()

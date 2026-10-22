"""Phase E: generic compliance from kpis.json (BackEnd/runners/star_compliance.py, star_traceability.py).

Synthetic KPIs only: no module runs. Covers the cases of the phase-E design: REQ-020 not_met with the violating value in
its reason, REQ-001 met through any_of, evidence-only requirements, module flags with an auto threshold, critical
fallbacks, a module that did not run, and the traceability gaps.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "BackEnd"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

try:
    import yaml  # noqa: F401
    from runners import star_compliance as sc
    from runners import star_kpis as K
except ModuleNotFoundError:          # PyYAML is optional for the other STAR suites (requirements.txt)
    sc = None

REQ_REENTRY = {"id": "REQ-001", "text": "Each satellite shall re-enter the atmosphere within 5 years of the end of its mission."}
REQ_BATTERY = {"id": "REQ-020", "text": "The battery temperature of the CubeSat shall stay within its operational limit."}
REQ_THERMAL = {"id": "REQ-019", "text": "The temperatures of the CubeSat faces, solar panels, central body and battery shall be assessed along the orbit."}


def entry(kpi_id, value, **kw):
    """A KPI as K.load_run returns it (module_id and node added)."""
    e = K.kpi(kpi_id, value, **kw)
    e["module_id"] = kpi_id.split(".")[0]
    e["node"] = e["module_id"]
    return e


def kpis_of(*entries):
    return {e["id"]: e for e in entries}


def thermal(bat_min=-36.8, bat_max=8.6):
    return [entry("END-019.battery_min_C", bat_min, context={"case": "cold", "satellite": "SAT-03"},
                  assessment=K.assessment(bat_min >= 0, ">=", 0, "C", "module_default", note="default 0..45 degC")),
            entry("END-019.battery_max_C", bat_max, context={"case": "hot", "satellite": "SAT-01"},
                  assessment=K.assessment(bat_max <= 45, "<=", 45, "C", "module_default", note="default 0..45 degC")),
            entry("END-019.central_body_max_C", 8.5), entry("END-019.solar_panel_max_C", 90.0),
            entry("END-019.solar_panel_min_C", -60.0), entry("END-019.face_max_C", 90.0), entry("END-019.face_min_C", -60.0)]


@unittest.skipIf(sc is None, "PyYAML not installed")
class TestGenericCompliance(unittest.TestCase):
    def check(self, req, *entries):
        return sc.check_requirement(req, kpis_of(*entries))

    def test_battery_cold_case_is_not_met_with_the_violating_value(self):
        r = self.check(REQ_BATTERY, *thermal())
        self.assertEqual(r["status"], "not_met")
        self.assertIn("-36.8", r["reason"])
        bad = [c for c in r["checks"] if c["status"] == "not_met"]
        self.assertEqual([c["kpi_id"] for c in bad], ["END-019.battery_min_C"])
        self.assertIn("-36.8", bad[0]["evidence"])
        self.assertIn("cold", bad[0]["evidence"])

    def test_battery_inside_its_limits_is_met(self):
        r = self.check(REQ_BATTERY, *thermal(bat_min=5.0, bat_max=30.0))
        self.assertEqual(r["status"], "met")
        self.assertTrue(all(c["evidence"] for c in r["checks"]))

    def test_reentry_met_through_any_of(self):
        r = self.check(REQ_REENTRY,
                       entry("END-016.passive_lifetime_years", 10.3),               # passive decay too slow
                       entry("END-006.dv_capacity_m_s", 60.0),
                       entry("END-016.disposal_dv_5y_m_s", 40.0))                    # but the propulsion gives the disposal delta-v
        self.assertEqual(r["status"], "met")

    def test_reentry_not_met_when_no_branch_is_met(self):
        r = self.check(REQ_REENTRY,
                       entry("END-016.passive_lifetime_years", 10.3),
                       entry("END-006.dv_capacity_m_s", 20.0),
                       entry("END-016.disposal_dv_5y_m_s", 40.0))
        self.assertEqual(r["status"], "not_met")

    def test_evidence_only_requirement_is_never_met(self):
        r = self.check(REQ_THERMAL, *thermal())
        self.assertEqual(r["status"], "evidence_provided")
        self.assertEqual(r["checks"], [])
        self.assertTrue(r["evidence_kpis"] and all(e["present"] for e in r["evidence_kpis"]))

    def test_evidence_requirement_without_its_module_is_not_verifiable(self):
        r = self.check(REQ_THERMAL, entry("END-001.n_satellites", 3))
        self.assertEqual(r["status"], "not_verifiable")

    def test_missing_module_is_not_verifiable(self):
        r = self.check(REQ_BATTERY, entry("END-001.n_satellites", 3))
        self.assertEqual(r["status"], "not_verifiable")

    def test_auto_flag_of_a_module_does_not_change_the_status(self):
        # END-001 flags its revisit with a threshold it chose itself (auto): informative only
        flagged = entry("END-001.max_revisit_h", 217.5, assessment=K.assessment(False, "<=", 50.97, "h", "auto"))
        kp = kpis_of(flagged, *thermal(bat_min=5.0))
        before = sc.check_requirement(REQ_BATTERY, kp)["status"]
        flagged["assessment"] = K.assessment(True, "<=", 50.97, "h", "auto")
        self.assertEqual(sc.check_requirement(REQ_BATTERY, kp)["status"], before)
        listed = [a for a in sc.module_assessments(kp) if a["kpi_id"] == "END-001.max_revisit_h"]
        self.assertTrue(listed and listed[0]["informative"])

    def test_critical_fallback_downgrades_met_and_evidence(self):
        rows = [sc.check_requirement(REQ_BATTERY, kpis_of(*thermal(bat_min=5.0))),
                sc.check_requirement(REQ_THERMAL, kpis_of(*thermal()))]
        self.assertEqual([r["status"] for r in rows], ["met", "evidence_provided"])
        sc.apply_fallbacks(rows, {"END-019": ["eps_battery_limits"]})
        self.assertEqual([r["status"] for r in rows], ["partially_verified", "partially_verified"])
        self.assertIn("END-019 used a critical fallback", rows[0]["reason"])

    def test_build_writes_compliance_map_and_traceability(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "RUN_TEST"
            node = run / "modules_output" / "END-019"
            node.mkdir(parents=True)
            K.write(node, K.document("END-019", thermal(), run_id=run.name))
            data = sc.build(run, [REQ_BATTERY, REQ_THERMAL, {"id": "REQ-099", "text": "The mission shall be fun."}])
            comp = run / "compliance"
            for name in ("compliance.json", "requirement_kpi_map.json", "traceability.json", "traceability.csv"):
                self.assertTrue((comp / name).is_file(), name)
            self.assertEqual(data["counts"]["not_met"], 1)
            self.assertEqual(data["counts"]["evidence_provided"], 1)
            trace = json.loads((comp / "traceability.json").read_text(encoding="utf-8"))
            self.assertIn("END-019", trace["nodes"])
            self.assertEqual(trace["matrix"]["REQ-020"]["END-019"]["status"], "not_met")
            self.assertEqual(trace["matrix"]["REQ-019"]["END-019"]["status"], "evidence_provided")
            self.assertIn("REQ-099", [g["req_id"] for g in trace["gaps"]["requirements_without_kpi"]])
            chain = [c for c in trace["chain"] if c["req_id"] == "REQ-020" and c["link_status"] == "not_met"]
            self.assertTrue(chain and chain[0]["kpi_id"] == "END-019.battery_min_C")


if __name__ == "__main__":
    unittest.main()

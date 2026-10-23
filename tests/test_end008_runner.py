"""END-008 in the STAR backend (phase 2, 2026-10-23): runner, KPI adapter and compliance rule.

From the STAR folder:   python -m unittest discover -s tests -p "test_end008_*.py"     (run_all_tests.py: suite END-008)

The adapter and the rule run on synthetic data (CI). The runner tests that need the END-008 delivery (battery_monitoring.exe,
power_budget_to_input.py, plot_battery_monitoring.py; not in git) are skipped when it is missing.
"""
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

STAR = Path(__file__).resolve().parent.parent
BACKEND = STAR / "BackEnd"
FIX = Path(__file__).resolve().parent / "fixtures" / "end008"
VENDOR = STAR / "END008-BatteryHealthMonitoring"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

try:
    import yaml  # noqa: F401
    from runners import end008_runner as R
    from runners import star_compliance as sc
    from runners import star_kpi_adapters as A
    from runners import star_kpis as K
    from runners.star_runner_io import module_prerequisites
    from runners.star_workflow_graph import Registry, WorkflowGraph
except ModuleNotFoundError:          # PyYAML is optional for the other STAR suites (requirements.txt)
    R = None

HAS_LIBS = all(importlib.util.find_spec(m) for m in ("openpyxl", "pandas", "matplotlib"))
HAS_DELIVERY = all((VENDOR / f).is_file() for f in ("battery_monitoring.exe", "power_budget_to_input.py", "plot_battery_monitoring.py"))

SUMMARY = {"soh_end_of_mission": 0.78, "soh_p05": 0.75, "soh_p95": 0.81, "eol_threshold_soh": 0.8, "eol_reached": True,
           "eol_sigma_points": "3 of 5", "soc_min_mission": 0.55, "orbits_below_soc_min": 0, "orbits": 16000,
           "law_domain_outside_fraction": 0.25, "degradation_law_domain": {"temperature_C": {"outside": False}},
           "run_mode": "full", "settings": {"duration_years": 3.0, "temperature_C": 12.0, "cells_in_series": 2,
                                             "cells_in_parallel": 4, "SOC_min": 0.2}}
REQ_SOH = {"id": "REQ-030", "text": "The battery state of health shall stay above its end-of-life threshold over the mission lifetime."}
REQ_SOH_EVIDENCE = {"id": "REQ-031", "text": "The battery state of health over the mission shall be assessed."}


def run_kpis(summary):
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "output_battery_health_monitoring" / "battery_health_summary.json"
        p.parent.mkdir(parents=True)
        p.write_text(json.dumps(summary), encoding="utf-8")
        return A.build_document("END-008", tmp)


def entries(doc):
    out = {}
    for k in doc["kpis"]:
        out[k["id"]] = {**k, "module_id": "END-008", "node": "END-008"}
    return out


@unittest.skipIf(R is None, "PyYAML not installed")
class TestAdapterAndRule(unittest.TestCase):
    def test_kpis_in_percent_with_the_eol_verdict(self):
        doc = run_kpis(SUMMARY)
        self.assertEqual(K.validate(doc), [])
        k = entries(doc)
        self.assertEqual(set(k), {"END-008." + x for x in ("soh_end_of_mission", "soh_p05", "eol_reached", "soc_min_mission",
                                                             "orbits_below_soc_min", "law_domain_outside_fraction")})
        self.assertAlmostEqual(k["END-008.soh_end_of_mission"]["value"], 78.0)
        a = k["END-008.soh_end_of_mission"]["assessment"]
        self.assertEqual((a["meets"], a["operator"], a["threshold"], a["threshold_source"]), (False, ">=", 80.0, "module_default"))
        self.assertFalse(k["END-008.eol_reached"]["assessment"]["meets"])
        self.assertTrue(k["END-008.soc_min_mission"]["assessment"]["meets"])
        self.assertEqual(k["END-008.law_domain_outside_fraction"]["value"], 25.0)

    def test_no_summary_no_kpis(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(A.adapt("END-008", tmp), [])

    def test_rule_soh_against_the_eol_threshold(self):
        r = sc.check_requirement(REQ_SOH, entries(run_kpis(SUMMARY)))
        self.assertEqual(r["status"], "not_met")
        self.assertIn("78", r["reason"])
        r = sc.check_requirement(REQ_SOH, entries(run_kpis({**SUMMARY, "soh_end_of_mission": 0.9, "eol_reached": False})))
        self.assertEqual(r["status"], "met")
        self.assertEqual(sc.check_requirement(REQ_SOH, {})["status"], "not_verifiable")

    def test_evidence_rule(self):
        r = sc.check_requirement(REQ_SOH_EVIDENCE, entries(run_kpis(SUMMARY)))
        self.assertEqual(r["status"], "evidence_provided")


@unittest.skipIf(R is None, "PyYAML not installed")
class TestRunnerWithoutTheDelivery(unittest.TestCase):
    def test_missing_executable_is_a_clear_skip(self):
        with tempfile.TemporaryDirectory() as tmp:
            inp = Path(tmp) / "in.json"
            inp.write_text(json.dumps({"requirements": [], "run_mode": "test"}), encoding="utf-8")
            r = R.run_end008(str(inp), str(Path(tmp) / "END-008"), run_id="T", star_root=tmp)
            self.assertEqual(r["status"], "skipped_blocked")
            self.assertIn("battery_monitoring.exe not found", r["evidence"])
            ok, why = module_prerequisites("END-008", tmp)
            self.assertFalse(ok)
            self.assertIn("END008-BatteryHealthMonitoring", why)

    def test_lifetime_from_the_shared_rule(self):
        if not (VENDOR / "star_integration").is_dir():
            self.skipTest("star_integration not present")
        sys.path.insert(0, str(VENDOR / "star_integration"))
        import star_end008_input as inp
        years, src = R._lifetime([{"id": "REQ-002", "text": "The mission lifetime shall be three years."}], inp)
        self.assertEqual((years, src), (3.0, "requirement REQ-002 (mission lifetime)"))
        self.assertEqual(R._lifetime([], inp), (None, ""))


@unittest.skipIf(R is None, "PyYAML not installed")
@unittest.skipUnless(HAS_DELIVERY and HAS_LIBS, "END-008 delivery or openpyxl / pandas / matplotlib not present")
class TestRunnerWithTheExecutable(unittest.TestCase):
    """The real executable on the fixture power budget (test run: 1 year, 120 s step, about 6 s)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        mo = Path(cls.tmp) / "modules_output"
        sd = mo / "END-006" / "output_component_selector" / "spacecraft_definition.json"
        sd.parent.mkdir(parents=True)
        sd.write_text(json.dumps({"mass_kg": 9.0, "class_u": 6, "battery": {"capacity_wh": 84.0}}), encoding="utf-8")
        payload = {"run_mode": "test", "requirements": [{"id": "REQ-002", "text": "The mission lifetime shall be three years."}],
                   "upstream_products": {
                       "power_budget_summary": {"paths": [str(FIX / "power_budget_summary_small.json")]},
                       "spacecraft_definition": {"paths": [str(sd)]},
                       "thermal_summary": {"paths": [str(FIX / "thermal_summary_small.json")]}}}
        inp = Path(cls.tmp) / "STEP_008_END-008_input.json"
        inp.write_text(json.dumps(payload), encoding="utf-8")
        cls.module_root = mo / "END-008"
        cls.result = R.run_end008(str(inp), str(cls.module_root), run_id="T")
        cls.mo = mo

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_status_and_provenance(self):
        r = self.result
        self.assertEqual(r["status"], "completed_with_fallback", r["evidence"])
        self.assertEqual(r["fallback_severity"], "minor")                   # cell and pack are minor assumptions
        items = {e["item"]: e for e in r["provenance"]["entries"]}
        self.assertEqual(items["cell"]["kind"], "fallback")
        self.assertEqual(items["mission.duration_years"]["value"], 1.0)    # test run
        self.assertEqual(items["pack.temperature_C"]["kind"], "input")      # END-019 temperature
        self.assertIn("SOH at the end of the 1-year mission", r["evidence"])

    def test_guaranteed_products_and_kpis(self):
        reg = Registry.load(STAR / "Input" / "input_base_knowledge" / "registry")
        graph = WorkflowGraph(reg, ["END-008"])
        self.assertEqual(graph.missing_outputs("END-008", self.mo), [])
        doc = K.load_doc(self.module_root / "kpis.json")
        self.assertEqual(K.validate(doc), [])
        self.assertEqual(len(doc["kpis"]), 6)
        s = json.loads((self.module_root / "output_battery_health_monitoring" / "battery_health_summary.json").read_text("utf-8"))
        self.assertEqual(s["settings"]["duration_years"], 1.0)
        self.assertEqual(s["settings"]["cells_in_parallel"], 4)

    def test_temperature_fallback_is_critical(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = json.loads((Path(self.tmp) / "STEP_008_END-008_input.json").read_text("utf-8"))
            payload["upstream_products"]["thermal_summary"] = {"paths": []}
            inp = Path(tmp) / "in.json"
            inp.write_text(json.dumps(payload), encoding="utf-8")
            r = R.run_end008(str(inp), str(Path(tmp) / "modules_output" / "END-008"), run_id="T")
        self.assertEqual(r["status"], "completed_with_fallback")
        self.assertEqual(r["fallback_severity"], "critical")
        self.assertIn("pack.temperature_C", [f["item"] for f in r["fallbacks"]])


if __name__ == "__main__":
    unittest.main()

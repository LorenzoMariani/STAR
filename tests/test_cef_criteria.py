"""CEF loop criteria (phase F, 2026-10-23): every criterion of Input/input_base_knowledge/config/cef_loop.yaml on synthetic KPIs.

From the STAR folder:   python -m unittest discover -s tests -p "test_cef_criteria.py"     (run_all_tests.py: suite STAR)

Statuses pass / fail / not_applicable / not_evaluable, the edges of the rules (1 % of the mass, 1.05 x the delta-v need, 80 % of
the wheels), the threshold syntax of requirement_kpi_rules.yaml (const | kpi | kpi_limit) and a need computed on another mass.
"""
import sys
import unittest
from pathlib import Path

STAR = Path(__file__).resolve().parent.parent
BACKEND = STAR / "BackEnd"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

try:
    import yaml  # noqa: F401
    from runners import star_cef as C
except ModuleNotFoundError:          # PyYAML is optional for the other STAR suites (requirements.txt)
    C = None


def k(value, limit=None, source="requirement"):
    """A KPI entry as star_kpis writes it (only what the criteria read)."""
    a = None if limit is None else {"meets": None, "operator": "<=", "threshold": limit, "unit": "-", "threshold_source": source,
                                    "requirement_ids": [], "note": ""}
    return {"value": value, "assessment": a}


def good():
    """KPIs of an iteration where every criterion passes."""
    return {
        "END-006.mass_kg": k(9.0), "END-006.design_signature": k("abc123"),
        "END-006.dv_capacity_m_s": k(27.6), "END-006.dv_need_m_s": k(24.0), "END-016.mass_used_kg": k(9.0),
        "END-003.peak_wheel_momentum_pct": k(0.15), "END-003.peak_control_torque_pct": k(0.01),
        "END-004.worst_dod_pct": k(1.2, limit=30.0),
        "END-019.battery_min_C": k(5.0), "END-019.battery_max_C": k(30.0),
        "END-019.battery_limit_min_C": k(0.0), "END-019.battery_limit_max_C": k(45.0),
    }


def used_of(mass=9.0, signature="abc123"):
    return {"END-006.mass_kg": k(mass), "END-006.design_signature": k(signature)}


def by_id(criteria):
    return {c["id"]: c for c in criteria}


@unittest.skipIf(C is None, "PyYAML not installed")
class TestCriteria(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = C.load_config()

    def evaluate(self, kpis=None, used=None, failed=None, inactive=None):
        return by_id(C.evaluate_criteria(self.config, kpis if kpis is not None else good(),
                                                       used if used is not None else used_of(), failed, inactive))

    def test_config_has_the_five_criteria_on_global_kpi_ids(self):
        ids = [c["id"] for c in self.config["criteria"]]
        self.assertEqual(ids, ["CEF-MASS", "CEF-COMPONENTS", "CEF-DV", "CEF-WHEELS", "CEF-BATTERY"])
        self.assertEqual(self.config["max_iterations"], 3)
        try:
            from runners import star_kpis
        except ImportError:
            self.skipTest("star_kpis not importable")
        for c in self.config["criteria"]:
            for chk in c["checks"]:
                for kid in C._check_kpis(chk):
                    self.assertIsNotNone(star_kpis.catalogue_entry(kid), f"{c['id']}: {kid} is not in the KPI catalogue")

    def test_everything_passes(self):
        res = self.evaluate()
        self.assertTrue(all(c["status"] == C.PASS for c in res.values()), {i: c["status"] for i, c in res.items()})
        self.assertTrue(C.criteria_ok(list(res.values())))

    def test_criteria_nodes_map_kpis_to_graph_nodes(self):
        self.assertEqual(sorted(C.criteria_nodes(self.config)), ["END-003", "END-004", "END-006/final", "END-016", "END-019"])

    # ---------------------------------------------------------------- CEF-MASS: 1 % against the design used
    def test_mass_edges(self):
        kp = good()
        kp["END-006.mass_kg"] = k(9.09)                               # +1.0 % of 9.0 kg: still pass
        self.assertEqual(self.evaluate(kp)["CEF-MASS"]["status"], C.PASS)
        kp["END-006.mass_kg"] = k(9.1)                                # +1.11 %
        res = self.evaluate(kp)["CEF-MASS"]
        self.assertEqual(res["status"], C.FAIL)
        self.assertIn("differs from 9", res["reason"])
        kp["END-006.mass_kg"] = k(8.91)                               # -1.0 %
        self.assertEqual(self.evaluate(kp)["CEF-MASS"]["status"], C.PASS)
        kp["END-006.mass_kg"] = k(8.9)
        self.assertEqual(self.evaluate(kp)["CEF-MASS"]["status"], C.FAIL)

    def test_mass_margin_and_values(self):
        res = self.evaluate()["CEF-MASS"]
        self.assertAlmostEqual(res["margin"]["END-006.mass_kg"], 0.09)
        self.assertEqual(res["values"]["END-006.mass_kg"], 9.0)

    def test_mass_without_the_design_used_is_not_evaluable(self):
        res = self.evaluate(used={})["CEF-MASS"]
        self.assertEqual(res["status"], C.NOT_EVALUABLE)
        self.assertIn("design used", res["reason"])

    # ---------------------------------------------------------------- CEF-COMPONENTS
    def test_components(self):
        self.assertEqual(self.evaluate()["CEF-COMPONENTS"]["status"], C.PASS)
        res = self.evaluate(used=used_of(signature="zzz999"))["CEF-COMPONENTS"]
        self.assertEqual(res["status"], C.FAIL)
        self.assertIn("abc123", res["reason"])

    # ---------------------------------------------------------------- CEF-DV: 1.05 x need, need on the same mass
    def test_dv_edges(self):
        kp = good()
        kp["END-006.dv_need_m_s"] = k(20.0)
        kp["END-006.dv_capacity_m_s"] = k(21.0)                        # exactly 1.05 x
        self.assertEqual(self.evaluate(kp)["CEF-DV"]["status"], C.PASS)
        kp["END-006.dv_capacity_m_s"] = k(20.99)
        res = self.evaluate(kp)["CEF-DV"]
        self.assertEqual(res["status"], C.FAIL)
        self.assertAlmostEqual(res["threshold"]["END-006.dv_capacity_m_s"], 21.0)

    def test_dv_need_on_another_mass_fails(self):
        kp = good()
        kp["END-016.mass_used_kg"] = k(7.81)                           # END-016 computed the need on D0, END-006 is at 9.0 kg
        res = self.evaluate(kp)["CEF-DV"]
        self.assertEqual(res["status"], C.FAIL)
        self.assertIn("Mass END-016 computed the need on", res["reason"])
        kp["END-016.mass_used_kg"] = k(9.09)                           # within 1 %
        self.assertEqual(self.evaluate(kp)["CEF-DV"]["status"], C.PASS)

    def test_dv_without_a_need_is_not_applicable(self):
        kp = good()
        del kp["END-006.dv_need_m_s"]
        self.assertEqual(self.evaluate(kp)["CEF-DV"]["status"], C.N_A)
        kp["END-006.dv_need_m_s"] = k(0.0)
        self.assertEqual(self.evaluate(kp)["CEF-DV"]["status"], C.N_A)
        kp["END-006.dv_need_m_s"] = k(None)
        self.assertEqual(self.evaluate(kp)["CEF-DV"]["status"], C.N_A)

    # ---------------------------------------------------------------- CEF-WHEELS: < 80 %
    def test_wheels_edges(self):
        kp = good()
        kp["END-003.peak_wheel_momentum_pct"] = k(79.99)
        self.assertEqual(self.evaluate(kp)["CEF-WHEELS"]["status"], C.PASS)
        kp["END-003.peak_wheel_momentum_pct"] = k(80.0)                # strictly below 80
        self.assertEqual(self.evaluate(kp)["CEF-WHEELS"]["status"], C.FAIL)
        kp["END-003.peak_wheel_momentum_pct"] = k(10.0)
        kp["END-003.peak_control_torque_pct"] = k(85.0)                # torque too
        res = self.evaluate(kp)["CEF-WHEELS"]
        self.assertEqual(res["status"], C.FAIL)
        self.assertIn("Peak control torque", res["reason"])

    def test_wheels_not_produced_by_a_running_module_is_not_applicable(self):
        kp = good()
        del kp["END-003.peak_wheel_momentum_pct"], kp["END-003.peak_control_torque_pct"]      # e.g. magnetorquers only
        self.assertEqual(self.evaluate(kp)["CEF-WHEELS"]["status"], C.N_A)

    # ---------------------------------------------------------------- CEF-BATTERY: kpi_limit and kpi thresholds
    def test_battery_edges(self):
        kp = good()
        kp["END-019.battery_min_C"] = k(0.0)                           # exactly at the lower limit
        self.assertEqual(self.evaluate(kp)["CEF-BATTERY"]["status"], C.PASS)
        kp["END-019.battery_min_C"] = k(-36.8)
        res = self.evaluate(kp)["CEF-BATTERY"]
        self.assertEqual(res["status"], C.FAIL)
        self.assertIn("Battery minimum temperature", res["reason"])
        self.assertAlmostEqual(res["margin"]["END-019.battery_min_C"], -36.8)
        kp = good()
        kp["END-019.battery_max_C"] = k(45.5)
        self.assertEqual(self.evaluate(kp)["CEF-BATTERY"]["status"], C.FAIL)

    def test_battery_dod_uses_the_limit_the_module_published(self):
        kp = good()
        kp["END-004.worst_dod_pct"] = k(30.0, limit=30.0)
        self.assertEqual(self.evaluate(kp)["CEF-BATTERY"]["status"], C.PASS)
        kp["END-004.worst_dod_pct"] = k(30.5, limit=30.0)
        res = self.evaluate(kp)["CEF-BATTERY"]
        self.assertEqual(res["status"], C.FAIL)
        self.assertIn("Worst-case depth of discharge", res["reason"])
        kp["END-004.worst_dod_pct"] = k(30.5, limit=40.0, source="component")
        self.assertEqual(self.evaluate(kp)["CEF-BATTERY"]["status"], C.PASS)

    def test_battery_dod_without_a_published_limit_is_skipped_not_failed(self):
        kp = good()
        kp["END-004.worst_dod_pct"] = k(95.0)                          # no assessment: nothing to check against
        res = self.evaluate(kp)["CEF-BATTERY"]
        self.assertEqual(res["status"], C.PASS)
        self.assertEqual([c["status"] for c in res["checks"]], [C.N_A, C.PASS, C.PASS])

    # ---------------------------------------------------------------- not_evaluable and not_applicable
    def test_missing_kpi_is_not_evaluable_with_the_reason_of_the_module(self):
        kp = {i: v for i, v in good().items() if not i.startswith("END-019")}
        res = self.evaluate(kp, failed={"END-019": "failed"})["CEF-BATTERY"]
        self.assertEqual(res["status"], C.NOT_EVALUABLE)
        self.assertIn("END-019 failed", res["reason"])
        res = self.evaluate(kp)["CEF-BATTERY"]                         # missing without a known cause
        self.assertEqual(res["status"], C.NOT_EVALUABLE)
        self.assertIn("END-019.battery_min_C missing", res["reason"])
        self.assertFalse(C.criteria_ok(C.evaluate_criteria(self.config, kp, used_of())))

    def test_a_failed_module_hides_its_kpis_even_if_they_are_in_the_file(self):
        res = self.evaluate(failed={"END-019": "failed"})["CEF-BATTERY"]       # stale kpis.json of the iteration before
        self.assertEqual(res["status"], C.NOT_EVALUABLE)

    def test_module_out_of_the_workflow_is_not_applicable(self):
        kp = {i: v for i, v in good().items() if not i.startswith("END-019")}
        res = self.evaluate(kp, inactive={"END-019": "is not in the workflow"})["CEF-BATTERY"]
        self.assertEqual([c["status"] for c in res["checks"]], [C.PASS, C.N_A, C.N_A])
        self.assertEqual(res["status"], C.PASS)
        kp = {i: v for i, v in kp.items() if not i.startswith("END-004")}
        res = self.evaluate(kp, inactive={"END-019": "is not in the workflow", "END-004": "was skipped (out of scope)"})["CEF-BATTERY"]
        self.assertEqual(res["status"], C.N_A)

    def test_fail_wins_over_not_evaluable(self):
        kp = good()
        kp["END-019.battery_min_C"] = k(-5.0)
        del kp["END-019.battery_max_C"]
        self.assertEqual(self.evaluate(kp)["CEF-BATTERY"]["status"], C.FAIL)

    def test_non_numeric_value_is_not_evaluable(self):
        kp = good()
        kp["END-019.battery_min_C"] = k("n/a")
        res = self.evaluate(kp)["CEF-BATTERY"]
        self.assertEqual(res["status"], C.NOT_EVALUABLE)

    def test_empty_criteria_never_converge(self):
        self.assertFalse(C.criteria_ok([]))


@unittest.skipIf(C is None, "PyYAML not installed")
class TestCheckSyntax(unittest.TestCase):
    """The operators and threshold forms of cef_loop.yaml, on their own."""

    def check(self, chk, kpis, used=None, **kw):
        return C.evaluate_check(chk, kpis, used or {}, **kw)

    def test_operators(self):
        kp = {"A": k(5.0)}
        for op, thr, expected in (("<=", 5, C.PASS), ("<", 5, C.FAIL), (">=", 5, C.PASS), (">", 5, C.FAIL), ("==", 5, C.PASS),
                                  ("==", 6, C.FAIL), ("<", 5.1, C.PASS)):
            self.assertEqual(self.check({"kpi": "A", "op": op, "threshold": thr}, kp)["status"], expected, f"{op} {thr}")

    def test_equality_of_text_and_booleans(self):
        self.assertEqual(self.check({"kpi": "A", "op": "==", "threshold": True}, {"A": k(True)})["status"], C.PASS)
        self.assertEqual(self.check({"kpi": "A", "op": "==", "threshold": True}, {"A": k(False)})["status"], C.FAIL)
        self.assertEqual(self.check({"kpi": "A", "op": "==", "ref": "used"}, {"A": k("x")}, {"A": k("x")})["status"], C.PASS)

    def test_kpi_threshold_with_factor(self):
        kp = {"A": k(10.5), "B": k(10.0)}
        chk = {"kpi": "A", "op": ">=", "threshold": {"kpi": "B", "factor": 1.05}}
        self.assertEqual(self.check(chk, kp)["status"], C.PASS)
        kp["A"] = k(10.4)
        self.assertEqual(self.check(chk, kp)["status"], C.FAIL)
        self.assertEqual(self.check(chk, {"A": k(1.0)})["status"], C.NOT_EVALUABLE)

    def test_kpi_limit_threshold_reads_the_assessment(self):
        chk = {"kpi": "A", "op": "<=", "threshold": {"kpi_limit": "A"}}
        self.assertEqual(self.check(chk, {"A": k(4.0, limit=5.0)})["status"], C.PASS)
        self.assertEqual(self.check(chk, {"A": k(6.0, limit=5.0)})["status"], C.FAIL)
        res = self.check(chk, {"A": k(4.0)})
        self.assertEqual(res["status"], C.NOT_EVALUABLE)
        self.assertIn("no limit published", res["reason"])

    def test_relative_band_against_a_reference_kpi(self):
        chk = {"kpi": "A", "op": "rel_le", "ref": {"kpi": "B"}, "threshold": 0.05}
        self.assertEqual(self.check(chk, {"A": k(10.5), "B": k(10.0)})["status"], C.PASS)
        self.assertEqual(self.check(chk, {"A": k(10.6), "B": k(10.0)})["status"], C.FAIL)

    def test_infinite_text_value(self):
        self.assertEqual(self.check({"kpi": "A", "op": "<=", "threshold": 5}, {"A": k("inf")})["status"], C.FAIL)

    def test_design_signature_is_a_hash_of_slot_to_component(self):
        from runners import star_kpi_adapters as A
        one = A.design_signature({"adcs": "bct-xact-100", "propulsion": "vacco-mips-1u"})
        self.assertEqual(one, A.design_signature({"propulsion": "vacco-mips-1u", "adcs": "bct-xact-100"}))
        self.assertNotEqual(one, A.design_signature({"adcs": "bct-xact-15", "propulsion": "vacco-mips-1u"}))
        self.assertNotEqual(one, A.design_signature({"adcs": "bct-xact-100"}))
        results = {"result": {"subsystems": [{"id": "adcs", "selected": {"id": "bct-xact-100"}},
                                              {"id": "propulsion", "selected": None}, {"id": "obc", "selected": {"id": "x"}}]}}
        self.assertEqual(A.design_components(results), {"adcs": "bct-xact-100", "obc": "x"})


if __name__ == "__main__":
    unittest.main()

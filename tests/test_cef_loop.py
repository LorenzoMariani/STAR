"""CEF loop controller with fake modules (phase F, 2026-10-23): BackEnd/runners/star_cef.py without the app.

From the STAR folder:   python -m unittest discover -s tests -p "test_cef_loop.py"     (run_all_tests.py: suite STAR)

A fake registry (END-006 initial/final, END-001 fixed, END-003/004/016/019 in the loop, END-010 and END-007 after it) and fake
runners: the ``run_node`` callback writes the declared products and a scripted kpis.json per iteration. Checks the node sets,
the outcomes (converged, not_converged, stalled, interrupted, stopped, not_applicable) and the artefacts (promotion, archive,
convergence.json, stale guard, END-001 warning).
"""
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

STAR = Path(__file__).resolve().parent.parent
BACKEND = STAR / "BackEnd"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

try:
    import yaml  # noqa: F401
    from runners import star_cef as C
    from runners import star_kpis as K
    from runners.star_runner_io import design_fingerprint
    from runners.star_workflow_graph import Registry, WorkflowGraph
except ModuleNotFoundError:          # PyYAML is optional for the other STAR suites (requirements.txt)
    C = None

SD = "output_component_selector/spacecraft_definition.json"
SDF = "output_component_selector/spacecraft_definition_final.json"


def _p(product, path, fmt="json", guaranteed=True, **extra):
    return {"product": product, "path": path, "format": fmt, "guaranteed": guaranteed, **extra}


def _c(product, required=True, **extra):
    return {"product": product, "required": required, **extra}


def fake_modules(with_end010=True, with_end007=True, with_end016=True, with_end019=True):
    mods = [
        {"module_id": "END-006", "module_name": "Selector", "always_in_workflow": True,
         "execution": {"runner_module": "x", "runner_function": "y"},
         "phases": {"initial": {"produces": [_p("kpis_end006_initial", "kpis_initial.json"), _p("spacecraft_definition", SD)]},
                    "final": {"consumes": [_c("spacecraft_definition", False), _c("power_summary", False), _c("safety_summary", False)],
                              "produces": [_p("kpis_end006", "kpis.json"),
                                           _p("spacecraft_definition_final", SDF, feeds_back_to="spacecraft_definition"),
                                           _p("selector_report", "report.html", "html")]}}},
        {"module_id": "END-001", "module_name": "Constellation", "always_in_workflow": True, "cef_loop": "fixed",
         "execution": {"runner_module": "x", "runner_function": "y"},
         "consumes": [_c("spacecraft_definition", False, uses=["radios"])],
         "produces": [_p("satellite_orbits", "out/satellite_*.json")]},
        {"module_id": "END-003", "module_name": "Attitude", "execution": {"runner_module": "x", "runner_function": "y"},
         "consumes": [_c("satellite_orbits"), _c("spacecraft_definition")],
         "produces": [_p("kpis_end003", "kpis.json"), _p("attitude_csv", "out/attitude.csv", "csv")]},
        {"module_id": "END-004", "module_name": "Power", "execution": {"runner_module": "x", "runner_function": "y"},
         "consumes": [_c("attitude_csv"), _c("spacecraft_definition")],
         "produces": [_p("kpis_end004", "kpis.json"), _p("power_summary", "out/power.json")]},
    ]
    if with_end016:
        mods.append({"module_id": "END-016", "module_name": "Safety", "execution": {"runner_module": "x", "runner_function": "y"},
                     "consumes": [_c("satellite_orbits"), _c("spacecraft_definition")],
                     "produces": [_p("kpis_end016", "kpis.json"), _p("safety_summary", "out/safety.json")]})
    if with_end019:
        mods.append({"module_id": "END-019", "module_name": "Thermal", "execution": {"runner_module": "x", "runner_function": "y"},
                     "consumes": [_c("satellite_orbits"), _c("spacecraft_definition"), _c("power_summary", False)],
                     "produces": [_p("kpis_end019", "kpis.json"), _p("thermal_summary", "out/thermal.json")]})
    if with_end010:
        mods.append({"module_id": "END-010", "module_name": "Reflectance", "execution": {"runner_module": "x", "runner_function": "y"},
                     "cef_loop": {"rerun_on": [{"product": "spacecraft_definition", "keys": ["class_u", "dims_m", "solar_panels.n_panels"]}]},
                     "consumes": [_c("spacecraft_definition"), _c("attitude_csv", False)],
                     "produces": [_p("kpis_end010", "kpis.json"), _p("reflectance_summary", "out/reflectance.json")]})
    if with_end007:
        mods.append({"module_id": "END-007", "module_name": "Synthetic", "execution": {"runner_module": "x", "runner_function": "y"},
                     "cef_loop": {"rerun_on": [{"product": "satellite_orbits"}]},
                     "consumes": [_c("attitude_csv")],
                     "produces": [_p("kpis_end007", "kpis.json"), _p("synthetic_images", "out/img.json")]})
    return mods


def design(mass=9.0, comps=None, dims=(0.2, 0.2, 0.3), radios="uhf", panels=4):
    comps = comps or {"adcs": "xact-100", "obc": "m3"}
    return {"mass_kg": mass, "class_u": 6, "dims_m": list(dims), "radios": {"comms": radios}, "solar_panels": {"n_panels": panels},
            "_components": comps}


def good_kpis(mass, sig, comps, battery_min=5.0, dv_mass=None, wheels=0.2):
    return {"END-006": [("END-006.mass_kg", mass), ("END-006.design_signature", sig, {"components": comps}),
                        ("END-006.dv_capacity_m_s", 27.0), ("END-006.dv_need_m_s", 24.0)],
            "END-016": [("END-016.mass_used_kg", dv_mass if dv_mass is not None else mass)],
            "END-003": [("END-003.peak_wheel_momentum_pct", wheels), ("END-003.peak_control_torque_pct", 0.1)],
            "END-004": [("END-004.worst_dod_pct", 1.0, None, 30.0)],
            "END-019": [("END-019.battery_min_C", battery_min), ("END-019.battery_max_C", 30.0),
                        ("END-019.battery_limit_min_C", 0.0), ("END-019.battery_limit_max_C", 45.0)]}


class FakeRun:
    """The run folder and the scripted runners. ``plan(iteration)`` -> {"design": dict, "battery_min": x, "fail": {module: status}}."""

    def __init__(self, tmp, plan, modules=None, d0=None):
        self.run = Path(tmp)
        self.root = self.run / "modules_output"
        self.registry = Registry.from_modules(modules or fake_modules())
        self.graph = WorkflowGraph.build(self.registry, ["END-003", "END-004", "END-016", "END-019", "END-010", "END-007"])
        self.plan, self.d0 = plan, d0 or design(7.8, {"adcs": "xact-100"})
        self.calls, self.used_log = [], {}
        self.stop = threading.Event()
        self.logs = []
        self.on_call = None

    def write(self, module, rel, content):
        path = self.root / module / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")

    def kpis(self, node_id, spec, iteration):
        node = self.graph.node(node_id)
        items = []
        for entry in spec.get(node.module_id, []):
            kid, value = entry[0], entry[1]
            ctx = entry[2] if len(entry) > 2 and isinstance(entry[2], dict) else {}
            limit = entry[3] if len(entry) > 3 else None
            a = None if limit is None else K.assessment(value <= limit, "<=", limit, "%", "requirement")
            items.append(K.kpi(kid, value, context=ctx, assessment=a))
        doc = K.document(node.module_id, items, node=node_id, phase=node.phase or "")
        K.write(self.root / node.module_id, doc, node.phase or "")

    def run_node(self, node_id, iteration):
        self.calls.append((node_id, iteration))
        if self.on_call:
            self.on_call(node_id, iteration)
        node = self.graph.node(node_id)
        plan = self.plan(iteration)
        status = plan.get("fail", {}).get(node_id) or plan.get("fail", {}).get(node.module_id, "completed")
        if status != "completed":
            return {"status": status, "evidence": f"{node_id} scripted {status}", "node": node_id, "iteration": iteration}
        if node_id == "END-006/initial":
            self.write("END-006", SD, self.d0)
            self.kpis(node_id, {"END-006": [("END-006.mass_kg", self.d0["mass_kg"]),
                                            ("END-006.design_signature", C_sig(self.d0["_components"]), {"components": self.d0["_components"]})]}, 1)
        elif node_id == "END-006/final":
            used = json.loads((self.root / "END-006" / SD).read_text(encoding="utf-8"))
            self.used_log[iteration] = used.get("design_iteration", 0)
            d = plan["design"]
            self.write("END-006", SDF, d)
            self.write("END-006", "report.html", "<html>big report</html>")
            self.kpis(node_id, good_kpis(d["mass_kg"], C_sig(d["_components"]), d["_components"], plan.get("battery_min", 5.0),
                                         plan.get("dv_mass"), plan.get("wheels", 0.2)), iteration)
        else:
            for item in node.produces:
                rel = item["path"].replace("*", "01")
                if item["product"].startswith("kpis_"):
                    continue
                self.write(node.module_id, rel, {"iteration": iteration, "node": node_id} if rel.endswith(".json") else f"data,{iteration}\n")
            if node.module_id != "END-001":
                # END-016 computes its need on the mass of the design it USED (the spacecraft_definition of the moment)
                used_mass = json.loads((self.root / "END-006" / SD).read_text(encoding="utf-8"))["mass_kg"]
                self.kpis(node_id, good_kpis(0, "", {}, plan.get("battery_min", 5.0), plan.get("dv_mass", used_mass), plan.get("wheels", 0.2)), iteration)
        out = {"status": "completed", "node": node_id, "iteration": iteration, "duration_seconds": 0.01}
        if node.module_id in ("END-003", "END-004", "END-016", "END-019"):
            # what load_spacecraft_definition would log: the stamp and signature of the file as it is now (or a scripted stale one)
            sd = json.loads((self.root / "END-006" / SD).read_text(encoding="utf-8"))
            stale = plan.get("stale", {}).get(node.module_id)
            out["design_used"] = [{"design_iteration": stale if stale is not None else int(sd.get("design_iteration") or 0),
                                   "signature": design_fingerprint(sd)}]
        return out

    def first_pass(self):
        results = {}
        for node_id in self.graph.order():
            results[node_id] = self.run_node(node_id, 1)
            if results[node_id]["status"] == "stopped":
                break
        return results

    def loop(self, config_over=None):
        config = C.load_config()
        config.update(config_over or {})
        return C.CefLoop(self.graph, config, self.root, self.run, self.run_node, log=lambda l, m: self.logs.append((l, m)),
                         stop_event=self.stop, run_id="RUN_FAKE")

    def execute(self, config_over=None):
        first = self.first_pass()
        self.state = self.loop(config_over).run(first)
        self.conv = json.loads((self.run / "convergence.json").read_text(encoding="utf-8"))
        return self.state


def C_sig(comps):
    from runners import star_kpi_adapters as A
    return A.design_signature(comps)


D1 = design(9.0, {"adcs": "xact-100", "propulsion": "mips"}, radios="uhf+s")


@unittest.skipIf(C is None, "PyYAML not installed")
class TestNodeSets(unittest.TestCase):
    def test_sets_of_the_fake_workflow(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = FakeRun(tmp, lambda k: {"design": D1})
            loop = r.loop()
            self.assertEqual(loop.loop_nodes, ["END-003", "END-004", "END-016", "END-019", "END-006/final"])
            self.assertEqual(loop.post_nodes, ["END-007", "END-010"])
            self.assertEqual(loop.fixed_nodes, ["END-001"])
            self.assertEqual(loop.edge, ("END-006/final", "spacecraft_definition_final", "spacecraft_definition"))

    def test_without_the_modules_of_the_criteria_the_sets_shrink(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = FakeRun(tmp, lambda k: {"design": D1}, modules=fake_modules(with_end016=False, with_end019=False))
            r.graph = WorkflowGraph.build(r.registry, ["END-003", "END-004", "END-010"])
            self.assertEqual(r.loop().loop_nodes, ["END-003", "END-004", "END-006/final"])


@unittest.skipIf(C is None, "PyYAML not installed")
class TestOutcomes(unittest.TestCase):
    def test_converges_at_iteration_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            # D0 -> D1 (heater-like change fixes the cold battery in iteration 2); D2 == D1
            r = FakeRun(tmp, lambda k: {"design": D1, "battery_min": -36.8 if k == 1 else 5.0})
            state = r.execute()
            self.assertEqual(state["status"], "converged")
            self.assertEqual(r.conv["converged_at"], 2)
            self.assertEqual(r.conv["iterations_run"], 2)
            self.assertEqual(r.conv["failing_criteria"], [])
            it1, it2 = r.conv["iterations"]
            self.assertEqual([c["id"] for c in it1["criteria"] if c["status"] == "fail"],
                             ["CEF-MASS", "CEF-COMPONENTS", "CEF-DV", "CEF-BATTERY"])      # DV: END-016 used D0, END-006 is at D1
            self.assertTrue(all(c["status"] in ("pass", "not_applicable") for c in it2["criteria"]))
            self.assertEqual(it1["design_used"]["source"], "initial design")
            self.assertEqual(it2["design_used"]["signature"], it1["design_produced"]["signature"])
            self.assertEqual(it1["design_produced"]["changes"], ["propulsion: none -> mips", "mass 7.8 -> 9 kg"])
            self.assertEqual(it2["design_produced"]["changes"], [])

    def test_node_sets_run_each_iteration(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = FakeRun(tmp, lambda k: {"design": D1, "battery_min": -36.8 if k == 1 else 5.0})
            r.execute()
            rerun = [c for c in r.calls if c[1] > 1]
            self.assertEqual(rerun, [(n, 2) for n in ("END-003", "END-004", "END-016", "END-019", "END-006/final")])
            self.assertEqual([c for c in r.calls if c[0] == "END-001"], [("END-001", 1)])           # never re-run
            self.assertEqual([c for c in r.calls if c[0] == "END-007"], [("END-007", 1)])           # orbit fixed: never re-run
            self.assertEqual([c for c in r.calls if c[0] == "END-010"], [("END-010", 1)])           # class and dims unchanged

    def test_modules_of_iteration_2_use_the_promoted_design(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = FakeRun(tmp, lambda k: {"design": D1, "battery_min": -36.8 if k == 1 else 5.0})
            r.execute()
            self.assertEqual(r.used_log, {1: 0, 2: 1})            # D0 has no stamp; iteration 2 used D1 promoted from iteration 1
            sd = json.loads((r.root / "END-006" / SD).read_text(encoding="utf-8"))
            self.assertEqual(sd["design_iteration"], 1)
            self.assertEqual(sd["promoted_from"], "END-006/final")
            self.assertEqual(sd["mass_kg"], 9.0)

    def test_every_loop_node_used_the_previous_design(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = FakeRun(tmp, lambda k: {"design": D1, "battery_min": -36.8 if k == 1 else 5.0})
            r.execute()
            for it in r.conv["iterations"]:
                checks = {n["node"]: n["design_check"] for n in it["nodes"]}
                self.assertEqual(checks["END-003"], "ok")
                self.assertEqual(checks["END-006/final"], "not_recorded")
                used = next(n for n in it["nodes"] if n["node"] == "END-019")["design_used"]
                self.assertEqual(used[0]["design_iteration"], it["k"] - 1)
            self.assertFalse([w for w in r.conv["warnings"] if " instead of " in w])      # no stale-read warning

    def test_a_stale_read_interrupts_the_loop(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = FakeRun(tmp, lambda k: {"design": D1, "battery_min": -36.8 if k == 1 else 5.0, "stale": {"END-004": 0} if k == 2 else {}})
            state = r.execute()
            self.assertEqual(state["status"], "interrupted")
            self.assertIn("END-004 used design 0 instead of D1", r.conv["reason"])
            self.assertEqual(next(n for n in r.conv["iterations"][1]["nodes"] if n["node"] == "END-004")["design_check"], "mismatch")
            self.assertTrue(any("END-004" in w for w in r.conv["warnings"]))

    def test_archive_holds_the_declared_products_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = FakeRun(tmp, lambda k: {"design": D1, "battery_min": -36.8 if k == 1 else 5.0})
            r.execute()
            cef = r.run / "cef"
            it1, it2 = cef / "iteration_01", cef / "iteration_02"
            self.assertTrue(it1.is_dir() and it2.is_dir())
            # iteration 1: D0 as used, the design produced, the initial node and the loop nodes
            used1 = json.loads((it1 / "spacecraft_definition_used.json").read_text(encoding="utf-8"))
            self.assertEqual(used1["mass_kg"], 7.8)
            self.assertNotIn("design_iteration", used1)
            self.assertEqual(json.loads((it1 / "spacecraft_definition_produced.json").read_text(encoding="utf-8"))["mass_kg"], 9.0)
            self.assertTrue((it1 / "modules_output" / "END-006" / SD).is_file())                      # D0 stays in iteration 1
            self.assertTrue((it1 / "modules_output" / "END-004" / "kpis.json").is_file())
            self.assertTrue((it1 / "process_results.json").is_file())
            used2 = json.loads((it2 / "spacecraft_definition_used.json").read_text(encoding="utf-8"))
            self.assertEqual(used2["design_iteration"], 1)
            # not copied: fixed / post-loop modules (they did not re-run), html reports
            for d in (it1, it2):
                self.assertFalse((d / "modules_output" / "END-001").exists())
                self.assertFalse((d / "modules_output" / "END-010").exists())
                self.assertFalse(list(d.rglob("*.html")))
            self.assertTrue((it2 / "modules_output" / "END-019" / "kpis.json").is_file())
            self.assertEqual({p.name for p in (it2 / "modules_output").iterdir()}, {"END-003", "END-004", "END-016", "END-019", "END-006"})

    def test_convergence_json_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = FakeRun(tmp, lambda k: {"design": D1, "battery_min": -36.8 if k == 1 else 5.0})
            r.execute()
            c = r.conv
            for key in ("status", "max_iterations", "iterations_run", "converged_at", "loop_nodes", "post_loop_nodes", "fixed_modules",
                        "criteria_def", "iterations", "failing_criteria", "reason", "warnings", "feedback"):
                self.assertIn(key, c)
            self.assertEqual(c["fixed_modules"], ["END-001"])
            self.assertEqual([x["id"] for x in c["criteria_def"]], ["CEF-MASS", "CEF-COMPONENTS", "CEF-DV", "CEF-WHEELS", "CEF-BATTERY"])
            self.assertEqual([p["node"] for p in c["post_loop_nodes"]], ["END-007", "END-010"])
            self.assertTrue(all(p["fired"] is False for p in c["post_loop_nodes"]))
            it = c["iterations"][0]
            for key in ("k", "design_used", "design_produced", "nodes", "criteria"):
                self.assertIn(key, it)
            self.assertEqual(set(it["design_used"]), {"source", "signature", "mass_kg"})
            self.assertEqual(set(it["design_produced"]), {"signature", "mass_kg", "changes"})
            self.assertEqual([n["node"] for n in it["nodes"]], ["END-003", "END-004", "END-016", "END-019", "END-006/final"])
            crit = it["criteria"][0]
            for key in ("id", "status", "values", "threshold", "margin", "reason"):
                self.assertIn(key, crit)
            self.assertEqual(c["status"], "converged")
            self.assertEqual(c["max_iterations"], 3)

    def test_not_converged_after_three_with_the_failing_criteria(self):
        with tempfile.TemporaryDirectory() as tmp:
            def plan(k):                                                # the mass keeps moving by more than 1 % and the battery stays cold
                return {"design": design(9.0 + 0.5 * k, {"adcs": "xact-100", "propulsion": "mips", "extra": f"v{k}"}), "battery_min": -36.8}
            r = FakeRun(tmp, plan)
            state = r.execute()
            self.assertEqual(state["status"], "not_converged")
            self.assertEqual(r.conv["iterations_run"], 3)
            self.assertIsNone(r.conv["converged_at"])
            self.assertEqual(r.conv["failing_criteria"], ["CEF-MASS", "CEF-COMPONENTS", "CEF-DV", "CEF-BATTERY"])
            self.assertIn("CEF-BATTERY", r.conv["reason"])
            self.assertEqual(len([c for c in r.calls if c[0] == "END-006/final"]), 3)
            self.assertTrue((r.run / "cef" / "iteration_03").is_dir())
            self.assertFalse((r.run / "cef" / "iteration_04").exists())
            self.assertTrue(any(level == "WARNING" and "not_converged" in m for level, m in r.logs))   # an outcome, logged as a warning

    def test_stalled_when_the_design_stops_changing_but_a_criterion_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = FakeRun(tmp, lambda k: {"design": D1, "battery_min": -36.8})
            state = r.execute()
            self.assertEqual(state["status"], "stalled")
            self.assertEqual(r.conv["iterations_run"], 2)               # D1 produced in 1, D1 again in 2: nothing more to gain
            self.assertEqual(r.conv["failing_criteria"], ["CEF-BATTERY"])
            self.assertIn("deterministic", r.conv["reason"])
            self.assertEqual(len([c for c in r.calls if c[0] == "END-019"]), 2)

    def test_stalled_at_iteration_1_when_d0_is_already_the_final_design(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = FakeRun(tmp, lambda k: {"design": design(7.8, {"adcs": "xact-100"}), "battery_min": -36.8})
            state = r.execute()
            self.assertEqual(state["status"], "stalled")
            self.assertEqual(r.conv["iterations_run"], 1)
            self.assertEqual([c for c in r.calls if c[1] > 1], [])

    def test_converged_at_iteration_1_when_nothing_has_to_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = FakeRun(tmp, lambda k: {"design": design(7.8, {"adcs": "xact-100"})})
            state = r.execute()
            self.assertEqual(state["status"], "converged")
            self.assertEqual(r.conv["converged_at"], 1)
            self.assertEqual([c for c in r.calls if c[1] > 1], [])

    def test_dv_need_computed_on_another_mass_keeps_the_loop_going(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = FakeRun(tmp, lambda k: {"design": D1})          # END-016 used D0 (7.8 kg) in iteration 1, D1 (9 kg) in 2
            state = r.execute()
            self.assertEqual(state["status"], "converged")
            self.assertEqual(r.conv["converged_at"], 2)
            dv1 = next(c for c in r.conv["iterations"][0]["criteria"] if c["id"] == "CEF-DV")
            self.assertEqual(dv1["status"], "fail")

    def test_interrupted_when_a_loop_node_fails_in_iteration_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = FakeRun(tmp, lambda k: {"design": D1, "battery_min": -36.8, "fail": {"END-019": "failed"} if k == 2 else {}})
            state = r.execute()
            self.assertEqual(state["status"], "interrupted")
            self.assertEqual(r.conv["iterations_run"], 2)
            self.assertIn("END-019", r.conv["reason"])
            self.assertIn("iteration 2", r.conv["reason"])
            battery = next(c for c in r.conv["iterations"][1]["criteria"] if c["id"] == "CEF-BATTERY")
            self.assertEqual(battery["status"], "not_evaluable")
            self.assertIn("END-019 failed", battery["reason"])
            self.assertEqual([c[0] for c in r.calls if c[1] == 2], ["END-003", "END-004", "END-016", "END-019"])   # the loop ended with it

    def test_interrupted_when_a_loop_node_failed_in_the_first_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = FakeRun(tmp, lambda k: {"design": D1, "fail": {"END-004": "failed"}})
            state = r.execute()
            self.assertEqual(state["status"], "interrupted")
            self.assertEqual(r.conv["iterations_run"], 1)

    def test_stopped_by_the_user(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = FakeRun(tmp, lambda k: {"design": D1, "battery_min": -36.8})

            def on_call(node_id, iteration):
                if (node_id, iteration) == ("END-004", 2):
                    r.stop.set()
            r.on_call = on_call
            first = r.first_pass()

            def run_node(node_id, iteration):
                res = r.run_node(node_id, iteration)
                if r.stop.is_set():
                    res = {**res, "status": "stopped"}
                return res
            loop = C.CefLoop(r.graph, C.load_config(), r.root, r.run, run_node, stop_event=r.stop)
            state = loop.run(first)
            self.assertEqual(state["status"], "stopped")
            self.assertEqual(json.loads((r.run / "convergence.json").read_text(encoding="utf-8"))["status"], "stopped")
            self.assertEqual([c for c in r.calls if c[1] == 2], [("END-003", 2), ("END-004", 2)])

    def test_not_applicable_without_a_final_design(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = FakeRun(tmp, lambda k: {"design": D1, "fail": {"END-006/final": "failed"}})
            r.graph = WorkflowGraph.build(r.registry, ["END-003", "END-004"])
            state = r.execute()
            self.assertEqual(state["status"], "not_applicable")
            self.assertIn("END-006/final", r.conv["reason"])
            self.assertEqual(r.conv["iterations"], [])
            self.assertFalse((r.run / "cef").exists())

    def test_not_applicable_when_no_module_uses_the_design(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = FakeRun(tmp, lambda k: {"design": D1})
            r.graph = WorkflowGraph.build(r.registry, [])              # only END-006 and END-001
            state = r.execute()
            self.assertEqual(state["status"], "not_applicable")
            self.assertIn("nothing to iterate", r.conv["reason"])

    def test_not_applicable_without_a_feedback_edge(self):
        with tempfile.TemporaryDirectory() as tmp:
            mods = fake_modules()
            for m in mods:
                for ph in (m.get("phases") or {}).values():
                    for p in ph.get("produces", []):
                        p.pop("feeds_back_to", None)
            r = FakeRun(tmp, lambda k: {"design": D1}, modules=mods)
            self.assertEqual(r.execute()["status"], "not_applicable")


@unittest.skipIf(C is None, "PyYAML not installed")
class TestPostLoopAndWarnings(unittest.TestCase):
    def test_end010_reruns_once_after_the_loop_when_the_shape_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            big = design(9.0, {"adcs": "xact-100", "propulsion": "mips"}, dims=(0.2263, 0.2263, 0.366), radios="uhf+s")
            r = FakeRun(tmp, lambda k: {"design": big, "battery_min": -36.8 if k == 1 else 5.0})
            state = r.execute()
            self.assertEqual(state["status"], "converged")
            post = [c for c in r.calls if c[0] in ("END-010", "END-007")]
            self.assertEqual(post, [("END-007", 1), ("END-010", 1), ("END-010", 2)])      # END-010 once more, after the loop; END-007 never
            trig = {p["node"]: p for p in r.conv["post_loop_nodes"]}
            self.assertTrue(trig["END-010"]["fired"])
            self.assertEqual(trig["END-010"]["changed"], [{"product": "spacecraft_definition", "keys": ["dims_m"]}])
            self.assertEqual(trig["END-010"]["status"], "completed")
            self.assertFalse(trig["END-007"]["fired"])
            self.assertEqual(r.calls[-1], ("END-010", 2))
            sd = json.loads((r.root / "END-006" / SD).read_text(encoding="utf-8"))
            self.assertEqual(sd["dims_m"], [0.2263, 0.2263, 0.366])         # END-010 ran on the final satellite
            self.assertTrue((r.run / "cef" / "post_loop_before" / "modules_output" / "END-010" / "out" / "reflectance.json").is_file())

    def test_end010_does_not_rerun_for_a_change_outside_its_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = FakeRun(tmp, lambda k: {"design": D1, "battery_min": -36.8 if k == 1 else 5.0})     # radios + mass differ, shape equal
            r.execute()
            self.assertEqual([c for c in r.calls if c[0] == "END-010"], [("END-010", 1)])

    def test_warnings_end001_radios_and_end007_attitude(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = FakeRun(tmp, lambda k: {"design": D1, "battery_min": -36.8 if k == 1 else 5.0})
            r.execute()
            warnings = r.conv["warnings"]
            self.assertTrue(any("END-001" in w and "radios" in w and "cef_loop: fixed" in w for w in warnings), warnings)
            self.assertTrue(any("END-007" in w and "attitude_csv" in w and "iteration 1" in w for w in warnings), warnings)
            self.assertTrue(any(level == "WARNING" and "END-001" in m for level, m in r.logs))

    def test_no_end001_warning_when_the_radios_do_not_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            same_radios = design(9.0, {"adcs": "xact-100", "propulsion": "mips"}, radios="uhf")
            r = FakeRun(tmp, lambda k: {"design": same_radios, "battery_min": -36.8 if k == 1 else 5.0})
            r.execute()
            self.assertFalse(any("END-001" in w for w in r.conv["warnings"]))

    def test_post_loop_nodes_do_not_run_when_interrupted(self):
        with tempfile.TemporaryDirectory() as tmp:
            big = design(9.0, {"adcs": "xact-100", "propulsion": "mips"}, dims=(0.3, 0.3, 0.4))
            r = FakeRun(tmp, lambda k: {"design": big, "fail": {"END-019": "failed"} if k == 2 else {}})
            self.assertEqual(r.execute()["status"], "interrupted")
            self.assertEqual([c for c in r.calls if c[0] == "END-010"], [("END-010", 1)])

    def test_post_loop_node_without_rerun_on_reruns_when_a_consumed_product_changed(self):
        with tempfile.TemporaryDirectory() as tmp:
            mods = fake_modules()
            for m in mods:
                if m["module_id"] == "END-007":
                    m.pop("cef_loop")                                  # attitude_csv is rewritten with the iteration inside
            r = FakeRun(tmp, lambda k: {"design": D1, "battery_min": -36.8 if k == 1 else 5.0}, modules=mods)
            r.execute()
            self.assertIn(("END-007", 2), r.calls)

    def test_a_failed_post_loop_rerun_is_a_warning_not_a_change_of_outcome(self):
        with tempfile.TemporaryDirectory() as tmp:
            big = design(9.0, {"adcs": "xact-100", "propulsion": "mips"}, dims=(0.3, 0.3, 0.4))
            state = {"after": False}

            def plan(k):
                return {"design": big, "battery_min": -36.8 if k == 1 else 5.0, "fail": {"END-010": "failed"} if state["after"] else {}}
            r = FakeRun(tmp, plan)
            r.on_call = lambda n, k: state.update(after=(n == "END-006/final" and k == 2) or state["after"])
            self.assertEqual(r.execute()["status"], "converged")
            self.assertTrue(any("END-010" in w and "failed" in w for w in r.conv["warnings"]))


@unittest.skipIf(C is None, "PyYAML not installed")
class TestStaleGuard(unittest.TestCase):
    def test_missing_outputs_with_since_flags_old_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = FakeRun(tmp, lambda k: {"design": D1})
            r.first_pass()
            self.assertEqual(r.graph.missing_outputs("END-004", r.root), [])
            self.assertEqual(r.graph.missing_outputs("END-004", r.root, since=time.time() - 60), [])
            path = r.root / "END-004" / "kpis.json"
            old = time.time() - 3600
            os.utime(path, (old, old))
            self.assertEqual(r.graph.missing_outputs("END-004", r.root, since=time.time() - 60), ["kpis_end004"])
            self.assertEqual(r.graph.missing_outputs("END-004", r.root), [])           # no since: the first pass is not affected

    def test_validate_schema_checks_the_feedback_target(self):
        mods = fake_modules()
        mods[0]["phases"]["final"]["produces"][1]["feeds_back_to"] = "nothing_produces_this"
        self.assertTrue(any("feeds_back_to" in i for i in Registry.from_modules(mods).validate_schema()))

    def test_the_feedback_edge_is_not_a_dependency(self):
        r = Registry.from_modules(fake_modules())
        g = WorkflowGraph(r, list(r.nodes))
        self.assertEqual(g.order()[0], "END-006/initial")
        self.assertEqual(g.order()[-1], "END-006/final")
        self.assertEqual(g.feedback_edges(), [("END-006/final", "spacecraft_definition_final", "spacecraft_definition")])


if __name__ == "__main__":
    unittest.main()

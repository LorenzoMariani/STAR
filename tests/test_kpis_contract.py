"""Phase E: kpis.json contract (BackEnd/runners/star_kpis.py, star_kpi_adapters.py).

- schema: validate() accepts a well-formed document and rejects duplicate ids, unknown units and categories;
- registry: every module that runs publishes a guaranteed `kpis` product;
- adapters: on the products of a real run (the newest RUN_* under Output/ with modules_output; skipped when there is none)
  every adapter gives a valid document;
- no module reads another module's KPI by its native number (KPI-nn): global ids only.
"""
import json
import re
import sys
import unittest
from pathlib import Path

STAR = Path(__file__).resolve().parent.parent
BACKEND = STAR / "BackEnd"
REGISTRY = STAR / "Input" / "input_base_knowledge" / "registry"
RUNNERS = BACKEND / "runners"
MANIFEST = Path(__file__).resolve().parent / "fixtures" / "smoke_products_manifest.json"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

try:
    import yaml  # noqa: F401
    from runners import star_kpis as K
    from runners import star_kpi_adapters as A
    from runners.star_workflow_graph import Registry
except ModuleNotFoundError:          # PyYAML is optional for the other STAR suites (requirements.txt)
    K = None


def latest_run():
    runs = [p for p in (STAR / "Output").glob("RUN_*") if (p / "modules_output").is_dir() and any((p / "modules_output").glob("END-*/kpis*.json"))]
    return max(runs, key=lambda p: p.stat().st_mtime) if runs else None


@unittest.skipIf(K is None, "PyYAML not installed")
class TestSchema(unittest.TestCase):
    def doc(self, *kpis):
        return K.document("END-004", list(kpis), run_id="RUN_X")

    def test_valid_document(self):
        doc = self.doc(K.kpi("END-004.worst_dod_pct", 1.2, unit="%"), K.kpi("END-004.peak_power_W", 12.0, unit="W"))
        self.assertEqual(K.validate(doc), [])

    def test_duplicate_ids_are_rejected(self):
        doc = self.doc(K.kpi("END-004.worst_dod_pct", 1.2, unit="%"), K.kpi("END-004.worst_dod_pct", 2.0, unit="%"))
        self.assertTrue(K.validate(doc))

    def test_unknown_unit_and_category_are_rejected(self):
        bad_unit = self.doc({**K.kpi("END-004.worst_dod_pct", 1.2, unit="%"), "unit": "furlongs"})
        bad_cat = self.doc({**K.kpi("END-004.worst_dod_pct", 1.2, unit="%"), "category": "vibes"})
        self.assertTrue(K.validate(bad_unit))
        self.assertTrue(K.validate(bad_cat))

    def test_other_module_prefix_is_rejected(self):
        self.assertTrue(K.validate(self.doc(K.kpi("END-003.eclipse_fraction_pct", 35.0, unit="%"))))

    def test_units_are_normalised(self):
        self.assertEqual(K.norm_unit("hours"), "h")
        self.assertIn(K.norm_unit("count"), K.UNITS)

    def test_write_and_load_run(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "RUN_T" / "modules_output" / "END-004"
            root.mkdir(parents=True)
            K.write(root, self.doc(K.kpi("END-004.worst_dod_pct", 1.2, unit="%")))
            loaded = K.load_run(Path(tmp) / "RUN_T")
            self.assertEqual(loaded["END-004.worst_dod_pct"]["value"], 1.2)
            self.assertEqual(loaded["END-004.worst_dod_pct"]["module_id"], "END-004")


@unittest.skipIf(K is None, "PyYAML not installed")
class TestRegistryAndSources(unittest.TestCase):
    def test_every_integrated_module_produces_kpis(self):
        registry = Registry.load(REGISTRY)
        missing = []
        for node in (n for n in registry.nodes.values() if (RUNNERS / f"{n.module_id.lower().replace('-', '')}_runner.py").is_file()):
            ok = any(str(p.get("product")).startswith("kpis_") and str(p.get("path", "")).startswith("kpis") and p.get("guaranteed")
                     and "kpis" in (p.get("required_keys") or []) for p in node.produces)
            if not ok:
                missing.append(node.id)
        self.assertEqual(missing, [], "nodes without a guaranteed kpis product")

    def test_smoke_manifest_lists_kpis_files(self):
        files = json.loads(MANIFEST.read_text(encoding="utf-8"))["files"]
        for module, names in files.items():
            if module == "END-007":
                continue
            self.assertTrue(any(n.split("/")[-1].startswith("kpis") for n in names), f"{module}: kpis.json is not in the smoke manifest")

    def test_no_cross_module_reference_by_native_number(self):
        # a runner may name its own KPI numbers (a module's catalogue); reading another module's KPI-nn is the old fragile link
        pat = re.compile(r"END-0\d\d[^\n]{0,60}KPI-\d\d|KPI-\d\d[^\n]{0,60}END-0\d\d")
        hits = []
        for py in RUNNERS.glob("*.py"):
            if py.name in ("star_kpis.py", "star_kpi_adapters.py"):
                continue                                  # the catalogue and the adapters are where native ids are mapped
            for n, line in enumerate(py.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if pat.search(line) and not line.lstrip().startswith("#"):
                    hits.append(f"{py.name}:{n}: {line.strip()[:100]}")
        self.assertEqual(hits, [])


@unittest.skipIf(K is None, "PyYAML not installed")
class TestAdaptersOnARun(unittest.TestCase):
    def test_adapters_give_valid_documents(self):
        run = latest_run()
        if run is None:
            self.skipTest("no run with modules_output under Output/")
        checked = 0
        for mdir in sorted((run / "modules_output").glob("END-*")):
            if mdir.name == "END-007":
                continue
            phases = ("initial", "final") if mdir.name == "END-006" else ("",)
            for phase in phases:
                doc = A.build_document(mdir.name, mdir, phase, run.name)
                if not doc["kpis"]:
                    continue
                errs = K.validate(doc)
                self.assertEqual(errs, [], f"{mdir.name} {phase}: {errs}")
                checked += 1
        self.assertGreater(checked, 0)

    def test_written_files_are_valid(self):
        run = latest_run()
        if run is None:
            self.skipTest("no run with modules_output under Output/")
        for f in sorted((run / "modules_output").glob("END-*/kpis*.json")):
            doc = json.loads(f.read_text(encoding="utf-8"))
            self.assertEqual(K.validate(doc), [], f.name)


@unittest.skipIf(K is None, "PyYAML not installed")
class TestWheelSizingInterface(unittest.TestCase):
    """IF-003-006 (phase F3): absolute END-003 peaks, END-006 ratio KPIs, END-006/final reading kpis_end003."""
    SUMMARY = {"kpis": [{"id": "KPI-15", "name": "Peak Angular Momentum Magnitude", "value": 1.3e-4, "unit": "Nms"},
                        {"id": "KPI-26", "name": "Peak Wheel Momentum", "value": 0.15, "unit": "% of capacity"},
                        {"id": "KPI-27", "name": "Peak Control Torque", "value": 0.01, "unit": "% of wheel torque"},
                        {"id": "KPI-32", "name": "Peak Magnetorquer Dipole", "value": 0.65, "unit": "% of dipole"}],
               "attitude_mode": "nadir",
               "attitude_control": {"wheel_momentum_Nms": 0.1, "wheel_torque_Nm": 0.006, "magnetorquer_dipole_Am2": 0.73,
                                    "wheels_source": "END-006 XACT-100"}}

    def end003(self, tmp, summary):
        d = Path(tmp) / "results_attitude_propagator"
        d.mkdir(parents=True)
        (d / "attitude_summary.json").write_text(json.dumps(summary), encoding="utf-8")
        return {k["id"]: k for k in A.adapt("END-003", tmp)}

    def test_absolute_peaks_derived_from_percentages(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            k = self.end003(tmp, self.SUMMARY)
        self.assertAlmostEqual(k["END-003.peak_wheel_momentum_Nms"]["value"], 1.5e-4)
        self.assertAlmostEqual(k["END-003.peak_control_torque_Nm"]["value"], 6e-7)
        self.assertAlmostEqual(k["END-003.peak_mtq_dipole_Am2"]["value"], 0.65e-2 * 0.73)
        self.assertEqual(k["END-003.peak_control_torque_Nm"]["unit"], "Nm")
        self.assertEqual(k["END-003.peak_mtq_dipole_Am2"]["unit"], "Am2")
        self.assertEqual(k["END-003.peak_control_torque_Nm"]["context"]["design_used"], "END-006 XACT-100")
        self.assertEqual(K.validate(K.document("END-003", list(k.values()))), [])

    def test_module_value_wins_and_no_capacity_gives_none(self):
        import copy
        import tempfile
        s = copy.deepcopy(self.SUMMARY)
        s["attitude_control"]["peak_control_torque_Nm"] = 2e-6
        del s["attitude_control"]["magnetorquer_dipole_Am2"]
        with tempfile.TemporaryDirectory() as tmp:
            k = self.end003(tmp, s)
        self.assertEqual(k["END-003.peak_control_torque_Nm"]["value"], 2e-6)
        self.assertEqual(k["END-003.peak_control_torque_Nm"]["context"]["derived_from"], "module value")
        self.assertNotIn("END-003.peak_mtq_dipole_Am2", k)

    def test_end006_ratio_kpis(self):
        import tempfile
        res = {"result": {"ok": True, "mission": {"wheel_sizing": {"component": "bct-xact-15", "need_momentum_nms": 1.5e-4, "need_torque_nm": 6e-7,
                                                                   "capacity_momentum_nms": 0.015, "capacity_torque_nm": 0.005,
                                                                   "momentum_ratio": 100.0, "torque_ratio": 8333.3, "design_factor": 2.0}},
                          "totals": {}, "subsystems": []}}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "output_component_selector"
            out.mkdir()
            (out / "component_selector_results.json").write_text(json.dumps(res), encoding="utf-8")
            k = {e["id"]: e for e in A.adapt("END-006", tmp, "final")}
        self.assertEqual(k["END-006.wheel_momentum_ratio"]["value"], 100.0)
        self.assertEqual(k["END-006.wheel_torque_ratio"]["context"]["component"], "bct-xact-15")

    def test_end006_final_reads_kpis_end003(self):
        import tempfile
        from runners.end006_runner import end003_peaks
        with tempfile.TemporaryDirectory() as tmp:
            kp, sd = Path(tmp) / "kpis.json", Path(tmp) / "spacecraft_definition.json"
            self.assertIsNone(end003_peaks(kp, None))          # no END-003: today's rule
            kp.write_text(json.dumps(K.document("END-003", [K.kpi("END-003.peak_momentum_Nms", 1.3e-4),
                                                            K.kpi("END-003.peak_wheel_momentum_Nms", 1.5e-4),
                                                            K.kpi("END-003.peak_control_torque_Nm", 6e-7)])), encoding="utf-8")
            sd.write_text(json.dumps({"inertia_kg_m2": [0.12, 0.12, 0.07]}), encoding="utf-8")
            e3 = end003_peaks(kp, sd)
        self.assertEqual(e3["peak_momentum_nms"], 1.5e-4)
        self.assertEqual(e3["peak_torque_nm"], 6e-7)
        self.assertEqual(e3["inertia_max_kgm2"], 0.12)

    def test_registry_end006_final_consumes_kpis_end003(self):
        nodes = {n.phase: n for n in Registry.load(REGISTRY).nodes_for("END-006")}
        final = {str(c.get("product")): c for c in nodes["final"].consumes}
        self.assertIn("kpis_end003", final)
        self.assertFalse(final["kpis_end003"].get("required"))
        self.assertNotIn("kpis_end003", {str(c.get("product")) for c in nodes["initial"].consumes})


@unittest.skipIf(K is None, "PyYAML not installed")
class TestBatteryHeaterInterface(unittest.TestCase):
    """IF-019-006 (phase F4): END-019 heater KPIs from heater_cases.json, END-006 heater KPIs, END-006/final reading kpis_end019."""
    SUMMARY = {"satellite_label": "SAT-01", "nodes": {"BAT": {"min_C": 2.0, "max_C": 8.0}, "CTR": {"min_C": 1.0, "max_C": 9.0}},
               "limits": {"BAT": 45, "BAT_min": 0, "CTR": 60},
               "design_cases": {"hot": {"beta_deg": 66, "nodes": {"BAT": {"max_C": 8.6}}},
                                "cold": {"eclipse_min": 35.4, "nodes": {"BAT": {"min_C": -36.8}}}}}
    INFO = {"config": {"bat_min_C": 0.0, "bat_max_C": 45.0}, "provenance": {"bat_min_C": "default 0..45 degC", "bat_max_C": "default 0..45 degC"}}

    def end019(self, tmp, heater_cases):
        out, res = Path(tmp) / "output_components_thermal_analysis", Path(tmp) / "results_components_thermal_analysis"
        out.mkdir()
        res.mkdir()
        (out / "thermal_summary_SAT-01.json").write_text(json.dumps(self.SUMMARY), encoding="utf-8")
        (res / "thermal_run_info.json").write_text(json.dumps(self.INFO), encoding="utf-8")
        if heater_cases:
            (out / "heater_cases.json").write_text(json.dumps(heater_cases), encoding="utf-8")
        return {k["id"]: k for k in A.adapt("END-019", tmp)}

    def heater_cases(self, power_w=0.0, with_heater=None):
        w = {"needed_peak_W": 21.3, "needed_mean_W_cold": 12.3, "duty_cold_pct": 100, "satellite_label": "SAT-01"}
        if with_heater is not None:
            w.update({"battery_min_with_heater_C": with_heater, "duty_cold_pct": 46.5})
        return {"status": "completed", "setpoint_C": 5, "heater_in_design": {"power_W": power_w}, "worst": w}

    def test_without_heater_cases_unchanged(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            k = self.end019(tmp, None)
        self.assertEqual(k["END-019.battery_min_C"]["value"], -36.8)
        self.assertFalse(k["END-019.battery_min_C"]["assessment"]["meets"])
        self.assertNotIn("END-019.heater_needed_peak_W", k)

    def test_sizing_without_heater_in_design(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            k = self.end019(tmp, self.heater_cases())
        self.assertEqual(k["END-019.battery_min_C"]["value"], -36.8)          # no heater in the design: unheated minimum
        self.assertEqual(k["END-019.battery_min_no_heater_C"]["value"], -36.8)
        self.assertEqual(k["END-019.heater_needed_peak_W"]["value"], 21.3)
        self.assertEqual(k["END-019.heater_needed_peak_W"]["context"]["setpoint_C"], 5)
        self.assertEqual(k["END-019.heater_needed_mean_W_cold"]["value"], 12.3)
        self.assertEqual(k["END-019.heater_in_design_W"]["value"], 0.0)
        self.assertEqual(K.validate(K.document("END-019", list(k.values()))), [])

    def test_minimum_with_the_heater_of_the_design(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            k = self.end019(tmp, self.heater_cases(26.65, 3.9))
        bmin = k["END-019.battery_min_C"]
        self.assertEqual(bmin["value"], 3.9)
        self.assertTrue(bmin["assessment"]["meets"])
        self.assertEqual(bmin["context"]["heater_W"], 26.65)
        self.assertEqual(k["END-019.battery_min_no_heater_C"]["value"], -36.8)
        self.assertEqual(k["END-019.battery_max_C"]["value"], 8.6)           # the hot side does not change
        self.assertEqual(k["END-019.heater_duty_cold_pct"]["value"], 46.5)

    def test_end006_final_reads_kpis_end019(self):
        import tempfile
        from runners.end006_runner import end019_heater
        with tempfile.TemporaryDirectory() as tmp:
            k = self.end019(tmp, self.heater_cases())
            self.assertIsNone(end019_heater(Path(tmp) / "missing.json"))
            kp = Path(tmp) / "kpis.json"
            kp.write_text(json.dumps(K.document("END-019", list(k.values()))), encoding="utf-8")
            e = end019_heater(kp)
        self.assertEqual((e["needed_peak_w"], e["needed_mean_w_cold"], e["setpoint_c"]), (21.3, 12.3, 5))
        self.assertEqual((e["battery_min_c"], e["battery_max_c"], e["limit_min_c"], e["limit_max_c"]), (-36.8, 8.6, 0.0, 45.0))

    def test_end006_heater_kpis_and_signature(self):
        import tempfile
        bh = {"component": "minco-hk6911", "source": "separate", "power_w": 6.3, "required_w": 6.25, "design_factor": 1.25, "status": "met",
              "need_peak_w": 5.0, "temperature_check": {"met": True, "what": "battery within its limits"}}
        res = {"result": {"ok": True, "mission": {"battery_heater": bh}, "totals": {},
                          "subsystems": [{"id": "eps", "selected": {"id": "spacemind-gemini-eps"}}]}}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "output_component_selector"
            out.mkdir()
            (out / "component_selector_results.json").write_text(json.dumps(res), encoding="utf-8")
            k = {e["id"]: e for e in A.adapt("END-006", tmp, "final")}
        self.assertEqual(k["END-006.battery_heater_W"]["value"], 6.3)
        self.assertTrue(k["END-006.battery_heater_W"]["assessment"]["meets"])
        self.assertTrue(k["END-006.check_battery_temperature"]["value"])
        self.assertEqual(A.design_components(res), {"eps": "spacemind-gemini-eps", "battery_heater": "minco-hk6911"})
        # an integrated heater changes the signature too (switching it on is a design change)
        res["result"]["mission"]["battery_heater"] = {**bh, "component": "spacemind-gemini-eps", "source": "integrated"}
        self.assertEqual(A.design_components(res)["battery_heater"], "spacemind-gemini-eps:integrated_heater")
        self.assertEqual(K.validate(K.document("END-006", list(k.values()), node="END-006/final", phase="final")), [])

    def test_registry_heater_products(self):
        reg = Registry.load(REGISTRY)
        final = {n.phase: n for n in reg.nodes_for("END-006")}["final"]
        c = {str(x.get("product")): x for x in final.consumes}
        self.assertIn("kpis_end019", c)
        self.assertFalse(c["kpis_end019"].get("required"))
        p = {str(x.get("product")): x for x in reg.nodes_for("END-019")[0].produces}
        self.assertIn("heater_cases", p)
        self.assertFalse(p["heater_cases"].get("guaranteed"))


if __name__ == "__main__":
    unittest.main()

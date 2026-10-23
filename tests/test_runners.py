"""Python runners of STAR without MATLAB (2026-10-20).

From the STAR folder:   python -m unittest discover -s tests -p "test_runners.py"      (run_all_tests.py: suite STAR)

What a runner decides before and after its model, with the model replaced by a stand-in engine (a small script that
writes the products the real model writes):
- END-016 (runners/end016_runner.py): spacecraft from END-001's input of the run, values from the requirements and from
  the user, provenance of each value, disposal rules, solar activity levels of the run mode, staging of the END-001
  products, the MATLAB command, the evidence line from the KPIs; the failures without END-001 products or MATLAB.
- END-019 (runners/end019_runner.py): CubeSat domain (mass above 24 kg, no CubeSat: skipped), class of the END-006 design,
  SAR payload and its power, panels, staging of the END-001 and END-003 products, the evidence line, the MATLAB Runtime hint.
- END-003 attitude control from the END-006 design (wheels, star tracker, magnetorquers), END-004 orbit period from the
  END-001 orbit, run mode and level, the END-006 spacecraft definition lookup.
"""
import json
import os
import shutil
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

STAR = Path(__file__).resolve().parent.parent
if str(STAR / "BackEnd") not in sys.path:
    sys.path.insert(0, str(STAR / "BackEnd"))

from runners import end003_runner, end004_runner, end016_runner, end019_runner, star_runner_io  # noqa: E402
from runners.star_provenance import Provenance, is_fallback_source  # noqa: E402
from runners.star_workflow_graph import Registry, WorkflowGraph  # noqa: E402

# Stand-in engine: records its arguments, then writes what the model of the module writes (or fails on request).
ENGINE = textwrap.dedent('''
    import csv, json, re, sys
    from pathlib import Path
    args = sys.argv[1:]
    Path("engine_args.json").write_text(json.dumps(args))
    behaviour = json.loads(Path(__file__).with_name("behaviour.json").read_text())
    if behaviour.get("fail"):
        print(behaviour["fail"])
        sys.exit(1)
    if behaviour["module"] == "END-016":
        cfg = json.loads(Path(re.search(r"star_collision_main\\('(.+?)'\\)", " ".join(args)).group(1)).read_text())
        out = Path(cfg["output_dir"])
        (out / "space_safety_summary.json").write_text(json.dumps({"kpis": behaviour["kpis"]}))
    else:
        cfg = json.loads(Path(args[-1]).read_text())
        out = Path(cfg["output_dir"])
        rows = behaviour["rows"]
        with (out / "thermal_constellation_output.csv").open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
''')


def make_engine(folder: Path, behaviour: dict) -> Path:
    """An executable stand-in for MATLAB / star_thermal.exe in folder (a .cmd on Windows, a shell script elsewhere)."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "engine.py").write_text(ENGINE, encoding="utf-8")
    (folder / "behaviour.json").write_text(json.dumps(behaviour), encoding="utf-8")
    if os.name == "nt":
        exe = folder / "engine.cmd"
        exe.write_text(f'@echo off\r\n"{sys.executable}" "{folder / "engine.py"}" %*\r\n', encoding="utf-8")
    else:
        exe = folder / "engine.sh"
        exe.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{folder / "engine.py"}" "$@"\n', encoding="utf-8")
        exe.chmod(0o755)
    return exe


def write_json(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def end001_products(modules_output: Path, n: int = 1, ephemeris: bool = True) -> None:
    out = modules_output / "END-001" / "output_constellation_optimizer"
    for k in range(1, n + 1):
        write_json(out / f"satellite_{k:02d}.json", {"orbit": {"alt_perigee_m": 550e3, "alt_apogee_m": 550e3}})
        if ephemeris:
            (out / f"satellite_{k:02d}_ephemeris.csv").write_text("time_utc,x_eci_km\n", encoding="utf-8")


def requirement(text: str) -> dict:
    return {"text": text}


class RunnerCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="star_runner_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.modules_output = self.tmp / "modules_output"
        env = {k: v for k, v in os.environ.items()
               if k not in ("MATLAB_EXECUTABLE", "STAR_END016_MATLAB_SOURCE", "STAR_END019_EXECUTABLE",
                            "STAR_END019_MATLAB_SOURCE", "STAR_RUN_MODE", "STAR_RUN_LEVEL")}
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    node = ""       # workflow node of the module under test: its consumed products are resolved as the orchestrator does

    def upstream_products(self) -> dict:
        registry = Registry.load(STAR / "Input" / "input_base_knowledge" / "registry")
        return WorkflowGraph(registry, list(registry.nodes)).resolve_inputs(self.node, self.modules_output) if self.node else {}

    def payload(self, name: str, **data) -> Path:
        data.setdefault("upstream_products", self.upstream_products())
        return write_json(self.tmp / f"{name}.json", data)


class TestEnd016Runner(RunnerCase):
    node = "END-016"

    def run_module(self, payload: dict, kpis: dict | None = None, fail: str | None = None) -> tuple[dict, dict, Path]:
        exe = make_engine(self.tmp / "engine", {"module": "END-016", "kpis": kpis or {}, "fail": fail})
        os.environ["MATLAB_EXECUTABLE"] = str(exe)
        module_root = self.modules_output / "END-016"
        result = end016_runner.run_end016(str(self.payload("end016_input", **payload)), str(module_root), run_id="RUN_TEST",
                                          modules_output_root=str(self.modules_output))
        info = json.loads((module_root / end016_runner.RESULTS_DIRNAME / "collision_run_info.json").read_text(encoding="utf-8"))
        return result, info, module_root

    def test_requirements_parsing(self):
        params, where = end016_runner._from_requirements([
            "The operational lifetime of the mission shall be five years.",
            "The satellite shall be de-orbited within 25 years; debris mitigation: re-entry within 10 years.",
            "Hard-body radius of 50 cm. The mass not exceeding 12 kg.",
            "Drag cross-section of 0.06 m2 with a drag coefficient of 2.3.",
        ])
        self.assertEqual(params["mission_lifetime_years"], 5.0)
        self.assertEqual(sorted(params["disposal_rules_years"]), [10.0, 25.0])
        self.assertAlmostEqual(params["hard_body_radius_m"], 0.5)
        self.assertEqual([params["mass_kg"], params["drag_area_m2"], params["cd"]], [12.0, 0.06, 2.3])
        self.assertEqual(where["mission_lifetime_years"], "requirement 1")
        self.assertEqual(where["cd"], "requirement 4")

    def test_user_values_and_first_guesses(self):
        items = [
            {"needed_by_module_id": "END-016", "parameter": "position_sigma_rtn_m", "proposed_value": "30 / 120 / 30 m",
             "source": "user", "reviewed_by_user": True},
            {"needed_by_module_id": "END-016", "parameter": "pc_threshold", "proposed_value": "1e-5", "reviewed_by_user": True},
            {"needed_by_module_id": "END-016", "parameter": "screening_km", "proposed_value": "5",
             "source": "module_registry_default"},                                              # first guess: ignored
            {"needed_by_module_id": "END-016", "parameter": "mission_lifetime_years", "proposed_value": "TBD"},
            {"needed_by_module_id": "END-019", "parameter": "hard_body_radius_m", "proposed_value": "3"},
        ]
        self.assertEqual(end016_runner._approved_inputs(items), {"position_sigma_rtn_m": [30.0, 120.0, 30.0], "pc_threshold": 1e-5})

    def test_configuration_provenance_command_and_evidence(self):
        end001_products(self.modules_output, n=2)
        write_json(self.modules_output / "END-006" / "output_component_selector" / "spacecraft_definition.json",
                   {"class_u": 6, "mass_kg": 8, "area_mean_projected_m2": 0.05, "cd": 2.1})
        kpis = {"n_pairs": 1, "min_separation_km": 12.3456, "min_separation_pair": "SAT-01 - SAT-02",
                "n_events_below_screening": 0, "passive_lifetime_years_mean_activity": 6.0,
                "complies_5y_rule_mean_activity": False, "disposal_dv_m_s_5y_rule_mean_activity": 3.21,
                "complies_10y_rule_mean_activity": True, "complies_25y_rule_mean_activity": True}
        result, info, root = self.run_module({
            "run_mode": "full",
            "requirements": [requirement("The mission lifetime shall be three years."),
                             requirement("The satellites shall be disposed of within 10 years after the mission."),
                             requirement("The mass not exceeding 20 kg.")],
            "resolved_inputs": [{"needed_by_module_id": "END-016", "parameter": "position_sigma_rtn_m",
                                 "proposed_value": "30, 120, 30", "reviewed_by_user": True}],
        }, kpis=kpis)
        self.assertEqual(result["status"], "completed", result["evidence"])
        cfg = info["config"]
        self.assertEqual(cfg["spacecraft"], {"mass_kg": 8.0, "drag_area_m2": 0.05, "cd": 2.1})       # the END-006 initial design
        self.assertEqual(info["provenance"]["spacecraft.mass_kg"], "END-006 initial design (spacecraft_definition.json)")
        self.assertEqual(cfg["hard_body_radius_m"], round(2 * (0.05 / 3.141592653589793) ** 0.5, 3))
        self.assertEqual(cfg["position_sigma_rtn_m"], [30.0, 120.0, 30.0])
        self.assertEqual(info["provenance"]["position_sigma_rtn_m"], "approved by the user")
        self.assertEqual([cfg["screening_km"], cfg["pc_threshold"]], [10.0, 1e-4])
        self.assertEqual(cfg["mission_lifetime_years"], 3.0)
        self.assertEqual(info["provenance"]["mission_lifetime_years"], "requirement 1")
        self.assertEqual(cfg["disposal_rules_years"], [5, 10, 25])
        self.assertEqual(cfg["solar_f107"], [70.0, 140.0, 220.0])                                    # full run
        model_input = json.loads((root / "input_collision_avoidance.json").read_text(encoding="utf-8"))
        self.assertEqual(Path(model_input["star_input_dir"]), root / "star_input")
        self.assertEqual({k: model_input[k] for k in cfg}, cfg)
        self.assertEqual(sorted(p.name for p in (root / "star_input").iterdir()),
                         ["satellite_01.json", "satellite_01_ephemeris.csv", "satellite_02.json", "satellite_02_ephemeris.csv"])
        args = json.loads((root / "engine_args.json").read_text(encoding="utf-8"))
        self.assertEqual(args[0], "-batch")
        self.assertIn("star_collision_main(", args[1])
        self.assertIn(str(STAR / "END016-CollisionAvoidance" / "lib"), args[1])
        self.assertEqual(result["evidence"], "2 satellite(s); minimum separation 12.346 km (SAT-01 - SAT-02); 0 close approach(es) "
                         "below 10 km; passive lifetime 6.0 y at mean solar activity; 5-year rule not met (disposal 3.2 m/s); "
                         "10-year rule met; 25-year rule met.")

    def test_test_mode_and_defaults(self):
        end001_products(self.modules_output)
        result, info, _ = self.run_module({"requirements": []}, kpis={"passive_lifetime_years_mean_activity": "Inf"})
        # no END-006 design: mass, area and Cd are defaults, a critical fallback (the orchestrator would fail it first when
        # END-006 is a required upstream of the workflow)
        self.assertEqual(result["status"], "completed_with_fallback", result["evidence"])
        self.assertEqual(result["fallback_severity"], "critical")
        self.assertEqual([f["item"] for f in result["fallbacks"]], ["spacecraft.mass_kg", "spacecraft.drag_area_m2", "spacecraft.cd"])
        cfg = info["config"]
        self.assertEqual(cfg["solar_f107"], [140.0])
        self.assertEqual(cfg["spacecraft"], {"mass_kg": 100.0, "drag_area_m2": 1.0, "cd": 2.2})
        self.assertEqual(cfg["position_sigma_rtn_m"], end016_runner.DEFAULT_SIGMA_RTN_M)
        self.assertNotIn("mission_lifetime_years", cfg)
        self.assertIn("Mission lifetime not stated: orbit maintenance is not assessed", info["notes"])
        self.assertIn("passive lifetime > 200 y", result["evidence"])

    def test_failures(self):
        result, info, _ = self.run_module({"requirements": []})
        self.assertEqual(result["status"], "failed")
        self.assertIn("END-016 needs END-001 earlier in the workflow", result["evidence"])
        end001_products(self.modules_output, ephemeris=False)
        result, _, _ = self.run_module({"requirements": []})
        self.assertIn("END-001 ephemerides missing for satellite_01.json", result["evidence"])
        end001_products(self.modules_output)
        result, _, _ = self.run_module({"requirements": []}, fail="Undefined function 'star_collision_main'")
        self.assertEqual(result["status"], "failed")
        self.assertIn("exited with code 1", result["evidence"])
        self.assertIn("Undefined function", result["evidence"])
        os.environ["MATLAB_EXECUTABLE"] = str(self.tmp / "no_matlab.exe")
        result = end016_runner.run_end016(str(self.payload("in", requirements=[])), str(self.modules_output / "END-016"),
                                          modules_output_root=str(self.modules_output))
        self.assertIn("MATLAB not found", result["evidence"])


class TestEnd019Runner(RunnerCase):
    node = "END-019"

    def setUp(self):
        super().setUp()
        self.module_root = self.modules_output / "END-019"

    def upstream(self) -> None:
        end001_products(self.modules_output, n=2)
        att = self.modules_output / "END-003" / "output_attitude_propagation"
        att.mkdir(parents=True, exist_ok=True)
        (att / "selected_pass_summary.csv").write_text("purpose,satellite_index\n", encoding="utf-8")
        (att / "output_attitude_propagation.csv").write_text("timestamp_utc,q_w\n", encoding="utf-8")
        # phase D: life envelope of END-001 and internal dissipation of END-004
        write_json(self.modules_output / "END-001" / "output_constellation_optimizer" / "eclipse_summary.json", {"life_envelope": {}, "satellites": [
            {"satellite_index": i, "life": {"beta_min_deg": -70.0, "beta_max_deg": 70.0}, "cold_case": {"beta_deg": 1.0}} for i in (1, 2)]})
        write_json(self.modules_output / "END-004" / "output_power_budget" / "power_design_cases.json",
                   {"dissipation_W": {"nominal": 3.0, "hot": 8.0, "cold": 1.5}})

    def run_module(self, payload: dict, rows: list | None = None, fail: str | None = None) -> tuple[dict, dict]:
        exe = make_engine(self.tmp / "engine", {"module": "END-019", "rows": rows or [{"satellite_label": "SAT-01"}], "fail": fail})
        os.environ["STAR_END019_EXECUTABLE"] = str(exe)
        result = end019_runner.run_end019(str(self.payload("end019_input", **payload)), str(self.module_root), run_id="RUN_TEST",
                                          modules_output_root=str(self.modules_output))
        info = json.loads((self.module_root / end019_runner.RESULTS_DIRNAME / "thermal_run_info.json").read_text(encoding="utf-8"))
        return result, info

    def test_requirements_parsing(self):
        params, evidence, out_of_scope, cubesat, sar = end019_runner._from_requirements([
            "The 6U CubeSat shall carry a SAR payload with a peak power of 120 W.",
            "Power from deployable solar panels and body-mounted solar cells.",
            "The satellite mass not exceeding 12 kg."])
        self.assertEqual(params, {"form_factor": "6U", "sar_power_W": 120.0, "panels": "both"})
        self.assertTrue(cubesat and sar)
        self.assertEqual(out_of_scope, [])
        self.assertIn("6U CubeSat", evidence["form_factor"])
        _, _, out_of_scope, _, _ = end019_runner._from_requirements(["A satellite with mass not exceeding 50 kg."])
        self.assertIn("50 kg > 24 kg", out_of_scope[0])

    def test_sar_cubesat_with_the_end006_design(self):
        self.upstream()
        write_json(self.modules_output / "END-006" / "output_component_selector" / "spacecraft_definition.json",
                   {"form_factor": "12U", "mass_kg": 9.5, "battery": {"component": "aac-optimus-30", "temp_op_c": [-10, 45]}})
        rows = [{"satellite_index": 1, "satellite_label": "SAT-01", "BAT_over_limit": "true"},
                {"satellite_index": 2, "satellite_label": "SAT-02", "BAT_over_limit": "false"}]
        result, info = self.run_module({
            "requirements": [requirement("The 6U CubeSat shall carry a SAR payload with a peak power of 120 W."),
                             requirement("Deployable solar panels shall supply the payload.")],
            "resolved_inputs": [{"needed_by_module_id": "END-019", "parameter": "sar_duty", "proposed_value": "0.1",
                                 "source": "module_registry_default"}],
        }, rows=rows)
        self.assertEqual(result["status"], "completed", result["evidence"])
        cfg, prov = info["config"], info["provenance"]
        self.assertEqual(cfg["form_factor"], "12U")                                    # the END-006 design of the run
        self.assertTrue(prov["form_factor"].startswith("END-006 initial design"))
        self.assertTrue(any("state a 6U CubeSat" in n for n in info["notes"]))
        self.assertEqual([cfg["sar_power_W"], cfg["panels"], cfg["n_internal_nodes"], cfg["sar_source"], cfg["sar_duty"]],
                         [120.0, "deployable", 3, "passes", 0.1])
        self.assertEqual(prov["sar_duty"], "first guess (registry default)")
        self.assertEqual(prov["sar_power_W"], "requirements")
        staged = self.module_root / "star_input"
        self.assertEqual(sorted(p.name for p in (staged / "output_constellation_optimizer").iterdir()),
                         ["satellite_01.json", "satellite_02.json"])
        self.assertEqual(sorted(p.name for p in (staged / "output_attitude_propagation").iterdir()),
                         ["output_attitude_propagation.csv", "selected_pass_summary.csv"])
        args = json.loads((self.module_root / "engine_args.json").read_text(encoding="utf-8"))
        self.assertEqual(Path(args[-1]), self.module_root / "input_termico.json")
        self.assertTrue(result["evidence"].startswith("2 satellite(s) analysed; BAT_over_limit on SAT-01 ("), result["evidence"])
        self.assertIn("form_factor=12U", result["evidence"])
        self.assertEqual((cfg["mass_kg"], cfg["P_internal_W"], cfg["bat_min_C"]), (9.5, 3.0, -10.0))
        hot, cold = cfg["cases"]
        self.assertEqual((hot["P_internal_W"], hot["beta_min_deg"], hot["beta_max_deg"]), (8.0, [-70.0, -70.0], [70.0, 70.0]))
        self.assertEqual((cold["P_internal_W"], cold["beta_deg"]), (1.5, [1.0, 1.0]))

    def test_mission_without_sar(self):
        self.upstream()
        result, info = self.run_module({
            "requirements": [requirement("A 3U CubeSat with an optical camera.")],
            "resolved_inputs": [{"needed_by_module_id": "END-019", "parameter": "sar_power_W", "proposed_value": "200",
                                 "source": "module_registry_default"}]})
        # no END-006 design: the battery limits are the default range, a minor fallback
        self.assertEqual((result["status"], result["fallback_severity"]), ("completed_with_fallback", "minor"), result["evidence"])
        self.assertEqual([f["item"] for f in result["fallbacks"]], ["bat_min_C"])
        self.assertEqual(info["config"]["n_internal_nodes"], 2)
        self.assertNotIn("sar_power_W", info["config"])
        self.assertIn("The third internal node of the model is a SAR payload: not modelled for this mission", info["notes"])

    def test_out_of_the_cubesat_domain(self):
        result, info = self.run_module({"requirements": [requirement("A 3U CubeSat with mass not exceeding 50 kg.")]})
        self.assertEqual(result["status"], "skipped_out_of_scope")
        self.assertEqual(info["config"], {})
        result, _ = self.run_module({"requirements": [requirement("A microsatellite for Earth observation.")]})
        self.assertEqual(result["status"], "skipped_out_of_scope")
        self.assertIn("names no CubeSat", result["evidence"])

    def test_failures(self):
        result, _ = self.run_module({"requirements": [requirement("A 3U CubeSat.")]})
        self.assertEqual(result["status"], "failed")
        self.assertIn("END-001 orbits (product satellite_orbits, satellite_XX.json) not found", result["evidence"])
        self.assertIn("selected_pass_summary.csv not found", result["evidence"])
        self.upstream()
        result, _ = self.run_module({"requirements": [requirement("A 3U CubeSat.")]},
                                    fail="Could not find version 26.1 of the MATLAB Runtime")
        self.assertEqual(result["evidence"], end019_runner.RUNTIME_HINT)


class TestRunnerHelpers(unittest.TestCase):
    def test_end003_attitude_control_from_the_end006_design(self):
        sat = {"control": {"enabled": True, "wheel_momentum_Nms": 0.01, "wheel_torque_Nm": 0.001}}
        out = end003_runner._apply_attitude_control(sat, {"attitude_control": {
            "wheels": {"momentum_nms": 0.03, "max_torque_nm": 0.002, "source": "reaction_wheel", "name": "RW-1"},
            "star_tracker": {"accuracy_cross_arcsec": 18, "accuracy_basis": "3-sigma", "component": "ST-1"},
            "magnetorquers": {"dipole_am2": 0.2, "axes": 3, "source": "magnetorquer", "name": "MTQ-1"}}})
        c = sat["control"]
        self.assertEqual([c["wheel_momentum_Nms"], c["wheel_torque_Nm"], c["magnetorquer_dipole_Am2"]], [0.03, 0.002, 0.2])
        self.assertAlmostEqual(c["attitude_knowledge_deg"], 18 / 3600 / 3)                 # 3-sigma -> 1-sigma
        self.assertEqual(out["wheels_source"], "END-006 RW-1 (reaction wheel, one per body axis)")
        self.assertEqual(out["magnetorquer_source"], "END-006 MTQ-1 (magnetorquer, dipole per body axis)")
        # an ADCS unit without star tracker, magnetorquers on two axes only: pointing accuracy, sizing rule for the dipole
        sat = {"control": {"wheel_momentum_Nms": 0.01, "wheel_torque_Nm": 0.001}}
        out = end003_runner._apply_attitude_control(sat, {"attitude_control": {
            "pointing_accuracy_deg": 0.5, "adcs_unit": "ADCS-X", "magnetorquers": {"dipole_am2": 0.1, "axes": 2}}})
        self.assertEqual(sat["control"]["attitude_knowledge_deg"], 0.5)
        self.assertNotIn("magnetorquer_dipole_Am2", sat["control"])
        self.assertIn("sizing rule", out["magnetorquer_source"])
        self.assertEqual(out["wheels_source"], "END-003 template (the END-006 design gives no wheel data)")
        sat = {"control": {"wheel_momentum_Nms": 0.01}}
        self.assertEqual(end003_runner._apply_attitude_control(sat, None)["wheels_source"], "END-003 template")
        self.assertEqual(sat["control"]["wheel_momentum_Nms"], 0.01)

    def test_end004_orbit_period_from_the_end001_orbit(self):
        with tempfile.TemporaryDirectory() as tmp:
            rt = write_json(Path(tmp) / "end003_runtime_input.json", {"orbit": {"alt_perigee_m": 540e3, "alt_apogee_m": 560e3}})
            orbit = end004_runner._orbit_from_upstream({}, None, rt)
        a = end004_runner.R_EARTH + 550e3
        period = 2 * 3.141592653589793 * (a ** 3 / end004_runner.MU_EARTH) ** 0.5 / 60
        self.assertAlmostEqual(orbit["period_min"], period, places=4)
        self.assertAlmostEqual(orbit["daily_orbits"], 1440 / period, places=3)
        self.assertIsNone(end004_runner._orbit_from_upstream({}, None, None))

    def test_end004_eclipse_and_operations_of_the_selected_satellite(self):
        # phase D: eclipse from END-001 eclipse_summary.json and operations of the satellite END-003 selected
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            sel = write_json(t / "selected_passes.json", {"imaging_pass": {"satellite_index": 2, "orbit": {"alt_perigee_m": 550e3, "alt_apogee_m": 550e3}}})
            ecl = write_json(t / "eclipse_summary.json", {"satellites": [
                {"satellite_index": 1, "window": {"eclipse_mean_min": 30.0}}, {"satellite_index": 2, "window": {"eclipse_mean_min": 33.5}}],
                "life_envelope": {"eclipse_max_min": 35.4}})
            ops = write_json(t / "operations_summary.json", {"constellation_mean": {"contact_orbits_per_day": 9.0},
                                                             "satellites": [{"satellite_index": 2, "contact_orbits_per_day": 4.0}]})
            payload = {"upstream_products": {"selected_passes": {"paths": [str(sel)]}, "eclipse_summary": {"paths": [str(ecl)]},
                                             "operations_summary": {"paths": [str(ops)]}}}
            orbit = end004_runner._orbit_from_upstream(payload, None, None)
            self.assertEqual(orbit["eclipse_min"], 33.5)
            self.assertAlmostEqual(orbit["sunlight_min"], orbit["period_min"] - 33.5, places=3)
            self.assertIn("SAT-02", orbit["source"])
            got = end004_runner._operations(payload)
            self.assertEqual(got["values"]["contact_orbits_per_day"], 4.0)
            self.assertIn("SAT-02", got["source"])
            # the selected satellite is not in the file: constellation mean, marked as a fallback
            del payload["upstream_products"]["selected_passes"]
            got = end004_runner._operations(payload)
            self.assertEqual(got["values"]["contact_orbits_per_day"], 9.0)
            self.assertTrue(is_fallback_source(got["source"]))

    def test_end004_battery_worst_case_and_dissipation(self):
        on = {"sun": 1, "eclipse": 1}
        off = {"sun": 0, "eclipse": 0}
        cfg = {"orbit": {"sunlight_min": 60.0, "eclipse_min": 35.0}, "battery": {"capacity_Wh": 20.0}, "margin_fraction": 0.1,
               "generation": {"power_generated_per_orbit_Wh": 10.0, "power_generated_per_orbit_Wh_by_mode": {"payload": 12.0}},
               "operations": {"mode_orbits_per_day": {"idle": 10, "tx_uhf": 0, "tx_sband": 4, "payload": 1}},
               "subsystems": [{"name": "OBDH", "powerW": 2.0, "duty": {m: on for m in end004_runner.MODE_KEYS}},
                              {"name": "CAMERAS", "powerW": 10.0, "duty": {**{m: off for m in end004_runner.MODE_KEYS}, "payload": {"sun": 0.5, "eclipse": 0}}},
                              {"name": "TX S BAND", "powerW": 6.0, "duty": {**{m: off for m in end004_runner.MODE_KEYS}, "tx_sband": {"sun": 0.2, "eclipse": 0.1}}}]}
        out = end004_runner.design_cases(cfg, {"mission_life_years": 1, "life_envelope": {"eclipse_max_min": 37.0, "satellite_eclipse_max": 3}}, 30.0)
        wc, nom = out["battery_worst_case"], out["nominal"]
        self.assertEqual(wc["eclipse_min"], 37.0)
        self.assertAlmostEqual(wc["sunlight_min"], 58.0)
        self.assertAlmostEqual(wc["generation_scale"], 58.0 / 60.0, places=5)
        self.assertAlmostEqual(wc["modes"]["idle"]["power_generated_per_orbit_Wh"], 10.0 * 58.0 / 60.0, places=3)
        self.assertAlmostEqual(wc["modes"]["payload"]["power_generated_per_orbit_Wh"], 12.0 * 58.0 / 60.0, places=3)
        # idle: generation 9.67 Wh > sunlit use 1.93 Wh -> DoD = eclipse use / capacity = 2 W x 37 min / 20 Wh
        self.assertAlmostEqual(wc["modes"]["idle"]["orbital_DoD"], 2.0 * 37.0 / 60.0 / 20.0, places=5)
        self.assertGreater(out["worst_dod_pct"], nom["max_dod_pct"])
        self.assertEqual(out["worst_dod_pct"], wc["max_dod_pct"])
        self.assertTrue(out["battery_within_dod_limit"])
        self.assertLess(wc["daily_balance_Wh"], nom["daily_balance_Wh"])
        d = out["dissipation_W"]
        self.assertAlmostEqual(d["cold"], 2.0)                                                      # idle: OBDH only
        self.assertAlmostEqual(d["hot"], 2.0 + 10.0 * 0.5 * 60 / 95 + 6.0 * (0.2 * 60 + 0.1 * 35) / 95, places=3)
        self.assertTrue(d["cold"] <= d["nominal"] <= d["hot"])
        # no life envelope: the eclipse of the run, recorded as not available
        out = end004_runner.design_cases(cfg, None)
        self.assertEqual(out["battery_worst_case"]["eclipse_min"], 35.0)
        self.assertTrue(is_fallback_source(out["battery_worst_case"]["eclipse_source"]))
        self.assertIsNone(out["battery_within_dod_limit"])

    def test_end004_battery_heater_in_the_worst_case_only(self):
        on = {"sun": 1, "eclipse": 1}
        cfg = {"orbit": {"sunlight_min": 60.0, "eclipse_min": 35.0}, "battery": {"capacity_Wh": 80.0}, "margin_fraction": 0.0,
               "generation": {"power_generated_per_orbit_Wh": 30.0},
               "operations": {"mode_orbits_per_day": {"idle": 15, "tx_uhf": 0, "tx_sband": 0, "payload": 0}},
               "subsystems": [{"name": "OBDH", "powerW": 2.0, "duty": {m: on for m in end004_runner.MODE_KEYS}},
                              {"name": "THERMAL", "powerW": 3.0, "duty": {m: {"sun": 0, "eclipse": 0.1} for m in end004_runner.MODE_KEYS}}]}
        env = {"mission_life_years": 1, "life_envelope": {"eclipse_max_min": 38.0, "satellite_eclipse_max": 1}}
        sat = {"thermal_control": {"battery_heater": {"component": "minco-hk6911", "power_w": 6.3, "mean_w_cold": 2.5}}}
        heater = end004_runner.battery_heater(sat)
        self.assertIsNotNone(heater)
        self.assertIsNone(end004_runner.battery_heater({"thermal_control": None}))
        base = end004_runner.design_cases(cfg, env)
        out = end004_runner.design_cases(cfg, env, None, heater)
        idle_b, idle_h = base["battery_worst_case"]["modes"]["idle"], out["battery_worst_case"]["modes"]["idle"]
        # cold-case mean x period, all in eclipse, in place of the template heaters (3 W x 10 % of the eclipse)
        self.assertAlmostEqual(idle_h["eclipse_consumption_Wh"] - idle_b["eclipse_consumption_Wh"], 2.5 * 95 / 60 - 3.0 * 0.1 * 38 / 60, places=3)
        self.assertGreater(out["worst_dod_pct"], base["worst_dod_pct"])
        bh = out["battery_heater"]
        self.assertAlmostEqual(bh["energy_per_orbit_Wh"], 2.5 * 95 / 60, places=3)
        self.assertEqual(bh["replaces"], "template heaters (THERMAL)")
        # nominal budget and dissipation unchanged; the heater listed apart (END-019 owns its heat)
        self.assertEqual(out["nominal"], base["nominal"])
        for case in ("hot", "cold", "nominal"):
            self.assertEqual(out["dissipation_W"][case], base["dissipation_W"][case])
        self.assertEqual(out["dissipation_W"]["heater_W"], 2.5)
        self.assertEqual(base["dissipation_W"]["heater_W"], 0.0)
        self.assertIsNone(base["battery_heater"])
        # the heater is not an always-on load of the budget
        self.assertIn("battery_heater", end004_runner.NO_LOAD)

    def test_end019_design_from_end006_end004_end001(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            pc = write_json(t / "power_design_cases.json", {"dissipation_W": {"nominal": 3.0, "hot": 8.0, "cold": 1.5}})
            ecl = write_json(t / "eclipse_summary.json", {"satellites": [
                {"satellite_index": 1, "life": {"beta_min_deg": -60.0, "beta_max_deg": 75.0}, "hot_case": {"beta_deg": 75.0}, "cold_case": {"beta_deg": 0.5}}]})
            sat = {"dims_m": [0.2263, 0.2263, 0.366], "mass_kg": 7.8, "solar_panels": {"body_faces": ["+X", "-X"]},
                   "battery": {"component": "aac-optimus-30", "temp_op_c": [-10, 45]}}
            payload = {"upstream_products": {"power_design_cases": {"paths": [str(pc)]}, "eclipse_summary": {"paths": [str(ecl)]}}}
            config, prov, notes = {}, {}, []
            end019_runner._apply_design(payload, sat, config, prov, {}, notes)
            self.assertEqual((config["mass_kg"], config["solar_faces"], config["panels"]), (7.8, ["+X", "-X"], "body"))
            self.assertEqual(config["P_internal_W"], 3.0)
            hot, cold = config["cases"]
            self.assertEqual((hot["P_internal_W"], hot["beta_min_deg"], hot["beta_max_deg"], cold["P_internal_W"], cold["beta_deg"]),
                             (8.0, [-60.0], [75.0], 1.5, [0.5]))
            self.assertEqual((config["bat_min_C"], config["bat_max_C"]), (-10.0, 45.0))
            self.assertFalse(any(is_fallback_source(v) for v in prov.values()))
            self.assertNotIn("battery_heater", config)
            # phase F4: the battery heater of the design goes to end019_heater_cases.m
            config, prov, notes = {}, {}, []
            sat_h = {**sat, "thermal_control": {"battery_heater": {"component": "minco-hk6911", "power_w": 6.3, "setpoint_c": -5.0}}}
            end019_runner._apply_design(payload, sat_h, config, prov, {}, notes)
            self.assertEqual(config["battery_heater"], {"power_w": 6.3, "setpoint_c": -5.0})
            self.assertIn("minco-hk6911", prov["battery_heater"])
            # no END-004, no END-001 envelope, no battery temperatures: model powers (critical), window beta, default limits
            config, prov, notes = {}, {}, []
            end019_runner._apply_design({}, {"mass_kg": 7.8}, config, prov, {}, notes)
            self.assertEqual(config["cases"][0]["P_internal_W"], end019_runner.MODEL_P_INTERNAL_W)
            self.assertNotIn("beta_deg", config["cases"][0])
            self.assertEqual((config["bat_min_C"], config["bat_max_C"]), end019_runner.BATTERY_DEFAULT_C)
            p = Provenance("END-019")
            p.add_origins({k: v for k, v in prov.items() if k in ("P_internal_W", "cases", "bat_min_C")})
            self.assertEqual(p.worst_severity(), "critical")
            self.assertEqual({e["item"] for e in p.fallbacks()}, {"P_internal_W", "cases", "bat_min_C"})

    def test_run_mode_and_level(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(star_runner_io.star_run_mode({"run_mode": "full"}), "full")
            self.assertEqual(star_runner_io.star_run_mode({"run_mode": "demo"}), "test")       # removed on 2026-10-15
            self.assertEqual(star_runner_io.star_run_mode({}), "test")
            self.assertEqual(star_runner_io.star_run_level({"run_level": "5"}), 5)
            self.assertEqual(star_runner_io.star_run_level({"run_level": 9}), star_runner_io.DEFAULT_FULL_LEVEL)
        with mock.patch.dict(os.environ, {"STAR_RUN_MODE": "full", "STAR_RUN_LEVEL": "1"}, clear=True):
            self.assertEqual(star_runner_io.star_run_mode({}), "full")
            self.assertEqual(star_runner_io.star_run_level({}), 1)

    def test_spacecraft_definition_lookup(self):
        with tempfile.TemporaryDirectory() as tmp:
            mo = Path(tmp)
            self.assertIsNone(star_runner_io.load_spacecraft_definition({}, mo))
            path = mo / "END-006" / "output_component_selector" / "spacecraft_definition.json"
            write_json(path, {"form_factor": "6U"})                                         # no mass: not a design
            self.assertIsNone(star_runner_io.load_spacecraft_definition({}, mo))
            write_json(path, {"form_factor": "6U", "mass_kg": 7.8})
            sat = star_runner_io.load_spacecraft_definition({"upstream_products": {"spacecraft_definition": {"paths": [str(path)]}}})
            self.assertEqual((sat["form_factor"], sat["_source_path"]), ("6U", str(path)))
            # a payload without the upstream_products block (hand-built): token match on the upstream artifacts
            sat = star_runner_io.load_spacecraft_definition({"upstream_artifacts_absolute": [str(path)]})
            self.assertEqual(sat["_source_path"], str(path))

    def test_design_loads_are_logged_with_iteration_and_signature(self):
        """Phase F5: every load of the satellite goes to <run>/design_loads.jsonl; the signature ignores the promotion stamps."""
        with tempfile.TemporaryDirectory() as tmp:
            mo = Path(tmp) / "modules_output"
            path = mo / "END-006" / "output_component_selector" / "spacecraft_definition.json"
            d0 = {"form_factor": "6U", "mass_kg": 7.8, "components": {"adcs": "xact-100"}, "design_iteration": 0}
            write_json(path, d0)
            star_runner_io.load_spacecraft_definition({}, mo)
            _, offset = star_runner_io.read_design_loads(mo)
            write_json(path, {**d0, "design_iteration": 1, "promoted_from": "END-006/final", "generated_at": "later"})
            star_runner_io.load_spacecraft_definition({}, mo)
            loads, _ = star_runner_io.read_design_loads(mo, 0)
            self.assertEqual([x["design_iteration"] for x in loads], [0, 1])
            self.assertEqual(loads[0]["signature"], loads[1]["signature"])             # same content, only the stamps differ
            self.assertEqual(loads[1]["promoted_from"], "END-006/final")
            self.assertEqual(len(star_runner_io.read_design_loads(mo, offset)[0]), 1)  # only the loads after the offset
            write_json(path, {**d0, "mass_kg": 9.0})
            star_runner_io.load_spacecraft_definition({}, mo)
            self.assertNotEqual(star_runner_io.read_design_loads(mo, 0)[0][-1]["signature"], loads[0]["signature"])


if __name__ == "__main__":
    unittest.main()

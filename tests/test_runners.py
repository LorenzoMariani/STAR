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
        self.assertEqual(result["status"], "completed", result["evidence"])
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
                   {"form_factor": "12U", "mass_kg": 9.5})
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

    def test_mission_without_sar(self):
        self.upstream()
        result, info = self.run_module({
            "requirements": [requirement("A 3U CubeSat with an optical camera.")],
            "resolved_inputs": [{"needed_by_module_id": "END-019", "parameter": "sar_power_W", "proposed_value": "200",
                                 "source": "module_registry_default"}]})
        self.assertEqual(result["status"], "completed", result["evidence"])
        self.assertEqual(info["config"]["n_internal_nodes"], 2)
        self.assertNotIn("sar_power_W", info["config"])
        self.assertIn("The third internal node of the model is a SAR payload: not modelled for this mission", info["notes"])

    def test_out_of_the_cubesat_domain(self):
        result, info = self.run_module({"requirements": [requirement("A 3U CubeSat with mass not exceeding 50 kg.")]})
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(info["config"], {})
        result, _ = self.run_module({"requirements": [requirement("A microsatellite for Earth observation.")]})
        self.assertEqual(result["status"], "skipped")
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


if __name__ == "__main__":
    unittest.main()

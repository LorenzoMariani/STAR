import io
import json
import unittest
from contextlib import redirect_stdout

from star_selector.api import SelectorService, bom_rows, power_handoff, requirements_to_params
from star_selector.cli import main

SERVICE = SelectorService()


class TestSelectApi(unittest.TestCase):
    def test_the_only_input_is_the_cubesat_class(self):
        res = SERVICE.select({"form_factor_u": 6})
        self.assertTrue(res["ok"])
        self.assertEqual(res["cubesat"]["mass_limit_kg"], 12.0)
        self.assertIn("CubeSat Design Specification Rev. 14.1", res["cubesat"]["standard"])
        self.assertAlmostEqual(res["cubesat"]["volume_limit_m3"], 0.1 * 0.2263 * 0.366)

    def test_other_parameters_are_refused(self):
        with self.assertRaisesRegex(ValueError, "unknown parameters: mission"):
            SERVICE.select({"form_factor_u": 6, "mission": "eo"})
        with self.assertRaisesRegex(ValueError, "form_factor_u is required"):
            SERVICE.select({})
        with self.assertRaisesRegex(ValueError, "unsupported CubeSat class"):
            SERVICE.select({"form_factor_u": 2})

    def test_the_class_can_be_a_string(self):
        self.assertEqual(SERVICE.select({"form_factor_u": "3"})["cubesat"]["class_u"], 3)

    def test_overview_lists_classes_and_subsystems(self):
        o = SERVICE.overview()
        self.assertEqual([c["class_u"] for c in o["classes"]], [1, 3, 6, 12])
        self.assertEqual(len(o["subsystems"]), 17)
        self.assertEqual(o["n_components"], 427)

    def test_component_record_carries_the_rows_and_the_dimensions(self):
        rec = SERVICE.component("aac-kryten-m3", with_image=False)
        self.assertEqual(rec["dimensions"]["mm"], [95.89, 90.17, 5.51])
        self.assertTrue(any(r["key"] == "mass_kg" for r in rec["rows"]))
        self.assertIsNone(SERVICE.component("endurosat-eps-i", with_image=False)["dimensions"])

    def test_images_are_embedded_on_request(self):
        res = SERVICE.select({"form_factor_u": 6}, with_images=True)
        sel = [s["selected"] for s in res["subsystems"] if s["selected"] and s["selected"]["image"]]
        self.assertTrue(sel)
        self.assertTrue(all(k["image"].get("data_uri", "").startswith("data:image") for k in sel))

    def test_bom_and_power_handoff_use_only_published_values(self):
        res = SERVICE.select({"form_factor_u": 6})
        rows = bom_rows(res)
        self.assertEqual(len(rows), res["totals"]["n_covered"])
        self.assertAlmostEqual(sum(r["mass_kg"] for r in rows), res["totals"]["mass_kg"])
        ph = power_handoff(res)
        self.assertEqual(ph["sum_declared_peak_W"], res["totals"]["power_w_declared_peak"])
        self.assertEqual(ph["not_publicly_available"], res["totals"]["power_unknown"])
        self.assertIn("no estimates", ph["kind"])

    def test_breakdowns_match_the_selected_components(self):
        res = SERVICE.select({"form_factor_u": 6})
        self.assertAlmostEqual(sum(res["breakdown"]["mass_kg"].values()), res["totals"]["mass_kg"])
        self.assertAlmostEqual(sum(res["breakdown"]["power_w"].values()), res["totals"]["power_w_declared_peak"])


class TestRequirements(unittest.TestCase):
    def test_the_class_is_read_from_the_requirements(self):
        for text, u in (("The satellite shall be a 6U CubeSat.", 6), ("A 12-unit CubeSat is required.", 12), ("Use a 1U platform for the demonstrator.", 1),
                        ("The mission needs a 3U structure.", 3)):
            out = requirements_to_params(text)
            self.assertEqual(out["params"]["form_factor_u"], u, text)
            self.assertTrue(out["applicable"])
            self.assertTrue(out["evidence"]["form_factor_u"])

    def test_nothing_is_invented_when_the_class_is_not_stated(self):
        out = requirements_to_params("The satellite shall observe the Earth with a GSD of 5 m.")
        self.assertNotIn("form_factor_u", out["params"])
        self.assertFalse(out["applicable"])
        self.assertTrue(out["notes"])

    def test_a_mass_above_24_kg_is_out_of_scope(self):
        out = requirements_to_params("Each satellite has a mass not exceeding 100 kg. It is a 6U-class demonstrator.")
        self.assertTrue(out["out_of_scope"])
        self.assertFalse(out["applicable"])

    def test_defaults_are_kept_only_if_the_requirements_do_not_say_otherwise(self):
        self.assertEqual(requirements_to_params("A CubeSat.", {"form_factor_u": 6})["params"]["form_factor_u"], 6)
        self.assertEqual(requirements_to_params("A 3U CubeSat.", {})["params"]["form_factor_u"], 3)


class TestCli(unittest.TestCase):
    def test_select_json(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["select", "--form-factor", "6", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(buf.getvalue())["cubesat"]["class_u"], 6)

    def test_select_text_marks_missing_data(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            main(["select", "--form-factor", "6"])
        out = buf.getvalue()
        self.assertIn("Not publicly available", out)
        self.assertIn("in database", out)

    def test_a_class_that_cannot_carry_everything_returns_a_non_zero_code(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["select", "--form-factor", "1", "--json"]), 1)

    def test_validate_and_list(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(main(["validate"]), 0)
            self.assertEqual(main(["list", "--category", "magnetorquer"]), 0)
        self.assertIn("427 valid components", buf.getvalue())
        self.assertIn("isis-imtq", buf.getvalue())


if __name__ == "__main__":
    unittest.main()

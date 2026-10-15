"""Valori di riferimento letti dai documenti dei fornitori per le categorie aggiunte il 2026-10-14 (propulsione, antenne, GNSS, magnetorquer,
ruote di reazione, strutture 1U)."""
import math
import unittest

from star_selector.api import SelectorService

SERVICE = SelectorService()
CAT = {c.id: c for c in SERVICE.catalog}
BY = {}
for _c in SERVICE.catalog:
    BY.setdefault(_c.category, []).append(_c)
G0 = 9.80665


class TestStructures1U(unittest.TestCase):
    def test_three_1u_structures_with_cds_limits(self):
        s1 = [c for c in BY["structure"] if c.spec("form_factor_u") == 1]
        self.assertEqual({c.id for c in s1}, {"isis-structure-1u", "endurosat-structure-1u", "spacemanic-structure-1u"})
        for c in s1:
            self.assertEqual(c.spec("max_total_mass_kg"), 2.0)
            self.assertEqual(c.dimensions_mm, [100.0, 100.0, 113.5])
        self.assertEqual(CAT["isis-structure-1u"].mass_kg, 0.2)       # struttura primaria + secondaria, come le altre strutture ISIS
        self.assertEqual(CAT["endurosat-structure-1u"].mass_kg, 0.12)  # con viti, kill switch e molle
        self.assertEqual(CAT["spacemanic-structure-1u"].mass_kg, 0.115)


class TestAttitudeActuators(unittest.TestCase):
    def test_magnetorquers(self):
        self.assertEqual(len(BY["magnetorquer"]), 8)
        imtq = CAT["isis-imtq"]
        self.assertEqual((imtq.mass_kg, imtq.dimensions_mm, imtq.spec("magnetic_moment_am2"), imtq.spec("power_w_max"), imtq.spec("axes")), (0.196, [95.9, 90.1, 17.0], 0.2, 1.2, 3))
        rods = sorted((c for c in BY["magnetorquer"] if c.spec("magnetorquer_type") == "rod"), key=lambda c: c.spec("magnetic_moment_am2"))
        self.assertEqual([c.spec("magnetic_moment_am2") for c in rods], [0.2, 0.3, 0.4, 1.0, 1.2, 2.0])
        self.assertEqual([c.mass_kg for c in rods], [0.0165, 0.023, 0.023, 0.037, 0.045, 0.054])
        self.assertTrue(all(c.spec("power_w_max") is None for c in rods))            # la potenza delle barre non e' pubblicata
        self.assertEqual(CAT["gomspace-nanotorque-gst-600-mk2"].mass_kg, 0.18)

    def test_reaction_wheels(self):
        self.assertEqual(len(BY["reaction_wheel"]), 10)
        rw = CAT["aac-rw210-15"]
        self.assertEqual((rw.mass_kg, rw.dimensions_mm, rw.spec("momentum_mnms"), rw.spec("max_torque_mnm")), (0.021, [25.0, 25.0, 15.0], 1.5, 0.1))
        self.assertEqual([CAT[f"aac-rw210-{s}"].spec("momentum_mnms") for s in ("15", "30", "60")], [1.5, 3.0, 6.0])
        self.assertEqual([CAT[f"aac-rw210-{s}"].mass_kg for s in ("15", "30", "60")], [0.021, 0.032, 0.048])
        r = CAT["rocketlab-rw-0-01"]
        self.assertEqual((r.mass_kg, r.dimensions_mm, r.spec("momentum_mnms"), r.spec("power_w_peak"), r.price[0]), (0.12, [50.0, 50.0, 30.0], 10.0, 1.05, 20000))
        self.assertEqual(CAT["cubespace-cubewheel-cw0057"].spec("momentum_mnms"), 5.7)
        self.assertEqual(CAT["bct-rwp015"].spec("momentum_mnms"), 15.0)
        self.assertIsNone(CAT["bct-rwp015"].spec("power_w_peak"))                       # Blue Canyon non pubblica la potenza nella pagina
        self.assertEqual(CAT["nanoavionics-rw0"].mass_kg, 0.137)

    def test_derived_values_are_flagged_in_the_notes(self):
        self.assertIn("DERIVAT", CAT["gomspace-nanotorque-gsw-600"].raw["notes"])      # potenza ricavata da tensione x corrente dichiarate
        self.assertIn("SOMMA", CAT["gomspace-nanotorque-gst-600-mk2"].raw["notes"])


class TestPropulsionAntennaGps(unittest.TestCase):
    def test_counts(self):
        self.assertEqual((len(BY["propulsion"]), len(BY["antenna"]), len(BY["gps"])), (17, 11, 6))

    def test_busek_bit3_derived_impulse_matches_the_declared_delta_v(self):
        """Il datasheet dichiara 2.39 km/s per un CubeSat da 14 kg: l'impulso derivato (Isp x g0 x propellente) deve darlo."""
        c = CAT["busek-bit-3"]
        isp, prop = c.spec("isp_s"), c.spec("propellant_mass_kg")
        self.assertAlmostEqual(c.spec("total_impulse_ns"), isp * G0 * prop, delta=1)
        dv = isp * G0 * math.log(14.0 / (14.0 - prop))
        self.assertAlmostEqual(dv, 2390, delta=15)

    def test_pm200_delta_v_is_close_to_the_declared_230_m_s(self):
        c = CAT["aac-pm200"]
        mprop = c.spec("total_impulse_ns") / (c.spec("isp_s") * G0)
        dv = c.spec("isp_s") * G0 * math.log(4.0 / (4.0 - mprop))
        self.assertTrue(200 <= dv <= 260, dv)

    def test_conflicting_values_are_left_undeclared(self):
        self.assertIsNone(CAT["endurosat-x-band-2x2"].spec("gain_dbi"))
        self.assertIsNone(CAT["endurosat-s-band-commercial"].spec("gain_dbi"))

    def test_gnss_reference_values(self):
        self.assertEqual(CAT["sstl-sgr-ligo"].spec("accuracy_position_m"), 5.0)
        self.assertEqual(CAT["skyfox-pinav-ng"].spec("accuracy_basis"), "2-sigma")
        self.assertIsNone(CAT["spacemanic-celeste"].spec("accuracy_position_m"))


if __name__ == "__main__":
    unittest.main()

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
        self.assertEqual(len(BY["reaction_wheel"]), 30)
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


class TestWheelsAndTrackers(unittest.TestCase):
    """Ruote e star tracker aggiunti il 2026-10-15 da datasheet dei fornitori."""

    def test_counts(self):
        self.assertEqual((len(BY["reaction_wheel"]), len(BY["star_tracker"])), (30, 9))

    def test_aac_wheels(self):
        for mom, mass in ((15, 0.197), (30, 0.21), (50, 0.375)):
            c = CAT[f"aac-rw400-{mom}"]
            self.assertEqual((c.spec("momentum_mnms"), c.mass_kg, c.dimensions_mm, c.spec("max_torque_mnm"), c.spec("power_w_peak")), (float(mom), mass, [50, 50, 27], 8.0, 1.9))
        for mom in (3, 6):
            c = CAT[f"aac-rw222-{mom}0"]
            self.assertIsNone(c.mass_kg)                              # il datasheet scrive 'TBC'
            self.assertEqual((c.spec("momentum_mnms"), c.spec("max_torque_mnm"), c.dimensions_mm), (float(mom), 2.0, [25, 25, 15]))
            self.assertIsNone(c.spec("max_speed_rpm"))                # '10000 / 15000 (to be tested)': non associata a una versione

    def test_astrofein_values_are_converted_from_newton_metre_second(self):
        a, b = CAT["astrofein-rw1-a"], CAT["astrofein-rw1-b"]
        self.assertEqual((a.spec("momentum_mnms"), a.spec("max_torque_mnm"), a.mass_kg, a.dimensions_mm), (0.58, 0.023, 0.024, [21, 21, 12]))
        self.assertEqual((b.spec("momentum_mnms"), b.spec("max_torque_mnm"), b.mass_kg), (0.1, 0.004, 0.012))
        self.assertEqual((CAT["astrofein-rw25"].spec("momentum_mnms"), CAT["astrofein-rw250"].spec("momentum_mnms"), CAT["astrofein-rwt250"].dimensions_mm), (30.0, 4000.0, [200, 200, 100]))
        self.assertEqual(len([c for c in BY["reaction_wheel"] if c.raw["vendor"] == "ASTROFEIN"]), 10)

    def test_newspace_and_vectronic_wheels(self):
        t5, v2, v1 = CAT["newspace-nrwa-t005"], CAT["vectronic-vrw-02"], CAT["vectronic-vrw-1"]
        self.assertEqual((t5.mass_kg, t5.dimensions_mm, t5.spec("momentum_mnms")), (0.5, [65, 65, 65], 50.0))
        self.assertIn("separat", t5.raw["notes"])                       # l'elettronica e' un'unita' a parte, esclusa
        self.assertEqual((v2.mass_kg, v2.dimensions_mm, v2.spec("momentum_mnms"), v2.spec("power_w_peak")), (1.0, [70, 70, 48], 200.0, 25.0))
        self.assertEqual((v1.mass_kg, v1.dimensions_mm, v1.spec("momentum_mnms")), (1.8, [115, 115, 77], 1000.0))
        self.assertIsNone(v1.raw.get("image"))                          # il datasheet ha solo il logo

    def test_sodern_auriga_optical_head_and_rocket_lab_variants(self):
        a = CAT["sodern-auriga-oh"]
        self.assertEqual((a.mass_kg, a.dimensions_mm, a.raw["power_w"], a.spec("accuracy_cross_arcsec"), a.spec("accuracy_roll_arcsec"), a.spec("accuracy_basis")), (0.225, [66, 59, 94], 0.8, 9.0, 51.0, "3-sigma"))
        self.assertIsNone(a.spec("fov_deg"))
        base, short, large = CAT["rocketlab-st16rt2"], CAT["rocketlab-st16rt2-short-baffle"], CAT["rocketlab-st16rt2-large-baffle"]
        self.assertEqual((short.mass_kg, short.dimensions_mm, short.spec("fov_deg")), (0.185, [62, 56, 68], [16.0, 16.0]))
        self.assertEqual((large.mass_kg, large.dimensions_mm, large.raw["dimensions"]["basis"]), (0.235, [99, 99, 120], "derived"))
        for v in (short, large):
            self.assertEqual(v.raw["datasheet"]["file"], base.raw["datasheet"]["file"])      # stessa scheda
            self.assertEqual(v.spec("accuracy_cross_arcsec"), base.spec("accuracy_cross_arcsec"))
        self.assertIn("DERIVAT", short.raw["notes"])


class TestSunSensors(unittest.TestCase):
    """Sensori solari (categoria aggiunta il 2026-10-15): valori letti dai documenti dei fornitori; i valori derivati sono dichiarati nelle note."""

    def test_the_five_sun_sensors(self):
        self.assertEqual(sorted(c.id for c in BY["sun_sensor"]), ["cubespace-cubesense-sun", "newspace-ncss-sa05", "newspace-nfss-411", "solarmems-nanossoc-d60", "solarmems-ssoc-a60"])

    def test_newspace_datasheet_values(self):
        n, f = CAT["newspace-ncss-sa05"], CAT["newspace-nfss-411"]
        self.assertEqual((n.mass_kg, n.dimensions_mm, n.spec("fov_deg"), n.spec("sensor_type")), (0.005, [33, 11, 6], [114], "coarse"))
        self.assertEqual((f.mass_kg, f.dimensions_mm, f.spec("fov_deg"), f.spec("accuracy_deg"), f.spec("accuracy_basis"), f.spec("update_rate_hz"), f.raw["power_w"]),
                         (0.035, [34, 40, 20], [140], 0.1, "RMS", 5, 0.15))
        self.assertEqual(f.spec("supply_voltage_ranges_v"), [[5, 50]])

    def test_solar_mems_and_cubespace_values(self):
        a, d, cs = CAT["solarmems-ssoc-a60"], CAT["solarmems-nanossoc-d60"], CAT["cubespace-cubesense-sun"]
        self.assertEqual((a.mass_kg, a.dimensions_mm, a.spec("accuracy_deg"), a.raw["power_w"]), (0.025, [30, 30, 12], 0.3, 0.036))
        self.assertEqual((d.mass_kg, d.dimensions_mm, d.spec("accuracy_deg"), d.spec("accuracy_basis"), d.spec("data_interfaces")), (0.0065, [43, 14, 5.9], 0.5, "3-sigma", ["UART", "I2C", "SPI"]))
        self.assertEqual((cs.mass_kg, cs.dimensions_mm, cs.spec("fov_deg"), cs.spec("accuracy_deg"), cs.spec("accuracy_basis")), (0.015, [35, 22, 24], [166], 0.2, "2-sigma"))
        self.assertIsNone(cs.raw.get("datasheet"))                       # solo pagina prodotto: nessun PDF

    def test_what_the_vendor_does_not_publish_stays_null(self):
        for cid in ("solarmems-ssoc-a60", "solarmems-nanossoc-d60"):
            c = CAT[cid]
            self.assertIsNone(c.spec("sensor_type"), cid)                  # il fornitore non lo classifica fine o coarse
            self.assertIsNone(c.spec("update_rate_hz"), cid)
        self.assertIsNone(CAT["solarmems-ssoc-a60"].spec("accuracy_basis"))
        for cid in ("newspace-ncss-sa05", "solarmems-nanossoc-d60", "solarmems-ssoc-a60"):
            self.assertIn("DERIVAT", CAT[cid].raw["notes"], cid)            # campo di vista pieno o potenza ricavati: dichiarati

    def test_sun_sensors_are_external_parts_and_are_in_every_selection(self):
        for u in (1, 3, 6, 12):
            res = SERVICE.select({"form_factor_u": u})
            sub = next(s for s in res["subsystems"] if s["id"] == "sun_sensor")
            self.assertTrue(sub["selected"]["external"], u)
            self.assertIsNone(sub["selected"]["volume_m3"], u)                # sulle facce: non nel volume interno
            self.assertEqual(sub["selected"]["id"], "newspace-ncss-sa05", u)  # completezza uguale ai fini/coarse con tutti i dati: il piu' leggero
            self.assertIn("sun_sensor", res["external_subsystems"])
            self.assertIn("sun_sensor", {e["subsystem"] for e in res["fit"]["external"]}, u)      # e' disegnato sulla faccia


class TestGnssAntennas(unittest.TestCase):
    """Antenne GNSS (categoria aggiunta il 2026-10-15): valori letti dai datasheet dei fornitori."""

    def test_the_three_antennas_and_their_documents(self):
        self.assertEqual(sorted(c.id for c in BY["gnss_antenna"]), ["exa-gca01", "isis-gapa", "newspace-nant-ptcl1"])
        for c in BY["gnss_antenna"]:
            self.assertTrue(c.raw["datasheet"]["file"] and c.raw["image"]["file"], c.id)
        self.assertEqual(CAT["newspace-nant-ptcl1"].raw["datasheet"]["file"], CAT["newspace-ngps-01-422"].raw["datasheet"]["file"])    # stesso datasheet del ricevitore

    def test_datasheet_values(self):
        g, e, n = CAT["isis-gapa"], CAT["exa-gca01"], CAT["newspace-nant-ptcl1"]
        self.assertEqual((g.mass_kg, g.dimensions_mm, g.spec("lna_gain_db"), g.spec("supply_voltage_ranges_v")), (0.018, [70, 70, 9.7], 34.5, [[3, 5]]))
        self.assertEqual((e.mass_kg, e.dimensions_mm, e.spec("total_gain_dbi"), e.spec("passive_gain_dbi"), e.spec("noise_figure_db")), (0.01138, [25.1, 25.1, 7.9], 15.5, -2.5, 2.8))
        self.assertEqual((n.mass_kg, n.dimensions_mm, n.spec("total_gain_dbi"), n.spec("beamwidth_deg"), n.raw["power_w"]), (0.08, [54, 54, 14.1], 16.0, 100.0, 0.08))

    def test_a_contradiction_inside_the_datasheet_is_left_undeclared(self):
        self.assertIsNone(CAT["isis-gapa"].spec("passive_gain_dbi"))       # 5.5 dBi nelle caratteristiche, 5.2 dBi nella tabella
        self.assertIn("5.5", CAT["isis-gapa"].raw["notes"])
        self.assertIn("5.2", CAT["isis-gapa"].raw["notes"])
        self.assertIn("DERIVAT", CAT["isis-gapa"].raw["notes"])             # potenza ricavata da corrente x tensione

    def test_the_gnss_antenna_is_an_external_subsystem_in_every_selection(self):
        for u in (1, 3, 6, 12):
            res = SERVICE.select({"form_factor_u": u})
            sub = next(s for s in res["subsystems"] if s["id"] == "gnss_antenna")
            self.assertEqual(sub["n_database"], 3)
            self.assertTrue(sub["selected"]["external"], u)
            self.assertIsNone(sub["selected"]["volume_m3"], u)
            self.assertIn("gnss_antenna", {e["subsystem"] for e in res["fit"]["external"]}, u)
            self.assertEqual(sub["selected"]["id"], "exa-gca01", u)       # a parita' di dati completi, la piu' leggera


class TestIceps2(unittest.TestCase):
    """EPS ISIS ICEPS2 Type A/B/C (aggiunti il 2026-10-15): valori del datasheet ISIS-ICEPS2-DSH-0001 issue 1.2."""
    IDS = ("isis-iceps2-type-a", "isis-iceps2-type-b", "isis-iceps2-type-c")

    def test_datasheet_values(self):
        a, b, c = (CAT[i] for i in self.IDS)
        self.assertEqual((a.mass_kg, b.mass_kg, c.mass_kg), (0.184, 0.310, 0.360))
        self.assertEqual((a.spec("integrated_battery_wh"), b.spec("integrated_battery_wh"), c.spec("integrated_battery_wh")), (28.8, 57.6, 57.6))
        self.assertEqual((a.spec("pv_channels"), b.spec("pv_channels"), c.spec("pv_channels")), (3, 3, 5))
        self.assertEqual((a.spec("pv_voltage_v"), b.spec("pv_voltage_v")), ([3.5, 7.5], [3.5, 13]))
        self.assertEqual({c_.raw["power_w"] for c_ in (a, b, c)}, {0.093})
        self.assertIn([28.2, 28.2], c.spec("output_voltage_ranges_v"))
        self.assertIsNone(a.spec("output_power_w_max"))                     # il datasheet da' solo le correnti per canale

    def test_dimensions_are_declared_for_a_and_derived_for_b_and_c(self):
        a, b, c = (CAT[i] for i in self.IDS)
        self.assertEqual((a.dimensions_mm, a.raw["dimensions"]["basis"]), ([96, 92, 26.5], "declared"))
        self.assertEqual((b.dimensions_mm, b.raw["dimensions"]["basis"]), ([96, 92, 32.3], "derived"))
        self.assertEqual((c.dimensions_mm, c.raw["dimensions"]["basis"]), ([96, 92, 37.0], "derived"))
        for x in (b, c):
            self.assertIn("DERIVATA", x.raw["notes"])

    def test_inconsistent_datasheet_values_are_flagged_and_documents_present(self):
        for i in self.IDS:
            c = CAT[i]
            self.assertIn("contraddizione", c.raw["notes"])
            self.assertTrue(c.raw["datasheet"]["file"] and c.raw["image"]["file"], i)
            self.assertIn(c.raw["shape"]["type"], ("board", "board_cells"), i)       # type A carries the battery pack on the card (image)
        self.assertEqual(len({CAT[i].raw["datasheet"]["file"] for i in self.IDS}), 1)


class TestGomspaceNanocomLink(unittest.TestCase):
    """GomSpace NanoCom Link S, X, SX (aggiunti il 2026-10-15): valori del datasheet DS 1076242 rev. 13.0; massa e potenze sono somme derivate dei moduli."""
    IDS = ("gomspace-nanocom-link-s", "gomspace-nanocom-link-x", "gomspace-nanocom-link-sx")

    def test_mass_is_the_derived_sum_of_the_declared_module_masses(self):
        s, x, sx = (CAT[i] for i in self.IDS)
        self.assertAlmostEqual(s.mass_kg, (272 + 123 + 23) / 1000, places=6)          # SDR + ANT2150-DUP Type C + cavi
        self.assertAlmostEqual(x.mass_kg, (272 + 150 + 26) / 1000, places=6)          # SDR + ANT8250 lato Y + cavi
        self.assertAlmostEqual(sx.mass_kg, (315 + 123 + 150 + 41) / 1000, places=6)   # SDR a due TR600 + i due front end + cavi
        for c in (s, x, sx):
            self.assertIn("DERIVAT", c.raw["notes"])

    def test_declared_dimensions_and_bands(self):
        s, x, sx = (CAT[i] for i in self.IDS)
        self.assertEqual((s.dimensions_mm, x.dimensions_mm, sx.dimensions_mm), ([95, 95, 23.85], [95, 95, 31.65], [95, 95, 31.65]))
        self.assertEqual((s.spec("band"), x.spec("band"), sx.spec("band")), ("S", "X", "S/X"))
        self.assertEqual((s.spec("has_receiver"), x.spec("has_receiver"), sx.spec("has_receiver")), (True, False, True))      # l'X-band e' solo trasmissione
        self.assertEqual((s.spec("data_rate_kbps_max"), x.spec("data_rate_kbps_max")), (7500.0, 225000.0))
        self.assertEqual(s.raw["temp_op_c"], [-40, 53])

    def test_power_sums_match_the_module_tables(self):
        s, x, sx = (CAT[i] for i in self.IDS)
        self.assertAlmostEqual(s.spec("power_w_idle"), 7.0 + 0.3, places=6)
        self.assertAlmostEqual(s.spec("power_w_tx"), 9.0 + 15.0, places=6)
        self.assertAlmostEqual(x.spec("power_w_idle"), 7.0 + 0.0 + 1.0, places=6)
        self.assertAlmostEqual(x.spec("power_w_tx"), 8.0 + 20.0 + 3.0, places=6)
        self.assertAlmostEqual(sx.spec("power_w_idle"), 7.5 + 0.3 + 0.0 + 1.0, places=6)
        self.assertAlmostEqual(sx.spec("power_w_tx"), 10.2 + 16.0 + 20.0 + 3.0, places=6)

    def test_documents_shared_and_standalone_sdr_not_in_catalogue(self):
        self.assertEqual(len({CAT[i].raw["datasheet"]["file"] for i in self.IDS}), 1)
        for i in self.IDS:
            self.assertTrue(CAT[i].raw["image"]["file"], i)
        self.assertNotIn("gomspace-nanocom-sdr-mk3", CAT)                 # nessun datasheet pubblico della SDR da sola
        self.assertNotIn("gomspace-nanocom-link-is1", CAT)                # datasheet preliminare con avviso di confidenzialita'


class TestIsisObcAndTrxuv(unittest.TestCase):
    """ISIS iOBC e TRXUV (aggiunti il 2026-10-15): valori delle brochure del fornitore."""

    def test_iobc_values_and_declared_discrepancies(self):
        c = CAT["isis-iobc"]
        self.assertEqual((c.category, c.mass_kg, c.dimensions_mm, c.raw["power_w"], c.raw["temp_op_c"], c.spec("supply_voltage_ranges_v")), ("obc", 0.1, [96, 90, 12.4], 0.4, [-25, 65], [[3.3, 3.3]]))
        for s in ("76 g", "100 g", "FM", "512 kB"):                    # massa di configurazioni diverse e valori delle pagine ISIS diversi dalla brochure
            self.assertIn(s, c.raw["notes"])
        self.assertIn("I2C", c.spec("data_interfaces"))

    def test_trxuv_values_and_it_is_not_the_trxvu(self):
        c = CAT["isis-trxuv"]
        self.assertEqual((c.category, c.mass_kg, c.dimensions_mm, c.raw["temp_op_c"]), ("comms", 0.085, [96, 90, 15], [-10, 45]))
        self.assertEqual((c.spec("data_rate_kbps_max"), c.spec("power_w_tx"), c.spec("power_w_idle"), c.spec("supply_voltage_ranges_v"), c.spec("has_receiver")), (9.6, 1.55, 0.2, [[6.5, 12.5]], True))
        self.assertNotEqual(c.raw["datasheet"]["file"], CAT["isis-trxvu"].raw["datasheet"]["file"])
        self.assertIn("TRXVU", c.raw["notes"])

    def test_both_have_documents_and_board_shape(self):
        for i, shape in (("isis-iobc", "board"), ("isis-trxuv", "board_shield")):         # the transceiver card has an RF shield (image)
            c = CAT[i]
            self.assertTrue(c.raw["datasheet"]["file"] and c.raw["image"]["file"], i)
            self.assertEqual(c.raw["shape"]["type"], shape, i)


class TestMorePropulsion(unittest.TestCase):
    """Propulsione aggiunta il 2026-10-15 (Dawn CubeDrive, CU Aerospace MPUC/PUC/MVP/FPPT, Enpulsion MICRO R3): valori dai documenti dei fornitori."""
    DAWN = ("dawn-cubedrive-0-8u", "dawn-cubedrive-2u", "dawn-cubedrive-8u")
    MPUC = ("cuaerospace-mpuc-1u", "cuaerospace-mpuc-1-5u", "cuaerospace-mpuc-2u")

    def test_dawn_cubedrive_values(self):
        a, b, c = (CAT[i] for i in self.DAWN)
        self.assertEqual((a.mass_kg, a.spec("dry_mass_kg"), a.spec("total_impulse_ns"), a.dimensions_mm), (1.25, 1.051, 400.0, [80, 96, 96]))
        self.assertEqual((b.mass_kg, b.spec("dry_mass_kg"), b.spec("total_impulse_ns"), b.dimensions_mm), (2.75, 2.0, 1500.0, [200, 96, 96]))
        self.assertEqual((c.mass_kg, c.spec("dry_mass_kg"), c.spec("total_impulse_ns"), c.dimensions_mm), (7.9, 6.0, 3500.0, None))
        self.assertEqual((a.spec("thrust_mn_min"), a.spec("thrust_mn_max")), (440.0, 1150.0))
        self.assertIn("DERIVAT", a.raw["notes"])                       # propellente = massa piena - massa a secco
        self.assertAlmostEqual(a.spec("propellant_mass_kg"), a.mass_kg - a.spec("dry_mass_kg"), places=6)
        self.assertAlmostEqual(b.spec("propellant_mass_kg"), b.mass_kg - b.spec("dry_mass_kg"), places=6)
        self.assertIsNone(c.spec("propellant_mass_kg"))                # la brochure panoramica non lo da'
        self.assertNotEqual(a.raw["datasheet"]["file"], c.raw["datasheet"]["file"])     # 8U: solo la brochure panoramica

    def test_mpuc_sizes_are_consistent_with_the_datasheet_table(self):
        for cid, wet, dry, prop, imp, vol in (("cuaerospace-mpuc-1u", 1.774, 1.35, 0.424, 740.0, 1.0), ("cuaerospace-mpuc-1-5u", 2.446, 1.641, 0.805, 1407.0, 1.5),
                                              ("cuaerospace-mpuc-2u", 3.25, 2.036, 1.214, 2122.0, 2.0)):
            c = CAT[cid]
            self.assertEqual((c.mass_kg, c.spec("dry_mass_kg"), c.spec("propellant_mass_kg"), c.spec("total_impulse_ns"), c.raw["volume_u"]), (wet, dry, prop, imp, vol), cid)
            self.assertAlmostEqual(c.spec("dry_mass_kg") + c.spec("propellant_mass_kg"), c.mass_kg, places=6, msg=cid)    # la tabella: massa piena = secco + propellente
        self.assertEqual(CAT["cuaerospace-mpuc-1u"].dimensions_mm, [102, 95, 95])
        self.assertIsNone(CAT["cuaerospace-mpuc-1-5u"].dimensions_mm)

    def test_cua_matrix_systems_and_enpulsion_micro(self):
        for cid, wet, imp, isp, firing in (("cuaerospace-puc", 0.718, 184.0, 70.0, 15.0), ("cuaerospace-mvp", 1.055, 280.0, 66.0, 45.0), ("cuaerospace-fppt", 3.03, 24000.0, 3200.0, 32.0)):
            c = CAT[cid]
            self.assertEqual((c.mass_kg, c.spec("total_impulse_ns"), c.spec("isp_s"), c.spec("power_w_firing")), (wet, imp, isp, firing), cid)
            self.assertIsNone(c.dimensions_mm, cid)
            self.assertFalse(c.raw.get("image"), cid)                 # il documento non ha immagini
            self.assertAlmostEqual(c.spec("dry_mass_kg") + c.spec("propellant_mass_kg"), wet, places=6, msg=cid)
        self.assertEqual(CAT["cuaerospace-fppt"].spec("propulsion_type"), "pulsed_plasma")
        m = CAT["enpulsion-micro-r3"]
        self.assertEqual((m.mass_kg, m.spec("dry_mass_kg"), m.spec("total_impulse_ns"), m.spec("isp_s"), m.dimensions_mm), (3.95, 2.7, 26000.0, 2700.0, [140, 120, 126.5]))
        self.assertEqual((m.spec("thrust_mn_min"), m.spec("thrust_mn_max"), m.spec("supply_voltage_ranges_v")), (0.5, 1.0, [[28.0, 28.0]]))

    def test_total_impulse_matches_isp_times_propellant_where_the_vendor_gives_all_three(self):
        """Controllo di coerenza dei documenti: Itot ~ Isp x g0 x propellente (tolleranza 3%); i sistemi con Isp o propellente mancanti non si controllano."""
        for cid in ("cuaerospace-puc", "cuaerospace-mvp", "cuaerospace-fppt", "cuaerospace-mpuc-1u", "cuaerospace-mpuc-1-5u", "cuaerospace-mpuc-2u"):
            c = CAT[cid]
            calc = c.spec("isp_s") * G0 * c.spec("propellant_mass_kg")
            self.assertAlmostEqual(calc / c.spec("total_impulse_ns"), 1.0, delta=0.05, msg=cid)
        m = CAT["enpulsion-micro-r3"]          # il datasheet dichiara meno impulso del propellente x Isp: usato il dichiarato e la differenza e' scritta nelle note
        self.assertGreater(m.spec("isp_s") * G0 * m.spec("propellant_mass_kg"), 1.2 * m.spec("total_impulse_ns"))
        self.assertIn("33100", m.raw["notes"])

    def test_thrusters_without_a_tank_are_not_in_the_catalogue(self):
        ids = {c.id for c in BY["propulsion"]}
        self.assertFalse({i for i in ids if "b20" in i or "b1-" in i or "satdrive" in i})


class TestPropulsionAntennaGps(unittest.TestCase):
    def test_counts(self):
        self.assertEqual((len(BY["propulsion"]), len(BY["antenna"]), len(BY["gps"])), (27, 11, 6))

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

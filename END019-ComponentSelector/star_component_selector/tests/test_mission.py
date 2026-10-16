"""Progetto per una missione (star_selector/mission.py, STAR 2026-10-15): sottosistemi richiesti, classe piu' piccola, requisiti verificati con i
dati pubblicati, sottosistemi non richiesti a parte, requisiti che nessun componente del catalogo soddisfa."""
import unittest
from pathlib import Path

from star_selector.api import SelectorService
from star_selector.mission import analyse, design
from star_selector.models import load_catalog
from star_selector.rows import subsystem_of
from star_selector.selector import CLASSES, Slot, select, total_impulse_ns

ROOT = Path(__file__).resolve().parent.parent
CATALOG = load_catalog(ROOT / "data" / "catalog.json")
BY_ID = {c.id: c for c in CATALOG}

V6 = [  # requisiti della proposta STAR v6 (PATRIMONIO-CUBE) rilevanti per END-019
    {"id": "REQ-002", "text": "Each satellite shall re-enter the atmosphere within 5 years of the end of its mission."},
    {"id": "REQ-003", "text": "The satellites shall keep a safe separation from each other."},
    {"id": "REQ-004", "text": "The constellation shall have sun-synchronous orbits between 500 km and 650 km of altitude."},
    {"id": "REQ-006", "text": "Each satellite shall be a 6U CubeSat with a mass not exceeding 12 kg."},
    {"id": "REQ-008", "text": "Each satellite shall be three-axis stabilised with a pointing accuracy better than 0.1 deg and point nominally at nadir."},
    {"id": "REQ-009", "text": "Each satellite shall carry a visible-spectrum push-broom camera with a panchromatic Ground Sample Distance of 4.0 m and a swath of 30 km at nadir."},
    {"id": "REQ-010", "text": "Each satellite shall acquire images in daylight only and send them to the ground through UHF and S-band links."},
]
END016 = {"kpis": {"disposal_dv_m_s_5y_rule_mean_activity": 58.0, "disposal_dv_m_s_25y_rule_mean_activity": 12.3,
                   "passive_lifetime_years_mean_activity": 35.2, "orbit_maintenance_needed": False},
          "config": {"mission_lifetime_years": 3}}


REQ_DOD = {"id": "REQ-018", "text": "The daily energy balance shall not be negative and the battery depth of discharge shall not exceed 30 percent in any orbit."}


def end004(per_orbit_wh, capacity_wh=19.0):
    """Riepilogo END-004 minimo: un modo volato con la scarica per orbita data (orbital_DoD = energia / capacita' usata da END-004)."""
    return {"orbit": {"batteryCapacityWh": capacity_wh},
            "mode_summaries": [{"mode": "Payload mode", "orbits_per_day": 8, "orbital_DoD": per_orbit_wh / capacity_wh},
                               {"mode": "TX mode S BAND", "orbits_per_day": 0, "orbital_DoD": 10 * per_orbit_wh / capacity_wh}]}


def slots_of(sel):
    return {r.id: r for r in sel.subsystems}


class NeedsTest(unittest.TestCase):
    def test_bus_only_mission(self):
        sel, m = design(CATALOG, [{"id": "R1", "text": "The CubeSat shall relay messages from ground sensors."}])
        self.assertEqual({r.subsystem for r in sel.subsystems}, {"structure", "obc", "eps", "battery", "solar_panel", "comms", "antenna"})
        self.assertEqual(sel.cubesat.units, 1)
        extras = {e["id"] for e in m["extras"]}
        self.assertIn("propulsion", extras)
        self.assertIn("payload_imager", extras)

    def test_no_manoeuvre_no_propulsion(self):
        sel, m = design(CATALOG, V6)
        self.assertNotIn("propulsion", {r.subsystem for r in sel.subsystems})
        prop = next(e for e in m["extras"] if e["id"] == "propulsion")
        self.assertIn("no requirement asks for manoeuvres", prop["why_not"])

    def test_end016_delta_v_brings_propulsion(self):
        sel, m = design(CATALOG, V6, {"altitude_km": [641.6, 641.6], "end016": END016})
        prop = slots_of(sel)["propulsion"]
        self.assertIsNotNone(prop.selected)
        self.assertEqual(m["dv"]["dv_m_s"], 58.0)
        given = total_impulse_ns(prop.selected.comp) / sel.mass_kg
        self.assertGreaterEqual(given, 58.0)
        self.assertAlmostEqual(m["dv"]["given_m_s"], given)
        self.assertEqual(m["subsystems"]["propulsion"]["requirement"]["id"], "REQ-002")
        self.assertIn("gps", slots_of(sel))            # manoeuvres need the orbit on board

    def test_one_radio_and_antenna_per_band(self):
        sel, _ = design(CATALOG, V6)
        s = slots_of(sel)
        for band, slot in (("UHF", "uhf"), ("S", "s")):
            radio, ant = s[f"comms_{slot}"].selected.comp, s[f"antenna_{slot}"].selected.comp
            self.assertIn(band, str(radio.spec("band")).upper().split("/"))
            self.assertIn(band, [str(b).upper() for b in ant.spec("bands")])
        self.assertNotIn("comms", s)

    def test_integrated_adcs_replaces_separate_parts(self):
        sel, m = design(CATALOG, V6)
        subs = {r.subsystem for r in sel.subsystems}
        self.assertIn("adcs", subs)
        for part in ("magnetorquer", "reaction_wheel", "star_tracker", "sun_sensor"):
            self.assertNotIn(part, subs)
            self.assertIn("integrated ADCS", next(e for e in m["extras"] if e["id"] == part)["why_not"])

    def test_solar_panel_of_the_class_and_deployable_when_asked(self):
        sel, _ = design(CATALOG, V6, {"altitude_km": [641.6, 641.6], "end016": END016})
        self.assertEqual(sel.cubesat.units, 6)
        self.assertEqual(slots_of(sel)["solar_panel"].selected.comp.raw["specs"]["face"], "6U")
        sel, m = design(CATALOG, V6 + [{"id": "REQ-099", "text": "Each satellite shall have two deployable solar panels."}],
                        {"altitude_km": [641.6, 641.6], "end016": END016})
        panel = slots_of(sel)["solar_panel"].selected.comp
        self.assertIn("deployable", panel.raw["name"].lower())
        self.assertEqual(panel.raw["specs"]["face"], f"{sel.cubesat.units}U" if sel.cubesat.units != 12 else "6U")
        self.assertEqual(next(r for r in m["requirements"] if r["what"] == "deployable solar panel")["status"], "met")

    def test_small_energy_need_uses_the_battery_of_the_eps(self):
        sel, m = design(CATALOG, V6 + [REQ_DOD], {"altitude_km": [641.6, 641.6], "end004": end004(1.29)})
        self.assertNotIn("battery", {r.subsystem for r in sel.subsystems})
        eps = slots_of(sel)["eps"].selected.comp
        self.assertGreaterEqual(eps.spec("integrated_battery_wh") * 0.30, 1.29)
        self.assertAlmostEqual(m["battery"]["need_wh"], 1.29 / 0.30)
        self.assertEqual(m["battery"]["mode"], "Payload mode")          # only the modes the mission flies
        self.assertIn("integrated in the EPS", next(e for e in m["extras"] if e["id"] == "battery")["why_not"])
        self.assertEqual(next(r for r in m["requirements"] if r["what"].startswith("battery capacity"))["status"], "met")

    def test_large_energy_need_selects_a_battery_big_enough(self):
        need_per_orbit = 45.0                       # 150 Wh at 30 % depth of discharge: no EPS battery, only the 198 Wh pack
        sel, m = design(CATALOG, V6 + [REQ_DOD], {"altitude_km": [641.6, 641.6], "end004": end004(need_per_orbit)})
        batt = slots_of(sel)["battery"].selected.comp
        self.assertGreaterEqual(batt.spec("capacity_wh") * 0.30, need_per_orbit)
        row = next(c for c in m["subsystems"]["battery"]["checks"] if c["what"].startswith("capacity"))
        self.assertTrue(row["met"])

    def test_battery_without_end004_is_not_verifiable(self):
        sel, m = design(CATALOG, V6 + [REQ_DOD])
        self.assertIn("battery", {r.subsystem for r in sel.subsystems})
        self.assertEqual(next(r for r in m["requirements"] if r["requirement"] and r["requirement"]["id"] == "REQ-018")["status"], "not_verifiable")

    def test_telecommand_radio_has_a_receiver(self):
        sel, m = design(CATALOG, V6)
        uhf = slots_of(sel)["comms_uhf"].selected.comp
        self.assertTrue(uhf.spec("has_receiver"))
        self.assertTrue(next(c for c in m["subsystems"]["comms_uhf"]["checks"] if c["what"] == "receiver for the telecommands")["met"])
        sel, _ = design(CATALOG, [{"id": "R1", "text": "The satellite shall take images with a GSD of 40 m at 500 km of altitude and downlink them in S-band."}])
        self.assertTrue(slots_of(sel)["comms_s"].selected.comp.spec("has_receiver"))     # one radio: it must receive the telecommands too

    def test_image_radio_has_the_highest_rate_of_its_band(self):
        sel, m = design(CATALOG, V6)
        s_radio = slots_of(sel)["comms_s"].selected.comp
        self.assertEqual(str(s_radio.spec("band")).upper(), "S")
        best = max(c.spec("data_rate_kbps_max") for c in CATALOG if subsystem_of(c) == "comms" and str(c.spec("band")).upper() == "S")
        self.assertEqual(s_radio.spec("data_rate_kbps_max"), best)
        self.assertIn("highest published data rate", m["subsystems"]["comms_s"]["why"])
        self.assertEqual(m["radio"]["slot"], "comms_s")

    def test_stated_data_rate_is_checked(self):
        sel, m = design(CATALOG, [{"id": "R1", "text": "The satellite shall take images with a GSD of 40 m at 500 km of altitude."},
                                  {"id": "R2", "text": "Images shall be downlinked in S-band with a data rate of at least 2 Mbps."}])
        self.assertGreaterEqual(slots_of(sel)["comms_s"].selected.comp.spec("data_rate_kbps_max"), 2000)
        self.assertEqual(next(r for r in m["requirements"] if r["what"].startswith("data rate"))["status"], "met")
        _, m = design(CATALOG, [{"id": "R1", "text": "The satellite shall take images with a GSD of 40 m at 500 km of altitude."},
                                {"id": "R2", "text": "Images shall be downlinked in UHF with a data rate of at least 5 Mbps."}])
        self.assertTrue(any(u.startswith("Does not satisfy R2 (data rate >= 5 Mbps): no UHF radio in the database meets it") for u in m["unmet"]), m["unmet"])

    def test_antenna_included_in_the_radio_is_not_duplicated(self):
        sel, m = design(CATALOG, [{"id": "R1", "text": "The satellite shall take images with a GSD of 40 m at 500 km of altitude and downlink them in S-band."}])
        s = slots_of(sel)
        self.assertIn("+ ANT", s["comms_s"].selected.comp.raw["name"])
        self.assertNotIn("antenna_s", s)
        ant = [e for e in m["extras"] if e["subsystem"] == "antenna"]
        self.assertEqual([e["id"] for e in ant], ["antenna_s"])
        self.assertIn("included in the radio", ant[0]["why_not"])

    def test_adcs_declared_for_the_class_of_the_design(self):
        sel, m = design(CATALOG, V6, {"altitude_km": [641.6, 641.6], "end016": END016})
        adcs = slots_of(sel)["adcs"].selected.comp
        self.assertEqual(sel.cubesat.units, 6)
        lo, hi = adcs.spec("form_factor_range_u")
        self.assertTrue(lo <= 6 <= hi, adcs.id)                     # e.g. XACT-50, not the 3U XACT-15
        self.assertLessEqual(adcs.spec("pointing_accuracy_deg"), 0.1)
        self.assertIn("declared by its vendor for 6U", m["subsystems"]["adcs"]["why"])
        sel, m = design(CATALOG, [{"id": "R1", "text": "The CubeSat shall point at nadir and relay messages through UHF."}])
        self.assertEqual(sel.cubesat.units, 1)
        self.assertIn("none is declared for a 1U", m["subsystems"]["adcs"]["why"])

    def test_named_part_is_required(self):
        sel, _ = design(CATALOG, [{"id": "R1", "text": "The CubeSat shall carry a star tracker."}])
        self.assertIn("star_tracker", {r.subsystem for r in sel.subsystems})


class ClassTest(unittest.TestCase):
    def test_smallest_class(self):
        for reqs in (V6, [{"id": "R1", "text": "The satellite shall take images with a ground sample distance of 40 m at 500 km of altitude."}]):
            sel, m = design(CATALOG, reqs)
            u = sel.cubesat.units
            for smaller in [c for c in sorted(CLASSES) if c < u]:
                tried = next(x for x in m["class_search"] if x["class_u"] == smaller)
                self.assertFalse(tried["ok"], (smaller, tried))
            self.assertTrue(next(x for x in m["class_search"] if x["class_u"] == u)["ok"])

    def test_stated_class_is_only_reported(self):
        sel, m = design(CATALOG, V6)      # v6 without END-016: the subsystems fit a 3U although REQ-006 says 6U
        self.assertEqual(sel.cubesat.units, 3)
        self.assertEqual(m["stated_class"]["class_u"], 6)
        self.assertTrue(any("REQ-006 states a 6U" in n for n in m["notes"]))

    def test_user_class_wins(self):
        sel, m = design(CATALOG, V6, forced_class_u=12)
        self.assertEqual(sel.cubesat.units, 12)
        self.assertEqual(m["forced_class_u"], 12)

    def test_mass_requirement_limits_the_class(self):
        sel, _ = design(CATALOG, [{"id": "R1", "text": "The satellite shall take images; its mass shall not exceed 1.5 kg."}])
        self.assertLessEqual(sel.cubesat.mass_limit_kg, 1.5)


class RequirementTest(unittest.TestCase):
    def test_gsd_scaled_to_altitude(self):
        _, m = design(CATALOG, V6, {"altitude_km": [641.6, 641.6]})
        sel, _ = design(CATALOG, V6, {"altitude_km": [641.6, 641.6]})
        img = slots_of(sel)["payload_imager"].selected.comp
        gsd = img.spec("gsd_m_at_ref") * 641.6 / img.spec("reference_altitude_km")
        self.assertLessEqual(gsd, 4.0)                      # GSD first: it is met
        # no imager of the catalogue gives GSD <= 4 m and swath >= 30 km at 642 km
        both = [c for c in CATALOG if subsystem_of(c) == "payload_imager" and c.spec("gsd_m_at_ref") and c.spec("reference_altitude_km")
                and c.spec("swath_km_at_ref") and c.spec("gsd_m_at_ref") * 641.6 / c.spec("reference_altitude_km") <= 4.0
                and c.spec("swath_km_at_ref") * 641.6 / c.spec("reference_altitude_km") >= 30.0]
        self.assertEqual(both, [])
        swath = next(r for r in m["requirements"] if r["what"].startswith("swath"))
        self.assertEqual(swath["status"], "not_met")
        self.assertIn("Does not satisfy REQ-009", swath["message"])
        self.assertIn("no payload imager in the database meets it", swath["message"])
        self.assertTrue(any(u.startswith("Does not satisfy REQ-009") for u in m["unmet"]))

    def test_pointing_accuracy(self):
        sel, m = design(CATALOG, V6)
        adcs = slots_of(sel)["adcs"].selected.comp
        self.assertLessEqual(adcs.spec("pointing_accuracy_deg"), 0.1)
        self.assertEqual(next(r for r in m["requirements"] if r["what"].startswith("pointing"))["status"], "met")

    def test_unreachable_delta_v(self):
        sel, m = design(CATALOG, [{"id": "R1", "text": "The CubeSat shall perform orbit manoeuvres with a delta-v of 100000 m/s."}])
        self.assertIn("dv", m["relaxed"])
        msg = next(u for u in m["unmet"] if "delta-v" in u)
        self.assertIn("no thruster in the database gives", msg)

    def test_altitude_unknown_is_not_verifiable(self):
        _, m = design(CATALOG, [{"id": "R1", "text": "The camera shall have a GSD of 5 m."}])
        self.assertEqual(next(r for r in m["requirements"] if r["what"].startswith("GSD"))["status"], "not_verifiable")

    def test_analyse_parses_v6(self):
        a = analyse(V6)
        self.assertEqual(a["stated"]["class_u"], 6)
        self.assertEqual(a["mass_limit"]["kg"], 12.0)
        self.assertEqual((a["altitude"]["min_km"], a["altitude"]["max_km"]), (500.0, 650.0))


class SelectorExtensionsTest(unittest.TestCase):
    def test_default_select_unchanged(self):
        a, b = select(CATALOG, 6), select(CATALOG, 6, slots=None, dv_m_s=None, mass_limit_kg=None)
        self.assertEqual([r.selected.comp.id if r.selected else None for r in a.subsystems], [r.selected.comp.id if r.selected else None for r in b.subsystems])

    def test_allowed_restricts_the_pool(self):
        radio = next(c for c in CATALOG if subsystem_of(c) == "comms" and c.spec("band") == "S")
        sel = select(CATALOG, 3, slots=[Slot("comms_s", "comms", "RADIO", frozenset({radio.id}))])
        self.assertEqual(sel.subsystems[0].selected.comp.id, radio.id)

    def test_dv_constraint(self):
        slots = [Slot(s, s, s.upper()) for s in ("structure", "obc", "eps", "battery", "propulsion")]
        sel = select(CATALOG, 3, slots=slots, dv_m_s=150.0)
        self.assertTrue(sel.within_limits)
        prop = next(r for r in sel.subsystems if r.subsystem == "propulsion").selected
        self.assertGreaterEqual(total_impulse_ns(prop.comp) / sel.mass_kg, 150.0)

    def test_service_design(self):
        out = SelectorService().design({"requirements": V6, "context": {"altitude_km": [641.6, 641.6], "end016": END016}})
        self.assertEqual(out["cubesat"]["class_u"], 6)
        self.assertTrue(all(s["design"] for s in out["subsystems"]))
        self.assertTrue(out["mission"]["extras"])
        self.assertEqual({s["subsystem"] for s in out["subsystems"]} & {"reaction_wheel", "star_tracker"}, set())


if __name__ == "__main__":
    unittest.main()

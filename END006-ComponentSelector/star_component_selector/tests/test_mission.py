"""Progetto per una missione (star_selector/mission.py, STAR 2026-10-15): sottosistemi richiesti, classe piu' piccola, requisiti verificati con i
dati pubblicati, sottosistemi non richiesti a parte, requisiti che nessun componente del catalogo soddisfa."""
import math
import unittest
from pathlib import Path

from star_selector.api import SelectorService
from star_selector.mission import analyse, battery_heater, design
from star_selector.models import load_catalog
from star_selector.rows import subsystem_of
from star_selector.selector import CLASSES, Slot, select, total_impulse_ns

ROOT = Path(__file__).resolve().parent.parent
CATALOG = load_catalog(ROOT / "data" / "catalog.json")
# the catalogue before the NASA SoA / datasheet imports of 2026-10-23: tests of one specific design logic keep the components it was written for
CATALOG_BEFORE_IMPORT = [c for c in CATALOG if c.raw["source"].get("retrieved") != "2026-10-23"]
BY_ID = {c.id: c for c in CATALOG}

V6 = [  # requisiti della proposta STAR v6 (PATRIMONIO-CUBE) rilevanti per END-006
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


def batteries(sel):
    """Batterie del progetto: quella separata e quella integrata nell'EPS (una sola, 2026-10-19)."""
    sep = sum(1 for r in sel.subsystems if r.subsystem == "battery" and r.selected)
    eps = sum(1 for r in sel.subsystems if r.subsystem == "eps" and r.selected and r.selected.comp.spec("integrated_battery_wh"))
    return sep + eps


class NeedsTest(unittest.TestCase):
    def test_bus_only_mission(self):
        sel, m = design(CATALOG, [{"id": "R1", "text": "The CubeSat shall relay messages from ground sensors."}])
        self.assertEqual({r.subsystem for r in sel.subsystems} - {"battery"}, {"structure", "obc", "eps", "solar_panel", "comms", "antenna"})
        self.assertEqual(batteries(sel), 1)
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
        self.assertEqual(sel.cubesat.units, 12)
        self.assertEqual(slots_of(sel)["solar_panel"].selected.comp.raw["specs"]["face"], "6U")      # a 12U uses the 6U panels
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
        self.assertEqual(batteries(sel), 1)
        self.assertEqual(next(r for r in m["requirements"] if r["requirement"] and r["requirement"]["id"] == "REQ-018")["status"], "not_verifiable")

    def test_one_battery_only(self):
        """Mai la batteria integrata nell'EPS insieme a una batteria separata: con e senza END-004, con la classe scelta dall'utente."""
        cases = [(V6, None, None), (V6 + [REQ_DOD], None, None), (V6 + [REQ_DOD], {"end004": end004(1.29)}, None),
                 (V6 + [REQ_DOD], {"end004": end004(45.0)}, None), (V6, None, 12), (V6, None, 6),
                 ([{"id": "R1", "text": "The CubeSat shall relay messages from ground sensors."}], None, 3)]
        for reqs, ctx, cls in cases:
            with self.subTest(ctx=bool(ctx), cls=cls):
                sel, m = design(CATALOG, reqs, ctx, forced_class_u=cls)
                self.assertEqual(batteries(sel), 1)
                if "battery" not in {r.subsystem for r in sel.subsystems}:
                    self.assertIn("integrated in the EPS", next(e for e in m["extras"] if e["id"] == "battery")["why_not"])

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
        sel, m = design(CATALOG_BEFORE_IMPORT, [{"id": "R1", "text": "The satellite shall take images with a GSD of 40 m at 500 km of altitude and downlink them in S-band."}])
        s = slots_of(sel)
        self.assertIn("+ ANT", s["comms_s"].selected.comp.raw["name"])
        self.assertNotIn("antenna_s", s)
        ant = [e for e in m["extras"] if e["subsystem"] == "antenna"]
        self.assertEqual([e["id"] for e in ant], ["antenna_s"])
        self.assertIn("included in the radio", ant[0]["why_not"])

    def test_adcs_declared_for_the_class_of_the_design(self):
        sel, m = design(CATALOG, V6, {"altitude_km": [641.6, 641.6], "end016": END016})
        adcs = slots_of(sel)["adcs"].selected.comp
        u = sel.cubesat.units
        lo, hi = adcs.spec("form_factor_range_u")
        self.assertTrue(lo <= u <= hi, adcs.id)                     # declared for the class of the design (not the 3U XACT-15)
        self.assertLessEqual(adcs.spec("pointing_accuracy_deg"), 0.1)
        self.assertIn("declared by its vendor for", m["subsystems"]["adcs"]["why"])
        sel, m = design(CATALOG, [{"id": "R1", "text": "The CubeSat shall point at nadir and relay messages through UHF."}])
        self.assertEqual(sel.cubesat.units, 1)
        self.assertIn("none is declared for a 1U", m["subsystems"]["adcs"]["why"])

    def test_thruster_the_solar_panel_can_power(self):
        from star_selector.selector import firing_power_w, is_electric
        sel, m = design(CATALOG, V6, {"altitude_km": [641.6, 641.6], "end016": END016})
        thr, panel = slots_of(sel)["propulsion"].selected.comp, slots_of(sel)["solar_panel"].selected.comp
        if is_electric(thr):
            self.assertLessEqual(firing_power_w(thr), panel.spec("peak_power_w"))
        self.assertNotEqual(thr.id, "thrustme-npt30-i2-1u")          # 65 W ion thruster on an 18.4 W panel (the choice before 2026-10-16)
        self.assertGreaterEqual(total_impulse_ns(thr) / sel.mass_kg, 58.0)

    def test_electric_power_check_in_the_selector(self):
        nano = next(c for c in CATALOG if c.raw["name"].startswith("NANO R3"))                     # FEEP, 45 W firing
        panel = BY_ID["endurosat-solar-6u-deployable-single"]                                      # 38.4 W peak
        slots = [Slot("solar_panel", "solar_panel", "SOL", frozenset({panel.id})), Slot("propulsion", "propulsion", "PRP", frozenset({nano.id}))]
        self.assertTrue(select(CATALOG, 6, slots=slots).within_limits)
        self.assertFalse(select(CATALOG, 6, slots=slots, electric_power_check=True).within_limits)

    def test_vendor_minimum_class_of_the_thruster(self):
        r = next(r for r in select(CATALOG, 1).subsystems if r.id == "propulsion")
        self.assertNotIn("aac-pm200", [k.comp.id for k in [r.selected, *r.alternatives] if k])      # declared from 3U
        r = next(r for r in select(CATALOG, 3).subsystems if r.id == "propulsion")
        self.assertIn("aac-pm200", [k.comp.id for k in [r.selected, *r.alternatives] if k])

    def test_green_propellant_when_asked(self):
        sel, m = design(CATALOG, V6 + [{"id": "REQ-098", "text": "The propulsion system shall use a non-toxic propellant."}],
                        {"altitude_km": [641.6, 641.6], "end016": END016})
        self.assertNotIn("hydrazine", str(slots_of(sel)["propulsion"].selected.comp.spec("propellant")).lower())
        self.assertEqual(next(r for r in m["requirements"] if r["what"].startswith("non-toxic"))["status"], "met")

    def test_unreachable_delta_v_takes_the_closest_thruster(self):
        sel, m = design(CATALOG, [{"id": "R1", "text": "The CubeSat shall raise its orbit with a delta-v of 1000 m/s and downlink through UHF."}])
        from star_selector import mission
        from star_selector.fit import check_fit
        thr = slots_of(sel)["propulsion"].selected.comp
        slots = [Slot(r.id, r.subsystem, r.label, frozenset({r.selected.comp.id})) for r in sel.subsystems if r.subsystem != "propulsion"]
        for c in CATALOG:                       # no thruster with more impulse fits this design (the closest to the delta-v is chosen);
            # a thruster without published size is a candidate only when no other is (selector rule), so only sized ones compete
            if subsystem_of(c) == "propulsion" and (total_impulse_ns(c) or 0) > total_impulse_ns(thr) and c.dimensions_mm and None not in c.dimensions_mm:
                trial = mission.select(CATALOG, sel.cubesat.units, slots=slots + [Slot("propulsion", "propulsion", "PRP", frozenset({c.id}))])
                self.assertFalse(trial.within_limits and all(r.selected for r in trial.subsystems)
                                 and check_fit(trial)["state"] in mission.ACCEPTED_FIT, c.id)
        self.assertIn("dv", m["relaxed"])
        self.assertTrue(any("no thruster in the database gives 1000.0 m/s" in u for u in m["unmet"]))

    def test_imager_declared_for_the_class_and_of_the_right_kind(self):
        sel, m = design(CATALOG, V6, {"altitude_km": [641.6, 641.6], "end016": END016})
        img = slots_of(sel)["payload_imager"].selected.comp
        self.assertLessEqual(img.spec("min_form_factor_u") or 0, sel.cubesat.units)        # vendor minimum class
        self.assertIn("PAN", img.spec("spectral_bands"))                                      # panchromatic, visible
        self.assertNotIn("snapshot", img.raw["name"].lower())                                 # push-broom
        rows = {r["what"]: r["status"] for r in m["requirements"]}
        self.assertEqual(rows["panchromatic channel"], "met")
        self.assertEqual(rows["push-broom camera (not a snapshot camera)"], "met")
        sel, m = design(CATALOG, [{"id": "R1", "text": "The satellite shall take multispectral images with a GSD of 40 m at 500 km of altitude."}])
        self.assertIn("MS", slots_of(sel)["payload_imager"].selected.comp.spec("spectral_bands"))

    def test_image_kind_that_no_camera_gives(self):
        _, m = design(CATALOG, [{"id": "R1", "text": "The satellite shall take thermal infrared images of wildfires."}])
        self.assertIn("Does not satisfy R1 (thermal infrared): no payload imager in the database meets it.", m["unmet"])

    def test_optical_terminal_for_the_link(self):
        sel, m = design(CATALOG, [{"id": "R1", "text": "The satellites shall exchange data through an inter-satellite optical link at 1 Gbps."}])
        term = slots_of(sel)["payload_optical"].selected.comp
        self.assertIn(term.spec("link_type"), ("inter_satellite", "both"))
        self.assertGreaterEqual(term.spec("link_data_rate_mbps"), 1000)
        self.assertLessEqual(term.spec("min_form_factor_u") or 0, sel.cubesat.units)

    def test_products_no_longer_sold_only_when_nothing_else(self):
        for units in CLASSES:
            for r in select(CATALOG, units).subsystems:
                if r.selected and r.selected.comp.raw.get("status") == "nla":
                    self.assertTrue(all(k.comp.raw.get("status") == "nla" for k in r.alternatives), (units, r.id))

    def test_obc_talks_to_every_component(self):
        from star_selector.selector import interfaces
        for reqs, ctx in ((V6, {"altitude_km": [641.6, 641.6], "end016": END016}),
                          ([{"id": "R1", "text": "The satellite shall take multispectral images with a GSD of 40 m at 500 km of altitude and downlink them in S-band."}], {})):
            sel, m = design(CATALOG, reqs, ctx)
            obc = slots_of(sel)["obc"].selected.comp
            for r in sel.subsystems:
                ci = interfaces(r.selected.comp) if r.selected else None
                if r.subsystem != "obc" and ci:
                    self.assertTrue(ci & interfaces(obc), (r.id, r.selected.comp.id, obc.id))
            self.assertTrue(next(c for c in m["subsystems"]["obc"]["checks"] if c["what"].startswith("data interfaces"))["met"])
        sel, _ = design(CATALOG, V6, {"altitude_km": [641.6, 641.6], "end016": END016})
        self.assertIn("RS-422", interfaces(slots_of(sel)["obc"].selected.comp))               # the XACT ADCS speaks RS-422 only

    def test_interface_check_in_the_selector(self):
        xact, nanomind = BY_ID["bct-xact-15"], next(c for c in CATALOG if c.raw["name"] == "NanoMind A3200")
        slots = [Slot("obc", "obc", "OBC", frozenset({nanomind.id})), Slot("adcs", "adcs", "ADCS", frozenset({xact.id}))]
        self.assertTrue(select(CATALOG, 3, slots=slots).within_limits)
        self.assertFalse(select(CATALOG, 3, slots=slots, interface_check=True).within_limits)

    def test_radiation_requirement_on_the_obc(self):
        sel, m = design(CATALOG, [{"id": "R1", "text": "The CubeSat shall relay messages through UHF; its computer shall tolerate a total ionizing dose of 30 krad."}])
        self.assertGreaterEqual(slots_of(sel)["obc"].selected.comp.raw["tid_krad"], 30)
        self.assertEqual(next(r for r in m["requirements"] if r["what"].startswith("radiation"))["status"], "met")

    def test_eps_powers_every_component(self):
        from star_selector.selector import eps_class_ok, panel_ok, powered_by
        for reqs, ctx in ((V6, {"altitude_km": [641.6, 641.6], "end016": END016}),
                          ([{"id": "R1", "text": "The satellite shall take multispectral images with a GSD of 40 m at 500 km of altitude and downlink them in S-band."}], {})):
            sel, m = design(CATALOG, reqs, ctx)
            s = slots_of(sel)
            eps = s["eps"].selected.comp
            self.assertTrue(eps_class_ok(eps, sel.cubesat.units))
            self.assertNotEqual(eps.raw["specs"].get("pv_channels"), 0)                   # it can charge from the panels
            self.assertTrue(panel_ok(s["solar_panel"].selected.comp, eps))
            for r in sel.subsystems:
                if r.selected and r.subsystem not in ("eps", "battery", "solar_panel"):
                    self.assertTrue(powered_by(r.selected.comp, eps), (r.id, r.selected.comp.id, eps.id))
            self.assertTrue(all(c["met"] for c in m["subsystems"]["eps"]["checks"]))
        sel, _ = design(CATALOG, V6, {"altitude_km": [641.6, 641.6], "end016": END016})
        self.assertNotEqual(slots_of(sel)["eps"].selected.comp.id, "pumpkin-linear-eps-11wh")    # 3.3/5 V only, no solar input: not for the 12 V XACT

    def test_supply_check_in_the_selector(self):
        xact, linear = BY_ID["bct-xact-15"], BY_ID["pumpkin-linear-eps-11wh"]
        slots = [Slot("eps", "eps", "EPS", frozenset({linear.id})), Slot("adcs", "adcs", "ADCS", frozenset({xact.id}))]
        self.assertTrue(select(CATALOG, 3, slots=slots).within_limits)
        self.assertFalse(select(CATALOG, 3, slots=slots, power_supply_check=True).within_limits)

    def test_reaction_wheels_for_the_mission(self):
        from star_selector.selector import adcs_tier, wheel_momentum_needed_mnms
        reqs = [{"id": "R1", "text": "The CubeSat shall be three-axis stabilised with reaction wheels and slew at 2 deg/s."},
                {"id": "R2", "text": "It shall take multispectral images with a GSD of 40 m at 500 km of altitude and downlink them in S-band."}]
        sel, m = design(CATALOG, reqs)
        k = slots_of(sel)["reaction_wheel"].selected
        self.assertEqual(k.quantity, 3)                                                     # one per axis
        self.assertAlmostEqual(k.mass_kg, 3 * k.comp.mass_kg)
        self.assertGreaterEqual(k.comp.spec("momentum_mnms"), wheel_momentum_needed_mnms(sel.cubesat, 2.0))
        self.assertNotEqual(adcs_tier(k.comp, sel.cubesat.units), 2)                         # never declared only for smaller CubeSats
        self.assertIsNotNone(k.comp.mass_kg)                                                 # published mass before the declared class
        self.assertEqual(next(r for r in m["requirements"] if r["what"].startswith("wheel momentum"))["status"], "met")
        self.assertIn("3 wheel(s), one per axis", m["subsystems"]["reaction_wheel"]["why"])

    def test_suggested_wheels_follow_the_class(self):
        sel, m = design(CATALOG, V6, {"altitude_km": [641.6, 641.6], "end016": END016})       # 12U, wheels inside the integrated ADCS
        x = next(e for e in m["extras"] if e["id"] == "reaction_wheel")
        best = BY_ID[x["best"]["id"]]
        lo, hi = best.spec("form_factor_range_u") or (0, 99)
        self.assertTrue(lo <= sel.cubesat.units <= hi, best.id)                              # not the 1U-3U RW210.15
        self.assertEqual(x["best"]["quantity"], 3)

    def test_unreachable_slew(self):
        _, m = design(CATALOG, [{"id": "R1", "text": "The CubeSat shall be three-axis stabilised with reaction wheels and slew at 5000 deg/s; UHF link."}])
        self.assertTrue(any("no reaction wheel in the database" in u for u in m["unmet"]), m["unmet"])

    def test_magnetorquers_cover_three_axes_and_dump_the_wheels(self):
        from star_selector.mission import dump_dipole_per_nms
        self.assertTrue(6.5 < dump_dipole_per_nms(500) < 8.0)                                  # about 7 A m2 per N m s in LEO
        reqs = [{"id": "R1", "text": "Each satellite shall be a 12U CubeSat, three-axis stabilised with reaction wheels and magnetorquers, slewing at 10 deg/s."},
                {"id": "R2", "text": "It shall fly at an altitude of 600 km and take images with a GSD of 2 m, downlinked in X-band."}]
        sel, m = design(CATALOG, reqs)
        s = slots_of(sel)
        mq, rw = s["magnetorquer"].selected, s["reaction_wheel"].selected
        self.assertGreaterEqual(mq.quantity * int(mq.comp.spec("axes") or 1), 3)               # three axes: one board or three rods
        need = rw.comp.spec("momentum_mnms") / 1000.0 * dump_dipole_per_nms(600)
        self.assertGreaterEqual(mq.comp.spec("magnetic_moment_am2"), need)                      # dumps a wheel in one orbit
        self.assertNotEqual(mq.comp.id, "gomspace-nanotorque-gst-600-mk2")                      # 0.4 A m2 is not enough for 100 mN m s wheels
        self.assertTrue(all(c["met"] for c in m["subsystems"]["magnetorquer"]["checks"]))
        if mq.quantity == 3:
            self.assertAlmostEqual(mq.mass_kg, 3 * mq.comp.mass_kg)

    def test_suggested_magnetorquer_covers_three_axes(self):
        _, m = design(CATALOG, V6, {"altitude_km": [641.6, 641.6], "end016": END016})
        x = next(e for e in m["extras"] if e["id"] == "magnetorquer")
        self.assertGreaterEqual(x["best"]["quantity"] * int(BY_ID[x["best"]["id"]].spec("axes") or 1), 3)

    def test_named_part_is_required(self):
        sel, _ = design(CATALOG, [{"id": "R1", "text": "The CubeSat shall carry a star tracker."}])
        self.assertIn("star_tracker", {r.subsystem for r in sel.subsystems})

    def test_star_tracker_accuracy_at_three_sigma(self):
        from star_selector.mission import tracker_accuracy_3sigma_arcsec
        self.assertAlmostEqual(tracker_accuracy_3sigma_arcsec(BY_ID["cubespace-cubestar"]), 216.0)   # 1-sigma roll x 3
        self.assertAlmostEqual(tracker_accuracy_3sigma_arcsec(BY_ID["bct-nst-mid"]), 30.0)           # already 3-sigma
        sel, m = design(CATALOG, [{"id": "R1", "text": "The CubeSat shall carry a star tracker with an attitude knowledge of 55 arcsec; UHF link."}])
        k = slots_of(sel)["star_tracker"].selected
        self.assertLessEqual(tracker_accuracy_3sigma_arcsec(k.comp), 55.0)
        self.assertNotEqual(k.comp.id, "sodern-auriga-oh")                                  # 51 arcsec, but an optical head without electronics
        self.assertEqual(k.quantity, 1)
        self.assertEqual(next(r for r in m["requirements"] if r["what"].startswith("attitude accuracy"))["status"], "met")

    def test_redundant_star_trackers(self):
        sel, _ = design(CATALOG, [{"id": "R1", "text": "The CubeSat shall carry two star trackers for redundancy; UHF link."}])
        k = slots_of(sel)["star_tracker"].selected
        self.assertEqual(k.quantity, 2)
        self.assertAlmostEqual(k.mass_kg, 2 * k.comp.mass_kg)

    def test_suggested_star_tracker_meets_the_pointing(self):
        from star_selector.mission import tracker_accuracy_3sigma_arcsec
        _, m = design(CATALOG, V6, {"altitude_km": [641.6, 641.6], "end016": END016})            # trackers inside the integrated ADCS
        x = next(e for e in m["extras"] if e["id"] == "star_tracker")
        self.assertLessEqual(tracker_accuracy_3sigma_arcsec(BY_ID[x["best"]["id"]]), 360.0)      # 0.1 deg of REQ-008
        self.assertNotIn("star_tracker", m["subsystems"])

    def test_star_tracker_accuracy_no_product_gives(self):
        _, m = design(CATALOG, [{"id": "R1", "text": "The CubeSat shall carry a star tracker with an attitude knowledge of 1 arcsec; UHF link."}])
        self.assertTrue(any("no star tracker in the database" in u for u in m["unmet"]), m["unmet"])


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
        sel, m = design(CATALOG, V6)      # v6: the only camera with GSD <= 4 m is declared for 12U, although REQ-006 says 6U
        self.assertEqual(sel.cubesat.units, 12)
        self.assertEqual(m["stated_class"]["class_u"], 6)
        note = next(n for n in m["notes"] if "REQ-006 states a 6U" in n)
        self.assertIn("follows from the performance", note)
        self.assertIn("declared by the vendor for larger CubeSats only", note)        # why a 6U cannot meet them
        sel, m = design(CATALOG, [{"id": "R1", "text": "Each satellite shall be a 6U CubeSat relaying messages through UHF."}])
        self.assertEqual(sel.cubesat.units, 1)                        # smaller than stated: reported, not imposed
        self.assertTrue(any("R1 states a 6U" in n for n in m["notes"]))

    def test_class_follows_the_performance(self):
        relaxed = [dict(r, text=r["text"].replace("4.0 m", "6.2 m")) if r["id"] == "REQ-009" else r for r in V6]
        sel, m = design(CATALOG, relaxed, {"altitude_km": [641.6, 641.6]})
        self.assertEqual(sel.cubesat.units, 6)                        # a 6U camera gives 6.1 m at 642 km
        self.assertEqual(next(r for r in m["requirements"] if r["what"].startswith("GSD"))["status"], "met")
        sel, _ = design(CATALOG, V6, {"altitude_km": [641.6, 641.6]})
        self.assertEqual(sel.cubesat.units, 12)                       # 4 m needs the 12U camera

    def test_least_launch_mass_in_the_class(self):
        from dataclasses import replace
        from star_selector.fit import check_fit
        from star_selector.mission import select as mission_select
        sel, _ = design(CATALOG, [{"id": "R1", "text": "The CubeSat shall relay messages from ground sensors through a UHF link."}])
        fixed = {r.id: r.selected.comp.id for r in sel.subsystems}
        slots = [Slot(r.id, r.subsystem, r.label) for r in sel.subsystems]
        for r in sel.subsystems:      # no lighter alternative in any slot gives a complete design that fits (least launch mass)
            for k in r.alternatives:
                if k.mass_kg is None or k.mass_kg >= r.selected.mass_kg - 1e-12:
                    continue
                trial = mission_select(CATALOG, sel.cubesat.units, 1.0,
                                       slots=[replace(s, allowed=frozenset({k.comp.id if s.id == r.id else fixed[s.id]})) for s in slots])
                ok = trial.within_limits and all(x.selected for x in trial.subsystems) and check_fit(trial)["state"] in ("fits", "undetermined")
                self.assertFalse(ok and trial.mass_kg < sel.mass_kg - 1e-9, (r.id, k.comp.id))

    def test_user_class_wins(self):
        sel, m = design(CATALOG, V6, forced_class_u=12)
        self.assertEqual(sel.cubesat.units, 12)
        self.assertEqual(m["forced_class_u"], 12)

    def test_user_class_takes_the_closest_component(self):
        sel, m = design(CATALOG, V6, {"altitude_km": [641.6, 641.6]}, forced_class_u=6)
        img = slots_of(sel)["payload_imager"].selected
        self.assertIsNotNone(img)                                      # it used to be left without a camera
        self.assertEqual(img.comp.id, "simera-multiscape100")          # the closest GSD that fits a 6U (6.1 m at 642 km)
        msg = next(u for u in m["unmet"] if "GSD" in u)
        self.assertIn("6U chosen by the user", msg)
        self.assertIn("in a 12U", msg)

    def test_extras_keep_the_design(self):
        sel, m = design(CATALOG, V6, {"altitude_km": [641.6, 641.6], "end016": END016})
        base = {r.id: r.selected.comp.id for r in sel.subsystems if r.selected}
        for x in m["extras"]:
            if x.get("best") and x["fits_with_design"]:
                self.assertTrue(x["best"]["mass_kg"] is None or sel.mass_kg + x["best"]["mass_kg"] <= sel.cubesat.mass_limit_kg + 1e-9, x["id"])
        sel2, _ = design(CATALOG, V6, {"altitude_km": [641.6, 641.6], "end016": END016})
        self.assertEqual(base, {r.id: r.selected.comp.id for r in sel2.subsystems if r.selected})      # repeatable

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
        self.assertEqual(out["cubesat"]["class_u"], 12)
        self.assertTrue(all(s["design"] for s in out["subsystems"]))
        self.assertTrue(out["mission"]["extras"])
        self.assertEqual({s["subsystem"] for s in out["subsystems"]} & {"reaction_wheel", "star_tracker"}, set())


class WheelSizingTest(unittest.TestCase):
    """IF-003-006: ruote al 50% dei picchi di END-003 (wheel_sizing), poi la capacita' piu' piccola (prefer), poi la massa."""
    REQS = [{"id": "REQ-001", "text": "The satellite shall be three-axis stabilised and point at nadir."}]

    def adcs(self, end003, forced=6):
        sel, m = design(CATALOG, self.REQS, {"end003": end003} if end003 else {}, forced_class_u=forced)
        r = next(r for r in sel.subsystems if r.subsystem == "adcs")
        ck = next((x for x in m["requirements"] if x["slot"] == "adcs" and "END-003" in x["what"]), None)
        return r.selected.comp.id, ck, m

    def test_without_end003_todays_rule(self):
        cid, ck, m = self.adcs(None)
        self.assertEqual(cid, "bct-xact-50")      # declared for 6U, the lightest
        self.assertIsNone(ck)
        self.assertIsNone(m["wheel_sizing"])

    def test_smallest_capacity_that_meets_twice_the_need(self):
        # 6U units declared for the class: XACT-50 (50 mN m s, 6 mN m, 1.23 kg), iADCS400 (15 mN m s, 2 mN m, 1.7 kg)
        cid, ck, m = self.adcs({"peak_momentum_nms": 1e-3, "peak_torque_nm": 1e-4})
        self.assertEqual(cid, "hyperion-iadcs400")
        self.assertEqual(ck["status"], "met")
        ws = m["wheel_sizing"]
        self.assertAlmostEqual(ws["momentum_ratio"], 15.0)
        self.assertAlmostEqual(ws["torque_ratio"], 20.0)
        self.assertEqual(ws["design_factor"], 2.0)

    def test_momentum_at_fifty_percent(self):
        # 2 x 10 mN m s > 15: the iADCS400 is out
        self.assertEqual(self.adcs({"peak_momentum_nms": 1e-2, "peak_torque_nm": 1e-4})[0], "bct-xact-50")
        # 2 x 7.5 = 15: exactly at 50 %, still in
        self.assertEqual(self.adcs({"peak_momentum_nms": 7.5e-3, "peak_torque_nm": 1e-4})[0], "hyperion-iadcs400")

    def test_torque_at_fifty_percent(self):
        self.assertEqual(self.adcs({"peak_momentum_nms": 1e-3, "peak_torque_nm": 1.5e-3})[0], "bct-xact-50")

    def test_declared_class_rule_still_applies(self):
        # MAI-200 (10.8 mN m s, no declared class) is smaller but the class has its own units
        self.assertNotEqual(self.adcs({"peak_momentum_nms": 1e-3, "peak_torque_nm": 1e-4})[0], "pumpkin-mai-200")

    def test_need_no_unit_meets(self):
        cid, ck, m = self.adcs({"peak_momentum_nms": 1.0, "peak_torque_nm": 1e-4})
        self.assertEqual(ck["status"], "not_met")
        self.assertTrue(any("END-003" in u for u in m["unmet"]))

    def test_need_drives_the_class(self):
        # the 1U XACT-15 (5 mN m) cannot give 2 x 3 mN m: a larger class
        self.assertEqual(design(CATALOG, self.REQS, {})[0].cubesat.units, 1)
        sel, m = design(CATALOG, self.REQS, {"end003": {"peak_momentum_nms": 1e-3, "peak_torque_nm": 3e-3}})
        self.assertGreater(sel.cubesat.units, 1)
        self.assertGreaterEqual(m["wheel_sizing"]["torque_ratio"], 2.0)

    def test_slew_momentum_with_the_inertia_end003_used(self):
        reqs = self.REQS + [{"id": "REQ-002", "text": "The satellite shall slew at 1 deg/s."}]
        a = analyse(reqs, {"end003": {"peak_momentum_nms": 1e-4, "peak_torque_nm": 1e-5, "inertia_max_kgm2": 0.1}})
        ck = next(c for nd in a["needs"] for c in nd.checks if c.key == "wheel_sizing")
        self.assertAlmostEqual(a["wheel_sizing"]["need_momentum_nms"], 0.1 * math.radians(1.0))
        self.assertEqual(ck.req.id, "REQ-002")

    def test_separate_wheels_carry_the_check(self):
        reqs = self.REQS + [{"id": "REQ-002", "text": "The satellite shall carry reaction wheels."}]
        a = analyse(reqs, {"end003": {"peak_momentum_nms": 1e-4, "peak_torque_nm": 1e-5}})
        self.assertEqual(a["wheel_sizing"]["slot"], "reaction_wheel")
        self.assertEqual([nd.slot.id for nd in a["needs"] if any(c.key == "wheel_sizing" for c in nd.checks)], ["reaction_wheel"])


class BatteryHeaterTest(unittest.TestCase):
    """IF-019-006 (phase F4): battery heater >= 1.25 x the END-019 cold-case peak, integrated in the battery if it is enough,
    otherwise the lightest catalogued film heater (power V^2 / R at the lowest battery voltage)."""
    REQS = [{"id": "REQ-001", "text": "The satellite shall be three-axis stabilised and point at nadir."}]

    @staticmethod
    def e19(peak, mean=None, hot=8.6, cold=-36.8):
        return {"needed_peak_w": peak, "needed_mean_w_cold": mean if mean is not None else peak / 2, "setpoint_c": 5.0, "battery_min_c": cold,
                "battery_max_c": hot, "limit_min_c": 0.0, "limit_max_c": 45.0, "heater_in_design_w": 0.0, "source": "test"}

    @staticmethod
    def holding(battery_id):
        """A design whose battery is the given pack (only what battery_heater reads)."""
        from types import SimpleNamespace as NS
        return NS(subsystems=[NS(id="battery", subsystem="battery", selected=NS(comp=BY_ID[battery_id]))])

    def test_catalogue_heaters_from_the_datasheet(self):
        heaters = [c for c in CATALOG if c.category == "heater"]
        self.assertGreaterEqual(len(heaters), 2)
        h = BY_ID["minco-hk6911"]
        self.assertEqual((h.spec("resistance_ohm"), h.spec("rated_power_w"), h.spec("rated_voltage_v")), (22.1, 36, 28))
        self.assertAlmostEqual(h.mass_kg, 0.04 * 5.08 * 5.08 / 1000.0, places=6)      # areal density x heated area
        self.assertEqual(BY_ID["gomspace-bpx-100wh-16v"].spec("integrated_heater_w"), 6.0)
        self.assertIsNone(BY_ID["aac-optimus-30"].spec("integrated_heater_w"))          # declared, power not published

    def test_without_end019_no_heater(self):
        _, m = design(CATALOG, self.REQS, {}, forced_class_u=6)
        self.assertIsNone(m["battery_heater"])

    def test_integrated_heater_when_it_is_enough(self):
        h = battery_heater(CATALOG, self.holding("gomspace-bpx-100wh-16v"), self.e19(4.0))       # 1.25 x 4 = 5 W <= 6 W
        self.assertEqual((h["source"], h["component"], h["power_w"], h["mass_kg"], h["status"]), ("integrated", "gomspace-bpx-100wh-16v", 6.0, 0.0, "met"))
        self.assertTrue(h["temperature_check"]["met"])
        self.assertAlmostEqual(h["duty_cold"], 2.0 / 6.0)

    def test_lightest_separate_heater_at_the_lowest_battery_voltage(self):
        # 1.25 x 5 = 6.25 W > 6 W integrated; at 11.8 V: HK6911 6.30 W (1.03 g), HK6905 7.21 W (1.29 g), HK6912 9.47 W (1.55 g)
        h = battery_heater(CATALOG, self.holding("gomspace-bpx-100wh-16v"), self.e19(5.0))
        self.assertEqual((h["source"], h["component"], h["bus_voltage_v"]), ("separate", "minco-hk6911", 11.8))
        self.assertAlmostEqual(h["power_w"], 11.8 ** 2 / 22.1)
        self.assertGreaterEqual(h["power_w"], 1.25 * 5.0)
        lighter = [c for c in CATALOG if c.category == "heater" and c.mass_kg < h["mass_kg"] and 11.8 ** 2 / c.spec("resistance_ohm") >= 6.25]
        self.assertEqual(lighter, [])

    def test_no_heater_meets_the_need(self):
        h = battery_heater(CATALOG, self.holding("aac-optimus-30"), self.e19(21.3, 12.3))
        self.assertEqual((h["status"], h["component"], h["bus_voltage_v"]), ("not_met", None, 6.2))
        self.assertIn("no catalogued heater gives 26.62 W", h["why"])
        self.assertFalse(h["temperature_check"]["met"])

    def test_no_heater_needed_and_hot_violation(self):
        h = battery_heater(CATALOG, self.holding("aac-optimus-30"), self.e19(0.0, hot=10.0, cold=3.0))
        self.assertEqual((h["status"], h["component"]), ("not_needed", None))
        self.assertTrue(h["temperature_check"]["met"])
        h = battery_heater(CATALOG, self.holding("aac-optimus-30"), self.e19(0.0, hot=50.0, cold=3.0))
        self.assertFalse(h["temperature_check"]["met"])           # no cooling option: the hot violation is reported

    def test_design_adds_the_heater_mass_and_power(self):
        svc = SelectorService()
        base = svc.design({"requirements": self.REQS, "form_factor_u": 6})
        out = svc.design({"requirements": self.REQS, "form_factor_u": 6, "context": {"end019": self.e19(0.2)}})
        h = out["mission"]["battery_heater"]
        self.assertEqual(h["status"], "met")
        self.assertGreaterEqual(h["power_w"], 0.25 - 1e-9)
        self.assertEqual(out["breakdown"]["power_w"]["battery_heater"], h["power_w"])
        if h["source"] == "separate":
            self.assertAlmostEqual(out["totals"]["mass_kg"], base["totals"]["mass_kg"] + h["mass_kg"])
        row = next(r for r in out["mission"]["subsystems"][h["slot"]]["checks"] if r["what"].startswith("battery heater"))
        self.assertTrue(row["met"])


if __name__ == "__main__":
    unittest.main()

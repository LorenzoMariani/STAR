import time
import unittest
from pathlib import Path

from star_selector.api import SelectorService
from star_selector.models import CATEGORIES, SPEC_FIELDS, Component, load_catalog
from star_selector.rows import completeness, declared_power_w, rows_for, subsystem_of, volume_m3
from star_selector.selector import CLASSES, SUBSYSTEMS, fits_envelope, select

CATALOG = Path(__file__).resolve().parent.parent / "data" / "catalog.json"
SERVICE = SelectorService()
CAT = {c.id: c for c in SERVICE.catalog}


def synthetic(cid, category, mass, dims=None, **specs):
    """Componente minimo per provare le regole di selezione con numeri noti."""
    base = {k: None for k in SPEC_FIELDS[category]}
    base.update(specs)
    raw = {"id": cid, "category": category, "vendor": "Test", "name": cid, "mass_kg": mass, "power_w": None, "specs": base,
           "source": {"url": "https://example.org", "document": "test", "retrieved": "2026-01-01", "verified": False}}
    if dims:
        raw["dimensions"] = {"mm": dims, "basis": "declared", "note": ""}
    return Component(raw)


def user_document(c):
    """Fonte = PDF fornito dall'utente senza URL pubblico (source.url null, source.origin): la copia in datasheets/ e' la prova."""
    src = c.raw["source"]
    return src["url"] is None and bool(src.get("origin")) and bool(c.raw.get("datasheet"))


def structure_1u():
    return synthetic("s", "structure", 0.1, [100, 100, 113.5], form_factor_u=1.0, max_total_mass_kg=2.0)


class TestCatalog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cat = load_catalog(CATALOG)

    def test_catalog_is_valid_and_has_427_components_in_all_categories(self):
        self.assertEqual(len(self.cat), 427)
        by_cat = {}
        for c in self.cat:
            by_cat[c.category] = by_cat.get(c.category, 0) + 1
        self.assertEqual(set(by_cat), set(CATEGORIES))
        self.assertEqual({k: by_cat[k] for k in ("structure", "magnetorquer", "reaction_wheel", "propulsion", "antenna", "gps")},
                         {"structure": 20, "magnetorquer": 9, "reaction_wheel": 66, "propulsion": 34, "antenna": 32, "gps": 7})

    def test_every_component_has_a_source_and_none_is_marked_verified_without_a_person(self):
        for c in self.cat:
            self.assertTrue(user_document(c) or c.raw["source"]["url"].startswith("https://"), c.id)
            self.assertTrue(c.raw["source"]["document"], c.id)
            self.assertFalse(c.verified, c.id)

    def test_every_declared_image_exists_has_a_source_and_a_vendor_component_name(self):
        root = CATALOG.parent.parent
        names = set()
        for c in self.cat:
            img = c.raw.get("image")
            if not img:
                continue
            path = root / img["file"]
            self.assertTrue(path.is_file(), c.id)
            self.assertRegex(path.name, r"^[A-Za-z0-9]+-[A-Za-z0-9.\-]+\.(png|jpg)$", c.id)
            web = ("https://",) if not user_document(c) else (c.raw["datasheet"]["file"],)      # foto dal PDF fornito dall'utente
            self.assertTrue(img["image_url"].startswith(web), c.id)
            self.assertTrue(img["page_url"].startswith(web), c.id)
            names.add(path.name)
        self.assertGreaterEqual(len(names), 150)

    def test_png_metadata_carries_the_source(self):
        from PIL import Image

        c = CAT["simera-triscape50"]
        with Image.open(CATALOG.parent.parent / c.raw["image"]["file"]) as im:
            self.assertEqual(im.text["Source"], c.raw["image"]["image_url"])
            self.assertIn(c.raw["image"]["page_url"], im.text["Description"])

    def test_manifest_lists_every_image_with_a_source(self):
        import csv

        with (CATALOG.parent.parent / "images" / "manifest.csv").open(encoding="utf-8-sig") as f:
            rows = {r["id_componente"]: r for r in csv.DictReader(f)}
        for c in self.cat:
            img = c.raw.get("image")
            if img:
                self.assertIn(c.id, rows, c.id)
                self.assertEqual(rows[c.id]["file"], Path(img["file"]).name, c.id)
                self.assertTrue(rows[c.id]["fonte_immagine"].startswith(c.raw["datasheet"]["file"] if user_document(c) else "https://"), c.id)

    def test_no_value_is_filled_with_a_default(self):
        self.assertIsNone(CAT["gomspace-nanopower-p60"].raw.get("power_w"))
        self.assertIsNone(CAT["endurosat-x-band-2x2"].spec("gain_dbi"))      # valori in contraddizione nella scheda del fornitore
        self.assertIsNone(CAT["l3harris-mps-120-1u"].spec("isp_s"))
        self.assertIsNone(CAT["bct-rwp015"].raw.get("dimensions"))


class TestCubeSatClasses(unittest.TestCase):
    def test_limits_follow_the_cubesat_design_specification(self):
        self.assertEqual({u: c.mass_limit_kg for u, c in CLASSES.items()}, {1: 2.0, 3: 6.0, 6: 12.0, 12: 24.0})
        self.assertEqual(CLASSES[1].envelope_mm, (100.0, 100.0, 113.5))
        self.assertEqual(CLASSES[3].envelope_mm, (100.0, 100.0, 340.5))
        self.assertEqual(CLASSES[6].envelope_mm, (100.0, 226.3, 366.0))
        self.assertEqual(CLASSES[12].envelope_mm, (226.3, 226.3, 366.0))

    def test_volume_limit_is_the_envelope_volume_in_cubic_metres(self):
        self.assertAlmostEqual(CLASSES[1].volume_limit_m3, 0.1 * 0.1 * 0.1135)
        self.assertAlmostEqual(CLASSES[3].volume_limit_m3, 0.1 * 0.1 * 0.3405)
        self.assertAlmostEqual(CLASSES[6].volume_limit_m3, 0.1 * 0.2263 * 0.366)
        self.assertAlmostEqual(CLASSES[12].volume_limit_m3, 0.2263 * 0.2263 * 0.366)

    def test_unsupported_class_is_rejected(self):
        with self.assertRaises(ValueError):
            select(SERVICE.catalog, 2)


class TestRows(unittest.TestCase):
    def test_a_missing_value_is_none_never_a_default(self):
        rows = {r["key"]: r for r in rows_for(CAT["endurosat-eps-i"])}
        self.assertEqual(rows["mass_kg"]["value"], "0.208")
        self.assertIsNone(rows["size"]["value"])          # EnduroSat non pubblica le quote
        self.assertIsNone(rows["volume_m3"]["value"])
        self.assertIsNone(rows["output_power_w_max"]["value"])
        self.assertEqual(rows["integrated_battery_wh"]["value"], "10.2")

    def test_volume_is_the_product_of_the_three_published_sizes(self):
        c = CAT["gomspace-nanomind-a3200"]            # 65 x 40 x 7.1 mm
        self.assertAlmostEqual(volume_m3(c), 65 * 40 * 7.1 * 1e-9)
        self.assertIsNone(volume_m3(CAT["gomspace-nanocom-ant430"]))   # altezza non dichiarata

    def test_volume_is_written_in_cubic_metres(self):
        rows = {r["key"]: r for r in rows_for(CAT["gomspace-nanomind-a3200"])}
        self.assertEqual(rows["volume_m3"]["unit"], "m³")
        self.assertEqual(rows["volume_m3"]["value"], "1.846×10⁻⁵")

    def test_completeness_counts_only_published_core_data(self):
        self.assertEqual(completeness(CAT["gomspace-nanomind-a3200"]), 1.0)
        self.assertTrue(0.0 < completeness(CAT["endurosat-eps-i"]) < 0.7)
        for c in SERVICE.catalog:
            self.assertTrue(0.0 <= completeness(c) <= 1.0, c.id)

    def test_declared_power_uses_the_maximum_published_value(self):
        self.assertEqual(declared_power_w(CAT["gomspace-nanocom-ax100"]), 2.64)       # trasmissione
        self.assertEqual(declared_power_w(CAT["vacco-mips-1u"]), 10.0)                # in spinta
        self.assertIsNone(declared_power_w(CAT["cubespace-cubetorquer-cr0012"]))      # non pubblicata
        self.assertEqual(declared_power_w(CAT["cubespace-cubewheel-cw0057"]), 2.7)    # picco

    def test_every_component_belongs_to_one_subsystem(self):
        ids = {sid for sid, _, _ in SUBSYSTEMS} | {"heater"}      # battery heaters: chosen by mission.battery_heater, not by the search
        for c in SERVICE.catalog:
            self.assertIn(subsystem_of(c), ids, c.id)


class TestSelection(unittest.TestCase):
    def test_one_card_per_subsystem_for_every_class(self):
        for u in CLASSES:
            res = SERVICE.select({"form_factor_u": u})
            self.assertEqual([s["id"] for s in res["subsystems"]], [sid for sid, _, _ in SUBSYSTEMS])
            self.assertEqual(res["cubesat"]["class_u"], u)

    def test_selected_components_fit_the_class_on_their_own(self):
        for u, cls in CLASSES.items():
            for s in SERVICE.select({"form_factor_u": u})["subsystems"]:
                if not s["selected"]:
                    continue
                c = CAT[s["selected"]["id"]]
                self.assertLessEqual(c.mass_kg, cls.mass_limit_kg, (u, c.id))
                self.assertTrue(fits_envelope(c, cls.envelope_mm), (u, c.id))
                if s["id"] == "structure":
                    self.assertEqual(c.spec("form_factor_u"), u)

    def test_the_selection_of_a_6u_respects_mass_and_volume(self):
        res = SERVICE.select({"form_factor_u": 6})
        t = res["totals"]
        self.assertTrue(res["within_limits"])
        self.assertLessEqual(t["mass_kg"], 12.0)
        self.assertLessEqual(t["volume_m3"], CLASSES[6].volume_limit_m3)
        self.assertEqual(t["n_covered"], t["n_subsystems"])
        self.assertAlmostEqual(t["mass_kg"], sum(s["selected"]["mass_kg"] for s in res["subsystems"] if s["selected"]))
        self.assertAlmostEqual(t["volume_m3"], sum(s["selected"]["volume_m3"] or 0.0 for s in res["subsystems"] if s["selected"]))

    def test_the_most_completely_documented_component_is_preferred(self):
        res = SERVICE.select({"form_factor_u": 12})   # limiti non vincolanti: vince la completezza
        self.assertTrue(res["within_limits"])
        for s in res["subsystems"]:
            if s["selected"]:
                self.assertTrue(all(s["selected"]["completeness"] >= a["completeness"] - 1e-9 for a in s["alternatives"]), s["id"])

    def test_counts_in_the_database_and_fitting(self):
        by = {s["id"]: s for s in SERVICE.select({"form_factor_u": 6})["subsystems"]}
        self.assertEqual(by["eps"]["n_database"], 47)
        self.assertEqual(by["propulsion"]["n_database"], 34)
        self.assertEqual(by["payload_imager"]["n_database"] + by["payload_optical"]["n_database"], 47)
        for s in by.values():
            self.assertLessEqual(s["n_fit"], s["n_database"], s["id"])
            self.assertEqual(s["n_fit"], (1 if s["selected"] else 0) + len(s["alternatives"]), s["id"])

    def test_a_1u_shows_a_magnetorquer_and_all_subsystems_do_not_fit_together(self):
        res = SERVICE.select({"form_factor_u": 1})
        by = {s["id"]: s for s in res["subsystems"]}
        self.assertEqual(CAT[by["magnetorquer"]["selected"]["id"]].category, "magnetorquer")
        self.assertEqual(CAT[by["structure"]["selected"]["id"]].spec("form_factor_u"), 1)
        self.assertFalse(res["within_limits"])
        self.assertTrue(any("do not fit" in m for m in res["messages"]))
        self.assertGreater(res["totals"]["mass_kg"], 2.0)

    def test_a_3u_solar_panel_does_not_fit_a_1u_but_the_1u_panels_do(self):
        by = {s["id"]: s for s in SERVICE.select({"form_factor_u": 1})["subsystems"]}
        sp = by["solar_panel"]
        self.assertEqual(sp["selected"]["id"], "isis-solar-1u")            # l'unico 1U con massa pubblicata; gli altri tre (EnduroSat 1U, DHV-1U-XY e -Z) ne sono privi
        self.assertEqual((sp["n_fit"], sp["n_fit_without_mass"]), (4, 3))       # + 2NDSpace CORE-01 and CORE-01Z, Spacemanic RA (import 2026-10-23)
        self.assertNotIn("isis-solar-3u", [sp["selected"]["id"]] + [a["id"] for a in sp["alternatives"]])
        self.assertIsNotNone({s["id"]: s for s in SERVICE.select({"form_factor_u": 3})["subsystems"]}["solar_panel"]["selected"])

    def test_the_1u_panels_come_from_vendor_documents_and_nothing_is_estimated(self):
        for cid, mass, power in (("isis-solar-1u", 0.05, 2.3), ("endurosat-solar-1u", None, 2.4), ("dhv-1u-xy", None, 2.47), ("dhv-1u-z", None, 2.47)):
            c = CAT[cid]
            self.assertEqual((c.mass_kg, c.spec("peak_power_w")), (mass, power), cid)
            self.assertTrue(c.raw["datasheet"]["file"] and c.raw["image"]["file"], cid)
        self.assertEqual(CAT["dhv-1u-xy"].dimensions_mm, [82.8, 97.8, None])      # lo spessore non e' pubblicato: resta null
        self.assertEqual(CAT["dhv-1u-z"].dimensions_mm, [97.8, 97.8, None])
        self.assertIsNone(CAT["endurosat-solar-1u"].dimensions_mm)

    def test_a_component_without_published_mass_is_never_chosen_when_another_exists(self):
        for u in CLASSES:
            for s in SERVICE.select({"form_factor_u": u})["subsystems"]:
                if s["selected"]:
                    self.assertIsNotNone(s["selected"]["mass_kg"], (u, s["id"]))

    def test_published_values_are_reported_as_they_are(self):
        for s in SERVICE.select({"form_factor_u": 6})["subsystems"]:
            k = s["selected"]
            if not k:
                continue
            c = CAT[k["id"]]
            self.assertEqual(k["mass_kg"], c.mass_kg)
            self.assertEqual(k["power_w_declared"], declared_power_w(c))
            rows = {r["key"]: r["value"] for r in k["rows"]}
            self.assertEqual(rows["size"] is None, volume_m3(c) is None, c.id)

    def test_the_search_is_fast(self):
        t0 = time.time()
        for u in CLASSES:
            SERVICE.select({"form_factor_u": u})
        self.assertLess(time.time() - t0, 6.0)


class TestBudgetSearch(unittest.TestCase):
    """Con un catalogo sintetico: quando il miglior componente di ogni sottosistema non entra nei limiti, si cerca la combinazione completa che ci entra."""

    def test_the_exact_search_replaces_a_greedy_choice_that_exceeds_the_mass(self):
        heavy = synthetic("obc-heavy", "obc", 1.8, [60, 60, 10], data_interfaces=["I2C"], supply_voltage_ranges_v=[[3, 5]])
        heavy.raw["power_w"] = 1.0
        light = synthetic("obc-light", "obc", 0.05, [60, 60, 10], data_interfaces=["I2C"])
        eps = synthetic("eps", "eps", 0.2, [90, 90, 15], pv_channels=2, output_power_w_max=50.0, integrated_battery_wh=10.0, data_interfaces=["I2C"])
        res = select([structure_1u(), heavy, light, eps], 1)
        chosen = {r.id: r.selected.comp.id for r in res.subsystems if r.selected}
        self.assertTrue(res.within_limits)
        self.assertEqual(chosen["obc"], "obc-light")
        self.assertLessEqual(res.mass_kg, 2.0)

    def test_when_the_greedy_choice_fits_it_is_kept(self):
        a = synthetic("obc-a", "obc", 0.3, [60, 60, 10], data_interfaces=["I2C"], supply_voltage_ranges_v=[[3, 5]])
        a.raw["power_w"] = 1.0
        b = synthetic("obc-b", "obc", 0.05, [60, 60, 10], data_interfaces=["I2C"])
        res = select([structure_1u(), a, b], 1)
        self.assertEqual({r.id: r.selected.comp.id for r in res.subsystems if r.selected}["obc"], "obc-a")

    def test_unknown_mass_is_used_only_if_nothing_else_exists(self):
        known = synthetic("obc-known", "obc", 0.05, None)
        unknown = synthetic("obc-unknown", "obc", None, [60, 60, 10], data_interfaces=["I2C"], supply_voltage_ranges_v=[[3, 5]])
        res = select([structure_1u(), known, unknown], 1)
        self.assertEqual({r.id: r.selected.comp.id for r in res.subsystems if r.selected}["obc"], "obc-known")
        res = select([structure_1u(), unknown], 1)
        sub = {r.id: r for r in res.subsystems}["obc"]
        self.assertEqual(sub.selected.comp.id, "obc-unknown")
        self.assertIn("without a published mass", sub.note)
        self.assertIn("obc-unknown", res.mass_unknown)

    def test_mass_objective_takes_the_lightest_complete_selection(self):
        a = synthetic("obc-a", "obc", 0.3, [60, 60, 10], data_interfaces=["I2C"], supply_voltage_ranges_v=[[3, 5]])
        a.raw["power_w"] = 1.0
        b = synthetic("obc-b", "obc", 0.05, [60, 60, 10], data_interfaces=["I2C"])
        res = select([structure_1u(), a, b], 1, objective="mass")      # the default keeps obc-a (more published data)
        self.assertEqual({r.id: r.selected.comp.id for r in res.subsystems if r.selected}["obc"], "obc-b")
        with self.assertRaises(ValueError):
            select([structure_1u(), a], 1, objective="cost")

    def test_mass_objective_on_the_catalogue_is_never_heavier(self):
        cat = load_catalog(CATALOG)
        flags = dict(electric_power_check=True, interface_check=True, power_supply_check=True)
        for u in (3, 6, 12):
            by_data = select(cat, u, 5.0, **flags)
            by_mass = select(cat, u, 5.0, objective="mass", **flags)
            self.assertTrue(by_mass.within_limits and not by_mass.truncated, u)
            self.assertLessEqual(by_mass.mass_kg, by_data.mass_kg + 1e-9, u)

    def test_require_all_skips_a_class_with_an_empty_slot(self):
        from star_selector.selector import Slot
        obc = synthetic("obc-a", "obc", 0.05, [60, 60, 10])
        res = select([structure_1u(), obc], 1, slots=[Slot("structure", "structure", "STRUCTURE"), Slot("obc", "obc", "OBC"),
                                                         Slot("eps", "eps", "EPS")], require_all=True)
        self.assertFalse(res.within_limits)
        self.assertIsNone({r.id: r for r in res.subsystems}["eps"].selected)

    def test_components_larger_than_the_envelope_are_not_candidates(self):
        big = synthetic("obc-big", "obc", 0.1, [200, 100, 100], data_interfaces=["I2C"])
        small = synthetic("obc-small", "obc", 0.1, [60, 60, 10])
        res = select([structure_1u(), big, small], 1)
        sub = {r.id: r for r in res.subsystems}["obc"]
        self.assertEqual((sub.n_database, sub.n_fit, sub.selected.comp.id), (2, 1, "obc-small"))
        self.assertTrue(fits_envelope(big, CLASSES[3].envelope_mm))      # entra in un 3U, ruotato


if __name__ == "__main__":
    unittest.main()


class TestStructureFit(unittest.TestCase):
    """La pila dei componenti interni usa le quote della struttura scelta (2026-10-16): un 6U lungo 340.5 mm porta meno di uno lungo 366 mm."""

    def test_a_long_stack_picks_the_longer_structure(self):
        from star_selector.selector import structure_envelope
        short = synthetic("s-short", "structure", 0.5, [100, 226.3, 340.5], form_factor_u=6, max_total_mass_kg=12.0)
        long_ = synthetic("s-long", "structure", 0.9, [100, 226.3, 366.0], form_factor_u=6, max_total_mass_kg=12.0)
        # quattro blocchi alti 180 mm: in una colonna da 366 mm ne stanno due, in una da 340.5 uno solo (6U: due colonne)
        parts = [synthetic(f"b-{cat}", cat, 0.3, [90, 90, 180]) for cat in ("obc", "eps", "battery", "adcs")]
        res = select([short, long_, *parts], 6)
        self.assertTrue(res.within_limits)
        self.assertEqual(next(r for r in res.subsystems if r.id == "structure").selected.comp.id, "s-long")
        self.assertEqual(structure_envelope(long_, CLASSES[6]), (100.0, 226.3, 366.0))
        res = select([short, *parts], 6)               # only the short one: the stack does not fit
        self.assertFalse(res.within_limits)

    def test_the_lighter_structure_when_the_stack_fits_both(self):
        short = synthetic("s-short", "structure", 0.5, [100, 226.3, 340.5], form_factor_u=6, max_total_mass_kg=12.0)
        long_ = synthetic("s-long", "structure", 0.9, [100, 226.3, 366.0], form_factor_u=6, max_total_mass_kg=12.0)
        parts = [synthetic(f"b-{cat}", cat, 0.3, [90, 90, 100]) for cat in ("obc", "eps", "battery", "adcs")]
        res = select([short, long_, *parts], 6)
        self.assertEqual(next(r for r in res.subsystems if r.id == "structure").selected.comp.id, "s-short")

    def test_the_panel_mounts_on_a_face_of_the_structure(self):
        from star_selector.selector import panel_on_structure
        self.assertTrue(panel_on_structure(CAT["spacemind-sp6x"], CAT["gomspace-nanostruct-12u"] if "gomspace-nanostruct-12u" in CAT
                                           else next(c for c in SERVICE.catalog if c.category == "structure" and c.spec("form_factor_u") == 12)))
        three_u = next(c for c in SERVICE.catalog if c.category == "structure" and c.spec("form_factor_u") == 3 and c.spec("panel_faces"))
        self.assertFalse(panel_on_structure(CAT["spacemind-sp6x"], three_u))       # a 6U panel on a 3U structure

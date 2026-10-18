import copy
import unittest
from pathlib import Path

from star_selector.api import SelectorService
from star_selector.models import DIMENSION_BASES, load_catalog, validate_component

CATALOG = Path(__file__).resolve().parent.parent / "data" / "catalog.json"
CAT = {c.id: c for c in load_catalog(CATALOG)}


class TestDimensions(unittest.TestCase):
    def test_coverage_and_schema(self):
        with_dims = [c for c in CAT.values() if c.raw.get("dimensions")]
        self.assertGreaterEqual(len(with_dims), 100)
        for c in with_dims:
            d = c.raw["dimensions"]
            self.assertIn(d["basis"], DIMENSION_BASES, c.id)
            self.assertEqual(len(d["mm"]), 3, c.id)
            self.assertTrue(d["note"], c.id)                         # every value says where it comes from
        by_category = {}
        for c in CAT.values():
            by_category.setdefault(c.category, [0, 0])[0 if c.raw.get("dimensions") else 1] += 1
        self.assertEqual(by_category["structure"][1], 0)             # all structures have an envelope
        self.assertEqual(by_category["star_tracker"][1], 0)
        self.assertEqual(by_category["battery"][1], 0)

    def test_validation_rejects_bad_dimensions(self):
        raw = copy.deepcopy(CAT["gomspace-nanopower-p60"].raw)
        self.assertEqual(validate_component(raw), [])
        for bad in ({"mm": [92, 88.9], "basis": "declared"}, {"mm": [92, -1, 5], "basis": "declared"}, {"mm": [None, None, None], "basis": "declared"},
                    {"mm": [92, 88.9, 19.9], "basis": "guessed"}):
            raw["dimensions"] = bad
            self.assertTrue(any("dimensions" in e for e in validate_component(raw)), bad)
        raw["dimensions"] = {"mm": [95.89, 90.17, None], "basis": "standard"}   # unknown height is allowed
        self.assertEqual(validate_component(raw), [])

    def test_values_copied_from_vendor_documents(self):
        spot = {"gomspace-nanopower-p60": [92, 88.9, 19.9], "gomspace-nanopower-p80": [95, 95, 38.8], "aac-optimus-40": [95.89, 90.17, 27.35],
                "dragonfly-gecko": [65, 90, 105], "dragonfly-caiman-rgb": [100, 100, 250], "rocketlab-st16rt2": [62, 56, 38], "hyperion-st200": [29, 29, 38.1],
                "tesat-scot30": [230, 280, 200], "aac-cubecat": [96, 96, 96], "endurosat-structure-6u": [100, 226.3, 366], "aac-starbuck-nano": [95.89, 90.17, 16.2]}
        for cid, mm in spot.items():
            self.assertEqual(CAT[cid].raw["dimensions"]["mm"], mm, cid)
        self.assertAlmostEqual(CAT["bct-battery-2p8s"].raw["dimensions"]["mm"][1], 7.2 * 25.4, places=1)

    def test_families_that_share_a_housing_share_the_size(self):
        for fam in (("dragonfly-gecko", "dragonfly-gecko-wide"), ("dragonfly-chameleon-rgb", "dragonfly-chameleon-ms", "dragonfly-chameleon-hs"),
                    ("dragonfly-mantis-rgb", "dragonfly-mantis-ms", "dragonfly-mantis-hs"), ("simera-triscape100", "simera-multiscape100", "simera-hyperscape100")):
            self.assertEqual(len({tuple(CAT[i].raw["dimensions"]["mm"]) for i in fam}), 1, fam)

    def test_declared_sizes_are_physically_plausible_for_the_declared_mass(self):
        """Mass divided by the box volume: a typo in a dimension shows up as an impossible density (0.2-3.5 g/cm3 covers boards, cameras and ADCS)."""
        for c in CAT.values():
            d = c.raw.get("dimensions")
            if not d or c.category in ("structure", "solar_panel", "antenna") or None in d["mm"] or not c.mass_kg:   # pannelli e patch: lastre sottili senza connettore
                continue
            a, b, h = d["mm"]
            density = c.mass_kg * 1000 / (a * b * h / 1000)
            top = 6.0 if c.category in ("reaction_wheel", "magnetorquer") else 3.5   # volano e nucleo delle barre sono di metallo
            low = 0.15 if c.category == "star_tracker" else 0.2      # i baffle sono quasi vuoti: la scatola che li racchiude e' molto piu' grande della massa
            self.assertTrue(low <= density <= top, (c.id, density))

    def test_standard_basis_is_only_used_for_published_formats(self):
        for c in CAT.values():
            d = c.raw.get("dimensions")
            if d and d["basis"] == "standard":
                self.assertTrue(c.id.startswith(("pumpkin", "nanoavionics", "alenspace")), c.id)
                self.assertIn("PC/104" if "PC/104" in d["note"] or "PC104" in d["note"] else "CDS", d["note"].replace("PC104", "PC/104") if "PC104" in d["note"] else d["note"])

    def test_dimensions_reach_the_api(self):
        rec = SelectorService().component("aac-kryten-m3", with_image=False)
        self.assertEqual(rec["dimensions"]["mm"], [95.89, 90.17, 5.51])
        self.assertIsNone(SelectorService().component("endurosat-eps-i", with_image=False)["dimensions"])


if __name__ == "__main__":
    unittest.main()

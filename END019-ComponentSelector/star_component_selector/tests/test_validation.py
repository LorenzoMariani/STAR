"""Validazione del selettore: confronto con una ricerca esaustiva indipendente su cataloghi casuali e invarianti sul catalogo reale."""
import itertools
import random
import unittest

from star_selector.api import SelectorService
from star_selector.models import SPEC_FIELDS, Component
from star_selector.rows import completeness, declared_power_w, subsystem_of, volume_m3
from star_selector import layout
from star_selector.selector import CLASSES, EXTERNAL_SUBSYSTEMS, SUBSYSTEMS, _admissible, fits_envelope, select

SERVICE = SelectorService()
CATALOG = SERVICE.catalog
EPS = 1e-9


def make(cid, category, mass, dims, rng):
    """Componente sintetico: ogni specifica ha una probabilita' casuale di essere non pubblicata."""
    specs = {k: None for k in SPEC_FIELDS[category]}
    for k in ("data_interfaces", "supply_voltage_ranges_v", "pv_channels", "capacity_wh", "band", "pointing_accuracy_deg", "output_power_w_max"):
        if k in specs and rng.random() < 0.6:
            specs[k] = {"data_interfaces": ["I2C"], "supply_voltage_ranges_v": [[3.0, 5.0]], "pv_channels": 2, "capacity_wh": 10.0, "band": ["UHF"],
                        "pointing_accuracy_deg": 1.0, "output_power_w_max": 20.0}[k]
    raw = {"id": cid, "category": category, "vendor": "Test", "name": cid, "mass_kg": mass, "power_w": None, "specs": specs,
           "source": {"url": "https://example.org", "document": "test", "retrieved": "2026-01-01", "verified": False}}
    if dims:
        raw["dimensions"] = {"mm": dims, "basis": "declared", "note": ""}
    return Component(raw)


def random_catalog(seed, units):
    rng = random.Random(seed)
    cls = CLASSES[units]
    struct = make("struct", "structure", round(rng.uniform(0.05, 0.4), 3), list(cls.envelope_mm), rng)
    struct.raw["specs"]["form_factor_u"] = float(units)
    comps = [struct]
    for cat in ("obc", "eps", "battery", "comms", "adcs"):
        for n in range(rng.randint(2, 4)):
            mass = None if rng.random() < 0.1 else round(rng.uniform(0.02, cls.mass_limit_kg * 0.45), 3)
            dims = None if rng.random() < 0.2 else [round(rng.uniform(10, 110), 1) for _ in range(3)]
            comps.append(make(f"{cat}-{n}", cat, mass, dims, rng))
    return comps


def brute_force(catalog, units):
    """Ricerca esaustiva indipendente: massima completezza totale, poi minima massa, con somma di masse e volumi entro i limiti e pila a serpentina fattibile."""
    cls = CLASSES[units]
    from star_selector.rows import subsystem_of
    pools, sids = [], []
    for sid, _, _ in SUBSYSTEMS:
        members = [c for c in catalog if subsystem_of(c) == sid]
        if sid == "structure":
            fit = [c for c in members if c.spec("form_factor_u") == units]
        else:
            fit = [c for c in members if _admissible(c, sid, cls)]
        known = [c for c in fit if c.mass_kg is not None]
        pool = known or fit
        if sid in layout.ORDER and any(layout.spec(c, sid, cls.envelope_mm) for c in pool):
            pool = [c for c in pool if layout.spec(c, sid, cls.envelope_mm)]      # senza quote complete solo se non c'e' di meglio
        if pool:
            pools.append(pool)
            sids.append(sid)
    best = None
    for combo in itertools.product(*pools):
        mass = sum(c.mass_kg or 0.0 for c in combo)
        vol = sum(0.0 if c.category == "structure" or subsystem_of(c) in EXTERNAL_SUBSYSTEMS else (volume_m3(c) or 0.0) for c in combo)
        if mass > cls.mass_limit_kg + 1e-12 or vol > cls.volume_limit_m3 + 1e-15:
            continue
        heights = {}
        for sid, c in zip(sids, combo):
            st = layout.spec(c, sid, cls.envelope_mm) if sid in layout.ORDER else None
            heights[sid] = st["height"] if st else None
        if not layout.stack_feasible(heights, cls.envelope_mm):
            continue
        key = (round(sum(completeness(c) for c in combo), 9), -mass)
        if best is None or key > best:
            best = key
    return best


class TestAgainstExhaustiveSearch(unittest.TestCase):
    def test_random_catalogues_match_the_brute_force_optimum(self):
        checked = infeasible = 0
        for units in (1, 3, 6):
            for seed in range(80):
                cat = random_catalog(seed * 7 + units, units)
                res = select(cat, units, time_budget_s=10)
                oracle = brute_force(cat, units)
                self.assertFalse(res.truncated)
                if oracle is None:
                    infeasible += 1
                    self.assertFalse(res.within_limits, (units, seed))
                    continue
                self.assertTrue(res.within_limits, (units, seed))
                got = (round(sum(r.selected.completeness for r in res.subsystems if r.selected), 9), -res.mass_kg)
                self.assertAlmostEqual(got[0], oracle[0], places=6, msg=(units, seed))
                self.assertAlmostEqual(got[1], oracle[1], places=6, msg=(units, seed))
                checked += 1
        self.assertGreater(checked, 100)      # il confronto e' stato fatto davvero su molti casi
        self.assertGreater(infeasible, 0)     # e almeno un caso in cui i limiti non permettono una soluzione


class TestRealCatalogueInvariants(unittest.TestCase):
    def test_every_class_respects_the_published_limits_and_the_totals_are_recomputable(self):
        for units, cls in CLASSES.items():
            res = select(CATALOG, units)
            chosen = [r.selected for r in res.subsystems if r.selected]
            self.assertEqual(len(res.subsystems), len(SUBSYSTEMS))
            for k in chosen:
                if k.comp.category != "structure":
                    self.assertTrue(fits_envelope(k.comp, cls.envelope_mm), (units, k.comp.id))
                self.assertTrue(k.mass_kg is None or k.mass_kg <= cls.mass_limit_kg + EPS, (units, k.comp.id))
            self.assertAlmostEqual(res.mass_kg, sum(k.comp.mass_kg or 0.0 for k in chosen), places=9)
            self.assertAlmostEqual(res.volume_m3, sum(0.0 if k.comp.category == "structure" or subsystem_of(k.comp) in EXTERNAL_SUBSYSTEMS else (volume_m3(k.comp) or 0.0) for k in chosen), places=12)
            self.assertAlmostEqual(res.power_w, sum(declared_power_w(k.comp) or 0.0 for k in chosen), places=9)
            if res.within_limits:
                self.assertLessEqual(res.mass_kg, cls.mass_limit_kg + EPS)
                self.assertLessEqual(res.volume_m3, cls.volume_limit_m3 + EPS)
            struct = next(r.selected for r in res.subsystems if r.id == "structure")
            self.assertEqual(struct.comp.spec("form_factor_u"), units)

    def test_the_selection_is_deterministic(self):
        for units in CLASSES:
            a, b = select(CATALOG, units), select(CATALOG, units)
            self.assertEqual([r.selected.comp.id if r.selected else None for r in a.subsystems], [r.selected.comp.id if r.selected else None for r in b.subsystems])

    def test_alternatives_all_fit_and_exclude_the_selected_component(self):
        for units, cls in CLASSES.items():
            for r in select(CATALOG, units).subsystems:
                ids = [k.comp.id for k in r.alternatives]
                self.assertEqual(len(ids), len(set(ids)))
                if r.selected:
                    self.assertNotIn(r.selected.comp.id, ids)
                    self.assertEqual(1 + len(ids), r.n_fit, (units, r.id))
                for k in r.alternatives:
                    self.assertTrue(fits_envelope(k.comp, cls.envelope_mm) or k.comp.category == "structure")

    def test_what_fits_a_smaller_class_fits_a_larger_one(self):
        fit = {u: {r.id: r.n_fit for r in select(CATALOG, u).subsystems if r.id != "structure"} for u in CLASSES}
        for small, big in ((1, 3), (3, 6), (6, 12)):
            for sid, n in fit[small].items():
                self.assertLessEqual(n, fit[big][sid], (small, big, sid))

    def test_every_subsystem_has_a_card_even_without_a_fitting_component(self):
        res = select(CATALOG, 1)
        empty = [r for r in res.subsystems if not r.selected]
        for r in empty:
            self.assertTrue(r.note)
            self.assertIn(r.label, " ".join(res.messages))

    def test_no_selected_number_is_invented(self):
        """Ogni massa/dimensione/potenza di un componente scelto e' quella del catalogo (stesso oggetto, nessun valore di default)."""
        for units in CLASSES:
            for r in select(CATALOG, units).subsystems:
                if not r.selected:
                    continue
                c = r.selected.comp
                self.assertEqual(r.selected.mass_kg, c.raw.get("mass_kg"))
                self.assertEqual(r.selected.power_w, declared_power_w(c))
                if r.selected.volume_m3 is not None:
                    self.assertTrue(all(x for x in c.dimensions_mm))


if __name__ == "__main__":
    unittest.main()

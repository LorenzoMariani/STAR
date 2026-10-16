"""Controllo di ingombro (star_selector/fit.py): stati, validita' delle disposizioni trovate, componenti esterni."""
import random
import unittest

from star_selector.api import SelectorService
from star_selector.fit import LABELS, check_fit, pack
from star_selector.rows import volume_m3
from star_selector.selector import CLASSES, EXTERNAL_SUBSYSTEMS, select
from tests.test_selector import structure_1u, synthetic

SERVICE = SelectorService()
EPS = 1e-6


def valid_witness(env, placed):
    """Ogni scatola e' dentro l'ingombro e non si sovrappone alle altre."""
    for _, x, y, z, dx, dy, dz, *_perm in placed:
        if x < -EPS or y < -EPS or z < -EPS or x + dx > env[0] + EPS or y + dy > env[1] + EPS or z + dz > env[2] + EPS:
            return False
    for i, a in enumerate(placed):
        for b in placed[i + 1:]:
            if all(a[1 + k] < b[1 + k] + b[4 + k] - EPS and a[1 + k] + a[4 + k] > b[1 + k] + EPS for k in range(3)):
                return False
    return True


class TestPacking(unittest.TestCase):
    def test_random_boxes_the_witness_is_always_valid(self):
        rng = random.Random(3)
        found = 0
        for _ in range(150):
            env = (rng.uniform(60, 120), rng.uniform(60, 240), rng.uniform(100, 370))
            boxes = [(f"b{i}", tuple(rng.uniform(8, 100) for _ in range(3))) for i in range(rng.randint(1, 9))]
            placed = pack(env, boxes)
            if placed is None:
                continue
            found += 1
            self.assertEqual(sorted(p[0] for p in placed), sorted(b[0] for b in boxes))
            self.assertTrue(valid_witness(env, placed))
            for name, x, y, z, dx, dy, dz, *_perm in placed:      # ogni scatola e' una rotazione di 90 gradi di quella data
                self.assertEqual(sorted((dx, dy, dz)), sorted(dict(boxes)[name]))
        self.assertGreater(found, 50)

    def test_known_cases(self):
        self.assertIsNotNone(pack((100, 100, 100), [("a", (100, 100, 50)), ("b", (100, 100, 50))]))      # due meta' esatte
        self.assertIsNone(pack((100, 100, 100), [("a", (100, 100, 60)), ("b", (100, 100, 60))]))         # 120% del volume
        self.assertIsNotNone(pack((100, 20, 30), [("a", (30, 100, 20))]))                                # serve ruotarlo


class TestStates(unittest.TestCase):
    def test_states_on_the_real_catalogue(self):
        got = {u: SERVICE.select({"form_factor_u": u})["fit"] for u in CLASSES}
        self.assertEqual(got[1]["state"], "does_not_fit")      # il volume interno e' il 236 % dell'ingombro
        self.assertGreater(got[1]["internal_volume_fraction"], 1.0)
        self.assertEqual(got[3]["state"], "fits")              # la selezione tiene conto della lunghezza della pila: un 3U ora entra
        self.assertEqual(got[6]["state"], "fits")
        self.assertEqual(got[12]["state"], "fits")
        for u in (3, 6, 12):
            self.assertEqual(got[u]["arrangement"], "stack", u)
            self.assertEqual(len(got[u]["placed"]), 12)
            placed = [(p["id"], *p["pos"], *p["size"]) for p in got[u]["placed"]]
            self.assertTrue(valid_witness(got[u]["envelope_mm"], placed), u)
        self.assertEqual(got[1]["placed"], [])                    # nessuna disposizione da mostrare

    def test_labels_and_messages_are_in_english_and_never_empty(self):
        for u in CLASSES:
            f = SERVICE.select({"form_factor_u": u})["fit"]
            self.assertEqual(f["label"], LABELS[f["state"]])
            self.assertTrue(f["message"])

    def test_the_volume_of_the_selection_is_the_internal_one(self):
        res = SERVICE.select({"form_factor_u": 6})
        by_id = {s["id"]: s["selected"] for s in res["subsystems"]}
        for sid in EXTERNAL_SUBSYSTEMS:
            self.assertIsNone(by_id[sid]["volume_m3"])          # montati sulle facce: non contati
            self.assertTrue(by_id[sid]["external"])
        self.assertFalse(by_id["obc"]["external"])
        self.assertAlmostEqual(res["totals"]["volume_m3"], res["fit"]["internal_volume_m3"], places=12)
        self.assertNotIn("solar_panel", res["totals"]["volume_unknown"])

    def test_unknown_size_gives_an_undetermined_state(self):
        obc = synthetic("obc-nosize", "obc", 0.05, None)
        res = select([structure_1u(), obc], 1)
        f = check_fit(res)
        self.assertEqual(f["state"], "undetermined")
        self.assertEqual(f["unknown_size"], ["obc-nosize"])
        self.assertEqual(f["placed"], [])

    def test_a_small_synthetic_selection_fits_and_a_large_one_does_not(self):
        small = synthetic("obc-s", "obc", 0.05, [60, 60, 10])
        f = check_fit(select([structure_1u(), small], 1))
        self.assertEqual((f["state"], len(f["placed"])), ("fits", 1))
        big = [synthetic(f"{c}-b", c, 0.1, [95, 95, 60]) for c in ("obc", "eps", "battery")]    # 3 x 541 cm3 su 1135 cm3
        f = check_fit(select([structure_1u()] + big, 1))
        self.assertEqual(f["state"], "does_not_fit")


class TestStack(unittest.TestCase):
    """Pila lungo l'asse lungo (layout.py): ordine, colonne, schede orizzontali, nessuna sovrapposizione."""

    def test_the_stack_follows_the_declared_order_and_never_overlaps(self):
        from star_selector import layout
        for u in (3, 6, 12):
            f = SERVICE.select({"form_factor_u": u})["fit"]
            placed = [(p["id"], *p["pos"], *p["size"]) for p in f["placed"]]
            self.assertTrue(valid_witness(f["envelope_mm"], placed), u)
            order = [layout.ORDER.index(p["subsystem"]) for p in f["placed"]]
            self.assertEqual(order, sorted(order), u)                               # nell'ordine dichiarato
            nx, ny, cx, cy = layout.grid(f["envelope_mm"])
            self.assertEqual(layout.columns(f["envelope_mm"]), {3: 1, 6: 2, 12: 4}[u])
            for p in f["placed"]:                                                   # ogni pezzo sta nella sezione di una colonna
                self.assertLessEqual(p["size"][0], cx + 1e-6)
                self.assertLessEqual(p["size"][1], cy + 1e-6)
            cols = {}
            for p in f["placed"]:
                col = (int((p["pos"][0] + p["size"][0] / 2) / cx), int((p["pos"][1] + p["size"][1] / 2) / cy))
                cols.setdefault(col, []).append(p)
            for c in cols.values():
                tops = [q["pos"][2] + q["size"][2] for q in c]
                self.assertEqual(tops, sorted(tops, reverse=True))                  # dall'alto verso il basso
                for a, b in zip(c, c[1:]):
                    self.assertAlmostEqual(a["pos"][2], b["pos"][2] + b["size"][2], places=2)     # strati contigui

    def test_boards_lie_flat_and_tubes_stand_along_the_stack(self):
        f = SERVICE.select({"form_factor_u": 6})["fit"]
        for p in f["placed"]:
            sh = p["shape"]
            if sh["type"] == "board":
                self.assertEqual(sh["normal"], 2, p["id"])                        # la normale della scheda e' lungo Z
            if sh["type"] in ("lens_box", "cylinder", "baffle_box") and p["subsystem"] not in ("magnetorquer", "reaction_wheel") and sh["axis"] is not None:
                self.assertEqual(sh["axis"], 2, p["id"])                          # obiettivi e tubi lungo Z

    def test_serpentine_basic_cases(self):
        from star_selector.layout import serpentine
        self.assertEqual(serpentine([("a", 100), ("b", 100)], 340.5, 1), [("a", 0, 240.5), ("b", 0, 140.5)])
        self.assertEqual([c for _, c, _ in serpentine([("a", 200), ("b", 200)], 340.5, 2)], [0, 1])
        self.assertIsNone(serpentine([("a", 200), ("b", 200)], 340.5, 1))
        self.assertIsNone(serpentine([("a", 400)], 340.5, 4))

    def test_the_selection_never_dodges_the_stack_with_a_component_of_unknown_height(self):
        for u in (3, 6, 12):
            res = SERVICE.select({"form_factor_u": u})
            self.assertEqual(res["fit"]["unknown_size"], [], u)


class TestExternalParts(unittest.TestCase):
    def test_external_parts_sit_on_a_face_outside_the_envelope(self):
        for u in (3, 6, 12):
            f = SERVICE.select({"form_factor_u": u})["fit"]
            self.assertEqual({e["subsystem"] for e in f["external"]}, {"solar_panel", "antenna", "sun_sensor", "gnss_antenna"})
            env = f["envelope_mm"]
            for e in f["external"]:
                n = {"+X": 0, "+Y": 1, "+Z": 2}[e["face"]]
                self.assertAlmostEqual(e["pos"][n], env[n])                       # appoggiato alla faccia, verso l'esterno
                for k in range(3):                                                # nel perimetro della faccia
                    if k != n:
                        self.assertGreaterEqual(e["pos"][k], -EPS)
                        self.assertLessEqual(e["pos"][k] + e["size"][k], env[k] + 0.11)

    def test_published_sizes_are_kept_and_unpublished_thickness_is_flagged(self):
        f = SERVICE.select({"form_factor_u": 3})["fit"]       # il pannello 3U scelto pubblica le tre quote (quello 6U no)
        panel = next(e for e in f["external"] if e["subsystem"] == "solar_panel")
        c = next(c for c in SERVICE.catalog if c.id == panel["id"])
        self.assertEqual(sorted(panel["size"], reverse=True), sorted(c.dimensions_mm, reverse=True))      # le quote del catalogo, non altre
        self.assertTrue(panel["size_published"])

    def test_a_panel_with_two_published_sizes_is_drawn_with_them_and_a_nominal_thickness(self):
        from star_selector.fit import _place_external
        c = next(c for c in SERVICE.catalog if c.id == "dhv-1u-xy")
        spot = _place_external(c, (100.0, 226.3, 366.0), set())
        self.assertFalse(spot["size_published"])                                  # lo spessore manca
        self.assertEqual(spot["published_mm"], [82.8, 97.8])
        self.assertEqual(sorted(spot["size"], reverse=True)[:2], [97.8, 82.8])


class TestShapes(unittest.TestCase):
    """Forme semplificate (campo `shape`): coerenza con le immagini, con le quote pubblicate e con la disposizione."""

    def test_every_component_has_a_valid_shape_and_its_basis_matches_the_image(self):
        from star_selector.models import AXIS_SHAPES, SHAPE_BASES, SHAPE_TYPES
        for c in SERVICE.catalog:
            sh = c.raw["shape"]
            self.assertIn(sh["type"], SHAPE_TYPES, c.id)
            self.assertIn(sh["basis"], SHAPE_BASES, c.id)
            if not c.raw.get("image"):
                self.assertEqual(sh["basis"], "subsystem", c.id)            # senza immagine la forma non puo' essere "letta dall'immagine"
            dims = c.dimensions_mm
            if sh["type"] in AXIS_SHAPES and dims and all(v is not None for v in dims):
                self.assertIn(sh["axis"], (0, 1, 2), c.id)
            if sh["type"] == "frame":
                self.assertEqual(c.category, "structure", c.id)
        self.assertEqual({c.id for c in SERVICE.catalog if c.raw["shape"]["basis"] == "subsystem" and c.raw.get("image")}, {"hyperion-st200", "aac-cubecat"})   # render/diagrammi

    def test_rods_are_long_cylinders_and_wheels_are_discs(self):
        for c in SERVICE.catalog:
            d = c.dimensions_mm
            if c.category == "magnetorquer" and c.spec("magnetorquer_type") == "rod":
                self.assertEqual((c.raw["shape"]["type"], d[c.raw["shape"]["axis"]]), ("cylinder", max(d)), c.id)
            if c.category == "reaction_wheel" and d and all(v is not None for v in d):
                self.assertEqual((c.raw["shape"]["type"], d[c.raw["shape"]["axis"]]), ("cylinder", min(d)), c.id)

    def test_placed_shapes_follow_the_orientation_found_by_the_arrangement(self):
        from star_selector.fit import VISUAL_THICKNESS_MM
        by_id = {c.id: c for c in SERVICE.catalog}
        for u in (3, 6, 12):
            f = SERVICE.select({"form_factor_u": u})["fit"]
            for p in f["placed"] + f["external"]:
                c, sh, dims = by_id[p["id"]], p["shape"], by_id[p["id"]].dimensions_mm
                if not dims or None in dims:
                    continue                       # pannello senza quote pubblicate: disegnato sulla faccia dichiarata (sotto)
                local = c.raw["shape"]["axis"]
                if sh["axis"] is not None:
                    self.assertAlmostEqual(p["size"][sh["axis"]], dims[local], places=1, msg=p["id"])     # l'asse segue la quota giusta dopo la rotazione
                if sh["normal"] is not None:
                    self.assertAlmostEqual(p["size"][sh["normal"]], min(dims), places=1, msg=p["id"])     # la normale e' la quota piu' piccola
            panel = next(e for e in f["external"] if e["subsystem"] == "solar_panel")
            self.assertEqual(panel["shape"]["type"], "panel")
            dims = by_id[panel["id"]].dimensions_mm
            thickness = min(dims) if dims and None not in dims else VISUAL_THICKNESS_MM     # spessore pubblicato, altrimenti quello nominale del disegno
            self.assertAlmostEqual(panel["size"][panel["shape"]["normal"]], thickness)


if __name__ == "__main__":
    unittest.main()

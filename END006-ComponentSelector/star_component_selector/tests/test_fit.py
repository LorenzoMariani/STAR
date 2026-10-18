"""Controllo di ingombro (star_selector/fit.py): stati, validita' delle disposizioni trovate, componenti esterni."""
import random
import unittest

from star_selector.api import SelectorService
from star_selector import fit
from star_selector.fit import LABELS, check_fit, pack
from star_selector.rows import volume_m3
from star_selector.selector import CLASSES, EXTERNAL_SUBSYSTEMS, select
from tests.test_selector import structure_1u, synthetic

SERVICE = SelectorService()
BY_ID = SERVICE.by_id
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


def no_overlap(placed):
    return valid_witness((1e9, 1e9, 1e9), [(n, x + 1e8, y + 1e8, z + 1e8, dx, dy, dz) for n, x, y, z, dx, dy, dz, *_ in placed])


class TestPreview(unittest.TestCase):
    """Anteprima quando l'ingombro non e' dimostrato (2026-10-16): c'e' sempre qualcosa da disegnare, "placed" resta la sola dimostrazione."""

    def test_a_proof_has_no_preview(self):
        self.assertIsNone(SERVICE.select({"form_factor_u": 6})["fit"]["preview"])

    def test_unknown_size_draws_the_others_and_the_free_space(self):
        obc = synthetic("obc-nosize", "obc", 0.05, None)
        eps = synthetic("eps-s", "eps", 0.05, [90, 90, 15])
        f = check_fit(select([structure_1u(), obc, eps], 1))
        pv = f["preview"]
        self.assertEqual((f["state"], f["placed"]), ("undetermined", []))
        self.assertEqual([p["id"] for p in pv["placed"]], ["eps-s"])
        self.assertFalse(pv["placed"][0]["outside"])
        self.assertEqual([p["id"] for p in pv["not_drawn"]], ["obc-nosize"])
        self.assertEqual(len(pv["free"]), 1)
        free = pv["free"][0]
        self.assertAlmostEqual(free["pos"][2] + free["size"][2], pv["placed"][0]["pos"][2], places=1)      # below the stack, up to it
        self.assertIn("not drawn", pv["message"])

    def test_v6_design_without_the_imager_size(self):
        import copy
        import json
        from pathlib import Path
        from star_selector.mission import design
        from star_selector.models import Component
        from tests.test_mission import CATALOG
        v6 = json.loads((Path(__file__).resolve().parents[3] / "Input/input_base_knowledge/sample_inputs/Mission_Proposal_v6_requirements.json").read_text(encoding="utf-8"))["requirements"]
        no_size = [Component({k: v for k, v in copy.deepcopy(c.raw).items() if k != "dimensions"}) if c.id == "satlantis-isim-90" else c for c in CATALOG]
        f = check_fit(design(no_size, v6, {"altitude_km": [641.6, 641.6]})[0])     # the camera as it was before its datasheet (no size)
        pv = f["preview"]
        self.assertEqual(f["state"], "undetermined")
        self.assertEqual(pv["kind"], "stack")
        self.assertIn("satlantis-isim-90", [p["id"] for p in pv["not_drawn"]])
        self.assertTrue(pv["placed"] and not any(p["outside"] for p in pv["placed"]))
        self.assertGreater(pv["free_volume_l"], 1.0)

    def test_v6_design_with_the_imager_datasheet(self):
        import json
        from pathlib import Path
        from star_selector.mission import design
        from tests.test_mission import CATALOG
        v6 = json.loads((Path(__file__).resolve().parents[3] / "Input/input_base_knowledge/sample_inputs/Mission_Proposal_v6_requirements.json").read_text(encoding="utf-8"))["requirements"]
        f = check_fit(design(CATALOG, v6, {"altitude_km": [641.6, 641.6]})[0])
        self.assertEqual((f["state"], f["arrangement"]), ("fits", "stack"))
        parts = {p["name"]: p for p in f["placed"] if p["id"] == "satlantis-isim-90"}
        self.assertEqual(len(parts), 2)                                            # optics and electronics box
        optics = next(p for n, p in parts.items() if "electronics" not in n)
        self.assertAlmostEqual(optics["size"][2], 308.0)                           # the telescope along the long axis
        self.assertGreater(max(optics["size"][:2]), f["envelope_mm"][0] / 2)        # wider than one column of a 12U
        placed = [(p["id"] + p["name"], *p["pos"], *p["size"]) for p in f["placed"]]
        self.assertTrue(valid_witness(f["envelope_mm"], placed))
        self.assertGreater(f["internal_volume_m3"], (308 * 114 * 100 + 209 * 96 * 46) * 1e-9)

    def test_does_not_fit_shows_the_extended_stack(self):
        f = SERVICE.select({"form_factor_u": 1})["fit"]
        pv = f["preview"]
        self.assertEqual((f["state"], f["placed"]), ("does_not_fit", []))
        self.assertEqual(pv["kind"], "extended_stack")
        self.assertEqual(len(pv["placed"]), 12)                                  # every internal component drawn
        self.assertGreater(pv["stack_length_mm"], f["envelope_mm"][2])
        self.assertTrue(any(p["outside"] for p in pv["placed"]))
        boxes = [(p["id"], *p["pos"], *p["size"]) for p in pv["placed"]]
        self.assertTrue(no_overlap(boxes))
        tops = [p["pos"][2] + p["size"][2] for p in pv["placed"]]
        self.assertAlmostEqual(max(tops), f["envelope_mm"][2], places=1)      # the stack starts at the top face

    def test_extended_stack_is_the_shortest_that_fits_the_columns(self):
        from star_selector.fit import extended_stack
        from star_selector import layout
        env = (226.3, 100.0, 100.0)                                              # two columns of 100 mm
        internal = [(f"s{i}", "obc", type("K", (), {"comp": synthetic(f"b{i}", "obc", 0.1, [90, 90, 40]), "quantity": 1})(), (90.0, 90.0, 40.0)) for i in range(6)]
        placed, length = extended_stack(env, internal)
        self.assertAlmostEqual(length, 120.0, delta=0.11)                        # 6 x 40 mm in 2 columns: 3 per column
        self.assertIsNotNone(layout.serpentine([(n, 40.0) for n, *_ in internal], length, 2))
        self.assertTrue(no_overlap(placed))


class TestWideParts(unittest.TestCase):
    """Componenti piu' larghi di una colonna e prodotti con piu' scatole (2026-10-16, datasheet della iSIM-90)."""

    def test_arrange_puts_wide_parts_at_the_bottom_of_adjacent_columns(self):
        from star_selector import layout
        env = (226.3, 226.3, 340.5)                                                 # 12U: 2 x 2 columns
        cells = layout.arrange([("a", 50.0), ("wide", 300.0, (2, 1)), ("b", 30.0), ("box", 46.0, (2, 1))], env)
        by = {k: (block, z) for k, block, z in cells}
        self.assertEqual(by["wide"], ((0, 0, 2, 1), 0.0))
        self.assertEqual(by["box"], ((0, 1, 2, 1), 0.0))
        self.assertEqual(by["a"][0][2:], (1, 1))
        self.assertAlmostEqual(by["a"][1], 340.5 - 50.0)                          # narrow parts from the top
        self.assertIsNone(layout.arrange([("w", 300.0, (2, 2)), ("x", 50.0)], env))      # no room left above a full-section block
        self.assertEqual(layout.arrange([("a", 50.0), ("b", 30.0)], env),
                         [(k, (c % 2, c // 2, 1, 1), z) for k, c, z in layout.serpentine([("a", 50.0), ("b", 30.0)], 340.5, 4)])   # same as before

    def test_spec_spans_columns_only_when_needed(self):
        from star_selector import layout
        isim = BY_ID["satlantis-isim-90"]
        st = layout.spec(isim, "payload_imager", CLASSES[12].envelope_mm)
        self.assertEqual((st["height"], st["span"]), (308.0, (2, 1)))
        box = layout.dims_spec(isim.extra_boxes_mm[0], "payload_imager", {}, CLASSES[12].envelope_mm)
        self.assertEqual((box["height"], box["span"]), (46.0, (2, 1)))             # lying on two columns, not 209 mm standing
        self.assertIsNone(layout.spec(isim, "payload_imager", CLASSES[3].envelope_mm)["perm"])       # does not fit a 3U at all
        obc = synthetic("obc-s", "obc", 0.05, [90, 90, 10])
        self.assertEqual(layout.spec(obc, "obc", CLASSES[12].envelope_mm)["span"], (1, 1))

    def test_nothing_in_front_of_the_camera(self):
        from star_selector import layout
        env = (100.0, 100.0, 340.5)                                                 # 3U: one column
        cells = {k: (b, z) for k, b, z in layout.arrange([("radio", 20.0), ("cam", 100.0, (1, 1), True), ("prop", 90.0)], env)}
        self.assertEqual(cells["cam"][1], 0.0)                                      # on the -Z face, the rest above it
        self.assertGreater(cells["prop"][1], 100.0 - 1e-9)
        self.assertIsNone(layout.arrange([("cam", 100.0, (1, 1), True), ("cam2", 100.0, (1, 1), True)], env))   # one bottom only
        cells = {k: (b, z) for k, b, z in layout.arrange([("wide", 60.0, (2, 1)), ("cam", 200.0, (2, 1), True)], (226.3, 226.3, 340.5))}
        self.assertEqual(cells["cam"][1], 0.0)                                      # the camera first, then the other wide parts
        self.assertEqual(cells["wide"][1], 0.0)
        self.assertNotEqual(cells["wide"][0][:2], cells["cam"][0][:2])
        # the generic search accepts only arrangements with the camera on the -Z face
        cam = type("C", (), {"raw": {"shape": {"type": "lens_box", "axis": 2}}})()          # optical axis along its third size
        accept = fit._aperture_check([("payload_imager", "payload_imager", type("K", (), {"comp": cam, "quantity": 1})(), (90.0, 90.0, 120.0))])
        self.assertTrue(accept([("payload_imager", 0.0, 0.0, 0.0, 90.0, 90.0, 120.0, (0, 1, 2))]))
        self.assertFalse(accept([("payload_imager", 0.0, 0.0, 50.0, 90.0, 90.0, 120.0, (0, 1, 2))]))

    def test_extra_boxes_count_in_the_volume(self):
        isim = BY_ID["satlantis-isim-90"]
        self.assertAlmostEqual(volume_m3(isim), (308 * 114 * 100 + 209 * 96 * 46) * 1e-9)


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
                stack = [q for q in c if q["subsystem"] not in layout.APERTURE_SUBSYSTEMS]
                for a, b in zip(stack, stack[1:]):
                    self.assertAlmostEqual(a["pos"][2], b["pos"][2] + b["size"][2], places=2)     # strati contigui
            for p in f["placed"]:
                if p["subsystem"] in layout.APERTURE_SUBSYSTEMS:                    # la camera sul fondo, obiettivo sulla faccia -Z
                    self.assertAlmostEqual(p["pos"][2], 0.0, places=3)
                    self.assertEqual(p["aperture"], "-Z", u)

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
                self.assertEqual((c.raw["shape"]["type"], d[c.raw["shape"]["axis"]]), ("rod", max(d)), c.id)
            if c.category == "reaction_wheel" and d and all(v is not None for v in d):         # disc, can or cube: rotation axis = smallest size
                self.assertIn(c.raw["shape"]["type"], ("wheel_disc", "wheel_can", "wheel_cube"), c.id)
                ax = c.raw["shape"]["axis"]
                base = [d[k] for k in range(3) if k != ax]
                self.assertTrue(d[ax] == min(d) or abs(base[0] - base[1]) < 1e-9, c.id)      # or the axis across a square base (tall can)

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

"""Phase E: kpis.json contract (BackEnd/runners/star_kpis.py, star_kpi_adapters.py).

- schema: validate() accepts a well-formed document and rejects duplicate ids, unknown units and categories;
- registry: every module that runs publishes a guaranteed `kpis` product;
- adapters: on the products of a real run (the newest RUN_* under Output/ with modules_output; skipped when there is none)
  every adapter gives a valid document;
- no module reads another module's KPI by its native number (KPI-nn): global ids only.
"""
import json
import re
import sys
import unittest
from pathlib import Path

STAR = Path(__file__).resolve().parent.parent
BACKEND = STAR / "BackEnd"
REGISTRY = STAR / "Input" / "input_base_knowledge" / "registry"
RUNNERS = BACKEND / "runners"
MANIFEST = Path(__file__).resolve().parent / "fixtures" / "smoke_products_manifest.json"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

try:
    import yaml  # noqa: F401
    from runners import star_kpis as K
    from runners import star_kpi_adapters as A
    from runners.star_workflow_graph import Registry
except ModuleNotFoundError:          # PyYAML is optional for the other STAR suites (requirements.txt)
    K = None


def latest_run():
    runs = [p for p in (STAR / "Output").glob("RUN_*") if (p / "modules_output").is_dir() and any((p / "modules_output").glob("END-*/kpis*.json"))]
    return max(runs, key=lambda p: p.stat().st_mtime) if runs else None


@unittest.skipIf(K is None, "PyYAML not installed")
class TestSchema(unittest.TestCase):
    def doc(self, *kpis):
        return K.document("END-004", list(kpis), run_id="RUN_X")

    def test_valid_document(self):
        doc = self.doc(K.kpi("END-004.worst_dod_pct", 1.2, unit="%"), K.kpi("END-004.peak_power_W", 12.0, unit="W"))
        self.assertEqual(K.validate(doc), [])

    def test_duplicate_ids_are_rejected(self):
        doc = self.doc(K.kpi("END-004.worst_dod_pct", 1.2, unit="%"), K.kpi("END-004.worst_dod_pct", 2.0, unit="%"))
        self.assertTrue(K.validate(doc))

    def test_unknown_unit_and_category_are_rejected(self):
        bad_unit = self.doc({**K.kpi("END-004.worst_dod_pct", 1.2, unit="%"), "unit": "furlongs"})
        bad_cat = self.doc({**K.kpi("END-004.worst_dod_pct", 1.2, unit="%"), "category": "vibes"})
        self.assertTrue(K.validate(bad_unit))
        self.assertTrue(K.validate(bad_cat))

    def test_other_module_prefix_is_rejected(self):
        self.assertTrue(K.validate(self.doc(K.kpi("END-003.eclipse_fraction_pct", 35.0, unit="%"))))

    def test_units_are_normalised(self):
        self.assertEqual(K.norm_unit("hours"), "h")
        self.assertIn(K.norm_unit("count"), K.UNITS)

    def test_write_and_load_run(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "RUN_T" / "modules_output" / "END-004"
            root.mkdir(parents=True)
            K.write(root, self.doc(K.kpi("END-004.worst_dod_pct", 1.2, unit="%")))
            loaded = K.load_run(Path(tmp) / "RUN_T")
            self.assertEqual(loaded["END-004.worst_dod_pct"]["value"], 1.2)
            self.assertEqual(loaded["END-004.worst_dod_pct"]["module_id"], "END-004")


@unittest.skipIf(K is None, "PyYAML not installed")
class TestRegistryAndSources(unittest.TestCase):
    def test_every_integrated_module_produces_kpis(self):
        registry = Registry.load(REGISTRY)
        missing = []
        for node in (n for n in registry.nodes.values() if (RUNNERS / f"{n.module_id.lower().replace('-', '')}_runner.py").is_file()):
            ok = any(str(p.get("product")).startswith("kpis_") and str(p.get("path", "")).startswith("kpis") and p.get("guaranteed")
                     and "kpis" in (p.get("required_keys") or []) for p in node.produces)
            if not ok:
                missing.append(node.id)
        self.assertEqual(missing, [], "nodes without a guaranteed kpis product")

    def test_smoke_manifest_lists_kpis_files(self):
        files = json.loads(MANIFEST.read_text(encoding="utf-8"))["files"]
        for module, names in files.items():
            if module == "END-007":
                continue
            self.assertTrue(any(n.split("/")[-1].startswith("kpis") for n in names), f"{module}: kpis.json is not in the smoke manifest")

    def test_no_cross_module_reference_by_native_number(self):
        # a runner may name its own KPI numbers (a module's catalogue); reading another module's KPI-nn is the old fragile link
        pat = re.compile(r"END-0\d\d[^\n]{0,60}KPI-\d\d|KPI-\d\d[^\n]{0,60}END-0\d\d")
        hits = []
        for py in RUNNERS.glob("*.py"):
            if py.name in ("star_kpis.py", "star_kpi_adapters.py"):
                continue                                  # the catalogue and the adapters are where native ids are mapped
            for n, line in enumerate(py.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if pat.search(line) and not line.lstrip().startswith("#"):
                    hits.append(f"{py.name}:{n}: {line.strip()[:100]}")
        self.assertEqual(hits, [])


@unittest.skipIf(K is None, "PyYAML not installed")
class TestAdaptersOnARun(unittest.TestCase):
    def test_adapters_give_valid_documents(self):
        run = latest_run()
        if run is None:
            self.skipTest("no run with modules_output under Output/")
        checked = 0
        for mdir in sorted((run / "modules_output").glob("END-*")):
            if mdir.name == "END-007":
                continue
            phases = ("initial", "final") if mdir.name == "END-006" else ("",)
            for phase in phases:
                doc = A.build_document(mdir.name, mdir, phase, run.name)
                if not doc["kpis"]:
                    continue
                errs = K.validate(doc)
                self.assertEqual(errs, [], f"{mdir.name} {phase}: {errs}")
                checked += 1
        self.assertGreater(checked, 0)

    def test_written_files_are_valid(self):
        run = latest_run()
        if run is None:
            self.skipTest("no run with modules_output under Output/")
        for f in sorted((run / "modules_output").glob("END-*/kpis*.json")):
            doc = json.loads(f.read_text(encoding="utf-8"))
            self.assertEqual(K.validate(doc), [], f.name)


if __name__ == "__main__":
    unittest.main()

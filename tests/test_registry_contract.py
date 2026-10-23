"""Registry <-> runners contract and workflow graph behaviour (phase B, 2026-10-21).

From the STAR folder:   python -m unittest discover -s tests -p "test_*.py"     (run_all_tests.py: suite STAR)

- Registry schema: integrated modules have a runner and produces/consumes, every consumed product has exactly one producer,
  no key of the old dependency model, the whole graph is acyclic, END-006 has an initial and a final phase.
- Runners: the products a runner reads through upstream_product() (directly or through the helpers of star_runner_io.py and
  end001_star_inputs.py) are exactly the products the registry says its module consumes, and the runners no longer match
  upstream files by name or read the folders of other modules.
- Produces vs reality: tests/fixtures/smoke_products_manifest.json (written by the smoke test) lists the files of a real run;
  every `guaranteed` product of the registry has to be in it.
- Graph behaviour: closure over the required products, order, blocking, product checks, cycles, planner view size.
- CEF loop (phase F): one feedback edge, loop / post-loop / fixed nodes, rerun_on and uses keys, criteria KPIs.
"""
import ast
import fnmatch
import json
import sys
import tempfile
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
    from runners.star_workflow_graph import Registry, WorkflowGraph, WorkflowGraphError
except ModuleNotFoundError:          # PyYAML is optional for the other STAR suites (requirements.txt)
    Registry = None

HELPER_FILES = ("star_runner_io.py", "end001_star_inputs.py")
PLANNING_VIEW_LIMIT = 6000


def module_consumes(registry: "Registry", module_id: str) -> set:
    return {str(c.get("product")) for node in registry.nodes_for(module_id) for c in node.consumes}


def _products_of_calls(tree: ast.AST) -> tuple:
    """(products read with upstream_product, names of the functions called) in an AST; calls whose first argument is the
    constant None (a helper used on the module's own files, not on its inputs) are not followed."""
    products, called = set(), set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ""
        if name == "upstream_product":
            arg = node.args[1] if len(node.args) > 1 else next((k.value for k in node.keywords if k.arg == "product"), None)
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                products.add(arg.value)
        elif node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value is None:
            continue
        else:
            called.add(name)
    return products, called


def helper_table() -> dict:
    table = {}
    for fname in HELPER_FILES:
        for fn in ast.walk(ast.parse((RUNNERS / fname).read_text(encoding="utf-8"))):
            if isinstance(fn, ast.FunctionDef):
                table[fn.name] = _products_of_calls(fn)
    return table


def runner_products(path: Path, table: dict) -> set:
    products, called = _products_of_calls(ast.parse(path.read_text(encoding="utf-8")))
    seen, todo = set(), list(called)
    while todo:
        name = todo.pop()
        if name in seen or name not in table:
            continue
        seen.add(name)
        direct, more = table[name]
        products |= direct
        todo.extend(more)
    return products


@unittest.skipIf(Registry is None, "PyYAML not installed")
class TestRegistrySchema(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = Registry.load(REGISTRY)

    def test_schema_has_no_issues(self):
        self.assertEqual(self.registry.validate_schema(), [])

    def test_integrated_modules(self):
        integrated = sorted(m for m in self.registry.modules if self.registry.has_contract(m))
        self.assertEqual(integrated, ["END-001", "END-003", "END-004", "END-006", "END-007", "END-010", "END-016", "END-019"])
        for module_id in integrated:
            execution = self.registry.modules[module_id].get("execution") or {}
            self.assertTrue(execution.get("runner_module") and execution.get("runner_function"), module_id)
            self.assertTrue((RUNNERS / (execution["runner_module"].split(".")[-1] + ".py")).is_file(), module_id)

    def test_end006_has_two_phases(self):
        self.assertEqual([n.id for n in self.registry.nodes_for("END-006")], ["END-006/initial", "END-006/final"])
        self.assertEqual(sorted(self.registry.always_in_workflow()), ["END-001", "END-006"])
        self.assertEqual(self.registry.producer_of("spacecraft_definition"), "END-006/initial")

    def test_every_consumed_product_has_one_producer(self):
        for node in self.registry.nodes.values():
            for item in node.consumes:
                self.assertEqual(len(self.registry.producers_of(item["product"])), 1, f"{node.id} consumes {item['product']}")

    def test_full_graph_is_acyclic(self):
        order = WorkflowGraph(self.registry, list(self.registry.nodes)).order()
        self.assertEqual(order[0], "END-006/initial")
        self.assertEqual(order[-1], "END-006/final")


@unittest.skipIf(Registry is None, "PyYAML not installed")
class TestRunnersFollowTheRegistry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = Registry.load(REGISTRY)
        cls.table = helper_table()

    def test_products_read_are_the_products_consumed(self):
        for module_id in sorted(m for m in self.registry.modules if self.registry.has_contract(m)):
            runner = RUNNERS / (self.registry.modules[module_id]["execution"]["runner_module"].split(".")[-1] + ".py")
            with self.subTest(module=module_id):
                self.assertEqual(runner_products(runner, self.table), module_consumes(self.registry, module_id))

    def test_runners_do_not_match_files_by_name(self):
        for runner in sorted(RUNNERS.glob("end0*_runner.py")):
            text = runner.read_text(encoding="utf-8")
            with self.subTest(runner=runner.name):
                self.assertNotIn("find_upstream_artifact(", text)
                self.assertNotIn("first_upstream_file(", text)
                self.assertNotRegex(text, r'modules_output\s*/\s*"END-')
                for other in ("end001_runtime_input.json", "end003_runtime_input.json"):
                    if other[:6] != runner.name[:6]:
                        self.assertNotIn(other, text)


@unittest.skipIf(Registry is None, "PyYAML not installed")
class TestProductsVersusARealRun(unittest.TestCase):
    @unittest.skipUnless(MANIFEST.is_file(), "tests/fixtures/smoke_products_manifest.json not there: run the smoke test and commit it")
    def test_guaranteed_products_are_in_the_smoke_run(self):
        files = json.loads(MANIFEST.read_text(encoding="utf-8"))["files"]
        registry = Registry.load(REGISTRY)
        # the smoke run leaves END-007 out
        for node in registry.nodes.values():
            if node.module_id not in files:
                continue
            for item in node.produces:
                if not item.get("guaranteed"):
                    continue
                with self.subTest(product=item["product"]):
                    matches = [f for f in files[node.module_id] if fnmatch.fnmatch(f, item["path"])]
                    self.assertGreaterEqual(len(matches), int(item.get("min_count", 1) or 1), f"{item['product']} ({item['path']})")


@unittest.skipIf(Registry is None, "PyYAML not installed")
class TestCefLoopDeclarations(unittest.TestCase):
    """What the registry declares for the design loop (phase F): the feedback edge, the fixed module, the post-loop triggers."""

    @classmethod
    def setUpClass(cls):
        cls.registry = Registry.load(REGISTRY)
        cls.graph = WorkflowGraph(cls.registry, list(cls.registry.nodes))
        from runners import star_cef
        cls.cef = star_cef
        cls.config = star_cef.load_config()
        cls.crit_nodes = star_cef.criteria_nodes(cls.config)

    def test_exactly_one_feedback_edge(self):
        self.assertEqual(self.registry.feedback_edges(), [("END-006/final", "spacecraft_definition_final", "spacecraft_definition")])
        self.assertEqual(self.graph.feedback_edges(), self.registry.feedback_edges())

    def test_the_feedback_edge_is_not_in_the_dependencies(self):
        self.assertNotIn("spacecraft_definition_final", {c["product"] for n in self.registry.nodes.values() for c in n.consumes})
        self.assertEqual(self.graph.order()[-1], "END-006/final")

    def test_loop_and_post_loop_nodes(self):
        self.assertEqual(set(self.graph.loop_nodes(self.crit_nodes)), {"END-003", "END-004", "END-016", "END-019", "END-006/final"})
        self.assertEqual(set(self.graph.post_loop_nodes(self.crit_nodes)), {"END-010", "END-007"})
        self.assertEqual(self.graph.fixed_nodes(), ["END-001"])
        self.assertEqual(self.graph.affected_by("spacecraft_definition"),
                         ["END-003", "END-004", "END-007", "END-010", "END-016", "END-019"])      # no END-001 (fixed), no END-006/final (producer)

    def test_loop_nodes_follow_the_workflow(self):
        # without the modules of the criteria only the ancestors of END-006 final stay in the loop
        graph = WorkflowGraph.build(self.registry, ["END-003", "END-004"])
        self.assertEqual(graph.loop_nodes(self.crit_nodes), ["END-003", "END-004", "END-006/final"])
        self.assertEqual(WorkflowGraph.build(self.registry, []).loop_nodes(self.crit_nodes), ["END-006/final"])

    def test_end001_is_fixed_and_declares_the_keys_it_uses(self):
        self.assertEqual(self.registry.cef_loop("END-001"), {"fixed": True, "rerun_on": []})
        uses = [c.get("uses") for c in self.registry.nodes["END-001"].consumes if c["product"] == "spacecraft_definition"]
        self.assertEqual(uses, [["radios"]])

    def test_rerun_on_declarations(self):
        end010 = self.registry.cef_loop("END-010")
        self.assertFalse(end010["fixed"])
        self.assertEqual([r["product"] for r in end010["rerun_on"]], ["spacecraft_definition"])
        self.assertEqual(self.registry.cef_loop("END-007")["rerun_on"], [{"product": "satellite_orbits"}])
        for module_id in self.registry.modules:
            for rule in self.registry.cef_loop(module_id)["rerun_on"]:
                self.assertTrue(self.registry.producers_of(rule["product"]), f"{module_id}: rerun_on {rule['product']} has no producer")

    def test_rerun_on_and_uses_keys_exist_in_the_spacecraft_definition(self):
        """The keys (dotted paths) must be written by end006_runner.spacecraft_definition(): a renamed key would silently stop the trigger."""
        tree = ast.parse((RUNNERS / "end006_runner.py").read_text(encoding="utf-8"))
        func = next(f for f in ast.walk(tree) if isinstance(f, ast.FunctionDef) and f.name == "spacecraft_definition")
        written = {n.value for n in ast.walk(func) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
        keys = []
        for module_id in self.registry.modules:
            for rule in self.registry.cef_loop(module_id)["rerun_on"]:
                if rule["product"] == "spacecraft_definition":
                    keys += [str(k) for k in rule.get("keys") or []]
        for node in self.registry.nodes.values():
            for c in node.consumes:
                if c.get("product") == "spacecraft_definition":
                    keys += [str(k) for k in c.get("uses") or []]
        self.assertTrue(keys)
        for key in keys:
            for part in key.split("."):
                self.assertIn(part, written, f"'{key}': '{part}' is not a key of the spacecraft definition")

    def test_criteria_read_catalogue_kpis_of_modules_in_the_registry(self):
        from runners import star_kpis
        modules = {n.module_id for n in self.registry.nodes.values()}
        for c in self.config["criteria"]:
            for chk in c["checks"]:
                for kid in self.cef._check_kpis(chk):
                    self.assertIsNotNone(star_kpis.catalogue_entry(kid), kid)
                    self.assertIn(self.cef.kpi_module(kid), modules, kid)
        for node_id in self.crit_nodes:
            self.assertIn(node_id, self.registry.nodes)


@unittest.skipIf(Registry is None, "PyYAML not installed")
class TestWorkflowGraph(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = Registry.load(REGISTRY)

    def build(self, modules, executable=None):
        return WorkflowGraph.build(self.registry, modules, executable)

    def test_images_only(self):
        graph = self.build(["END-007"])
        self.assertEqual(graph.order(), ["END-006/initial", "END-001", "END-003", "END-007", "END-006/final"])
        self.assertEqual(graph.validate(), [])
        self.assertIn("END-007 needs", graph.why("END-003"))

    def test_the_smoke_workflow_order(self):
        graph = self.build(["END-001", "END-003", "END-004", "END-010", "END-016", "END-019", "END-006"])
        self.assertEqual(graph.order(), ["END-006/initial", "END-001", "END-003", "END-004", "END-010", "END-016", "END-019",
                                         "END-006/final"])

    def test_closure_adds_the_hard_upstream_of_a_module(self):
        graph = self.build(["END-004"])
        self.assertEqual(sorted(graph.module_ids), ["END-001", "END-003", "END-004", "END-006"])
        # a module without the optional ones is complete: END-006/final only has optional inputs
        self.assertEqual(self.registry.required_producer_modules("END-006"), [])

    def test_modules_that_cannot_run_are_left_out_with_their_dependents(self):
        graph = self.build(["END-003", "END-004"], executable=lambda m: m != "END-001")
        self.assertEqual(graph.module_ids, ["END-006"])
        self.assertIn("END-001", graph.dropped)
        self.assertIn("END-003", graph.dropped)

    def test_blocking_follows_the_required_products(self):
        graph = self.build(["END-004", "END-016"])
        self.assertEqual(sorted(graph.upstream("END-004")), ["END-001", "END-003", "END-006/initial"])
        self.assertEqual(graph.upstream("END-006/final", required_only=True), [])
        self.assertIn("END-001", graph.upstream("END-006/final", required_only=False))
        self.assertIn("END-004", graph.downstream("END-003"))
        self.assertNotIn("END-006/final", graph.downstream("END-001", required_only=True))

    def test_check_products_text_and_content(self):
        graph = self.build(["END-004"])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "END-001" / "output_constellation_optimizer"
            out.mkdir(parents=True)
            missing = graph.check_products("END-004", root)
            self.assertIn("END-004: missing operations_summary.json from END-001 "
                          "(output_constellation_optimizer/operations_summary.json): not found", missing)
            (out / "operations_summary.json").write_text("", encoding="utf-8")
            self.assertTrue(any("operations_summary.json is empty" in m for m in graph.check_products("END-004", root)))
            (out / "operations_summary.json").write_text("{not json", encoding="utf-8")
            self.assertTrue(any("not valid JSON" in m for m in graph.check_products("END-004", root)))
            (out / "operations_summary.json").write_text(json.dumps({"epoch_utc": "x"}), encoding="utf-8")
            self.assertTrue(any("lacks the keys constellation_mean" in m for m in graph.check_products("END-004", root)))
            (out / "operations_summary.json").write_text(json.dumps({"constellation_mean": {}}), encoding="utf-8")
            self.assertFalse(any("operations_summary" in m for m in graph.check_products("END-004", root)))
            # optional products are reported only when asked for
            required_only = graph.check_products("END-004", root, required_only=True)
            everything = graph.check_products("END-004", root, required_only=False)
            self.assertTrue(set(required_only) <= set(everything))
            self.assertTrue(any("attitude_summary.json" in m for m in everything) and
                            not any("attitude_summary.json" in m for m in required_only))

    def test_resolve_inputs_and_missing_outputs(self):
        graph = self.build(["END-016"])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "END-001" / "output_constellation_optimizer"
            out.mkdir(parents=True)
            for k in (1, 2):
                (out / f"satellite_{k:02d}.json").write_text("{}", encoding="utf-8")
                (out / f"satellite_{k:02d}_ephemeris.csv").write_text("t\n", encoding="utf-8")
            inputs = graph.resolve_inputs("END-016", root)
            self.assertEqual(sorted(inputs), ["satellite_ephemerides", "satellite_orbits", "spacecraft_definition"])
            self.assertEqual(len(inputs["satellite_orbits"]["paths"]), 2)
            self.assertEqual(inputs["spacecraft_definition"]["paths"], [])
            self.assertEqual(inputs["satellite_orbits"]["from"], "END-001")
            self.assertIn("space_safety_summary", graph.missing_outputs("END-016", root))

    def test_a_cycle_is_an_error_with_the_products(self):
        modules = [
            {"module_id": "END-901", "consumes": [{"product": "b_out", "required": True}], "produces": [{"product": "a_out", "path": "a.json"}]},
            {"module_id": "END-902", "consumes": [{"product": "a_out", "required": True}], "produces": [{"product": "b_out", "path": "b.json"}]},
        ]
        registry = Registry.from_modules(modules)
        with self.assertRaises(WorkflowGraphError) as ctx:
            WorkflowGraph(registry, list(registry.nodes)).order()
        self.assertIn("a_out", str(ctx.exception))
        self.assertTrue(any("cycle" in issue for issue in registry.validate_schema()))

    def test_duplicate_producer_and_orphan_product_are_schema_issues(self):
        modules = [
            {"module_id": "END-901", "execution": {"runner_module": "r", "runner_function": "f"},
             "produces": [{"product": "p", "path": "a.json"}], "consumes": [{"product": "ghost", "required": False}]},
            {"module_id": "END-902", "execution": {"runner_module": "r", "runner_function": "f"},
             "produces": [{"product": "p", "path": "b.json"}]},
        ]
        issues = Registry.from_modules(modules).validate_schema()
        self.assertTrue(any("more than one producer" in i for i in issues))
        self.assertTrue(any("ghost" in i for i in issues))

    def test_planning_view_is_short(self):
        view = self.registry.planning_view()
        self.assertLessEqual(len(view), PLANNING_VIEW_LIMIT, len(view))
        self.assertIn("END-004", view)
        self.assertNotIn("END-008", view)        # not integrated
        self.assertEqual(len(view.splitlines()), 8)

    def test_graph_json(self):
        data = self.build(["END-007"]).to_json()
        self.assertEqual(data["order"], ["END-006/initial", "END-001", "END-003", "END-007", "END-006/final"])
        self.assertEqual(data["issues"], [])
        self.assertEqual({n["id"] for n in data["nodes"]}, set(data["order"]))


if __name__ == "__main__":
    unittest.main()

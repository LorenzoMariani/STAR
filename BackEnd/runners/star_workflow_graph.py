"""STAR workflow graph (phase B, 2026-10-21): one dependency source for the whole platform.

Modules declare the products they consume and produce in their registry YAML (``produces`` / ``consumes``, optional
``phases`` for END-006 and ``always_in_workflow``). The graph derived from them is used by the planner, the user edits of the
workflow, the ordering, the blocking of the modules that miss their data, the runner inputs, the planner prompt and CI.

Pure Python (PyYAML only): importable by the app, the runner tests and CI.
"""
from __future__ import annotations

import glob
import heapq
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

import yaml

# Keys of the old dependency model; the registry must not use them any more (CI checks it).
REMOVED_KEYS = ("upstream_dependencies", "optional_upstream_dependencies", "downstream_dependencies",
                "required_upstream_modules", "optional_upstream_modules", "produced_by")
PHASE_ORDER = {"initial": 0, "final": 1}
LAST_RANK = 900  # a node of the final phase runs after the END modules of its workflow, as the final design of END-006 did


class WorkflowGraphError(RuntimeError):
    """Cycle or inconsistent registry."""


def module_number(module_id: str) -> int:
    match = re.search(r"END-(\d+)", str(module_id).upper())
    return int(match.group(1)) if match else 500


@dataclass
class Node:
    id: str                     # "END-004" or "END-006/initial"
    module_id: str
    phase: str | None
    name: str
    consumes: list[dict[str, Any]] = field(default_factory=list)
    produces: list[dict[str, Any]] = field(default_factory=list)

    @property
    def rank(self) -> tuple[int, int, str]:
        """Execution order key: END number, except that the final phase runs last."""
        if self.phase == "final":
            return (LAST_RANK, PHASE_ORDER["final"], self.id)
        return (module_number(self.module_id), PHASE_ORDER.get(self.phase or "", 0), self.id)

    @property
    def label(self) -> str:
        return f"{self.module_id} ({self.phase} design)" if self.phase else self.module_id


def _as_list(value: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in (value or []) if isinstance(item, dict)]


class Registry:
    """Modules, nodes (module x phase) and the product index."""

    def __init__(self, modules: Iterable[dict[str, Any]]) -> None:
        self.modules: dict[str, dict[str, Any]] = {}
        for module in modules:
            module_id = str(module.get("module_id") or module.get("id") or "").upper()
            if module_id:
                self.modules[module_id] = module
        self.nodes: dict[str, Node] = {}
        self.nodes_of: dict[str, list[str]] = {}
        for module_id, module in self.modules.items():
            for node in self._expand(module_id, module):
                self.nodes[node.id] = node
                self.nodes_of.setdefault(module_id, []).append(node.id)
        self._producers: dict[str, list[str]] = {}
        for node in self.nodes.values():
            for item in node.produces:
                self._producers.setdefault(str(item.get("product", "")), []).append(node.id)

    @classmethod
    def load(cls, registry_dir: str | Path) -> "Registry":
        modules = []
        for path in sorted(Path(registry_dir).glob("*.y*ml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if isinstance(data, dict):
                data["registry_path"] = str(path)
                modules.append(data)
        return cls(modules)

    @classmethod
    def from_modules(cls, modules: Iterable[dict[str, Any]]) -> "Registry":
        return cls(modules)

    @staticmethod
    def _expand(module_id: str, module: dict[str, Any]) -> list[Node]:
        name = str(module.get("module_name") or module.get("name") or module_id)
        phases = module.get("phases")
        if isinstance(phases, dict) and phases:
            return [Node(f"{module_id}/{phase}", module_id, str(phase), name, _as_list((block or {}).get("consumes")),
                         _as_list((block or {}).get("produces")))
                    for phase, block in sorted(phases.items(), key=lambda kv: PHASE_ORDER.get(str(kv[0]), 5))]
        return [Node(module_id, module_id, None, name, _as_list(module.get("consumes")), _as_list(module.get("produces")))]

    # ------------------------------------------------------------------ queries
    def has_contract(self, module_id: str) -> bool:
        """True when the module declares produces/consumes (an integrated module)."""
        return any(node.produces or node.consumes for node in self.nodes_for(module_id))

    def nodes_for(self, module_id: str) -> list[Node]:
        return [self.nodes[n] for n in self.nodes_of.get(str(module_id).upper(), [])]

    def always_in_workflow(self) -> list[str]:
        return [m for m, module in self.modules.items() if module.get("always_in_workflow")]

    def producers_of(self, product: str) -> list[str]:
        return list(self._producers.get(product, []))

    def producer_of(self, product: str) -> str | None:
        producers = self.producers_of(product)
        return producers[0] if producers else None

    def produce_spec(self, product: str) -> dict[str, Any] | None:
        producer = self.producer_of(product)
        if not producer:
            return None
        return next((p for p in self.nodes[producer].produces if p.get("product") == product), None)

    def required_producer_modules(self, module_id: str) -> list[str]:
        """Modules that produce what the module needs (required consumes), END order."""
        found: set[str] = set()
        for node in self.nodes_for(module_id):
            for item in node.consumes:
                if item.get("required"):
                    producer = self.producer_of(str(item.get("product")))
                    if producer:
                        found.add(self.nodes[producer].module_id)
        found.discard(str(module_id).upper())
        return sorted(found, key=module_number)

    def cef_loop(self, module_id: str) -> dict[str, Any]:
        """CEF loop declaration of a module (phase F): ``cef_loop: fixed`` -> {"fixed": True, "rerun_on": []};
        ``cef_loop: {rerun_on: [{product, keys}]}`` -> {"fixed": False, "rerun_on": [...]}; nothing -> no rule."""
        raw = (self.modules.get(str(module_id).upper()) or {}).get("cef_loop")
        if isinstance(raw, str):
            return {"fixed": raw.strip().lower() == "fixed", "rerun_on": []}
        raw = raw if isinstance(raw, dict) else {}
        return {"fixed": bool(raw.get("fixed")) or str(raw.get("mode", "")).lower() == "fixed",
                "rerun_on": [dict(r) for r in (raw.get("rerun_on") or []) if isinstance(r, dict) and r.get("product")]}

    def feedback_edges(self) -> list[tuple[str, str, str]]:
        """(producer node, produced product, product it feeds back to) of the whole registry."""
        return [(n.id, str(p.get("product")), str(p.get("feeds_back_to"))) for n in self.nodes.values() for p in n.produces
                if p.get("feeds_back_to")]

    def consumer_nodes(self, module_id: str) -> list[str]:
        """Nodes that consume a product of the module (any requirement level), execution order."""
        mine = {item.get("product") for node in self.nodes_for(module_id) for item in node.produces}
        out = [n.id for n in self.nodes.values() if n.module_id != str(module_id).upper()
               and any(c.get("product") in mine for c in n.consumes)]
        return sorted(out, key=lambda n: self.nodes[n].rank)

    # ------------------------------------------------------------------ schema validation
    def validate_schema(self) -> list[str]:
        """Issues of the registry itself (CI): removed keys, runner, product index, cycle in the full graph."""
        issues: list[str] = []
        for module_id, module in self.modules.items():
            blob = json.dumps(module, default=str)
            for key in REMOVED_KEYS:
                if re.search(rf'"{key}"\s*:', blob):
                    issues.append(f"{module_id}: removed key '{key}' still in the registry")
            if self.has_contract(module_id):
                if module.get("outputs"):
                    issues.append(f"{module_id}: 'outputs' must be replaced by 'produces'")
                execution = module.get("execution") or {}
                if not (execution.get("runner_module") and execution.get("runner_function")):
                    issues.append(f"{module_id}: integrated module without execution.runner_module/runner_function")
        for product, producers in self._producers.items():
            if len(producers) > 1:
                issues.append(f"product {product} has more than one producer: {', '.join(producers)}")
        for node in self.nodes.values():
            for item in node.consumes:
                product = str(item.get("product", ""))
                if not product:
                    issues.append(f"{node.id}: consumes entry without product")
                elif not self.producers_of(product):
                    issues.append(f"{node.id} consumes {product}, which no module produces")
        for producer, product, target in self.feedback_edges():
            if not self.producers_of(target):
                issues.append(f"{producer}: {product} feeds_back_to {target}, which no module produces")
        try:
            WorkflowGraph(self, list(self.nodes), {}).order()
        except WorkflowGraphError as exc:
            issues.append(str(exc))
        return issues

    # ------------------------------------------------------------------ planner prompt
    def planning_view(self, executable: Callable[[str], bool] | None = None) -> str:
        """One line per executable module for the planner prompt (the graph closes the workflow, the LLM only selects)."""
        lines = []
        for module_id in sorted(self.modules, key=module_number):
            module = self.modules[module_id]
            if not self.has_contract(module_id) or (executable and not executable(module_id)):
                continue
            desc = str(module.get("short_description") or module.get("description") or "").strip()
            desc = re.split(r"(?<=[.;])\s", " ".join(desc.split()), maxsplit=1)[0][:130]
            needs = self.required_producer_modules(module_id)
            feeds = self.consumer_nodes(module_id)
            rules = module.get("activation_rules") or {}
            words = list(rules.get("include_when_any_requirement_contains") or rules.get("keywords") or [])[:7]
            name = str(module.get("module_name") or module_id)
            line = f"{module_id} {name} | {desc}"
            line += f" | needs {', '.join(needs)}" if needs else " | needs nothing"
            if feeds:
                line += f" | feeds {', '.join(feeds)}"
            if words:
                line += " | triggers: " + ", ".join(str(w) for w in words)
            lines.append(line)
        return "\n".join(lines)


class WorkflowGraph:
    """The nodes of one workflow, their order, blocking and product checks."""

    def __init__(self, registry: Registry, node_ids: Iterable[str], reasons: dict[str, str] | None = None,
                 dropped: dict[str, str] | None = None) -> None:
        self.registry = registry
        self.node_ids = list(dict.fromkeys(node_ids))
        self.reasons = dict(reasons or {})      # module id -> why it is in the workflow
        self.dropped = dict(dropped or {})      # module id -> why it was left out

    # ------------------------------------------------------------------ construction
    @classmethod
    def build(cls, registry: Registry, module_ids: Iterable[str], executable: Callable[[str], bool] | None = None,
              requested_reason: str = "requested") -> "WorkflowGraph":
        """Closure over the REQUIRED consumes of the requested modules plus the always_in_workflow ones; modules that are not
        executable are left out (and the modules that need them with them)."""
        reasons: dict[str, str] = {}
        dropped: dict[str, str] = {}
        present: list[str] = []

        def ok(module_id: str) -> bool:
            if not registry.has_contract(module_id):
                dropped.setdefault(module_id, "no produces/consumes in the registry: the module is not integrated in STAR yet")
                return False
            if executable and not executable(module_id):
                dropped.setdefault(module_id, "not executable on this machine")
                return False
            return True

        def add(module_id: str, why: str) -> None:
            if module_id not in present and ok(module_id):
                present.append(module_id)
                reasons[module_id] = why

        for module_id in module_ids:
            add(str(module_id).upper(), requested_reason)
        for module_id in registry.always_in_workflow():
            add(module_id, "always in the STAR chain")
        changed = True
        while changed:
            changed = False
            for module_id in list(present):
                for node in registry.nodes_for(module_id):
                    for item in node.consumes:
                        if not item.get("required"):
                            continue
                        product = str(item.get("product"))
                        producer = registry.producer_of(product)
                        if producer is None:
                            continue
                        producer_module = registry.nodes[producer].module_id
                        if producer_module not in present and producer_module not in dropped:
                            add(producer_module, f"{module_id} needs {product} from {producer_module}")
                            changed = changed or producer_module in present
        # a module whose required producer cannot run cannot run either (fixed point)
        changed = True
        while changed:
            changed = False
            for module_id in list(present):
                missing = [m for m in registry.required_producer_modules(module_id) if m not in present]
                if missing:
                    present.remove(module_id)
                    dropped[module_id] = f"needs {', '.join(missing)}, which cannot run"
                    changed = True
        node_ids = [n for m in present for n in registry.nodes_of[m]]
        return cls(registry, node_ids, reasons, dropped)

    # ------------------------------------------------------------------ views
    @property
    def module_ids(self) -> list[str]:
        out: list[str] = []
        for node_id in self.node_ids:
            module_id = self.registry.nodes[node_id].module_id
            if module_id not in out:
                out.append(module_id)
        return out

    def node(self, node_id: str) -> Node:
        return self.registry.nodes[node_id]

    def order(self) -> list[str]:
        """Topological order of the nodes, ties by END number (the final phase last); a cycle raises."""
        present = set(self.node_ids)
        deps: dict[str, set[str]] = {n: set() for n in present}
        for node_id in present:
            for item in self.node(node_id).consumes:
                for producer in self.registry.producers_of(str(item.get("product"))):
                    if producer in present and producer != node_id:
                        deps[node_id].add(producer)
        heap = [(self.node(n).rank, n) for n in present if not deps[n]]
        heapq.heapify(heap)
        done: list[str] = []
        queued = {n for _, n in heap}
        left = {n: set(d) for n, d in deps.items()}
        while heap:
            _, node_id = heapq.heappop(heap)
            done.append(node_id)
            for other, waiting in left.items():
                waiting.discard(node_id)
                if not waiting and other not in queued:
                    queued.add(other)
                    heapq.heappush(heap, (self.node(other).rank, other))
        if len(done) != len(present):
            stuck = sorted(present - set(done))
            products = sorted({str(item.get("product")) for n in stuck for item in self.node(n).consumes
                               if any(p in stuck for p in self.registry.producers_of(str(item.get("product"))))})
            raise WorkflowGraphError(f"dependency cycle between {', '.join(stuck)} through the products {', '.join(products)}")
        return done

    def upstream(self, node_id: str, required_only: bool = True) -> list[str]:
        """Nodes of the workflow that produce what the node consumes (direct)."""
        present = set(self.node_ids)
        found: list[str] = []
        for item in self.node(node_id).consumes:
            if required_only and not item.get("required"):
                continue
            for producer in self.registry.producers_of(str(item.get("product"))):
                if producer in present and producer != node_id and producer not in found:
                    found.append(producer)
        return sorted(found, key=lambda n: self.node(n).rank)

    def downstream(self, node_id: str, required_only: bool = False) -> list[str]:
        return [n for n in self.node_ids if n != node_id and node_id in self.upstream(n, required_only)]

    # ------------------------------------------------------------------ CEF loop (phase F)
    def feedback_edges(self) -> list[tuple[str, str, str]]:
        """Feedback edges whose producer is in this workflow. They are not dependencies: order() ignores them."""
        present = set(self.node_ids)
        return [e for e in self.registry.feedback_edges() if e[0] in present]

    def fixed_nodes(self) -> list[str]:
        return [n for n in self.node_ids if self.registry.cef_loop(self.node(n).module_id)["fixed"]]

    def consumers_of_product(self, product: str) -> list[str]:
        return [n for n in self.node_ids if any(str(c.get("product")) == product for c in self.node(n).consumes)]

    def affected_by(self, product: str) -> list[str]:
        """Nodes whose results depend on the feedback product: its transitive consumers (required or optional), minus the
        fixed modules (and what only reaches them) and minus the nodes that produce the feedback. Execution order."""
        producers = {p for p, _, target in self.feedback_edges() if target == product}
        fixed = set(self.fixed_nodes())
        found: list[str] = []
        todo = list(self.consumers_of_product(product))
        while todo:
            node_id = todo.pop()
            if node_id in found or node_id in fixed or node_id in producers:
                continue
            found.append(node_id)
            for item in self.node(node_id).produces:
                todo.extend(self.consumers_of_product(str(item.get("product"))))
        return sorted(found, key=lambda n: self.node(n).rank)

    def ancestors(self, node_id: str) -> set[str]:
        """All nodes the node depends on (required or optional consumes), transitively."""
        found: set[str] = set()
        todo = [node_id]
        while todo:
            for up in self.upstream(todo.pop(), required_only=False):
                if up not in found:
                    found.add(up)
                    todo.append(up)
        return found

    def _affected_by_feedback(self) -> set[str]:
        affected: set[str] = set()
        for _, _, target in self.feedback_edges():
            affected |= set(self.affected_by(target))
        return affected

    def loop_nodes(self, criteria_nodes: Iterable[str] = ()) -> list[str]:
        """The nodes the CEF loop re-runs: the producers of the feedback plus the affected nodes that are ancestors of one
        of them or the node of a criterion KPI. Execution order; empty without a feedback edge."""
        producers = {p for p, _, _ in self.feedback_edges()}
        if not producers:
            return []
        wanted = set(producers)
        for p in producers:
            wanted |= self.ancestors(p)
        for n in criteria_nodes:
            if n in self.node_ids:
                wanted |= {n} | self.ancestors(n)
        chosen = (self._affected_by_feedback() & wanted) | producers
        return [n for n in self.order() if n in chosen]

    def post_loop_nodes(self, criteria_nodes: Iterable[str] = ()) -> list[str]:
        """Affected nodes the loop does not re-run: they run once after it, if their trigger fired."""
        inside = set(self.loop_nodes(criteria_nodes))
        affected = self._affected_by_feedback()
        return [n for n in self.order() if n in affected and n not in inside]

    def why(self, module_id: str) -> str:
        return self.reasons.get(module_id, "")

    # ------------------------------------------------------------------ validation
    def validate(self) -> list[str]:
        issues: list[str] = []
        present = set(self.node_ids)
        for node_id in self.node_ids:
            for item in self.node(node_id).consumes:
                product = str(item.get("product"))
                producers = self.registry.producers_of(product)
                if not producers:
                    issues.append(f"{node_id} consumes {product}, which no module produces")
                elif item.get("required") and not any(p in present for p in producers):
                    issues.append(f"{node_id} needs {product} from {self.node(producers[0]).module_id}, which is not in the workflow")
        try:
            self.order()
        except WorkflowGraphError as exc:
            issues.append(str(exc))
        return issues

    # ------------------------------------------------------------------ products on disk
    def _module_root(self, module_id: str, modules_output_root: Path | str) -> Path:
        return Path(modules_output_root) / module_id

    def find_product(self, product: str, modules_output_root: Path | str) -> list[Path]:
        """Existing files of a product (path or glob under modules_output/END-XXX/)."""
        producer = self.registry.producer_of(product)
        spec = self.registry.produce_spec(product)
        if producer is None or spec is None:
            return []
        root = self._module_root(self.node(producer).module_id, modules_output_root)
        pattern = str(spec.get("path", ""))
        if any(ch in pattern for ch in "*?["):
            return sorted(Path(p) for p in glob.glob(str(root / pattern)) if Path(p).is_file())
        path = root / pattern
        return [path] if path.is_file() else []

    def _problems(self, product: str, modules_output_root: Path | str, since: float | None = None) -> list[str]:
        """Why a product is not usable. ``since`` (epoch seconds): an older file is stale (CEF loop: the product of a re-run
        node must have been written by the re-run, not left by an earlier iteration)."""
        spec = self.registry.produce_spec(product) or {}
        found = self.find_product(product, modules_output_root)
        need = int(spec.get("min_count", 1) or 1)
        if len(found) < need:
            return ["not found" if not found else f"{len(found)} file(s) found, {need} expected"]
        problems: list[str] = []
        for path in found:
            if path.stat().st_size <= 0:
                problems.append(f"{path.name} is empty")
                continue
            if since is not None and path.stat().st_mtime < since:
                problems.append(f"{path.name} is older than the re-run (stale product of an earlier iteration)")
                continue
            if str(spec.get("format", "")).lower() == "json":
                try:
                    data = json.loads(path.read_text(encoding="utf-8-sig"))
                except Exception as exc:
                    problems.append(f"{path.name} is not valid JSON ({exc})")
                    continue
                keys = [str(k) for k in (spec.get("required_keys") or [])]
                absent = [k for k in keys if not isinstance(data, dict) or k not in data]
                if absent:
                    problems.append(f"{path.name} lacks the keys {', '.join(absent)}")
        return problems

    def check_products(self, node_id: str, modules_output_root: Path | str, required_only: bool = True) -> list[str]:
        """Missing / unusable consumed products, with a text ready for the log and the step evidence."""
        out: list[str] = []
        node = self.node(node_id)
        for item in node.consumes:
            if required_only and not item.get("required"):
                continue
            product = str(item.get("product"))
            problems = self._problems(product, modules_output_root)
            if not problems:
                continue
            spec = self.registry.produce_spec(product) or {}
            producer = self.registry.producer_of(product)
            producer_module = self.node(producer).module_id if producer else "?"
            file_name = Path(str(spec.get("path", product))).name
            out.append(f"{node.module_id}: missing {file_name} from {producer_module} ({spec.get('path', '?')}): {'; '.join(problems)}")
        return out

    def missing_outputs(self, node_id: str, modules_output_root: Path | str, since: float | None = None) -> list[str]:
        """Guaranteed products of the node that its run did not write (with ``since``: or wrote before that time)."""
        out = []
        for item in self.node(node_id).produces:
            if item.get("guaranteed") and self._problems(str(item.get("product")), modules_output_root, since):
                out.append(str(item.get("product")))
        return out

    def resolve_inputs(self, node_id: str, modules_output_root: Path | str) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for item in self.node(node_id).consumes:
            product = str(item.get("product"))
            producer = self.registry.producer_of(product)
            out[product] = {"from": producer or "", "required": bool(item.get("required")),
                            "paths": [str(p.resolve()) for p in self.find_product(product, modules_output_root)]}
        return out

    # ------------------------------------------------------------------ export
    def to_json(self) -> dict[str, Any]:
        order = self.order()
        return {
            "nodes": [{"id": n, "module_id": self.node(n).module_id, "phase": self.node(n).phase,
                       "reason": self.reasons.get(self.node(n).module_id, ""),
                       "consumes": [{"product": c.get("product"), "required": bool(c.get("required")),
                                     "from": self.registry.producer_of(str(c.get("product")))} for c in self.node(n).consumes],
                       "produces": [p.get("product") for p in self.node(n).produces],
                       "upstream_required": self.upstream(n, True), "upstream_optional": [u for u in self.upstream(n, False)
                                                                                         if u not in self.upstream(n, True)]}
                      for n in order],
            "order": order,
            "dropped": self.dropped,
            "issues": self.validate(),
        }

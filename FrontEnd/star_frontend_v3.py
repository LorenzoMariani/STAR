"""STAR FrontEnd v3 (2026-10-15): star_frontend_v2.py plus END-019 Satellite
Design Component Selector (canonical module, default runner, planner rule,
output folders, live selector API for its results tab). It writes its own
pages (web/star_*_v3.html, from web/star_results_shell_template_v3.html), so
star_frontend_v2.py keeps working unchanged next to it.
"""
from __future__ import annotations

import csv
import html
import inspect
import json
import os
import re
import shutil
import threading
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

import sys

_BACKEND_DIR = Path(__file__).resolve().parent.parent / "BackEnd"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import webview

from modules.module_registry import load_module_registry
from ai.openai_compatible_provider import OpenAICompatibleProvider


ALLOWED_REQUIREMENT_CATEGORIES = [
    "functional",
    "mission",
    "interface",
    "environmental",
    "operational",
    "human factor",
    "physical",
    "product assurance",
    "configuration",
    "design",
    "verification"
]

ALLOWED_REQUIREMENT_STATUSES = [
    "extracted",
    "under_specified",
    "requires_review",
]

ALLOWED_MISSING_INFORMATION_STATUSES = [
    "provided",
    "proposed",
    "requires_user_input",
    "expected_from_upstream",
    "not_applicable",
    "approved",
]

ALLOWED_MISSING_INFORMATION_SOURCES = [
    "mission_document",
    "module_registry_default",
    "module_registry_required_input",
    "upstream_module_output",
    "user_reviewed",
    "not_applicable",
]

ALLOWED_WORKFLOW_STATUSES = [
    "proposed",
    "ready",
    "requires_review",
    "skipped",
    "approved",
]

ALLOWED_EXECUTION_STATUSES = [
    "pending",
    "running",
    "completed",
    "failed",
    "skipped",
    "stopped",
    "approved",
]

CANONICAL_MODULE_CATALOG = [
    {"module_id": "END-001", "module_name": "Constellation Optimizer", "owner": "UNIRM1"},
    {"module_id": "END-002", "module_name": "Constellation Orbit Determination", "owner": "UNIPD"},
    {"module_id": "END-003", "module_name": "Attitude Propagation", "owner": "UNIRM1"},
    {"module_id": "END-004", "module_name": "Power Budget", "owner": "UNIRM1"},
    {"module_id": "END-005", "module_name": "CMG Healt Monitoring", "owner": "TASI-POLIBA"},
    {"module_id": "END-006", "module_name": "Scenario Generation", "owner": "TELESPAZIO"},
    {"module_id": "END-007", "module_name": "Synthetic Data Generation", "owner": "TELESPAZIO"},
    {"module_id": "END-008", "module_name": "Battery Healt Monitorying", "owner": "UNIRM1"},
    {"module_id": "END-009", "module_name": "Solar Array Wings", "owner": "TASI-POLIBA"},
    {"module_id": "END-010", "module_name": "Reflectance Determination", "owner": "UNIRM1"},
    {"module_id": "END-011", "module_name": "Multy-Fidelity Analysis", "owner": "POLITO"},
    {"module_id": "END-012", "module_name": "Degradation of Materials and Structures", "owner": "UNIPA"},
    {"module_id": "END-013", "module_name": "Interaction with Planetary surface", "owner": "POLIMI"},
    {"module_id": "END-014", "module_name": "Robotic Manipulator", "owner": "UNIRM1"},
    {"module_id": "END-015", "module_name": "Flexible Components Health Monitorying", "owner": "UNIRM1"},
    {"module_id": "END-016", "module_name": "Collision Avoidance", "owner": "UNIRM1"},
    {"module_id": "END-017", "module_name": "Clock Anomalies Detection", "owner": "INRIM"},
    {"module_id": "END-018", "module_name": "Components Thermal Analysis", "owner": "TBD"},   # was "ABEP" (SITAEL) until 2026-10-15
    {"module_id": "END-019", "module_name": "Satellite Design Component Selector", "owner": "UNIRM1"},
]


class StarApi:
    """
    STAR desktop backend exposed to the HTML frontend through pywebview.

    This corrected full version includes:
    - registry-driven Module Bay;
    - upload mission request document;
    - rule-based and local-LLM requirement extraction;
    - editable requirement review;
    - registry-driven missing parameter analysis;
    - editable missing parameter review and assumption approval;
    - registry-driven workflow proposal;
    - editable workflow review and workflow approval.

    The workflow buttons are now driven by backend state:
    once assumptions are approved, Propose Workflow becomes available.
    """

    def __init__(self):
        self.project_dir = Path(__file__).resolve().parent
        self.data_dir = self.project_dir.parent / "Input" / "input_base_knowledge"
        self.star_root = self.resolve_star_root()
        self.registry_dir = self.data_dir / "registry"
        self.outputs_dir = self.resolve_output_root()
        self.config_dir = self.data_dir / "config"

        self.outputs_dir.mkdir(parents=True, exist_ok=True)
        self.config_dir.mkdir(exist_ok=True)

        self.modules = self.apply_canonical_module_catalog(load_module_registry(self.registry_dir))
        self.logs: list[str] = []

        self.current_run_id: str | None = None
        self.current_run_path: Path | None = None

        self.uploaded_text: str | None = None
        self.input_document_filename: str | None = None
        self.input_document_original_path: str | None = None
        self.input_document_saved_relative_path: str | None = None
        self.input_document_saved_absolute_path: str | None = None

        self.requirements: list[dict[str, Any]] = []
        self.requirements_extraction_mode: str | None = None
        self.requirements_review_status: str = "not_available"

        self.missing_information: list[dict[str, Any]] = []
        self.missing_information_review_status: str = "not_available"
        self.assumptions_approved: bool = False

        self.workflow_steps: list[dict[str, Any]] = []
        self.workflow_review_status: str = "not_available"
        self.workflow_approved: bool = False

        self.execution_results: list[dict[str, Any]] = []
        self.execution_review_status: str = "not_available"
        self.execution_approved: bool = False
        self.execution_running: bool = False
        self.execution_error: str | None = None
        self.execution_result_payload: dict[str, Any] | None = None
        self.execution_thread: threading.Thread | None = None
        self.execution_stop_event = threading.Event()
        self.execution_stop_requested: bool = False
        self.active_module_name: str | None = None
        self.active_module_id: str | None = None

        self.report_manifest: list[dict[str, Any]] = []
        self.report_status: str = "not_available"

        self.ai_config = self.load_ai_config()
        self.local_llm_provider: OpenAICompatibleProvider | None = None

        self.add_log("SYSTEM", "STAR webview backend initialized.")
        self.add_log("SYSTEM", f"Registry folder: {self.registry_dir}")
        self.add_log("SYSTEM", f"STAR root: {self.star_root}")
        self.add_log("SYSTEM", f"Output root: {self.outputs_dir}")
        self.add_log("SYSTEM", f"Loaded modules: {len(self.modules)}")
        self.add_log("SYSTEM", "Canonical END-001 ... END-018 module catalog applied.")
        self.add_log("SYSTEM", "Waiting for mission request document.")

    # ------------------------------------------------------------------
    # General state and logging
    # ------------------------------------------------------------------
    def resolve_star_root(self) -> Path:
        """Return the external STAR project root used for shared module I/O.

        Preferred location on the development workstation:
            C:/Users/s5oss/Desktop/software_s5lab/STAR

        The path can be overridden with STAR_PROJECT_ROOT.  When the app is
        launched from STAR/STAR-ORCHESTRATOR/star_cef, the ancestor named
        "STAR" is selected automatically.
        """
        env_root = os.environ.get("STAR_PROJECT_ROOT", "").strip()
        if env_root:
            return Path(env_root).expanduser().resolve()

        for candidate in [self.project_dir, *self.project_dir.parents]:
            if candidate.name.lower() == "star":
                return candidate.resolve()

        # Fallback for the expected local layout:
        # STAR/STAR-ORCHESTRATOR/star_cef/app_webview.py
        try:
            return self.project_dir.parents[1].resolve()
        except IndexError:
            return self.project_dir.resolve()

    def resolve_output_root(self) -> Path:
        """Return the central output folder for all STAR runs and modules."""
        env_output = os.environ.get("STAR_OUTPUT_ROOT", "").strip()
        if env_output:
            return Path(env_output).expanduser().resolve()
        return (self.star_root / "Output").resolve()

    def _timestamp(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    def add_log(self, level: str, message: str) -> str:
        line = f"[{self._timestamp()}] [{level}] {message}"
        self.logs.append(line)
        return line

    def format_duration(self, seconds: float | None) -> str:
        if seconds is None:
            return "unknown duration"
        seconds = max(0.0, float(seconds))
        if seconds < 1.0:
            return f"{seconds * 1000:.0f} ms"
        if seconds < 60.0:
            return f"{seconds:.2f} s"
        minutes, remaining = divmod(seconds, 60.0)
        if minutes < 60.0:
            return f"{int(minutes)} min {remaining:.1f} s"
        hours, minutes = divmod(minutes, 60.0)
        return f"{int(hours)} h {int(minutes)} min {remaining:.1f} s"

    def get_initial_state(self) -> dict[str, Any]:
        return {
            "app_name": "STAR-Local Desktop App",
            "subtitle": "Space mission Twin for Architecture Representation",
            "modules": self.modules,
            "logs": self.logs,
            "run": self.get_run_state(),
            "requirements": self.requirements,
            "requirements_review_status": self.requirements_review_status,
            "missing_information": self.missing_information,
            "missing_information_review_status": self.missing_information_review_status,
            "assumptions_approved": self.assumptions_approved,
            "workflow": self.workflow_steps,
            "workflow_review_status": self.workflow_review_status,
            "workflow_approved": self.workflow_approved,
            "execution_results": self.execution_results,
            "execution_review_status": self.execution_review_status,
            "execution_approved": self.execution_approved,
            "execution_running": self.execution_running,
            "execution_error": self.execution_error,
            "execution_stop_requested": self.execution_stop_requested,
            "active_module_name": self.active_module_name,
            "active_module_id": self.active_module_id,
            "report_manifest": self.report_manifest,
            "report_status": self.report_status,
            "allowed_requirement_categories": ALLOWED_REQUIREMENT_CATEGORIES,
            "allowed_requirement_statuses": ALLOWED_REQUIREMENT_STATUSES,
            "allowed_missing_information_statuses": ALLOWED_MISSING_INFORMATION_STATUSES,
            "allowed_missing_information_sources": ALLOWED_MISSING_INFORMATION_SOURCES,
            "allowed_workflow_statuses": ALLOWED_WORKFLOW_STATUSES,
            "allowed_execution_statuses": ALLOWED_EXECUTION_STATUSES,
            "module_names": self.get_module_names(),
        }

    def get_run_state(self) -> dict[str, Any]:
        return {
            "current_run_id": self.current_run_id,
            "current_run_path": str(self.current_run_path) if self.current_run_path else None,
            "star_root": str(getattr(self, "star_root", "")),
            "outputs_root": str(getattr(self, "outputs_dir", "")),
            "modules_output_root": str((self.current_run_path / "modules_output") if self.current_run_path else ""),
            "input_document_filename": self.input_document_filename,
            "input_document_original_path": self.input_document_original_path,
            "input_document_saved_relative_path": self.input_document_saved_relative_path,
            "input_document_saved_absolute_path": self.input_document_saved_absolute_path,
        }

    def get_source_document_metadata(self) -> dict[str, str]:
        return {
            "source_document": "mission_request_document",
            "source_document_filename": self.input_document_filename or "unknown",
            "source_document_original_path": self.input_document_original_path or "unknown",
            "source_document_saved_relative_path": self.input_document_saved_relative_path or "unknown",
            "source_document_saved_absolute_path": self.input_document_saved_absolute_path or "unknown",
        }

    def get_module_names(self) -> list[str]:
        return [module.get("module_name", module.get("module_id", "unknown module")) for module in self.modules]

    def get_module_by_name(self, module_name: str) -> dict[str, Any] | None:
        for module in self.modules:
            if module.get("module_name") == module_name:
                return module
        return None

    def get_module_order_score(self, module: dict[str, Any]) -> int:
        module_id = str(module.get("module_id", "")).upper()
        match = re.search(r"END-(\d+)", module_id)
        if match:
            return int(match.group(1))

        upstream_dependencies = module.get("execution", {}).get("upstream_dependencies", []) or []
        return 100 + len(upstream_dependencies) * 10

    def apply_canonical_module_catalog(self, loaded_modules: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Force the Module Bay to use the official END-001 ... END-018 order.

        If a module already exists in registry/*.yaml, its technical metadata
        (inputs, outputs, capabilities, execution rules) is preserved. The
        canonical catalog only overrides module_id, module_name, owner and
        display order. Missing YAML entries are represented as lightweight
        placeholder modules so the full federation remains visible in the GUI.
        """
        loaded_by_id: dict[str, dict[str, Any]] = {}
        loaded_by_name: dict[str, dict[str, Any]] = {}

        for module in loaded_modules or []:
            module_id = str(module.get("module_id", module.get("id", ""))).strip()
            module_name = str(module.get("module_name", module.get("name", ""))).strip()
            if module_id:
                loaded_by_id[module_id] = module
            if module_name:
                loaded_by_name[module_name.lower()] = module

        # Backward-compatible aliases for the YAML files already used in the MVP.
        alias_by_id = {
            "END-001": ["constellation optimizer", "Constellation Optimizer"],
            "END-003": ["attitude propagation", "Attitude Propagation"],
            "END-007": ["synthetic data generation", "Synthetic Data Generation"],
            "END-008": ["battery healt monitoring", "Battery Health Monitoring"],
        }

        canonical_modules: list[dict[str, Any]] = []

        for item in CANONICAL_MODULE_CATALOG:
            module_id = item["module_id"]
            canonical_name = item["module_name"]
            owner = item["owner"]

            source = loaded_by_id.get(module_id)
            if source is None:
                for alias in alias_by_id.get(module_id, []):
                    source = loaded_by_name.get(alias.lower())
                    if source is not None:
                        break

            if source is not None:
                module = dict(source)
            else:
                module = {
                    "module_type": "digital_twin_module",
                    "module_version": "0.1.0",
                    "description": f"Placeholder registry entry for {canonical_name}.",
                    "capabilities": [],
                    "required_inputs": [],
                    "outputs": [],
                    "execution": {
                        "estimated_runtime": 1,
                        "execution_mode": "not_connected_yet",
                        "upstream_dependencies": [],
                        "downstream_dependencies": [],
                    },
                }

            module["module_id"] = module_id
            module["id"] = module_id
            module["module_name"] = canonical_name
            module["name"] = canonical_name
            module["owner"] = owner
            module["status"] = "Idle"
            module.setdefault("required_inputs", [])
            module.setdefault("outputs", [])
            module.setdefault("capabilities", [])
            execution_cfg = module.setdefault("execution", {})

            # Default real runners for the modules already integrated in STAR.
            # This avoids placeholder execution when the registry YAML lacks
            # execution.runner_module / execution.runner_function metadata.
            default_runner_by_id = {
                "END-001": ("runners.end001_runner", "run_end001"),
                "END-003": ("runners.end003_runner", "run_end003"),
                "END-004": ("runners.end004_runner", "run_end004"),
                "END-007": ("runners.end007_runner", "run_end007"),
                "END-010": ("runners.end010_runner", "run_end010"),
                "END-018": ("runners.end018_runner", "run_end018"),
                "END-019": ("runners.end019_runner", "run_end019"),
            }
            if module_id in default_runner_by_id:
                runner_module, runner_function = default_runner_by_id[module_id]
                if not execution_cfg.get("runner_module") and not execution_cfg.get("python_module"):
                    execution_cfg["runner_module"] = runner_module
                if not execution_cfg.get("runner_function") and not execution_cfg.get("function"):
                    execution_cfg["runner_function"] = runner_function

            canonical_modules.append(module)

        return canonical_modules


    # ------------------------------------------------------------------
    # Module status API
    # ------------------------------------------------------------------
    def get_modules(self) -> list[dict[str, Any]]:
        return self.modules

    def set_module_status(self, module_id: str, status: str) -> dict[str, Any]:
        allowed_statuses = {"Idle", "Ready", "Running", "Completed", "Error", "Stopped"}

        if status not in allowed_statuses:
            return {"ok": False, "error": f"Unsupported status: {status}", "modules": self.modules}

        for module in self.modules:
            if module["module_id"] == module_id:
                module["status"] = status
                log = self.add_log("SYSTEM", f"{module['module_name']} ({module_id}) status set to {status}.")
                return {"ok": True, "modules": self.modules, "logs": self.logs, "log": log}

        return {"ok": False, "error": f"Module not found: {module_id}", "modules": self.modules}

    def set_all_modules_ready(self) -> dict[str, Any]:
        for module in self.modules:
            module["status"] = "Ready"

        self.add_log("SYSTEM", "Development test: all modules set to Ready.")
        return {"ok": True, "modules": self.modules, "logs": self.logs}

    def reset_modules(self) -> dict[str, Any]:
        for module in self.modules:
            module["status"] = "Idle"

        self.add_log("SYSTEM", "Module states reset to Idle.")
        return {"ok": True, "modules": self.modules, "logs": self.logs}

    def run_visual_demo(self) -> dict[str, Any]:
        sequence = []

        for module in self.modules:
            sequence.append({"module_id": module["module_id"], "status": "Ready"})

        for module in self.modules:
            sequence.append({"module_id": module["module_id"], "status": "Running"})
            sequence.append({"module_id": module["module_id"], "status": "Completed"})

        self.add_log("SYSTEM", "Visual execution demo sequence generated.")
        return {"ok": True, "sequence": sequence, "logs": self.logs}

    # ------------------------------------------------------------------
    # Run management and upload
    # ------------------------------------------------------------------
    def create_run_folder(self) -> None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.current_run_id = f"RUN_{timestamp}"
        self.current_run_path = self.outputs_dir / self.current_run_id

        for subfolder in ["input", "intermediate", "planning", "module_inputs", "modules_output", "reports", "logs"]:
            (self.current_run_path / subfolder).mkdir(parents=True, exist_ok=True)

    def reset_downstream_from_requirements(self) -> None:
        self.missing_information = []
        self.missing_information_review_status = "not_available"
        self.assumptions_approved = False
        self.workflow_steps = []
        self.workflow_review_status = "not_available"
        self.workflow_approved = False

    def reset_downstream_from_assumptions(self) -> None:
        self.workflow_steps = []
        self.workflow_review_status = "not_available"
        self.workflow_approved = False
        self.reset_downstream_from_workflow()

    def reset_downstream_from_workflow(self) -> None:
        self.execution_results = []
        self.execution_review_status = "not_available"
        self.execution_approved = False
        self.reset_downstream_from_execution()

    def reset_downstream_from_execution(self) -> None:
        self.report_manifest = []
        self.report_status = "not_available"

    def reset_run_state_after_new_upload(self) -> None:
        self.uploaded_text = None
        self.input_document_filename = None
        self.input_document_original_path = None
        self.input_document_saved_relative_path = None
        self.input_document_saved_absolute_path = None

        self.requirements = []
        self.requirements_extraction_mode = None
        self.requirements_review_status = "not_available"

        self.missing_information = []
        self.missing_information_review_status = "not_available"
        self.assumptions_approved = False

        self.workflow_steps = []
        self.workflow_review_status = "not_available"
        self.workflow_approved = False

        self.execution_results = []
        self.execution_review_status = "not_available"
        self.execution_approved = False
        self.execution_error = None
        self.execution_stop_requested = False
        self.active_module_name = None
        self.active_module_id = None
        if hasattr(self, "execution_stop_event"):
            self.execution_stop_event.clear()

        self.report_manifest = []
        self.report_status = "not_available"

        for module in self.modules:
            module["status"] = "Idle"

    def read_document_text(self, source_path: Path) -> str:
        """Extract the plain text of a mission request document.

        Supports .docx (via python-docx: paragraphs, then table cells, in
        document order) in addition to plain UTF-8 text files (.txt, .md,
        ...). Raises ValueError with a user-facing message on failure so
        callers can surface it without leaking a raw traceback.
        """
        if source_path.suffix.lower() == ".docx":
            try:
                import docx  # python-docx
            except ImportError as exc:
                raise ValueError(
                    "Reading .docx files requires the 'python-docx' package. "
                    "Install it with: pip install python-docx"
                ) from exc
            try:
                document = docx.Document(str(source_path))
            except Exception as exc:
                raise ValueError(f"The selected .docx file could not be opened: {exc}") from exc

            parts = [p.text for p in document.paragraphs if p.text.strip()]
            for table in document.tables:
                for row in table.rows:
                    cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                    if cells:
                        parts.append(" | ".join(cells))
            text = "\n".join(parts)
            if not text.strip():
                raise ValueError("The selected .docx file does not contain any extractable text.")
            return text

        try:
            return source_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("The selected file could not be read as UTF-8 text.") from exc

    def upload_document(self, custom_run_folder_name: str | None = None) -> dict[str, Any]:
        window = webview.windows[0]

        file_paths = window.create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=False,
            file_types=("Word documents (*.docx)", "Text files (*.txt;*.md)", "All files (*.*)"),
        )

        if not file_paths:
            return {"ok": False, "cancelled": True, "message": "Upload cancelled."}

        source_path = Path(file_paths[0])

        try:
            text = self.read_document_text(source_path)
        except ValueError as exc:
            return {
                "ok": False,
                "error": str(exc),
                "logs": self.logs,
            }

        self.create_run_folder(custom_run_folder_name)
        self.reset_run_state_after_new_upload()

        assert self.current_run_path is not None
        destination = self.current_run_path / "input" / source_path.name
        shutil.copy2(source_path, destination)

        self.uploaded_text = text
        self.input_document_filename = source_path.name
        self.input_document_original_path = str(source_path)
        self.input_document_saved_relative_path = destination.relative_to(self.current_run_path).as_posix()
        self.input_document_saved_absolute_path = str(destination)

        self.add_log("SYSTEM", "New run created.")
        self.add_log("SYSTEM", f"Current run ID: {self.current_run_id}")
        self.add_log("SYSTEM", f"Document uploaded: {source_path.name}")
        self.add_log("SYSTEM", "Document content extracted successfully.")

        return {
            "ok": True,
            **self.state_payload(),
            "message": "Mission request received. Requirements can now be extracted.",
        }

    def state_payload(self) -> dict[str, Any]:
        return {
            "run": self.get_run_state(),
            "modules": self.modules,
            "requirements": self.requirements,
            "requirements_review_status": self.requirements_review_status,
            "missing_information": self.missing_information,
            "missing_information_review_status": self.missing_information_review_status,
            "assumptions_approved": self.assumptions_approved,
            "workflow": self.workflow_steps,
            "workflow_review_status": self.workflow_review_status,
            "workflow_approved": self.workflow_approved,
            "execution_results": self.execution_results,
            "execution_review_status": self.execution_review_status,
            "execution_approved": self.execution_approved,
            "execution_running": self.execution_running,
            "execution_error": self.execution_error,
            "execution_stop_requested": self.execution_stop_requested,
            "active_module_name": self.active_module_name,
            "active_module_id": self.active_module_id,
            "report_manifest": self.report_manifest,
            "report_status": self.report_status,
            "logs": self.logs,
        }

    # ------------------------------------------------------------------
    # AI configuration and provider
    # ------------------------------------------------------------------
    def load_ai_config(self) -> dict[str, Any]:
        config_path = self.config_dir / "ai_config.json"

        default_config = {
            "llm_provider": "openai_compatible",
            "requirement_extraction_mode": "rule_based",
            "openai_compatible": {
                "base_url": "http://localhost:11434/v1",
                "api_key": "local",
                "model": "qwen2.5:7b",
                "temperature": 0.1,
                "timeout_s": 300,
                "max_output_tokens": 2200,
            },
        }

        if not config_path.exists():
            config_path.write_text(json.dumps(default_config, indent=4), encoding="utf-8")
            return default_config

        try:
            loaded = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            return default_config

        merged = default_config.copy()
        merged.update({k: v for k, v in loaded.items() if k != "openai_compatible"})
        merged["openai_compatible"] = default_config["openai_compatible"].copy()
        merged["openai_compatible"].update(loaded.get("openai_compatible", {}))
        return merged

    def get_local_llm_provider(self) -> OpenAICompatibleProvider:
        if self.local_llm_provider is not None:
            return self.local_llm_provider

        llm_config = self.ai_config.get("openai_compatible", {})

        self.local_llm_provider = OpenAICompatibleProvider(
            base_url=llm_config.get("base_url", "http://localhost:11434/v1"),
            api_key=llm_config.get("api_key", "local"),
            model=llm_config.get("model", "qwen2.5:7b"),
            temperature=llm_config.get("temperature", 0.1),
            timeout_s=llm_config.get("timeout_s", 300),
            max_output_tokens=llm_config.get("max_output_tokens", 2200),
        )

        self.add_log(
            "SYSTEM",
            "Local LLM provider initialized: "
            f"model={llm_config.get('model', 'qwen2.5:7b')}, "
            f"base_url={llm_config.get('base_url', 'http://localhost:11434/v1')}",
        )

        return self.local_llm_provider

    # ------------------------------------------------------------------
    # Requirement extraction and review
    # ------------------------------------------------------------------
    def extract_requirements(self, mode: str) -> dict[str, Any]:
        if not self.uploaded_text:
            return {"ok": False, "error": "No mission request document has been uploaded yet.", "logs": self.logs}

        mode = mode or "Rule-based MVP"
        self.add_log("AI", f"Extracting candidate requirements using mode: {mode}.")

        try:
            if mode == "Local LLM via Ollama":
                provider = self.get_local_llm_provider()
                requirements = provider.extract_requirements(self.uploaded_text)
            else:
                requirements = self.rule_based_requirement_extraction(self.uploaded_text)
        except Exception as exc:
            self.add_log("ERROR", f"Requirement extraction failed: {exc}")
            return {"ok": False, "error": str(exc), "logs": self.logs}

        self.requirements = requirements
        self.requirements_extraction_mode = mode
        self.requirements_review_status = "not_reviewed"
        self.reset_downstream_from_requirements()

        active_path = self.save_requirements_json(
            requirements=requirements,
            extraction_mode=mode,
            review_status="not_reviewed",
            output_filename="requirements.json",
            source="requirement_extraction",
        )

        extracted_path = self.save_requirements_json(
            requirements=requirements,
            extraction_mode=mode,
            review_status="not_reviewed",
            output_filename="requirements_extracted.json",
            source="requirement_extraction_raw_output",
        )

        self.add_log("AI", f"{len(requirements)} candidate requirements extracted.")
        self.add_log("SYSTEM", f"Active requirements saved: {active_path}")
        self.add_log("SYSTEM", f"Raw extracted requirements saved: {extracted_path}")

        return {
            "ok": True,
            **self.state_payload(),
            "requirements_path": str(active_path),
            "requirements_extracted_path": str(extracted_path),
            "message": f"{len(requirements)} candidate requirements extracted using {mode}.",
        }

    def save_reviewed_requirements(self, reviewed_requirements: list[dict[str, Any]]) -> dict[str, Any]:
        if not self.current_run_path:
            return {"ok": False, "error": "No active run is available.", "logs": self.logs}

        try:
            normalized = self.validate_and_normalize_reviewed_requirements(reviewed_requirements)
        except Exception as exc:
            self.add_log("ERROR", f"Reviewed requirements validation failed: {exc}")
            return {"ok": False, "error": str(exc), "logs": self.logs}

        self.requirements = normalized
        self.requirements_review_status = "reviewed_by_user"
        self.reset_downstream_from_requirements()

        reviewed_path = self.save_requirements_json(
            requirements=normalized,
            extraction_mode=self.requirements_extraction_mode or "unknown",
            review_status="reviewed_by_user",
            output_filename="requirements_reviewed.json",
            source="user_reviewed_requirements",
        )

        active_path = self.save_requirements_json(
            requirements=normalized,
            extraction_mode=self.requirements_extraction_mode or "unknown",
            review_status="reviewed_by_user",
            output_filename="requirements.json",
            source="active_requirements_after_user_review",
        )

        self.add_log("USER", "Requirements table reviewed and saved by user.")
        self.add_log("SYSTEM", f"Reviewed requirements saved: {reviewed_path}")
        self.add_log("SYSTEM", f"Active requirements updated: {active_path}")
        self.add_log("SYSTEM", "Downstream states invalidated after requirement review.")

        return {
            "ok": True,
            **self.state_payload(),
            "requirements_reviewed_path": str(reviewed_path),
            "requirements_path": str(active_path),
            "message": "Reviewed requirements saved. The reviewed table is now the active requirement set for downstream steps.",
        }

    def validate_and_normalize_reviewed_requirements(self, reviewed_requirements: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not isinstance(reviewed_requirements, list):
            raise ValueError("Reviewed requirements payload must be a list.")

        normalized = []
        seen_ids = set()

        for index, req in enumerate(reviewed_requirements, start=1):
            req_id = str(req.get("id", "")).strip()
            text = str(req.get("text", "")).strip()
            category = str(req.get("category", "")).strip()
            status = str(req.get("status", "")).strip()
            source = str(req.get("source", "mission_request_document")).strip() or "mission_request_document"

            if not req_id:
                raise ValueError(f"Requirement at row {index} has an empty ID.")
            if req_id in seen_ids:
                raise ValueError(f"Duplicate requirement ID found: {req_id}")
            if not text:
                raise ValueError(f"Requirement {req_id} has empty requirement text.")
            if category not in ALLOWED_REQUIREMENT_CATEGORIES:
                raise ValueError(f"Requirement {req_id} has invalid category '{category}'.")
            if status not in ALLOWED_REQUIREMENT_STATUSES:
                raise ValueError(f"Requirement {req_id} has invalid status '{status}'.")

            confidence = req.get("confidence", None)
            if confidence in {"", "-", None}:
                confidence_value = None
            else:
                try:
                    confidence_value = max(0.0, min(1.0, float(confidence)))
                except (TypeError, ValueError):
                    confidence_value = None

            seen_ids.add(req_id)

            normalized_req = {
                "id": req_id,
                "text": text,
                "category": category,
                "status": status,
                "source": source,
                "reviewed_by_user": True,
            }

            if confidence_value is not None:
                normalized_req["confidence"] = confidence_value

            if isinstance(req.get("quality_flags"), list):
                normalized_req["quality_flags"] = req.get("quality_flags")

            if req.get("standard_reference"):
                normalized_req["standard_reference"] = str(req.get("standard_reference"))

            normalized.append(normalized_req)

        return normalized

    def get_llm_provider_label(self, extraction_mode: str) -> str:
        if extraction_mode == "Local LLM via Ollama":
            llm_config = self.ai_config.get("openai_compatible", {})
            return f"openai_compatible:{llm_config.get('model', 'unknown_model')}"
        return "none"

    def save_requirements_json(
        self,
        requirements: list[dict[str, Any]],
        extraction_mode: str,
        review_status: str,
        output_filename: str,
        source: str,
    ) -> Path:
        if not self.current_run_path:
            raise RuntimeError("No active run folder is available.")

        output_path = self.current_run_path / "intermediate" / output_filename

        with output_path.open("w", encoding="utf-8") as file:
            json.dump(
                {
                    "run_id": self.current_run_id,
                    "generated_at": datetime.now().isoformat(),
                    **self.get_source_document_metadata(),
                    "source": source,
                    "extraction_mode": extraction_mode,
                    "llm_provider": self.get_llm_provider_label(extraction_mode),
                    "review_status": review_status,
                    "allowed_categories": ALLOWED_REQUIREMENT_CATEGORIES,
                    "allowed_statuses": ALLOWED_REQUIREMENT_STATUSES,
                    "requirements": requirements,
                },
                file,
                indent=4,
            )

        return output_path

    def normalize_text(self, text: str) -> str:
        normalized = unicodedata.normalize("NFKD", text)
        normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        return normalized.lower().strip()

    def end018_thermal_requested(self, normalized_text: str) -> bool:
        """END-018 domain: a CubeSat (named, or a 1U/3U/6U/12U class) whose thermal
        behaviour is asked for. Outside it (larger satellites) the module would only
        report that the mission is out of scope, so it is not planned."""
        cubesat = "cubesat" in normalized_text or re.search(r"\b(1|3|6|12)\s*-?\s*u\b(?!\w)", normalized_text) is not None
        thermal = any(token in normalized_text for token in [
            "thermal", "temperature", "overheat", "heat dissipation", "heat load", "termic", "temperatur",
        ])
        return cubesat and thermal

    def end019_design_requested(self, normalized_text: str) -> bool:
        """END-019 domain: a CubeSat (named, or a 1U/3U/6U/12U class) whose platform
        components or subsystems are to be chosen; used by the consistency check of
        LLM plans (the rule-based planner has its own, broader keyword list)."""
        cubesat = "cubesat" in normalized_text or re.search(r"\b(1|3|6|12)\s*-?\s*u\b(?!\w)", normalized_text) is not None
        design = any(token in normalized_text for token in [
            "component", "subsystem", "bill of materials", "satellite design", "platform design", "off-the-shelf", "datasheet",
        ])
        return cubesat and design

    def rule_based_requirement_extraction(self, text: str) -> list[dict[str, Any]]:
        normalized_text = self.normalize_text(text)
        requirements: list[dict[str, Any]] = []

        def contains_any(keywords: list[str]) -> bool:
            return any(keyword in normalized_text for keyword in keywords)

        def add_requirement(requirement_text: str, category: str, status: str) -> None:
            requirement_text = requirement_text.strip()
            if " shall " not in f" {requirement_text.lower()} ":
                requirement_text = f"The system shall {requirement_text[0].lower() + requirement_text[1:]}"
            if not requirement_text.endswith("."):
                requirement_text += "."
            if any(req["text"] == requirement_text for req in requirements):
                return
            requirements.append(
                {
                    "id": f"REQ-{len(requirements) + 1:03d}",
                    "text": requirement_text,
                    "category": category,
                    "status": status,
                    "source": "mission_request_document",
                    "standard_reference": "ECSS-E-ST-10-06C-inspired",
                }
            )

        if contains_any(["volcanic", "volcano", "etna", "eruptive"]):
            if "etna" in normalized_text:
                add_requirement("Monitor volcanic activity over Mount Etna", "mission", "extracted")
            else:
                add_requirement("Monitor volcanic activity over the target area", "mission", "under_specified")

        if contains_any(["agricultural", "agriculture", "vegetation", "crop"]):
            if "southern italy" in normalized_text:
                add_requirement("Provide Earth observation imaging of agricultural areas in Southern Italy", "mission", "extracted")
            else:
                add_requirement("Provide Earth observation imaging of agricultural areas", "mission", "under_specified")

        if "vegetation monitoring" in normalized_text or contains_any(["vegetation index", "ndvi"]):
            add_requirement("Support vegetation monitoring over the agricultural target areas", "functional", "extracted")

        if (
            contains_any(["earth observation", "eo mission", "earth-observation"])
            and "monitor" in normalized_text
            and not contains_any(["volcanic", "volcano", "etna", "agricultural", "agriculture", "vegetation"])
        ):
            if "target area" in normalized_text:
                add_requirement("Monitor the specified target area with a preliminary Earth observation mission", "mission", "under_specified")
            else:
                add_requirement("Monitor the specified target with a preliminary Earth observation mission", "mission", "requires_review")

        if "optical" in normalized_text:
            add_requirement("Use an optical Earth observation payload", "design", "extracted")
        if "multispectral" in normalized_text:
            add_requirement("Use a multispectral Earth observation payload", "design", "extracted")
        if contains_any(["radar", "sar"]):
            add_requirement("Use a radar Earth observation payload", "design", "extracted")

        if "weekly" in normalized_text:
            add_requirement("Provide weekly acquisitions over the target area", "functional", "extracted")
        if "frequent revisit" in normalized_text or "revisit" in normalized_text:
            add_requirement("Provide frequent revisit over the target area", "functional", "under_specified")
        if "frequent acquisitions" in normalized_text:
            add_requirement("Provide frequent acquisitions over the target area", "functional", "under_specified")

        if "acquisition schedules" in normalized_text or "acquisition schedule" in normalized_text:
            add_requirement("Generate preliminary acquisition schedules", "functional", "extracted")
        if "acquisition opportunities" in normalized_text or "data acquisition opportunities" in normalized_text:
            add_requirement("Generate acquisition opportunities over the target area", "functional", "extracted")
        if "data acquisition opportunities" in normalized_text and "assessment" in normalized_text:
            add_requirement("Perform a preliminary assessment of data acquisition opportunities", "functional", "extracted")
        if "identify missing mission parameters" in normalized_text or "missing mission parameters" in normalized_text:
            add_requirement("Identify missing mission parameters required to mature the preliminary concept", "functional", "extracted")
        if "first feasibility assessment" in normalized_text or "preliminary feasibility assessment" in normalized_text:
            add_requirement("Support a first preliminary feasibility assessment", "functional", "under_specified")

        if "power feasibility" in normalized_text:
            add_requirement("Perform a preliminary power feasibility assessment", "functional", "extracted")
        elif contains_any(["battery", "eps", "energy", "solar array", "soh", "rul"]):
            add_requirement("Assess preliminary electrical power subsystem feasibility", "functional", "under_specified")

        if not requirements:
            add_requirement("Analyze the uploaded mission request and identify candidate mission requirements", "functional", "requires_review")

        return requirements

    # ------------------------------------------------------------------
    # Missing information analysis and review
    # ------------------------------------------------------------------
    def analyze_missing_information(self, mode: str = "Registry-driven MVP") -> dict[str, Any]:
        if not self.requirements:
            return {"ok": False, "error": "No active requirements are available. Extract and review requirements first.", "logs": self.logs}

        mode = mode or "Registry-driven MVP"
        self.add_log("AI", f"Analyzing missing information using mode: {mode}.")

        try:
            if mode == "Local LLM via Ollama":
                missing_information = self.llm_assisted_missing_information_analysis(self.requirements)
                source = "llm_assisted_missing_information_analysis"
                raw_source = "llm_assisted_missing_information_raw_output"
            else:
                missing_information = self.registry_driven_missing_information_analysis(self.requirements)
                source = "registry_driven_missing_information_analysis"
                raw_source = "registry_driven_missing_information_raw_output"
        except Exception as exc:
            self.add_log("ERROR", f"Missing-information analysis failed in {mode}: {exc}")
            self.add_log("AI", "Falling back to registry-driven missing-information analysis.")
            missing_information = self.registry_driven_missing_information_analysis(self.requirements)
            source = "registry_driven_missing_information_analysis_after_llm_fallback"
            raw_source = "registry_driven_missing_information_raw_output_after_llm_fallback"

        self.missing_information = missing_information
        self.missing_information_review_status = "not_reviewed"
        self.assumptions_approved = False
        self.reset_downstream_from_assumptions()

        active_path = self.save_missing_information_json(
            missing_information=missing_information,
            review_status="not_reviewed",
            output_filename="missing_information.json",
            source=source,
        )

        extracted_path = self.save_missing_information_json(
            missing_information=missing_information,
            review_status="not_reviewed",
            output_filename="missing_information_extracted.json",
            source=raw_source,
        )

        self.add_log("AI", f"{len(missing_information)} missing/required information items identified.")
        self.add_log("SYSTEM", f"Active missing information saved: {active_path}")
        self.add_log("SYSTEM", f"Raw missing information saved: {extracted_path}")

        return {
            "ok": True,
            **self.state_payload(),
            "missing_information_path": str(active_path),
            "missing_information_extracted_path": str(extracted_path),
            "message": f"{len(missing_information)} missing/required information items identified using {mode}.",
        }

    def registry_driven_missing_information_analysis(self, requirements: list[dict[str, Any]]) -> list[dict[str, Any]]:
        categories = {req.get("category", "functional") for req in requirements}
        req_text = " ".join(req.get("text", "") for req in requirements).lower()
        source_text = (self.uploaded_text or "").lower()
        combined_text = f"{req_text} {source_text}"

        selected_modules = self.select_modules_for_missing_information(categories, combined_text)

        items: list[dict[str, Any]] = []
        seen_keys = set()

        for module in selected_modules:
            module_name = module.get("module_name", module.get("module_id", "unknown module"))
            module_id = module.get("module_id", "unknown_module")

            for input_item in module.get("required_inputs", []) or []:
                if not self.should_include_input_item(input_item, categories, combined_text):
                    continue

                parameter = str(input_item.get("name", "unknown_parameter")).strip()
                key = (module_id, parameter)
                if key in seen_keys:
                    continue
                seen_keys.add(key)

                proposed_value, status, source = self.infer_missing_information_value(
                    input_item=input_item,
                    module=module,
                    combined_text=combined_text,
                    selected_modules=selected_modules,
                )

                item = {
                    "parameter": parameter,
                    "needed_by": module_name,
                    "needed_by_module_id": module_id,
                    "reason": str(input_item.get("missing_information_reason") or input_item.get("description") or "Required by the selected module interface.").strip(),
                    "proposed_value": proposed_value,
                    "unit": str(input_item.get("unit", "-")),
                    "status": status,
                    "source": source,
                    "required": bool(input_item.get("required", False)),
                    "assumption_allowed": bool(input_item.get("assumption_allowed", False)),
                    "data_type": str(input_item.get("data_type", "unknown")),
                    "reviewed_by_user": False,
                }

                items.append(item)

        return items

    def select_modules_for_missing_information(self, categories: set[str], combined_text: str) -> list[dict[str, Any]]:
        if not self.modules:
            return []

        selected: list[dict[str, Any]] = []

        sorted_modules = sorted(self.modules, key=self.get_module_order_score)

        for module in sorted_modules:
            name = str(module.get("module_name", "")).lower()
            module_id = str(module.get("module_id", "")).lower()

            is_constellation = "constellation" in name or "constellation" in module_id
            is_observation = "observation" in name or "observation" in module_id
            is_eps = "power" in name or "budget" in name or "battery" in name or "eps" in name or "power" in module_id or "battery" in module_id

            if is_constellation and categories & {"mission", "functional", "functional", "design", "mission", "functional"}:
                selected.append(module)
            elif is_observation and categories & {"mission", "functional", "functional", "design", "functional"}:
                selected.append(module)
            elif is_eps and ("functional" in categories or any(word in combined_text for word in ["battery", "functional", "power", "energy", "soh", "rul"])):
                selected.append(module)

        if not selected:
            selected = sorted_modules[: min(2, len(sorted_modules))]

        return selected

    def should_include_input_item(self, input_item: dict[str, Any], categories: set[str], combined_text: str) -> bool:
        required = bool(input_item.get("required", False))
        name = str(input_item.get("name", "")).lower()

        if required:
            return True
        if "design" in categories and any(token in name for token in ["sensor", "fov", "field", "sar", "optical"]):
            return True
        if "functional" in categories and any(token in name for token in ["environment", "acquisition", "terrain", "model"]):
            return True
        if "functional" in categories and any(token in name for token in ["battery", "telemetry", "mission", "acquisition"]):
            return True
        if "synthetic" in combined_text and any(token in name for token in ["terrain", "3d", "model", "object"]):
            return True
        return False

    def infer_missing_information_value(
        self,
        input_item: dict[str, Any],
        module: dict[str, Any],
        combined_text: str,
        selected_modules: list[dict[str, Any]],
    ) -> tuple[str, str, str]:
        name = str(input_item.get("name", "")).lower()
        produced_by = str(input_item.get("produced_by", "")).strip()
        default_value = input_item.get("default_value", None)
        assumption_allowed = bool(input_item.get("assumption_allowed", False))
        required = bool(input_item.get("required", False))

        selected_module_ids = {m.get("module_id") for m in selected_modules}
        selected_module_names = {m.get("module_name") for m in selected_modules}

        if produced_by:
            if produced_by in selected_module_ids or produced_by in selected_module_names:
                return f"generated by {produced_by}", "expected_from_upstream", "upstream_module_output"

        if any(token in name for token in ["area_of_interest", "points_or_areas_of_interest", "target_area"]):
            if "etna" in combined_text:
                return "Mount Etna", "provided", "mission_document"
            if "southern italy" in combined_text:
                return "Southern Italy", "provided", "mission_document"
            if "target area" in combined_text:
                return "target area not geometrically specified", "requires_user_input", "module_registry_required_input"

        if "scenario_definition" in name:
            return "mission_request_document", "provided", "mission_document"

        if "sensor_specifications" in name:
            sensor_bits = []
            if "multispectral" in combined_text:
                sensor_bits.append("sensor_type=multispectral")
            elif "optical" in combined_text:
                sensor_bits.append("sensor_type=optical")
            elif "sar" in combined_text or "radar" in combined_text:
                sensor_bits.append("sensor_type=radar/SAR")
            if sensor_bits:
                return "; ".join(sensor_bits), "provided", "mission_document"

        if "mission_specific_information" in name:
            return "preliminary mission profile derived from active requirements", "proposed", "module_registry_default"

        if default_value not in [None, "null", "None"]:
            value = json.dumps(default_value) if isinstance(default_value, (dict, list)) else str(default_value)
            return value, "proposed", "module_registry_default"

        if assumption_allowed:
            return "TBD - user assumption required", "requires_user_input", "module_registry_required_input"

        if required:
            return "TBD - required input", "requires_user_input", "module_registry_required_input"

        return "-", "not_applicable", "not_applicable"

    def save_reviewed_missing_information(self, reviewed_items: list[dict[str, Any]]) -> dict[str, Any]:
        if not self.current_run_path:
            return {"ok": False, "error": "No active run is available.", "logs": self.logs}

        try:
            normalized = self.validate_and_normalize_reviewed_missing_information(reviewed_items)
        except Exception as exc:
            self.add_log("ERROR", f"Reviewed missing information validation failed: {exc}")
            return {"ok": False, "error": str(exc), "logs": self.logs}

        self.missing_information = normalized
        self.missing_information_review_status = "reviewed_by_user"
        self.assumptions_approved = False
        self.reset_downstream_from_assumptions()

        reviewed_path = self.save_missing_information_json(
            missing_information=normalized,
            review_status="reviewed_by_user",
            output_filename="missing_information_reviewed.json",
            source="user_reviewed_missing_information",
        )

        active_path = self.save_missing_information_json(
            missing_information=normalized,
            review_status="reviewed_by_user",
            output_filename="missing_information.json",
            source="active_missing_information_after_user_review",
        )

        self.add_log("USER", "Missing information table reviewed and saved by user.")
        self.add_log("SYSTEM", f"Reviewed missing information saved: {reviewed_path}")
        self.add_log("SYSTEM", f"Active missing information updated: {active_path}")

        return {
            "ok": True,
            **self.state_payload(),
            "missing_information_reviewed_path": str(reviewed_path),
            "missing_information_path": str(active_path),
            "message": "Reviewed missing parameters saved. These values can now be approved as preliminary assumptions.",
        }

    def validate_and_normalize_reviewed_missing_information(self, reviewed_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not isinstance(reviewed_items, list):
            raise ValueError("Reviewed missing information payload must be a list.")

        module_names = set(self.get_module_names())
        normalized = []
        seen_keys = set()

        for index, item in enumerate(reviewed_items, start=1):
            parameter = str(item.get("parameter", "")).strip()
            needed_by = str(item.get("needed_by", "")).strip()
            reason = str(item.get("reason", "")).strip()
            proposed_value = str(item.get("proposed_value", "")).strip()
            unit = str(item.get("unit", "-")).strip() or "-"
            status = str(item.get("status", "")).strip()
            source = str(item.get("source", "")).strip()

            if not parameter:
                raise ValueError(f"Missing-information row {index} has an empty parameter name.")
            if not needed_by:
                raise ValueError(f"Missing-information row {index} has an empty module name.")
            if module_names and needed_by not in module_names:
                raise ValueError(f"Missing-information row {index} has invalid module name '{needed_by}'.")
            if not reason:
                raise ValueError(f"Missing-information row {index} has an empty reason.")
            if status not in ALLOWED_MISSING_INFORMATION_STATUSES:
                raise ValueError(f"Missing-information row {index} has invalid status '{status}'.")
            if source not in ALLOWED_MISSING_INFORMATION_SOURCES:
                raise ValueError(f"Missing-information row {index} has invalid source '{source}'.")

            key = (needed_by, parameter)
            if key in seen_keys:
                raise ValueError(f"Duplicate missing-information item found: {needed_by} / {parameter}")
            seen_keys.add(key)

            module = self.get_module_by_name(needed_by)
            normalized.append(
                {
                    "parameter": parameter,
                    "needed_by": needed_by,
                    "needed_by_module_id": module.get("module_id", "unknown") if module else "unknown",
                    "reason": reason,
                    "proposed_value": proposed_value,
                    "unit": unit,
                    "status": status,
                    "source": source,
                    "required": bool(item.get("required", False)),
                    "assumption_allowed": bool(item.get("assumption_allowed", False)),
                    "data_type": str(item.get("data_type", "unknown")),
                    "reviewed_by_user": True,
                }
            )

        return normalized

    def approve_missing_information(self) -> dict[str, Any]:
        if not self.current_run_path:
            return {"ok": False, "error": "No active run is available.", "logs": self.logs}

        if not self.missing_information:
            return {"ok": False, "error": "No missing information is available to approve.", "logs": self.logs}

        approved_items = []
        for index, item in enumerate(self.missing_information, start=1):
            approved_item = dict(item)
            approved_item["assumption_id"] = f"ASS-{index:03d}"
            approved_item["status"] = "approved"
            approved_item["approved_by_user"] = True
            approved_items.append(approved_item)

        self.missing_information = approved_items
        self.missing_information_review_status = "approved_by_user"
        self.assumptions_approved = True
        self.reset_downstream_from_assumptions()

        approved_path = self.save_approved_assumptions_json(approved_items)

        active_path = self.save_missing_information_json(
            missing_information=approved_items,
            review_status="approved_by_user",
            output_filename="missing_information.json",
            source="approved_missing_information",
        )

        self.add_log("USER", "Missing information approved as preliminary assumptions.")
        self.add_log("SYSTEM", f"approved_assumptions.json saved: {approved_path}")
        self.add_log("SYSTEM", f"Active missing information updated: {active_path}")
        self.add_log("SYSTEM", "Workflow proposal is now enabled.")

        return {
            "ok": True,
            **self.state_payload(),
            "approved_assumptions_path": str(approved_path),
            "missing_information_path": str(active_path),
            "message": "Missing parameters approved as preliminary assumptions.",
        }

    def save_missing_information_json(
        self,
        missing_information: list[dict[str, Any]],
        review_status: str,
        output_filename: str,
        source: str,
    ) -> Path:
        if not self.current_run_path:
            raise RuntimeError("No active run folder is available.")

        output_path = self.current_run_path / "intermediate" / output_filename

        with output_path.open("w", encoding="utf-8") as file:
            json.dump(
                {
                    "run_id": self.current_run_id,
                    "generated_at": datetime.now().isoformat(),
                    **self.get_source_document_metadata(),
                    "source": source,
                    "review_status": review_status,
                    "allowed_statuses": ALLOWED_MISSING_INFORMATION_STATUSES,
                    "allowed_sources": ALLOWED_MISSING_INFORMATION_SOURCES,
                    "missing_information": missing_information,
                },
                file,
                indent=4,
            )

        return output_path

    def save_approved_assumptions_json(self, approved_items: list[dict[str, Any]]) -> Path:
        if not self.current_run_path:
            raise RuntimeError("No active run folder is available.")

        output_path = self.current_run_path / "intermediate" / "approved_assumptions.json"

        with output_path.open("w", encoding="utf-8") as file:
            json.dump(
                {
                    "run_id": self.current_run_id,
                    "generated_at": datetime.now().isoformat(),
                    **self.get_source_document_metadata(),
                    "source": "user_approved_assumptions",
                    "approved_assumptions": approved_items,
                },
                file,
                indent=4,
            )

        return output_path


    def compact_module_registry_for_llm(self) -> list[dict[str, Any]]:
        """Return a compact, JSON-serializable registry view for LLM prompts."""
        compact = []

        for module in self.modules:
            compact.append(
                {
                    "module_id": module.get("module_id"),
                    "module_name": module.get("module_name"),
                    "aliases": module.get("aliases", []),
                    "short_description": module.get("short_description", ""),
                    "description": module.get("description", ""),
                    "capabilities": module.get("capabilities", []),
                    "activation_rules": module.get("activation_rules", {}),
                    "planning_guidance": module.get("planning_guidance", ""),
                    "domain_of_validity": module.get("domain_of_validity", {}),
                    "required_inputs": [
                        {
                            "name": input_item.get("name"),
                            "data_type": input_item.get("data_type"),
                            "unit": input_item.get("unit", "-"),
                            "required": bool(input_item.get("required", False)),
                            "default_value": input_item.get("default_value"),
                            "assumption_allowed": bool(input_item.get("assumption_allowed", False)),
                            "produced_by": input_item.get("produced_by"),
                            "description": input_item.get("description", ""),
                            "missing_information_reason": input_item.get("missing_information_reason", ""),
                        }
                        for input_item in (module.get("required_inputs", []) or [])
                    ],
                    "outputs": [
                        {
                            "name": output.get("name"),
                            "artifact_name": output.get("artifact_name"),
                            "data_type": output.get("data_type"),
                            "description": output.get("description", ""),
                        }
                        for output in (module.get("outputs", []) or [])
                    ],
                    "execution": module.get("execution", {}),
                    "interface_notes": module.get("interface_notes", ""),
                }
            )

        return compact

    def parse_llm_json_response(self, content: str) -> dict[str, Any]:
        """Parse JSON returned by the local LLM, tolerating markdown fences."""
        cleaned = (content or "").strip()

        if cleaned.startswith("```json"):
            cleaned = cleaned.removeprefix("```json").strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.removeprefix("```").strip()
        if cleaned.endswith("```"):
            cleaned = cleaned.removesuffix("```").strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start >= 0 and end > start:
                return json.loads(cleaned[start:end + 1])
            raise

    def call_local_llm_json(self, system_prompt: str, user_prompt: str, max_tokens: int | None = None) -> dict[str, Any]:
        """Call the configured OpenAI-compatible local provider and parse JSON.

        max_tokens (optional) bounds the answer: a 7B model that derails into free
        text otherwise generates until the 300 s client timeout before STAR falls
        back to the rule-based planner.
        """
        provider = self.get_local_llm_provider()

        extra: dict[str, Any] = {"max_tokens": int(max_tokens)} if max_tokens else {}
        response = provider.client.chat.completions.create(
            model=provider.model,
            temperature=provider.temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            **extra,
        )

        content = response.choices[0].message.content or ""
        return self.parse_llm_json_response(content)

    def allowed_parameter_names_by_module(self) -> dict[str, set[str]]:
        mapping = {}

        for module in self.modules:
            module_name = module.get("module_name")
            mapping[module_name] = {
                str(input_item.get("name"))
                for input_item in (module.get("required_inputs", []) or [])
                if input_item.get("name")
            }

        return mapping

    def normalize_missing_status(self, status: str) -> str:
        value = str(status or "").strip()

        if value in ALLOWED_MISSING_INFORMATION_STATUSES:
            return value

        lowered = value.lower()
        if lowered in {"missing", "required", "needs_user", "user_input", "tbd"}:
            return "requires_user_input"
        if lowered in {"default", "assumption", "assumed"}:
            return "proposed"
        if lowered in {"upstream", "generated", "from_upstream"}:
            return "expected_from_upstream"
        if lowered in {"available", "document", "found"}:
            return "provided"
        if lowered in {"n/a", "na", "not_required"}:
            return "not_applicable"

        return "requires_user_input"

    def normalize_missing_source(self, source: str) -> str:
        value = str(source or "").strip()

        if value in ALLOWED_MISSING_INFORMATION_SOURCES:
            return value

        lowered = value.lower()
        if lowered in {"document", "mission_request", "mission request", "input_document"}:
            return "mission_document"
        if lowered in {"default", "registry_default", "assumption"}:
            return "module_registry_default"
        if lowered in {"required_input", "registry_required", "missing"}:
            return "module_registry_required_input"
        if lowered in {"upstream", "module_output", "produced_by_module"}:
            return "upstream_module_output"
        if lowered in {"user", "human", "reviewed"}:
            return "user_reviewed"
        if lowered in {"n/a", "na", "not_required"}:
            return "not_applicable"

        return "module_registry_required_input"

    def normalize_workflow_status(self, status: str) -> str:
        value = str(status or "").strip()

        if value in ALLOWED_WORKFLOW_STATUSES:
            return value

        lowered = value.lower()
        if lowered in {"ok", "selected", "planned"}:
            return "proposed"
        if lowered in {"needs_review", "review"}:
            return "requires_review"
        if lowered in {"validated"}:
            return "ready"

        return "proposed"

    def llm_assisted_missing_information_analysis(self, requirements: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Use the local LLM to map requirements onto registry-declared module inputs."""
        registry = self.compact_module_registry_for_llm()
        module_names = self.get_module_names()

        system_prompt = (
            "You are STAR's missing-information analysis assistant. "
            "You must return only valid JSON. Do not use markdown fences. "
            "You must not invent modules or parameters outside the provided registry."
        )

        user_prompt = f"""
TASK
Identify the missing, provided, proposed, or upstream-generated parameters required to run the STAR modules.

INPUTS
1. Active reviewed requirements:
{json.dumps(requirements, indent=2)}

2. Module registry:
{json.dumps(registry, indent=2)}

3. Mission request document excerpt:
\"\"\"
{(self.uploaded_text or "")[:6000]}
\"\"\"

STRICT RULES
- Use only these module names: {json.dumps(module_names)}
- For each module, use only parameter names that appear in that module's required_inputs list.
- Do not invent module names.
- Do not invent parameter names.
- If a numerical value is missing, do not invent it.
- If a required input is already implied by the mission request, set status = "provided" and source = "mission_document".
- If a required input has a registry default value, set status = "proposed" and source = "module_registry_default".
- If a required input is produced by an upstream module selected in the workflow, set status = "expected_from_upstream" and source = "upstream_module_output".
- If a required input is needed but not available, set status = "requires_user_input" and source = "module_registry_required_input".
- Use "not_applicable" only for optional inputs that are clearly irrelevant.
- Use the mission request to decide whether each registry input is provided, proposed, expected from upstream, or missing.
- Process only modules that are relevant to the active requirements.
- Do not include optional inputs unless they are explicitly mentioned in the mission request or clearly required by a selected module.
- For each selected module, include required inputs first.
- Do not extract budget, launch, ground segment, downlink details unless a selected module has a matching required_input for them.
- If all required_inputs of the selected modules have been classified, stop immediately and return JSON.
- Do not add explanations, reasoning, comments, markdown, or summaries.
- Return the JSON object immediately.
- Apply ECSS-E-ST-10-06C-inspired requirement writing principles.
- Extract requirements as needs to be fulfilled, not as implementation explanations.
- Prefer requirements that are clear, atomic, unambiguous, unique, traceable, and verifiable.
- Each requirement shall express one single need.
- Each requirement shall have a clear subject and a clear required action.
- Use "shall" wording when rewriting requirement text.
- Do not include long explanatory clauses inside the requirement text.
- Do not mix objective, design solution, verification method, budget, and operational narrative in the same requirement.
- If a requirement contains vague terms such as high, frequent, rapid, optimized, efficient, or preliminary without quantitative criteria, set status = "under_specified".
- If a numerical value and unit are explicitly present in the mission request, preserve them.
- If a requirement cannot be verified from the available information, set status = "requires_review" or "under_specified".
- Do not extract descriptive mission background as a requirement unless it constrains the system or defines a required capability.

ALLOWED STATUSES
{json.dumps(ALLOWED_MISSING_INFORMATION_STATUSES)}

ALLOWED SOURCES
{json.dumps(ALLOWED_MISSING_INFORMATION_SOURCES)}

OUTPUT FORMAT
Return only valid JSON:
{{
  "missing_information": [
    {{
      "parameter": "registry input name",
      "needed_by": "exact module_name from registry",
      "reason": "why this information is needed",
      "proposed_value": "value, default, upstream reference, or TBD",
      "unit": "-",
      "status": "provided | proposed | requires_user_input | expected_from_upstream | not_applicable",
      "source": "mission_document | module_registry_default | module_registry_required_input | upstream_module_output | not_applicable"
    }}
  ]
}}
"""

        data = self.call_local_llm_json(system_prompt, user_prompt)
        raw_items = data.get("missing_information", data.get("missing_parameters", []))

        if not isinstance(raw_items, list):
            raise ValueError("LLM response does not contain a missing_information list.")

        normalized = self.normalize_llm_missing_information(raw_items)

        if not normalized:
            self.add_log("AI", "LLM missing-information output was empty after registry validation.")
            return self.registry_driven_missing_information_analysis(requirements)

        return normalized

    def normalize_llm_missing_information(self, raw_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        module_names = set(self.get_module_names())
        parameter_map = self.allowed_parameter_names_by_module()

        normalized = []
        seen = set()
        skipped_count = 0

        for item in raw_items:
            if not isinstance(item, dict):
                skipped_count += 1
                continue

            module_name = str(item.get("needed_by", item.get("module", ""))).strip()
            parameter = str(item.get("parameter", item.get("name", ""))).strip()

            if module_name not in module_names:
                skipped_count += 1
                continue

            if parameter not in parameter_map.get(module_name, set()):
                skipped_count += 1
                continue

            key = (module_name, parameter)
            if key in seen:
                continue
            seen.add(key)

            module = self.get_module_by_name(module_name)
            input_item = None
            for candidate in module.get("required_inputs", []) or []:
                if candidate.get("name") == parameter:
                    input_item = candidate
                    break

            input_item = input_item or {}

            normalized.append(
                {
                    "parameter": parameter,
                    "needed_by": module_name,
                    "needed_by_module_id": module.get("module_id", "unknown") if module else "unknown",
                    "reason": str(
                        item.get("reason")
                        or input_item.get("missing_information_reason")
                        or input_item.get("description")
                        or "Required by the selected module interface."
                    ).strip(),
                    "proposed_value": str(item.get("proposed_value", item.get("value", "TBD - required input"))).strip(),
                    "unit": str(item.get("unit", input_item.get("unit", "-")) or "-").strip(),
                    "status": self.normalize_missing_status(item.get("status", "requires_user_input")),
                    "source": self.normalize_missing_source(item.get("source", "module_registry_required_input")),
                    "required": bool(input_item.get("required", False)),
                    "assumption_allowed": bool(input_item.get("assumption_allowed", False)),
                    "data_type": str(input_item.get("data_type", "unknown")),
                    "reviewed_by_user": False,
                }
            )

        if skipped_count:
            self.add_log("AI", f"Discarded {skipped_count} LLM missing-information item(s) not compliant with the registry.")

        return normalized

    def llm_assisted_workflow_proposal(self) -> list[dict[str, Any]]:
        """Use the local LLM to propose a workflow using only registry modules."""
        registry = self.compact_module_registry_for_llm()
        module_names = self.get_module_names()

        approved_assumptions = [
            item for item in self.missing_information
            if item.get("status") == "approved" or item.get("approved_by_user")
        ]

        system_prompt = (
            "You are STAR's workflow-planning assistant. "
            "You must return only valid JSON. Do not use markdown fences. "
            "You must not invent modules outside the provided registry."
        )

        user_prompt = f"""
TASK
Propose an executable STAR workflow from the approved assumptions and module registry.

INPUTS
1. Active reviewed requirements:
{json.dumps(self.requirements, indent=2)}

2. Approved assumptions:
{json.dumps(approved_assumptions, indent=2)}

3. Module registry:
{json.dumps(registry, indent=2)}

STRICT RULES
- Use only these module names: {json.dumps(module_names)}
- Do not invent modules.
- Select only modules needed to satisfy the active requirements and approved assumptions.
- Respect dependencies implied by produced_by, upstream_dependencies, and downstream_dependencies when available.
- A constellation/orbit-level module should usually precede an observation module.
- A battery/EPS module should usually follow mission/observation timeline definition when selected.
- Every selected module must appear at most once.
- The output_artifacts field must be based on that module's declared outputs.
- The input_data_artifacts field must be based on approved assumptions and/or upstream module outputs.
- Keep rationale concise but specific.

ALLOWED STATUSES
{json.dumps(ALLOWED_WORKFLOW_STATUSES)}

OUTPUT FORMAT
Return only valid JSON:
{{
  "workflow": [
    {{
      "step": 1,
      "module": "exact module_name from registry",
      "input_data_artifacts": "short semicolon-separated input summary",
      "output_artifacts": "short semicolon-separated output summary",
      "rationale": "why this module is needed",
      "status": "proposed"
    }}
  ]
}}
"""

        data = self.call_local_llm_json(system_prompt, user_prompt)
        raw_steps = data.get("workflow", data.get("workflow_steps", data.get("steps", [])))

        if not isinstance(raw_steps, list):
            raise ValueError("LLM response does not contain a workflow list.")

        normalized = self.normalize_llm_workflow(raw_steps)

        if not normalized:
            self.add_log("AI", "LLM workflow output was empty after registry validation.")
            return self.registry_driven_workflow_proposal()

        return normalized

    def normalize_llm_workflow(self, raw_steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
        module_names = set(self.get_module_names())

        normalized = []
        seen_modules = set()
        skipped_count = 0

        for index, step in enumerate(raw_steps, start=1):
            if not isinstance(step, dict):
                skipped_count += 1
                continue

            module_name = str(step.get("module", step.get("module_name", ""))).strip()

            if module_name not in module_names:
                skipped_count += 1
                continue

            if module_name in seen_modules:
                continue
            seen_modules.add(module_name)

            module = self.get_module_by_name(module_name)

            output_artifacts = str(step.get("output_artifacts", "")).strip()
            if not output_artifacts:
                output_artifacts = self.build_workflow_output_summary(module)

            input_data = str(step.get("input_data_artifacts", step.get("inputs", ""))).strip()
            if not input_data:
                related_items = [
                    item for item in self.missing_information
                    if item.get("needed_by") == module_name
                ]
                input_data = self.build_workflow_input_summary(module, related_items)

            normalized.append(
                {
                    "step": len(normalized) + 1,
                    "module": module_name,
                    "module_id": module.get("module_id", "unknown") if module else "unknown",
                    "input_data_artifacts": input_data,
                    "output_artifacts": output_artifacts,
                    "rationale": str(step.get("rationale", step.get("reason", "Selected by LLM-assisted workflow proposal."))).strip(),
                    "status": self.normalize_workflow_status(step.get("status", "proposed")),
                    "reviewed_by_user": False,
                }
            )

        if skipped_count:
            self.add_log("AI", f"Discarded {skipped_count} LLM workflow step(s) not compliant with the registry.")

        normalized.sort(
            key=lambda row: self.get_module_order_score(self.get_module_by_name(row["module"]) or {})
        )

        for index, row in enumerate(normalized, start=1):
            row["step"] = index

        return normalized


    # ------------------------------------------------------------------
    # Workflow proposal and review
    # ------------------------------------------------------------------
    def propose_workflow(self, mode: str = "Registry-driven MVP") -> dict[str, Any]:
        if not self.assumptions_approved:
            return {
                "ok": False,
                "error": "Approve assumptions before proposing a workflow.",
                "logs": self.logs,
            }

        if not self.current_run_path:
            return {"ok": False, "error": "No active run is available.", "logs": self.logs}

        mode = mode or "Registry-driven MVP"
        self.add_log("AI", f"Generating workflow proposal using mode: {mode}.")

        try:
            if mode == "Local LLM via Ollama":
                workflow = self.llm_assisted_workflow_proposal()
                source = "llm_assisted_workflow_proposal"
                raw_source = "llm_assisted_workflow_raw_output"
            else:
                workflow = self.registry_driven_workflow_proposal()
                source = "registry_driven_workflow_proposal"
                raw_source = "registry_driven_workflow_raw_output"
        except Exception as exc:
            self.add_log("ERROR", f"Workflow proposal failed in {mode}: {exc}")
            self.add_log("AI", "Falling back to registry-driven workflow proposal.")
            workflow = self.registry_driven_workflow_proposal()
            source = "registry_driven_workflow_proposal_after_llm_fallback"
            raw_source = "registry_driven_workflow_raw_output_after_llm_fallback"

        if not workflow:
            return {
                "ok": False,
                "error": "No workflow steps could be generated from the approved assumptions and module registry.",
                "logs": self.logs,
            }

        self.workflow_steps = workflow
        self.workflow_review_status = "not_reviewed"
        self.workflow_approved = False
        self.reset_downstream_from_workflow()

        for module in self.modules:
            if module.get("module_name") in {step["module"] for step in workflow}:
                module["status"] = "Ready"
            else:
                module["status"] = "Idle"

        active_path = self.save_workflow_json(
            workflow=workflow,
            review_status="not_reviewed",
            output_filename="workflow_proposal.json",
            source=source,
        )

        extracted_path = self.save_workflow_json(
            workflow=workflow,
            review_status="not_reviewed",
            output_filename="workflow_proposal_extracted.json",
            source=raw_source,
        )

        self.add_log("AI", f"{len(workflow)} workflow steps proposed.")
        self.add_log("SYSTEM", f"Active workflow proposal saved: {active_path}")
        self.add_log("SYSTEM", f"Raw workflow proposal saved: {extracted_path}")

        return {
            "ok": True,
            **self.state_payload(),
            "workflow_proposal_path": str(active_path),
            "workflow_proposal_extracted_path": str(extracted_path),
            "message": f"{len(workflow)} workflow steps proposed using {mode}.",
        }

    def registry_driven_workflow_proposal(self) -> list[dict[str, Any]]:
        approved_modules = {
            item.get("needed_by")
            for item in self.missing_information
            if item.get("needed_by") and item.get("status") == "approved"
        }

        if not approved_modules:
            approved_modules = {
                item.get("needed_by")
                for item in self.missing_information
                if item.get("needed_by")
            }

        candidate_modules = [
            module for module in self.modules
            if module.get("module_name") in approved_modules
        ]

        if not candidate_modules:
            return []

        ordered_modules = sorted(candidate_modules, key=self.get_module_order_score)

        workflow: list[dict[str, Any]] = []

        for index, module in enumerate(ordered_modules, start=1):
            module_name = module.get("module_name", module.get("module_id", "unknown module"))
            module_id = module.get("module_id", "unknown")

            related_items = [
                item for item in self.missing_information
                if item.get("needed_by") == module_name
            ]

            input_data = self.build_workflow_input_summary(module, related_items)
            output_artifacts = self.build_workflow_output_summary(module)
            rationale = self.build_workflow_rationale(module, related_items)

            workflow.append(
                {
                    "step": index,
                    "module": module_name,
                    "module_id": module_id,
                    "input_data_artifacts": input_data,
                    "output_artifacts": output_artifacts,
                    "rationale": rationale,
                    "status": "proposed",
                    "reviewed_by_user": False,
                }
            )

        return workflow

    def build_workflow_input_summary(self, module: dict[str, Any], related_items: list[dict[str, Any]]) -> str:
        if related_items:
            parts = []
            for item in related_items:
                parameter = item.get("parameter", "unknown")
                value = item.get("proposed_value", "")
                unit = item.get("unit", "-")
                status = item.get("status", "")
                unit_text = "" if unit in ["-", "", None] else f" {unit}"
                parts.append(f"{parameter}={value}{unit_text} [{status}]")
            return "; ".join(parts)

        required_inputs = module.get("required_inputs", []) or []
        if required_inputs:
            return "; ".join(str(item.get("name", "unknown_input")) for item in required_inputs)

        return "No explicit input declared in module registry."

    def build_workflow_output_summary(self, module: dict[str, Any]) -> str:
        outputs = module.get("outputs", []) or []
        if not outputs:
            return "No output artifact declared in module registry."

        names = []
        for output in outputs:
            artifact = output.get("artifact_name")
            name = output.get("name", "unknown_output")
            names.append(str(artifact or name))

        return "; ".join(names)

    def build_workflow_rationale(self, module: dict[str, Any], related_items: list[dict[str, Any]]) -> str:
        capability_text = ", ".join(module.get("capabilities", [])[:4]) if module.get("capabilities") else "declared module capabilities"
        if related_items:
            parameters = ", ".join(item.get("parameter", "unknown") for item in related_items[:4])
            return f"Selected because approved assumptions provide or define: {parameters}. Module capabilities: {capability_text}."
        return f"Selected based on approved workflow dependencies and module capabilities: {capability_text}."

    def build_workflow_step_for_module(self, module: dict[str, Any], status: str = "proposed") -> dict[str, Any]:
        module_name = module.get("module_name", module.get("module_id", "unknown module"))
        return {
            "step": len(self.workflow_steps) + 1,
            "module": module_name,
            "module_id": module.get("module_id", "unknown"),
            "input_data_artifacts": self.build_workflow_input_summary(module, []),
            "output_artifacts": self.build_workflow_output_summary(module),
            "rationale": "Added manually by the user during workflow review.",
            "status": status,
            "reviewed_by_user": False,
        }

    def add_module_to_workflow(self, module_name_or_id: str) -> dict[str, Any]:
        self.ensure_pipeline_state()
        if self.workflow_approved:
            return {"ok": False, "error": "The approved workflow cannot be edited. Generate a new planning proposal or reset downstream state first.", **self.state_payload()}

        module = self.get_module_by_id(module_name_or_id) or self.get_module_by_name(module_name_or_id)
        if not module:
            return {"ok": False, "error": f"Module not found: {module_name_or_id}", **self.state_payload()}

        module_id = module.get("module_id")
        if any(str(step.get("module_id")) == str(module_id) for step in self.workflow_steps):
            return {"ok": False, "error": f"Module already present in workflow: {module.get('module_name')}", **self.state_payload()}

        self.workflow_steps.append(self.build_workflow_step_for_module(module))
        self.workflow_steps = self.sort_and_renumber_workflow(self.workflow_steps)
        self.workflow_review_status = "edited_not_saved"
        self.workflow_approved = False
        self.missing_information = []
        self.missing_information_review_status = "not_available"
        self.assumptions_approved = False
        self.reset_downstream_from_workflow()

        selected_module_names = {step.get("module") for step in self.workflow_steps}
        for candidate in self.modules:
            candidate["status"] = "Ready" if candidate.get("module_name") in selected_module_names else "Idle"

        self.add_log("USER", f"Module added to workflow: {module.get('module_name')} ({module_id}).")
        self.add_log("SYSTEM", "Workflow marked as edited; save and approve it again before resolving inputs or executing.")
        return {"ok": True, "message": f"Module added to workflow: {module.get('module_name')}", **self.state_payload()}

    def remove_module_from_workflow(self, module_name_or_id: str) -> dict[str, Any]:
        self.ensure_pipeline_state()
        if self.workflow_approved:
            return {"ok": False, "error": "The approved workflow cannot be edited. Generate a new planning proposal or reset downstream state first.", **self.state_payload()}

        original_count = len(self.workflow_steps)
        target = self.normalize_text(module_name_or_id)
        self.workflow_steps = [
            step for step in self.workflow_steps
            if self.normalize_text(str(step.get("module", ""))) != target
            and self.normalize_text(str(step.get("module_id", ""))) != target
        ]

        if len(self.workflow_steps) == original_count:
            return {"ok": False, "error": f"Module not found in current workflow: {module_name_or_id}", **self.state_payload()}

        self.workflow_steps = self.sort_and_renumber_workflow(self.workflow_steps)
        self.workflow_review_status = "edited_not_saved" if self.workflow_steps else "not_available"
        self.workflow_approved = False
        self.missing_information = []
        self.missing_information_review_status = "not_available"
        self.assumptions_approved = False
        self.reset_downstream_from_workflow()

        selected_module_names = {step.get("module") for step in self.workflow_steps}
        for candidate in self.modules:
            candidate["status"] = "Ready" if candidate.get("module_name") in selected_module_names else "Idle"

        self.add_log("USER", f"Module removed from workflow: {module_name_or_id}.")
        self.add_log("SYSTEM", "Workflow marked as edited; save and approve it again before resolving inputs or executing.")
        return {"ok": True, "message": f"Module removed from workflow: {module_name_or_id}", **self.state_payload()}

    def update_workflow_from_frontend(self, reviewed_workflow: list[dict[str, Any]]) -> dict[str, Any]:
        """Store an edited workflow without approving it. Kept for frontend compatibility."""
        return self.save_reviewed_workflow(reviewed_workflow)

    def save_reviewed_workflow(self, reviewed_workflow: list[dict[str, Any]]) -> dict[str, Any]:
        if not self.current_run_path:
            return {"ok": False, "error": "No active run is available.", "logs": self.logs}

        try:
            normalized = self.validate_and_normalize_reviewed_workflow(reviewed_workflow)
        except Exception as exc:
            self.add_log("ERROR", f"Reviewed workflow validation failed: {exc}")
            return {"ok": False, "error": str(exc), "logs": self.logs}

        self.workflow_steps = normalized
        self.workflow_review_status = "reviewed_by_user"
        self.workflow_approved = False
        self.reset_downstream_from_workflow()

        reviewed_module_names = {step.get("module") for step in normalized}
        for module in self.modules:
            module["status"] = "Ready" if module.get("module_name") in reviewed_module_names else "Idle"

        reviewed_path = self.save_workflow_json(
            workflow=normalized,
            review_status="reviewed_by_user",
            output_filename="workflow_proposal_reviewed.json",
            source="user_reviewed_workflow_proposal",
        )

        active_path = self.save_workflow_json(
            workflow=normalized,
            review_status="reviewed_by_user",
            output_filename="workflow_proposal.json",
            source="active_workflow_after_user_review",
        )

        self.add_log("USER", "Workflow proposal reviewed and saved by user.")
        self.add_log("SYSTEM", f"Reviewed workflow saved: {reviewed_path}")
        self.add_log("SYSTEM", f"Active workflow proposal updated: {active_path}")

        return {
            "ok": True,
            **self.state_payload(),
            "workflow_reviewed_path": str(reviewed_path),
            "workflow_proposal_path": str(active_path),
            "message": "Reviewed workflow saved. It can now be approved.",
        }

    def validate_and_normalize_reviewed_workflow(self, reviewed_workflow: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not isinstance(reviewed_workflow, list):
            raise ValueError("Reviewed workflow payload must be a list.")

        module_names = set(self.get_module_names())
        normalized = []
        seen_steps = set()

        for index, step in enumerate(reviewed_workflow, start=1):
            step_value = str(step.get("step", "")).strip()
            module_name = str(step.get("module", "")).strip()
            input_data = str(step.get("input_data_artifacts", "")).strip()
            output_artifacts = str(step.get("output_artifacts", "")).strip()
            rationale = str(step.get("rationale", "")).strip()
            status = str(step.get("status", "")).strip()

            # The frontend contains an in-table "+" row used only to add modules.
            # If an older frontend accidentally sends that empty UI row, ignore it
            # instead of blocking Save Reviewed Workflow / Approve Workflow.
            if not any([step_value, module_name, input_data, output_artifacts, rationale, status]):
                continue

            if not step_value:
                raise ValueError(f"Workflow row {index} has an empty step.")
            if step_value in seen_steps:
                raise ValueError(f"Duplicate workflow step found: {step_value}")
            if not module_name:
                raise ValueError(f"Workflow step {step_value} has an empty module name.")
            if module_names and module_name not in module_names:
                raise ValueError(f"Workflow step {step_value} has invalid module name '{module_name}'.")
            if not output_artifacts:
                raise ValueError(f"Workflow step {step_value} has empty output artifacts.")
            if status not in ALLOWED_WORKFLOW_STATUSES:
                raise ValueError(f"Workflow step {step_value} has invalid status '{status}'.")

            seen_steps.add(step_value)
            module = self.get_module_by_name(module_name)

            normalized.append(
                {
                    "step": step_value,
                    "module": module_name,
                    "module_id": module.get("module_id", "unknown") if module else "unknown",
                    "input_data_artifacts": input_data,
                    "output_artifacts": output_artifacts,
                    "rationale": rationale,
                    "status": status,
                    "reviewed_by_user": True,
                }
            )

        return normalized

    def approve_workflow(self) -> dict[str, Any]:
        if not self.workflow_steps:
            return {"ok": False, "error": "No workflow proposal is available to approve.", "logs": self.logs}
        if self.workflow_review_status == "edited_not_saved":
            return {"ok": False, "error": "Save the reviewed workflow before approving it.", **self.state_payload()}

        approved_steps = []
        approved_module_names = set()

        for step in self.workflow_steps:
            approved_step = dict(step)
            approved_step["status"] = "approved"
            approved_step["approved_by_user"] = True
            approved_steps.append(approved_step)
            approved_module_names.add(approved_step.get("module"))

        self.workflow_steps = approved_steps
        self.workflow_review_status = "approved_by_user"
        self.workflow_approved = True
        self.reset_downstream_from_workflow()

        for module in self.modules:
            if module.get("module_name") in approved_module_names:
                module["status"] = "Ready"
            else:
                module["status"] = "Idle"

        approved_path = self.save_workflow_json(
            workflow=approved_steps,
            review_status="approved_by_user",
            output_filename="approved_workflow.json",
            source="user_approved_workflow",
        )

        active_path = self.save_workflow_json(
            workflow=approved_steps,
            review_status="approved_by_user",
            output_filename="workflow_proposal.json",
            source="approved_active_workflow",
        )

        self.add_log("USER", "Workflow approved by user.")
        self.add_log("SYSTEM", f"approved_workflow.json saved: {approved_path}")
        self.add_log("SYSTEM", f"Active workflow proposal updated: {active_path}")

        return {
            "ok": True,
            **self.state_payload(),
            "approved_workflow_path": str(approved_path),
            "workflow_proposal_path": str(active_path),
            "message": "Workflow approved.",
        }

    def save_workflow_json(
        self,
        workflow: list[dict[str, Any]],
        review_status: str,
        output_filename: str,
        source: str,
    ) -> Path:
        if not self.current_run_path:
            raise RuntimeError("No active run folder is available.")

        output_path = self.current_run_path / "intermediate" / output_filename

        with output_path.open("w", encoding="utf-8") as file:
            json.dump(
                {
                    "run_id": self.current_run_id,
                    "generated_at": datetime.now().isoformat(),
                    **self.get_source_document_metadata(),
                    "source": source,
                    "review_status": review_status,
                    "allowed_statuses": ALLOWED_WORKFLOW_STATUSES,
                    "workflow": workflow,
                },
                file,
                indent=4,
            )

        return output_path


    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------
    def execute_workflow(self) -> dict[str, Any]:
        if not self.workflow_approved:
            return {
                "ok": False,
                "error": "Approve the workflow before executing it.",
                "logs": self.logs,
            }

        if not self.current_run_path:
            return {"ok": False, "error": "No active run is available.", "logs": self.logs}

        if not self.workflow_steps:
            return {"ok": False, "error": "No approved workflow steps are available.", "logs": self.logs}

        self.add_log("EXECUTION", "Starting deterministic workflow execution.")

        execution_results = []

        for module in self.modules:
            if module.get("module_name") in {step.get("module") for step in self.workflow_steps}:
                module["status"] = "Running"

        for workflow_step in self.workflow_steps:
            result = self.execute_workflow_step(workflow_step)
            execution_results.append(result)

            module_name = workflow_step.get("module")
            for module in self.modules:
                if module.get("module_name") == module_name:
                    module["status"] = "Completed" if result["status"] == "completed" else "Error"

        for module in self.modules:
            if module.get("module_name") not in {step.get("module") for step in self.workflow_steps}:
                module["status"] = "Idle"

        self.execution_results = execution_results
        self.execution_review_status = "not_reviewed"
        self.execution_approved = False

        if any(result.get("status") == "stopped" for result in execution_results):
            self.add_log("EXECUTION", "Execution ended with status: stopped by user.")

        active_path = self.save_execution_results_json(
            execution_results=execution_results,
            review_status="not_reviewed",
            output_filename="execution_results.json",
            source="deterministic_workflow_execution",
        )

        extracted_path = self.save_execution_results_json(
            execution_results=execution_results,
            review_status="not_reviewed",
            output_filename="execution_results_extracted.json",
            source="deterministic_workflow_execution_raw_output",
        )

        self.add_log("EXECUTION", f"{len(execution_results)} workflow steps executed.")
        self.add_log("SYSTEM", f"Active execution results saved: {active_path}")
        self.add_log("SYSTEM", f"Raw execution results saved: {extracted_path}")

        return {
            "ok": True,
            **self.state_payload(),
            "execution_results_path": str(active_path),
            "execution_results_extracted_path": str(extracted_path),
            "message": f"{len(execution_results)} workflow steps executed deterministically.",
        }

    def execute_workflow_step(self, workflow_step: dict[str, Any]) -> dict[str, Any]:
        started_at = datetime.now().isoformat()

        step = workflow_step.get("step", "")
        module_name = workflow_step.get("module", "")
        module_id = workflow_step.get("module_id", "unknown")
        input_data_artifacts = workflow_step.get("input_data_artifacts", "")
        output_artifacts = workflow_step.get("output_artifacts", "")

        generated_artifacts = self.generate_execution_artifacts(
            step=step,
            module_name=module_name,
            output_artifacts=output_artifacts,
        )

        completed_at = datetime.now().isoformat()

        evidence = (
            f"Deterministic execution completed for {module_name}. "
            f"{len(generated_artifacts)} artifact(s) generated in the module output folder."
        )

        return {
            "step": step,
            "module": module_name,
            "module_id": module_id,
            "input_data_artifacts": input_data_artifacts,
            "output_artifacts": output_artifacts,
            "generated_artifacts": "; ".join(generated_artifacts),
            "evidence": evidence,
            "status": "completed",
            "started_at": started_at,
            "completed_at": completed_at,
            "reviewed_by_user": False,
        }

    def generate_execution_artifacts(
        self,
        step: str | int,
        module_name: str,
        output_artifacts: str,
    ) -> list[str]:
        if not self.current_run_path:
            raise RuntimeError("No active run folder is available.")

        artifacts_dir = self.current_run_path / "modules_output" / self.sanitize_artifact_name(module_name)
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        artifact_names = self.parse_output_artifact_names(output_artifacts)
        generated_paths: list[str] = []

        if not artifact_names:
            artifact_names = [f"step_{step}_{module_name}_result.json"]

        for artifact_name in artifact_names:
            clean_name = self.sanitize_artifact_name(artifact_name)

            if "." not in Path(clean_name).name:
                clean_name = f"{clean_name}.json"

            artifact_path = artifacts_dir / clean_name
            suffix = artifact_path.suffix.lower()

            if suffix == ".csv":
                content = (
                    "field,value\n"
                    f"run_id,{self.current_run_id}\n"
                    f"step,{step}\n"
                    f"module,{module_name}\n"
                    "status,completed\n"
                )
                artifact_path.write_text(content, encoding="utf-8")
            elif suffix == ".txt":
                artifact_path.write_text(
                    f"STAR execution artifact\n"
                    f"run_id: {self.current_run_id}\n"
                    f"step: {step}\n"
                    f"module: {module_name}\n"
                    f"status: completed\n",
                    encoding="utf-8",
                )
            else:
                artifact_path.write_text(
                    json.dumps(
                        {
                            "run_id": self.current_run_id,
                            "generated_at": datetime.now().isoformat(),
                            "step": step,
                            "module": module_name,
                            "status": "completed",
                            "artifact_name": clean_name,
                            "note": "Deterministic placeholder artifact generated by STAR desktop prototype.",
                        },
                        indent=4,
                    ),
                    encoding="utf-8",
                )

            generated_paths.append(artifact_path.relative_to(self.current_run_path).as_posix())

        return generated_paths

    def parse_output_artifact_names(self, output_artifacts: str) -> list[str]:
        if not output_artifacts:
            return []

        raw_parts = []
        for part in str(output_artifacts).replace(",", ";").split(";"):
            cleaned = part.strip()
            if cleaned:
                raw_parts.append(cleaned)

        return raw_parts

    def sanitize_artifact_name(self, name: str) -> str:
        value = str(name).strip()
        value = value.replace("\\", "/").split("/")[-1]
        value = value.replace(" ", "_")
        allowed = []
        for char in value:
            if char.isalnum() or char in {"_", "-", "."}:
                allowed.append(char)
            else:
                allowed.append("_")

        sanitized = "".join(allowed).strip("._")

        if not sanitized:
            sanitized = "execution_artifact"

        return sanitized

    def save_reviewed_execution_results(self, reviewed_results: list[dict[str, Any]]) -> dict[str, Any]:
        if not self.current_run_path:
            return {"ok": False, "error": "No active run is available.", "logs": self.logs}

        try:
            normalized = self.validate_and_normalize_reviewed_execution_results(reviewed_results)
        except Exception as exc:
            self.add_log("ERROR", f"Reviewed execution results validation failed: {exc}")
            return {"ok": False, "error": str(exc), "logs": self.logs}

        self.execution_results = normalized
        self.execution_review_status = "reviewed_by_user"
        self.execution_approved = False

        reviewed_path = self.save_execution_results_json(
            execution_results=normalized,
            review_status="reviewed_by_user",
            output_filename="execution_results_reviewed.json",
            source="user_reviewed_execution_results",
        )

        active_path = self.save_execution_results_json(
            execution_results=normalized,
            review_status="reviewed_by_user",
            output_filename="execution_results.json",
            source="active_execution_results_after_user_review",
        )

        self.add_log("USER", "Execution results reviewed and saved by user.")
        self.add_log("SYSTEM", f"Reviewed execution results saved: {reviewed_path}")
        self.add_log("SYSTEM", f"Active execution results updated: {active_path}")

        return {
            "ok": True,
            **self.state_payload(),
            "execution_results_reviewed_path": str(reviewed_path),
            "execution_results_path": str(active_path),
            "message": "Reviewed execution results saved. They can now be approved.",
        }

    def validate_and_normalize_reviewed_execution_results(self, reviewed_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not isinstance(reviewed_results, list):
            raise ValueError("Reviewed execution results payload must be a list.")

        module_names = set(self.get_module_names())
        normalized = []
        seen_steps = set()

        for index, result in enumerate(reviewed_results, start=1):
            step_value = str(result.get("step", "")).strip()
            module_name = str(result.get("module", "")).strip()
            input_data_artifacts = str(result.get("input_data_artifacts", "")).strip()
            output_artifacts = str(result.get("output_artifacts", "")).strip()
            generated_artifacts = str(result.get("generated_artifacts", "")).strip()
            evidence = str(result.get("evidence", "")).strip()
            status = str(result.get("status", "")).strip()

            if not step_value:
                raise ValueError(f"Execution row {index} has an empty step.")
            if step_value in seen_steps:
                raise ValueError(f"Duplicate execution step found: {step_value}")
            if not module_name:
                raise ValueError(f"Execution step {step_value} has an empty module name.")
            if module_names and module_name not in module_names:
                raise ValueError(f"Execution step {step_value} has invalid module name '{module_name}'.")
            if not output_artifacts:
                raise ValueError(f"Execution step {step_value} has empty output artifacts.")
            if status not in ALLOWED_EXECUTION_STATUSES:
                raise ValueError(f"Execution step {step_value} has invalid status '{status}'.")
            if not generated_artifacts and status not in {"stopped", "skipped", "failed"}:
                raise ValueError(f"Execution step {step_value} has empty generated artifacts.")
            if not evidence:
                raise ValueError(f"Execution step {step_value} has empty evidence.")

            seen_steps.add(step_value)
            module = self.get_module_by_name(module_name)

            normalized.append(
                {
                    "step": step_value,
                    "module": module_name,
                    "module_id": module.get("module_id", "unknown") if module else "unknown",
                    "input_data_artifacts": input_data_artifacts,
                    "output_artifacts": output_artifacts,
                    "generated_artifacts": generated_artifacts,
                    "evidence": evidence,
                    "status": status,
                    "started_at": str(result.get("started_at", "")),
                    "completed_at": str(result.get("completed_at", "")),
                    "duration_seconds": result.get("duration_seconds", ""),
                    "duration_human": str(result.get("duration_human", "")),
                    "reviewed_by_user": True,
                }
            )

        return normalized

    def approve_execution_results(self) -> dict[str, Any]:
        if not self.execution_results:
            return {"ok": False, "error": "No execution results are available to approve.", "logs": self.logs}

        approved_results = []
        approved_module_names = set()

        for result in self.execution_results:
            approved_result = dict(result)
            approved_result["status"] = "approved"
            approved_result["approved_by_user"] = True
            approved_results.append(approved_result)
            approved_module_names.add(approved_result.get("module"))

        self.execution_results = approved_results
        self.execution_review_status = "approved_by_user"
        self.execution_approved = True
        self.reset_downstream_from_execution()

        for module in self.modules:
            if module.get("module_name") in approved_module_names:
                module["status"] = "Completed"
            else:
                module["status"] = "Idle"

        approved_path = self.save_execution_results_json(
            execution_results=approved_results,
            review_status="approved_by_user",
            output_filename="approved_execution_results.json",
            source="user_approved_execution_results",
        )

        active_path = self.save_execution_results_json(
            execution_results=approved_results,
            review_status="approved_by_user",
            output_filename="execution_results.json",
            source="approved_active_execution_results",
        )

        self.add_log("USER", "Execution results approved by user.")
        self.add_log("SYSTEM", f"approved_execution_results.json saved: {approved_path}")
        self.add_log("SYSTEM", f"Active execution results updated: {active_path}")

        return {
            "ok": True,
            **self.state_payload(),
            "approved_execution_results_path": str(approved_path),
            "execution_results_path": str(active_path),
            "message": "Execution results approved.",
        }

    def save_execution_results_json(
        self,
        execution_results: list[dict[str, Any]],
        review_status: str,
        output_filename: str,
        source: str,
    ) -> Path:
        if not self.current_run_path:
            raise RuntimeError("No active run folder is available.")

        output_path = self.current_run_path / "intermediate" / output_filename

        with output_path.open("w", encoding="utf-8") as file:
            json.dump(
                {
                    "run_id": self.current_run_id,
                    "generated_at": datetime.now().isoformat(),
                    **self.get_source_document_metadata(),
                    "source": source,
                    "review_status": review_status,
                    "allowed_statuses": ALLOWED_EXECUTION_STATUSES,
                    "execution_results": execution_results,
                },
                file,
                indent=4,
            )

        return output_path



    # ------------------------------------------------------------------
    # Report generation
    # ------------------------------------------------------------------
    def generate_report_package(self) -> dict[str, Any]:
        if not self.execution_approved:
            return {
                "ok": False,
                "error": "Approve execution results before generating the report package.",
                "logs": self.logs,
            }

        if not self.current_run_path:
            return {"ok": False, "error": "No active run is available.", "logs": self.logs}

        self.add_log("REPORT", "Generating STAR preliminary report package.")

        reports_dir = self.current_run_path / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)

        report_md_path = reports_dir / "star_preliminary_mission_study_report.md"
        executive_summary_path = reports_dir / "executive_summary.txt"
        traceability_path = reports_dir / "traceability_matrix.csv"
        artifact_registry_path = reports_dir / "artifact_registry.csv"
        run_summary_path = reports_dir / "run_summary.json"

        report_md_path.write_text(self.build_preliminary_report_markdown(), encoding="utf-8")
        executive_summary_path.write_text(self.build_executive_summary_text(), encoding="utf-8")
        self.write_traceability_matrix_csv(traceability_path)
        self.write_artifact_registry_csv(artifact_registry_path)

        run_summary = self.build_run_summary()
        run_summary_path.write_text(json.dumps(run_summary, indent=4), encoding="utf-8")

        manifest = [
            {
                "artifact": "STAR preliminary mission study report",
                "type": "markdown",
                "path": report_md_path.relative_to(self.current_run_path).as_posix(),
                "status": "generated",
            },
            {
                "artifact": "Executive summary",
                "type": "text",
                "path": executive_summary_path.relative_to(self.current_run_path).as_posix(),
                "status": "generated",
            },
            {
                "artifact": "Traceability matrix",
                "type": "csv",
                "path": traceability_path.relative_to(self.current_run_path).as_posix(),
                "status": "generated",
            },
            {
                "artifact": "Artifact registry",
                "type": "csv",
                "path": artifact_registry_path.relative_to(self.current_run_path).as_posix(),
                "status": "generated",
            },
            {
                "artifact": "Run summary",
                "type": "json",
                "path": run_summary_path.relative_to(self.current_run_path).as_posix(),
                "status": "generated",
            },
        ]

        self.report_manifest = manifest
        self.report_status = "generated"

        manifest_reports_path = reports_dir / "report_manifest.json"
        manifest_intermediate_path = self.current_run_path / "intermediate" / "report_manifest.json"

        manifest_payload = {
            "run_id": self.current_run_id,
            "generated_at": datetime.now().isoformat(),
            **self.get_source_document_metadata(),
            "source": "star_report_generation",
            "report_status": self.report_status,
            "report_manifest": manifest,
        }

        manifest_reports_path.write_text(json.dumps(manifest_payload, indent=4), encoding="utf-8")
        manifest_intermediate_path.write_text(json.dumps(manifest_payload, indent=4), encoding="utf-8")

        manifest.append(
            {
                "artifact": "Report manifest",
                "type": "json",
                "path": manifest_reports_path.relative_to(self.current_run_path).as_posix(),
                "status": "generated",
            }
        )

        # Rewrite run summary after the final manifest is available so counts are consistent.
        run_summary_path.write_text(json.dumps(self.build_run_summary(), indent=4), encoding="utf-8")

        self.add_log("REPORT", f"Report package generated with {len(manifest)} files.")
        for item in manifest:
            self.add_log("REPORT", f"{item['artifact']}: {item['path']}")

        return {
            "ok": True,
            **self.state_payload(),
            "report_manifest_path": str(manifest_reports_path),
            "report_manifest_intermediate_path": str(manifest_intermediate_path),
            "message": f"Report package generated with {len(manifest)} files.",
        }

    def build_preliminary_report_markdown(self) -> str:
        lines: list[str] = []

        lines.append("# STAR Preliminary Mission Study Report")
        lines.append("")
        lines.append(f"**Run ID:** {self.current_run_id}")
        lines.append(f"**Generated at:** {datetime.now().isoformat()}")
        lines.append(f"**Input document:** {self.input_document_filename or 'unknown'}")
        lines.append("")

        lines.append("## 1. Mission Request Source")
        lines.append("")
        lines.append(f"- Source document: `{self.input_document_filename or 'unknown'}`")
        lines.append(f"- Saved copy: `{self.input_document_saved_relative_path or 'unknown'}`")
        lines.append("")

        lines.append("## 2. Reviewed Requirements")
        lines.append("")
        lines.append("| ID | Requirement | Category | Status |")
        lines.append("|---|---|---|---|")
        for req in self.requirements:
            lines.append(
                f"| {self.md(req.get('id'))} | {self.md(req.get('text'))} | "
                f"{self.md(req.get('category'))} | {self.md(req.get('status'))} |"
            )
        lines.append("")

        lines.append("## 3. Approved Assumptions / Mission Parameters")
        lines.append("")
        lines.append("| Assumption | Parameter | Needed by | Value | Unit | Source |")
        lines.append("|---|---|---|---|---|---|")
        for item in self.missing_information:
            lines.append(
                f"| {self.md(item.get('assumption_id', '-'))} | {self.md(item.get('parameter'))} | "
                f"{self.md(item.get('needed_by'))} | {self.md(item.get('proposed_value'))} | "
                f"{self.md(item.get('unit'))} | {self.md(item.get('source'))} |"
            )
        lines.append("")

        lines.append("## 4. Approved Workflow")
        lines.append("")
        lines.append("| Step | Module | Input data / artifacts | Output artifacts | Status |")
        lines.append("|---|---|---|---|---|")
        for step in self.workflow_steps:
            lines.append(
                f"| {self.md(step.get('step'))} | {self.md(step.get('module'))} | "
                f"{self.md(step.get('input_data_artifacts'))} | {self.md(step.get('output_artifacts'))} | "
                f"{self.md(step.get('status'))} |"
            )
        lines.append("")

        lines.append("## 5. Approved Execution Results")
        lines.append("")
        lines.append("| Step | Module | Generated artifacts | Evidence | Status |")
        lines.append("|---|---|---|---|---|")
        for result in self.execution_results:
            lines.append(
                f"| {self.md(result.get('step'))} | {self.md(result.get('module'))} | "
                f"{self.md(result.get('generated_artifacts'))} | {self.md(result.get('evidence'))} | "
                f"{self.md(result.get('status'))} |"
            )
        lines.append("")

        lines.append("## 6. Notes")
        lines.append("")
        lines.append(
            "This report was generated by the STAR desktop prototype from reviewed and approved "
            "intermediate artifacts. Current module outputs are deterministic placeholder artifacts "
            "intended to validate the workflow, traceability and report-generation pipeline."
        )
        lines.append("")

        return "\n".join(lines)

    def build_executive_summary_text(self) -> str:
        completed_modules = [
            result.get("module", "unknown module")
            for result in self.execution_results
            if result.get("status") in {"completed", "approved"}
        ]

        lines = [
            "STAR Preliminary Mission Study - Executive Summary",
            "",
            f"Run ID: {self.current_run_id}",
            f"Input document: {self.input_document_filename or 'unknown'}",
            f"Reviewed requirements: {len(self.requirements)}",
            f"Approved assumptions: {len(self.missing_information)}",
            f"Approved workflow steps: {len(self.workflow_steps)}",
            f"Approved execution results: {len(self.execution_results)}",
            "",
            "Executed modules:",
        ]

        if completed_modules:
            for module_name in completed_modules:
                lines.append(f"- {module_name}")
        else:
            lines.append("- none")

        lines.extend(
            [
                "",
                "The current report package is generated from the reviewed STAR pipeline artifacts.",
            ]
        )

        return "\n".join(lines)

    def build_run_summary(self) -> dict[str, Any]:
        return {
            "run_id": self.current_run_id,
            "generated_at": datetime.now().isoformat(),
            **self.get_source_document_metadata(),
            "counts": {
                "requirements": len(self.requirements),
                "approved_assumptions": len(self.missing_information),
                "workflow_steps": len(self.workflow_steps),
                "execution_results": len(self.execution_results),
                "generated_report_files": len(self.report_manifest),
            },
            "status": {
                "requirements_review_status": self.requirements_review_status,
                "missing_information_review_status": self.missing_information_review_status,
                "assumptions_approved": self.assumptions_approved,
                "workflow_review_status": self.workflow_review_status,
                "workflow_approved": self.workflow_approved,
                "execution_review_status": self.execution_review_status,
                "execution_approved": self.execution_approved,
                "report_status": self.report_status,
            },
            "modules": self.modules,
        }

    def write_traceability_matrix_csv(self, output_path: Path) -> None:
        rows = self.build_traceability_rows()

        with output_path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=[
                    "requirement_id",
                    "requirement_text",
                    "requirement_category",
                    "workflow_step",
                    "module",
                    "execution_status",
                    "generated_artifacts",
                    "evidence",
                ],
            )
            writer.writeheader()
            writer.writerows(rows)

    def build_traceability_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []

        for requirement in self.requirements:
            linked_results = self.find_execution_results_for_requirement(requirement)

            if not linked_results:
                rows.append(
                    {
                        "requirement_id": requirement.get("id", ""),
                        "requirement_text": requirement.get("text", ""),
                        "requirement_category": requirement.get("category", ""),
                        "workflow_step": "",
                        "module": "",
                        "execution_status": "not_linked",
                        "generated_artifacts": "",
                        "evidence": "No direct execution result linked by the current deterministic mapper.",
                    }
                )
                continue

            for result in linked_results:
                rows.append(
                    {
                        "requirement_id": requirement.get("id", ""),
                        "requirement_text": requirement.get("text", ""),
                        "requirement_category": requirement.get("category", ""),
                        "workflow_step": result.get("step", ""),
                        "module": result.get("module", ""),
                        "execution_status": result.get("status", ""),
                        "generated_artifacts": result.get("generated_artifacts", ""),
                        "evidence": result.get("evidence", ""),
                    }
                )

        return rows

    def find_execution_results_for_requirement(self, requirement: dict[str, Any]) -> list[dict[str, Any]]:
        category = str(requirement.get("category", "")).lower()
        text = str(requirement.get("text", "")).lower()

        preferred_keywords: list[str] = []

        if category in {"mission", "functional"} or any(word in text for word in ["revisit", "coverage", "constellation", "latency"]):
            preferred_keywords.append("constellation")

        if category in {"mission", "design", "functional", "functional"} or any(word in text for word in ["observation", "design", "acquisition", "sensor", "monitor"]):
            preferred_keywords.append("observation")

        if category == "functional" or any(word in text for word in ["battery", "power", "functional", "energy", "soh", "rul"]):
            preferred_keywords.extend(["battery", "functional"])

        linked = []
        for result in self.execution_results:
            module_name = str(result.get("module", "")).lower()
            if any(keyword in module_name for keyword in preferred_keywords):
                linked.append(result)

        if not linked and self.execution_results:
            linked.append(self.execution_results[0])

        return linked

    def write_artifact_registry_csv(self, output_path: Path) -> None:
        rows = []

        for result in self.execution_results:
            artifact_paths = [
                path.strip()
                for path in str(result.get("generated_artifacts", "")).split(";")
                if path.strip()
            ]

            for artifact_path in artifact_paths:
                rows.append(
                    {
                        "artifact_path": artifact_path,
                        "produced_by": result.get("module", ""),
                        "workflow_step": result.get("step", ""),
                        "status": result.get("status", ""),
                        "evidence": result.get("evidence", ""),
                    }
                )

        with output_path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=[
                    "artifact_path",
                    "produced_by",
                    "workflow_step",
                    "status",
                    "evidence",
                ],
            )
            writer.writeheader()
            writer.writerows(rows)

    def md(self, value: Any) -> str:
        text = str(value if value is not None else "")
        text = text.replace("|", "\\|")
        text = text.replace("\n", " ")
        return text


    # ------------------------------------------------------------------
    # STAR pipeline refactor: RAG-based planning -> input resolution
    # ------------------------------------------------------------------
    def ensure_pipeline_state(self) -> None:
        if not hasattr(self, "requested_outputs"):
            self.requested_outputs: list[dict[str, Any]] = []
        if not hasattr(self, "requested_outputs_review_status"):
            self.requested_outputs_review_status = "not_available"
        if not hasattr(self, "mission_planning_status"):
            self.mission_planning_status = "not_available"
        if not hasattr(self, "rag_sources"):
            self.rag_sources: list[dict[str, Any]] = []

    def get_initial_state(self) -> dict[str, Any]:
        self.ensure_pipeline_state()
        return {
            "app_name": "STAR-Local Desktop App",
            "subtitle": "Space mission Twin for Architecture Representation",
            "modules": self.modules,
            "logs": self.logs,
            "run": self.get_run_state(),
            "requirements": self.requirements,
            "requirements_review_status": self.requirements_review_status,
            "requested_outputs": self.requested_outputs,
            "requested_outputs_review_status": self.requested_outputs_review_status,
            "mission_planning_status": self.mission_planning_status,
            "rag_sources": self.rag_sources,
            "missing_information": self.missing_information,
            "missing_information_review_status": self.missing_information_review_status,
            "assumptions_approved": self.assumptions_approved,
            "workflow": self.workflow_steps,
            "workflow_review_status": self.workflow_review_status,
            "workflow_approved": self.workflow_approved,
            "execution_results": self.execution_results,
            "execution_review_status": self.execution_review_status,
            "execution_approved": self.execution_approved,
            "execution_running": self.execution_running,
            "execution_error": self.execution_error,
            "execution_stop_requested": self.execution_stop_requested,
            "active_module_name": self.active_module_name,
            "active_module_id": self.active_module_id,
            "report_manifest": self.report_manifest,
            "report_status": self.report_status,
            "allowed_requirement_categories": ALLOWED_REQUIREMENT_CATEGORIES,
            "allowed_requirement_statuses": ALLOWED_REQUIREMENT_STATUSES,
            "allowed_missing_information_statuses": ALLOWED_MISSING_INFORMATION_STATUSES,
            "allowed_missing_information_sources": ALLOWED_MISSING_INFORMATION_SOURCES,
            "allowed_workflow_statuses": ALLOWED_WORKFLOW_STATUSES,
            "allowed_execution_statuses": ALLOWED_EXECUTION_STATUSES,
            "module_names": self.get_module_names(),
        }

    def state_payload(self) -> dict[str, Any]:
        self.ensure_pipeline_state()
        return {
            "run": self.get_run_state(),
            "modules": self.modules,
            "requirements": self.requirements,
            "requirements_review_status": self.requirements_review_status,
            "requested_outputs": self.requested_outputs,
            "requested_outputs_review_status": self.requested_outputs_review_status,
            "mission_planning_status": self.mission_planning_status,
            "rag_sources": self.rag_sources,
            "missing_information": self.missing_information,
            "missing_information_review_status": self.missing_information_review_status,
            "assumptions_approved": self.assumptions_approved,
            "workflow": self.workflow_steps,
            "workflow_review_status": self.workflow_review_status,
            "workflow_approved": self.workflow_approved,
            "execution_results": self.execution_results,
            "execution_review_status": self.execution_review_status,
            "execution_approved": self.execution_approved,
            "execution_running": self.execution_running,
            "execution_error": self.execution_error,
            "execution_stop_requested": self.execution_stop_requested,
            "active_module_name": self.active_module_name,
            "active_module_id": self.active_module_id,
            "report_manifest": self.report_manifest,
            "report_status": self.report_status,
            "logs": self.logs,
        }

    def sanitize_run_folder_name(self, raw_name: str | None) -> str | None:
        """Return a safe user-defined run folder name, or None for the default name."""
        name = (raw_name or "").strip()
        if not name:
            return None

        # Keep only characters that are safe on Windows/macOS/Linux filesystems.
        name = re.sub(r"[^A-Za-z0-9_. -]+", "_", name)
        name = re.sub(r"\s+", "_", name).strip("._- ")
        return name[:80] or None

    def unique_run_id(self, base_name: str) -> str:
        """Avoid overwriting an existing run folder by adding _01, _02, ..."""
        candidate = base_name
        counter = 1
        while (self.outputs_dir / candidate).exists():
            candidate = f"{base_name}_{counter:02d}"
            counter += 1
        return candidate

    def create_run_folder(self, custom_run_folder_name: str | None = None) -> None:
        sanitized_name = self.sanitize_run_folder_name(custom_run_folder_name)
        if sanitized_name:
            self.current_run_id = self.unique_run_id(sanitized_name)
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.current_run_id = self.unique_run_id(f"RUN_{timestamp}")

        # Every run is created outside the star_cef software folder, under:
        #   <STAR root>/Output/<RUN_ID>/
        self.current_run_path = self.outputs_dir / self.current_run_id

        for subfolder in [
            "input",
            "intermediate",
            "planning",
            "module_inputs",
            "modules_output",
            "reports",
            "logs",
        ]:
            (self.current_run_path / subfolder).mkdir(parents=True, exist_ok=True)

        self.add_log("SYSTEM", f"Run output folder created: {self.current_run_path}")

    def reset_downstream_from_requirements(self) -> None:
        self.ensure_pipeline_state()
        self.requested_outputs = []
        self.requested_outputs_review_status = "not_available"
        self.mission_planning_status = "not_available"
        self.rag_sources = []

        self.missing_information = []
        self.missing_information_review_status = "not_available"
        self.assumptions_approved = False

        self.workflow_steps = []
        self.workflow_review_status = "not_available"
        self.workflow_approved = False

        self.execution_results = []
        self.execution_review_status = "not_available"
        self.execution_approved = False
        self.execution_error = None
        self.execution_stop_requested = False
        self.active_module_name = None
        self.active_module_id = None
        if hasattr(self, "execution_stop_event"):
            self.execution_stop_event.clear()

        self.report_manifest = []
        self.report_status = "not_available"

    def reset_downstream_from_workflow(self) -> None:
        self.execution_results = []
        self.execution_review_status = "not_available"
        self.execution_approved = False
        self.reset_downstream_from_execution()

    def reset_downstream_from_assumptions(self) -> None:
        self.execution_results = []
        self.execution_review_status = "not_available"
        self.execution_approved = False
        self.reset_downstream_from_execution()

    def reset_run_state_after_new_upload(self) -> None:
        self.ensure_pipeline_state()
        self.uploaded_text = None
        self.input_document_filename = None
        self.input_document_original_path = None
        self.input_document_saved_relative_path = None
        self.input_document_saved_absolute_path = None

        self.requirements = []
        self.requirements_extraction_mode = None
        self.requirements_review_status = "not_available"

        self.requested_outputs = []
        self.requested_outputs_review_status = "not_available"
        self.mission_planning_status = "not_available"
        self.rag_sources = []

        self.missing_information = []
        self.missing_information_review_status = "not_available"
        self.assumptions_approved = False

        self.workflow_steps = []
        self.workflow_review_status = "not_available"
        self.workflow_approved = False

        self.execution_results = []
        self.execution_review_status = "not_available"
        self.execution_approved = False
        self.execution_error = None
        self.execution_stop_requested = False
        self.active_module_name = None
        self.active_module_id = None
        if hasattr(self, "execution_stop_event"):
            self.execution_stop_event.clear()

        self.report_manifest = []
        self.report_status = "not_available"

        for module in self.modules:
            module["status"] = "Idle"

    # ------------------------------
    # Lightweight local RAG retrieval
    # ------------------------------
    def tokenize_for_retrieval(self, text: str) -> set[str]:
        normalized = self.normalize_text(text or "")
        tokens = set(re.findall(r"[a-z0-9_\-]{4,}", normalized))
        stop_words = {
            "shall", "with", "from", "that", "this", "mission", "system", "module",
            "required", "requirements", "preliminary", "analysis", "design", "using",
            "into", "over", "under", "where", "which", "when", "what", "must",
        }
        return {token for token in tokens if token not in stop_words}

    def iter_knowledge_documents(self) -> list[tuple[Path, str]]:
        kb_dir = self.data_dir / "knowledge_base"
        if not kb_dir.exists():
            return []

        documents: list[tuple[Path, str]] = []
        for path in sorted(kb_dir.rglob("*")):
            if path.is_file() and path.suffix.lower() in {".md", ".txt", ".rst"}:
                try:
                    text = path.read_text(encoding="utf-8-sig")
                except UnicodeDecodeError:
                    text = path.read_text(encoding="utf-8", errors="ignore")
                if text.strip():
                    documents.append((path, text))
        return documents

    def split_knowledge_text(self, text: str, max_chars: int = 1800) -> list[str]:
        chunks: list[str] = []
        current: list[str] = []
        current_len = 0
        for block in re.split(r"\n(?=#)|\n\s*\n", text):
            block = block.strip()
            if not block:
                continue
            if current and current_len + len(block) > max_chars:
                chunks.append("\n\n".join(current))
                current = []
                current_len = 0
            current.append(block)
            current_len += len(block)
        if current:
            chunks.append("\n\n".join(current))
        return chunks

    def module_doc_boost_for_retrieval(self, relative_path: str, query_text: str, query_tokens: set[str]) -> float:
        """Boost module documents that are explicitly relevant to the planning query.

        The simple keyword retriever can otherwise be dominated by long IDDs with
        many generic space-mission terms.  This targeted boost keeps retrieval
        balanced without turning the planner into a hard-coded workflow.
        """
        path = relative_path.lower()
        query_norm = self.normalize_text(query_text)
        boost = 0.0

        if "end-007" in path or "synthetic" in path:
            if any(token in query_norm for token in [
                "synthetic", "simulated", "simulation", "image", "imagery",
                "payload", "optical", "gsd", "ground sample distance",
                "spatial resolution", "swath", "footprint",
                "acquisition geometry", "data acquisition", "observation geometry",
                "sensor", "camera", "imager",
            ]):
                boost += 18.0

        if "end-003" in path or "attitude" in path:
            if any(token in query_norm for token in [
                "attitude", "nadir", "pointing", "quaternion",
                "line of sight", "viewing geometry", "observation geometry",
                "target tracking", "sensor-target",
            ]):
                boost += 14.0

        if "end-001" in path or "constellation" in path:
            if any(token in query_norm for token in [
                "constellation", "revisit", "coverage", "access",
                "observation window", "acquisition frequency", "orbit",
            ]):
                boost += 10.0

        if "mission_design" in path and any(token in query_norm for token in [
            "earth observation", "monitoring", "payload", "acquisition",
            "observation", "geometry", "revisit", "coverage",
        ]):
            boost += 4.0

        return boost

    def retrieve_knowledge_context(self, query: str, max_chunks: int = 8) -> list[dict[str, Any]]:
        query_tokens = self.tokenize_for_retrieval(query)
        query_text = query or ""
        scored: list[tuple[float, dict[str, Any]]] = []

        for path, text in self.iter_knowledge_documents():
            relative_path = path.relative_to(self.data_dir).as_posix()
            path_tokens = self.tokenize_for_retrieval(relative_path.replace("/", " ").replace("_", " "))
            for idx, chunk in enumerate(self.split_knowledge_text(text), start=1):
                chunk_tokens = self.tokenize_for_retrieval(chunk)
                overlap = query_tokens & (chunk_tokens | path_tokens)
                if not overlap:
                    continue
                score = float(len(overlap))
                if "mission_design" in relative_path:
                    score += 1.5
                if "module_docs" in relative_path:
                    score += 1.0
                if "standards" in relative_path:
                    score += 0.5
                if any(token in relative_path.lower() for token in query_tokens):
                    score += 1.0
                score += self.module_doc_boost_for_retrieval(relative_path, query_text, query_tokens)
                scored.append(
                    (
                        score,
                        {
                            "source_path": relative_path,
                            "chunk_id": idx,
                            "score": score,
                            "content": chunk[:2500],
                        },
                    )
                )

        scored.sort(key=lambda item: item[0], reverse=True)

        # Keep the context diverse: no single long IDD should consume all slots.
        selected: list[dict[str, Any]] = []
        per_source_count: dict[str, int] = {}
        per_source_limit = 2
        for _, item in scored:
            source = str(item.get("source_path", ""))
            if per_source_count.get(source, 0) >= per_source_limit:
                continue
            selected.append(item)
            per_source_count[source] = per_source_count.get(source, 0) + 1
            if len(selected) >= max_chunks:
                break

        # If diversity filtering made the context too small, fill remaining slots.
        if len(selected) < max_chunks:
            seen = {(item.get("source_path"), item.get("chunk_id")) for item in selected}
            for _, item in scored:
                key = (item.get("source_path"), item.get("chunk_id"))
                if key in seen:
                    continue
                selected.append(item)
                if len(selected) >= max_chunks:
                    break

        return selected

    def format_rag_context_for_prompt(self, chunks: list[dict[str, Any]]) -> str:
        if not chunks:
            return "No local knowledge-base chunks were retrieved."
        parts = []
        for chunk in chunks:
            parts.append(
                f"[SOURCE: {chunk['source_path']}#chunk-{chunk['chunk_id']} | score={chunk['score']:.1f}]\n"
                f"{chunk['content']}"
            )
        return "\n\n---\n\n".join(parts)

    # ------------------------------
    # Mission planning: outputs + workflow
    # ------------------------------
    def propose_workflow(self, mode: str = "Local LLM via Ollama (RAG)") -> dict[str, Any]:
        self.ensure_pipeline_state()

        if not self.requirements:
            return {"ok": False, "error": "No active requirements are available. Extract and review requirements first.", "logs": self.logs}
        if self.requirements_review_status != "reviewed_by_user":
            return {"ok": False, "error": "Save reviewed requirements before generating mission planning.", "logs": self.logs}
        if not self.current_run_path:
            return {"ok": False, "error": "No active run is available.", "logs": self.logs}

        mode = mode or "Local LLM via Ollama (RAG)"
        self.add_log("AI", f"Generating mission planning using mode: {mode}.")

        try:
            if "LLM" in mode or "RAG" in mode:
                requested_outputs, workflow, rag_sources = self.llm_rag_mission_planning()
                source = "llm_rag_mission_planning"
                raw_source = "llm_rag_mission_planning_raw_output"
            else:
                requested_outputs, workflow, rag_sources = self.rule_based_mission_planning()
                source = "rule_based_mission_planning"
                raw_source = "rule_based_mission_planning_raw_output"
        except Exception as exc:
            self.add_log("ERROR", f"Mission planning failed in {mode}: {exc}")
            self.add_log("AI", "Falling back to rule-based mission planning.")
            requested_outputs, workflow, rag_sources = self.rule_based_mission_planning()
            source = "rule_based_mission_planning_after_llm_fallback"
            raw_source = "rule_based_mission_planning_raw_output_after_llm_fallback"

        if not requested_outputs or not workflow:
            return {"ok": False, "error": "No requested outputs or workflow steps could be generated.", "logs": self.logs}

        self.requested_outputs = requested_outputs
        self.requested_outputs_review_status = "not_reviewed"
        self.mission_planning_status = "not_reviewed"
        self.rag_sources = rag_sources

        self.workflow_steps = workflow
        self.workflow_review_status = "not_reviewed"
        self.workflow_approved = False

        self.missing_information = []
        self.missing_information_review_status = "not_available"
        self.assumptions_approved = False
        self.reset_downstream_from_workflow()

        requested_active_path = self.save_requested_outputs_json(
            requested_outputs=requested_outputs,
            review_status="not_reviewed",
            output_filename="requested_outputs.json",
            source=source,
            rag_sources=rag_sources,
        )
        requested_raw_path = self.save_requested_outputs_json(
            requested_outputs=requested_outputs,
            review_status="not_reviewed",
            output_filename="requested_outputs_extracted.json",
            source=raw_source,
            rag_sources=rag_sources,
        )
        workflow_active_path = self.save_workflow_json(
            workflow=workflow,
            review_status="not_reviewed",
            output_filename="workflow_proposal.json",
            source=source,
        )
        workflow_raw_path = self.save_workflow_json(
            workflow=workflow,
            review_status="not_reviewed",
            output_filename="workflow_proposal_extracted.json",
            source=raw_source,
        )
        planning_package_path = self.save_mission_planning_package_json(
            requested_outputs=requested_outputs,
            workflow=workflow,
            review_status="not_reviewed",
            source=source,
            rag_sources=rag_sources,
        )

        planned_module_names = {step.get("module") for step in workflow}
        for module in self.modules:
            module["status"] = "Ready" if module.get("module_name") in planned_module_names else "Idle"

        self.add_log("AI", f"Mission planning generated {len(requested_outputs)} requested output(s) and {len(workflow)} workflow step(s).")
        if rag_sources:
            self.add_log("RAG", f"Retrieved {len(rag_sources)} knowledge-base chunk(s) for planning.")
        self.add_log("SYSTEM", f"requested_outputs.json saved: {requested_active_path}")
        self.add_log("SYSTEM", f"workflow_proposal.json saved: {workflow_active_path}")

        return {
            "ok": True,
            **self.state_payload(),
            "requested_outputs_path": str(requested_active_path),
            "requested_outputs_extracted_path": str(requested_raw_path),
            "workflow_proposal_path": str(workflow_active_path),
            "workflow_proposal_extracted_path": str(workflow_raw_path),
            "mission_planning_package_path": str(planning_package_path),
            "message": f"Mission planning generated {len(requested_outputs)} requested output(s) and {len(workflow)} workflow step(s) using {mode}.",
        }

    def llm_rag_mission_planning(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        query = "\n".join([
            self.uploaded_text or "",
            json.dumps(self.requirements, ensure_ascii=False),
            json.dumps(self.compact_module_registry_for_llm(), ensure_ascii=False),
        ])[:12000]
        rag_sources = self.retrieve_knowledge_context(query, max_chunks=8)
        registry = self.compact_module_registry_for_llm()
        module_names = self.get_module_names()

        system_prompt = (
            "You are STAR's RAG-based mission planning assistant. "
            "Use retrieved documents as background engineering knowledge, not as a fixed recipe. "
            "Reason from the approved requirements and requested final outputs. "
            "Return only valid JSON and do not use markdown fences."
        )

        user_prompt = f"""
TASK
After requirements have been approved, identify what STAR must calculate/generate/evaluate as final requested outputs, then propose a coherent workflow of STAR modules to obtain those outputs.

INPUTS
1. Mission request excerpt:
\"\"\"
{(self.uploaded_text or "")[:7000]}
\"\"\"

2. Approved requirements:
{json.dumps(self.requirements, indent=2)}

3. Module registry. Use only these modules and their declared interfaces:
{json.dumps(registry, indent=2)}

4. Retrieved local knowledge-base context:
{self.format_rag_context_for_prompt(rag_sources)}

STRICT RULES
- First identify final requested outputs: results, products, analyses, datasets, metrics, or feasibility assessments that are actually requested by the mission request or approved requirements.
- Distinguish final requested outputs from intermediate artifacts.
- Then select modules that contribute to requested outputs, produce required upstream artifacts, or evaluate explicitly requested constraints.
- Use only these exact module names: {json.dumps(module_names)}
- Do not invent modules.
- Do not invent module outputs that conflict with the registry. If a useful module has incomplete registry outputs, state a generic output based on its module purpose and mark the rationale as requiring registry refinement.
- Do not include a module only because it is generally related to Earth Observation.
- Do not include power/battery modules unless power, battery, energy, duty cycle, EPS, SOH/RUL, or operational feasibility is requested or needed by an approved output.
- Treat payload/sensor performance checks as possible final requested outputs when the requirements mention optical payload, sensor, image products, spatial resolution, GSD, swath, footprint, acquisition geometry or verification of observation performance.
- If trajectory/access windows and attitude/pointing are produced for an EO payload case, check whether a sensor-level observation/synthetic-data module is needed to transform geometry into payload-resolution, image, metadata or observation-performance outputs.
- If a downstream module requires acquisition geometry, trajectory, access windows, scenario package, attitude profile or sensor model, include upstream modules only when they are needed to produce those artifacts.
- Do not force a custom scenario-generation module before synthetic-data generation if the selected module registry says that simplified/base scenes or global reference maps are acceptable. Include custom scenario generation only when the mission requires high-fidelity terrain, local DEM/texture, 3D targets, event-specific rendering or a mission-specific scene package.
- Use RAG documents as engineering context. Adapt them to this mission; do not copy a generic workflow.
- Return a compact workflow in execution order.

OUTPUT FORMAT
Return only valid JSON:
{{
  "requested_outputs": [
    {{
      "id": "OUT-001",
      "description": "output to be produced",
      "output_type": "mission_analysis_result | data_product | engineering_feasibility | simulation_product | report_artifact | other",
      "priority": "high | medium | low",
      "derived_from_requirements": ["REQ-001"],
      "rationale": "why this is a final requested output",
      "status": "proposed"
    }}
  ],
  "workflow": [
    {{
      "step": 1,
      "module": "exact module_name from registry",
      "module_id": "module id",
      "input_data_artifacts": "expected inputs or upstream artifacts, not detailed missing parameters yet",
      "output_artifacts": "declared or expected outputs used by the plan",
      "rationale": "why this module is needed and which requested outputs it supports",
      "status": "proposed"
    }}
  ]
}}

FINAL INSTRUCTION
The retrieved knowledge-base text above is background only: do not continue, summarise or imitate it.
Reply with ONLY the JSON object described in OUTPUT FORMAT, starting with {{ and ending with }}.
"""

        # A complete plan (requested outputs + 5-6 workflow steps) needs ~1500 tokens;
        # 3500 leaves a wide margin while cutting off a derailed, endless answer.
        data = self.call_local_llm_json(system_prompt, user_prompt, max_tokens=3500)
        requested_outputs = self.normalize_requested_outputs(data.get("requested_outputs", []))
        workflow = self.normalize_planning_workflow(data.get("workflow", data.get("workflow_steps", [])))

        if not requested_outputs or not workflow:
            self.add_log("AI", "LLM/RAG planning output was empty after validation.")
            return self.rule_based_mission_planning()

        requested_outputs, workflow = self.repair_mission_plan_consistency(requested_outputs, workflow)
        return requested_outputs, workflow, rag_sources

    def repair_mission_plan_consistency(
        self,
        requested_outputs: list[dict[str, Any]],
        workflow: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Apply light consistency repairs after LLM/RAG planning.

        This is not a deterministic workflow generator. It is a guardrail that
        checks whether the LLM omitted a module whose registry capabilities are
        directly required by the already extracted outputs/requirements.
        """
        combined_text = self.normalize_text(" ".join(
            [self.uploaded_text or ""]
            + [req.get("text", "") for req in self.requirements]
            + [output.get("description", "") for output in requested_outputs]
        ))

        def workflow_has(module_id: str) -> bool:
            return any(str(step.get("module_id", "")).upper() == module_id for step in workflow)

        def append_requested_output(description: str, output_type: str, priority: str, rationale: str, keywords: list[str]) -> None:
            existing = self.normalize_text(" ".join(output.get("description", "") for output in requested_outputs))
            if any(self.normalize_text(word) in existing for word in keywords):
                return
            derived = [
                req.get("id", "REQ-???")
                for req in self.requirements
                if any(self.normalize_text(word) in self.normalize_text(req.get("text", "")) for word in keywords)
            ]
            requested_outputs.append({
                "id": f"OUT-{len(requested_outputs) + 1:03d}",
                "description": description,
                "output_type": output_type,
                "priority": priority,
                "derived_from_requirements": derived or [req.get("id", "REQ-001") for req in self.requirements[:1]],
                "rationale": rationale,
                "status": "proposed",
                "reviewed_by_user": False,
            })

        payload_observation_needed = any(token in combined_text for token in [
            "optical payload", "payload", "camera", "imager", "image", "imagery",
            "ground sample distance", "gsd", "spatial resolution", "swath",
            "footprint", "acquisition geometry", "observation geometry",
            "data acquisition sequence", "simulated acquisition",
            "synthetic image", "synthetic data", "payload performance",
            "sensor viewing", "viewing conditions",
        ]) and any(token in combined_text for token in [
            "optical", "visible", "panchromatic", "gsd", "swath",
            "image", "imagery", "sensor", "payload",
        ])

        if payload_observation_needed:
            append_requested_output(
                "Assess sensor-level optical observation performance, including acquisition geometry, GSD, swath, footprint or simulated payload products when required by the mission concept.",
                "simulation_product",
                "high",
                "The approved requirements or mission request include optical payload, GSD, swath, image acquisition or sensor-level observation performance information.",
                ["payload", "gsd", "swath", "resolution", "synthetic", "sensor-level"],
            )
            if not workflow_has("END-007"):
                module = self.get_module_by_id("END-007")
                if module:
                    workflow.append({
                        "step": len(workflow) + 1,
                        "module": module.get("module_name", "Synthetic Data Generation"),
                        "module_id": "END-007",
                        "input_data_artifacts": self.build_workflow_input_summary(module, []),
                        "output_artifacts": self.build_workflow_output_summary(module),
                        "rationale": "Added by planning consistency check because the approved requirements imply sensor-level optical observation, payload-resolution, GSD, swath, footprint, acquisition-geometry or simulated-observation assessment.",
                        "status": "proposed",
                        "reviewed_by_user": False,
                    })
                    self.add_log("AI", "Planning consistency check added END-007 Synthetic Data Generation for payload/sensor-level observation assessment.")

        # If END-007 is selected for sensor-level products and attitude/pointing is
        # explicitly relevant, END-003 should be available upstream.
        attitude_needed = any(token in combined_text for token in [
            "attitude", "nadir", "pointing", "line of sight", "viewing geometry",
            "sensor-target", "quaternion", "pointing error",
        ])
        if workflow_has("END-007") and attitude_needed and not workflow_has("END-003"):
            module = self.get_module_by_id("END-003")
            if module:
                workflow.append({
                    "step": len(workflow) + 1,
                    "module": module.get("module_name", "Attitude Propagation"),
                    "module_id": "END-003",
                    "input_data_artifacts": self.build_workflow_input_summary(module, []),
                    "output_artifacts": self.build_workflow_output_summary(module),
                    "rationale": "Added by planning consistency check because the selected synthetic/sensor-level observation workflow requires attitude, pointing or line-of-sight information.",
                    "status": "proposed",
                    "reviewed_by_user": False,
                })
                self.add_log("AI", "Planning consistency check added END-003 Attitude Propagation as upstream attitude/pointing provider.")

        reflectance_needed = any(token in combined_text for token in [
            "reflectance","environmental impact", "light curve", "lightcurve", "flux", "brightness", "photometry",
            "photometric", "apparent magnitude", "magnitude", "phase angle", "illumination geometry", "optical detectability", "rendered frames", "unity simulation"
        ])

        if reflectance_needed:
            append_requested_output(
                "Generate reflectance, light-curve, flux or photometric simulation products from orbit, attitude, illumination and observer geometry.",
                "simulation_product", "high",
                "The approved requirements imply reflectance, light-curve, brightness, photometric, illumination or optical detectability analysis.",
                ["reflectance", "light curve", "flux", "brightness", "photometry", "phase angle", "illumination"]
            )

            if not workflow_has("END-003"):
                module = self.get_module_by_id("END-003")
                if module:
                    workflow.append({
                        "step": len(workflow) + 1,
                        "module": module.get("module_name", "Attitude Propagation"),
                        "module_id": "END-003",
                        "input_data_artifacts": self.build_workflow_input_summary(module, []),
                        "output_artifacts": self.build_workflow_output_summary(module),
                        "rationale": "Added because END-010 reflectance simulation requires orbit/attitude or observation geometry inputs.",
                        "status": "proposed",
                        "reviewed_by_user": False,
                    })

            if not workflow_has("END-010"):
                module = self.get_module_by_id("END-010")
                if module:
                    workflow.append({
                        "step": len(workflow) + 1,
                        "module": module.get("module_name", "Reflectance Determination"),
                        "module_id": "END-010",
                        "input_data_artifacts": self.build_workflow_input_summary(module, []),
                        "output_artifacts": self.build_workflow_output_summary(module),
                        "rationale": "Added because the approved requirements imply reflectance, light-curve, photometric, phase-angle or optical detectability products.",
                        "status": "proposed",
                        "reviewed_by_user": False,
                    })

                self.add_log("AI", "Planning consistency check added END-010 Reflectance Determination for reflectance/light-curve simulation.")

        # A small local LLM may omit a module the request explicitly asks for. Add
        # END-001 (constellation) and END-004 (power budget) when the approved text
        # clearly requests them; sort_and_renumber_workflow() below then fixes the
        # execution order (END-001, END-003, END-004, END-007, END-010).
        constellation_needed = any(token in combined_text for token in [
            "constellation", "revisit", "walker", "orbital planes", "number of satellites",
        ])
        if constellation_needed and not workflow_has("END-001"):
            module = self.get_module_by_id("END-001")
            if module:
                append_requested_output(
                    "Determine the constellation architecture (number of satellites, orbital planes, altitude and inclination) and its revisit/coverage performance over the area of interest.",
                    "mission_analysis_result", "high",
                    "The approved requirements define a satellite constellation whose architecture and revisit/coverage performance must be determined.",
                    ["constellation", "revisit", "coverage"],
                )
                workflow.append({
                    "step": len(workflow) + 1,
                    "module": module.get("module_name", "Constellation Optimizer"),
                    "module_id": "END-001",
                    "input_data_artifacts": self.build_workflow_input_summary(module, []),
                    "output_artifacts": self.build_workflow_output_summary(module),
                    "rationale": "Added by planning consistency check because the approved requirements define a satellite constellation whose orbits feed the downstream modules.",
                    "status": "proposed",
                    "reviewed_by_user": False,
                })
                self.add_log("AI", "Planning consistency check added END-001 Constellation Optimizer for the requested constellation architecture.")

        power_needed = any(token in combined_text for token in [
            "power budget", "battery", "depth of discharge", "duty cycle", "solar array", "energy balance", "electrical power",
        ]) or re.search(r"\beps\b", combined_text) is not None
        if power_needed and not workflow_has("END-004"):
            module = self.get_module_by_id("END-004")
            if module:
                append_requested_output(
                    "Compute the preliminary power budget (per-mode consumption in sunlight and eclipse, battery depth of discharge and daily energy balance).",
                    "engineering_feasibility", "medium",
                    "The approved requirements mention the power budget, battery, duty cycle or energy balance.",
                    ["power", "battery", "energy", "duty"],
                )
                workflow.append({
                    "step": len(workflow) + 1,
                    "module": module.get("module_name", "Power Budget"),
                    "module_id": "END-004",
                    "input_data_artifacts": self.build_workflow_input_summary(module, []),
                    "output_artifacts": self.build_workflow_output_summary(module),
                    "rationale": "Added by planning consistency check because the approved requirements request a power/energy budget.",
                    "status": "proposed",
                    "reviewed_by_user": False,
                })
                self.add_log("AI", "Planning consistency check added END-004 Power Budget for the requested power/energy assessment.")
                if not workflow_has("END-003"):
                    upstream = self.get_module_by_id("END-003")
                    if upstream:
                        workflow.append({
                            "step": len(workflow) + 1,
                            "module": upstream.get("module_name", "Attitude Propagation"),
                            "module_id": "END-003",
                            "input_data_artifacts": self.build_workflow_input_summary(upstream, []),
                            "output_artifacts": self.build_workflow_output_summary(upstream),
                            "rationale": "Added because END-004 derives orbit period and timing from the END-003 propagation CSV.",
                            "status": "proposed",
                            "reviewed_by_user": False,
                        })

        # END-018 Components Thermal Analysis (CubeSats only): add it when the
        # request asks for the thermal behaviour of a CubeSat, and give it its
        # upstream END-001 (orbits) and END-003 (imaging passes, attitude).
        if self.end018_thermal_requested(combined_text) and not workflow_has("END-018"):
            module = self.get_module_by_id("END-018")
            if module:
                append_requested_output(
                    "Compute the temperatures of the CubeSat faces, solar panels and internal nodes along the orbit and the imaging passes, and flag the limits that are exceeded.",
                    "engineering_feasibility", "medium",
                    "The approved requirements describe a CubeSat and mention its thermal behaviour, temperatures or thermal limits.",
                    ["thermal", "temperature", "overheat", "heat", "battery", "cubesat"],
                )
                workflow.append({
                    "step": len(workflow) + 1,
                    "module": module.get("module_name", "Components Thermal Analysis"),
                    "module_id": "END-018",
                    "input_data_artifacts": self.build_workflow_input_summary(module, []),
                    "output_artifacts": self.build_workflow_output_summary(module),
                    "rationale": "Added by planning consistency check because the approved requirements ask for the thermal behaviour of a CubeSat.",
                    "status": "proposed",
                    "reviewed_by_user": False,
                })
                self.add_log("AI", "Planning consistency check added END-018 Components Thermal Analysis for the CubeSat thermal assessment.")
        if workflow_has("END-018"):
            for upstream_id, reason in (("END-001", "END-018 analyses the orbits of the END-001 satellites."),
                                        ("END-003", "END-018 switches the SAR on during the END-003 imaging passes and refines them with the propagated attitude.")):
                if workflow_has(upstream_id):
                    continue
                upstream = self.get_module_by_id(upstream_id)
                if upstream:
                    workflow.append({
                        "step": len(workflow) + 1,
                        "module": upstream.get("module_name", upstream_id),
                        "module_id": upstream_id,
                        "input_data_artifacts": self.build_workflow_input_summary(upstream, []),
                        "output_artifacts": self.build_workflow_output_summary(upstream),
                        "rationale": f"Added because {reason}",
                        "status": "proposed",
                        "reviewed_by_user": False,
                    })
                    self.add_log("AI", f"Planning consistency check added {upstream_id} upstream of END-018.")

        # END-019 Satellite Design Component Selector: add it when the request asks
        # to choose the components or subsystems of a CubeSat (no upstream module).
        if self.end019_design_requested(combined_text) and not workflow_has("END-019"):
            module = self.get_module_by_id("END-019")
            if module:
                append_requested_output(
                    "Select the satellite platform components (structure, OBC, EPS, battery, solar panels, radio, ADCS and payload) from real vendor datasheets and size the design.",
                    "engineering_feasibility", "medium",
                    "The approved requirements ask to choose the components or subsystems of a CubeSat.",
                    ["cubesat", "component", "subsystem", "bill of materials", "form factor"],
                )
                workflow.append({
                    "step": len(workflow) + 1,
                    "module": module.get("module_name", "Satellite Design Component Selector"),
                    "module_id": "END-019",
                    "input_data_artifacts": self.build_workflow_input_summary(module, []),
                    "output_artifacts": self.build_workflow_output_summary(module),
                    "rationale": "Added by planning consistency check because the approved requirements ask to choose the components of a CubeSat.",
                    "status": "proposed",
                    "reviewed_by_user": False,
                })
                self.add_log("AI", "Planning consistency check added END-019 Satellite Design Component Selector for the CubeSat platform design.")

        workflow = self.sort_and_renumber_workflow(workflow)
        for index, output in enumerate(requested_outputs, start=1):
            output["id"] = f"OUT-{index:03d}"
        return requested_outputs, workflow

    def sort_and_renumber_workflow(self, workflow: list[dict[str, Any]]) -> list[dict[str, Any]]:
        module_by_id = {module.get("module_id"): module for module in self.modules}
        deduplicated: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for step in workflow:
            module_id = str(step.get("module_id", "")).upper()
            if not module_id or module_id in seen_ids:
                continue
            seen_ids.add(module_id)
            deduplicated.append(step)
        deduplicated.sort(key=lambda step: self.get_module_order_score(module_by_id.get(str(step.get("module_id")), step)))
        for index, step in enumerate(deduplicated, start=1):
            step["step"] = index
        return deduplicated

    def rule_based_mission_planning(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        combined_text = self.normalize_text(" ".join([self.uploaded_text or ""] + [req.get("text", "") for req in self.requirements]))
        rag_sources = self.retrieve_knowledge_context(combined_text, max_chunks=5)

        outputs: list[dict[str, Any]] = []
        module_ids: list[str] = []

        def add_output(description: str, output_type: str, priority: str, rationale: str, keywords: list[str]) -> None:
            derived = [req.get("id", "REQ-???") for req in self.requirements if any(word in self.normalize_text(req.get("text", "")) for word in keywords)]
            outputs.append(
                {
                    "id": f"OUT-{len(outputs) + 1:03d}",
                    "description": description,
                    "output_type": output_type,
                    "priority": priority,
                    "derived_from_requirements": derived or [req.get("id", "REQ-???") for req in self.requirements[:1]],
                    "rationale": rationale,
                    "status": "proposed",
                }
            )

        if any(word in combined_text for word in ["revisit", "coverage", "access", "acquisition opportun", "observation window", "frequency"]):
            add_output(
                "Estimate access opportunities, acquisition frequency, coverage or revisit performance for the target area.",
                "mission_analysis_result",
                "high",
                "The approved requirements mention revisit, coverage, access windows or acquisition opportunities.",
                ["revisit", "coverage", "access", "acquisition"],
            )
            module_ids.append("END-001")

        if any(word in combined_text for word in [
            "synthetic", "simulated image", "synthetic image", "dataset", "ground truth",
            "payload resolution", "spatial resolution", "gsd", "ground sampling distance",
            "swath", "footprint", "sensor performance", "payload verification", "image metadata",
            "acquisition geometry", "optical payload", "camera", "imager"
        ]):
            add_output(
                "Generate or assess sensor-level EO observation products, payload-resolution quantities, acquisition geometry or synthetic-data metadata.",
                "simulation_product",
                "high",
                "The approved requirements mention synthetic data, image/sensor products, payload resolution, GSD, swath, footprint, acquisition geometry or payload-performance verification.",
                ["synthetic", "simulated", "dataset", "ground truth", "resolution", "gsd", "swath", "footprint", "sensor", "payload", "image", "acquisition"],
            )
            if "END-001" not in module_ids:
                module_ids.append("END-001")
            if "END-007" not in module_ids:
                module_ids.append("END-007")

        if any(word in combined_text for word in ["scenario", "terrain", "dem", "3d", "scene", "volcanic event"]):
            add_output(
                "Prepare a target scenario or scene representation required for simulation or synthetic data generation.",
                "simulation_product",
                "medium",
                "The approved requirements or mission request mention scenario, terrain, 3D scene, DEM, or event representation.",
                ["scenario", "terrain", "dem", "3d", "scene"],
            )
            if "END-006" not in module_ids:
                module_ids.append("END-006")

        if any(word in combined_text for word in ["power", "battery", "energy", "eps", "duty cycle", "power budget", "solar array", "payload duty", "operational power"]):
            add_output(
                "Compute the preliminary mission power budget using orbit, attitude-propagation timing and operational duty-cycle assumptions.",
                "engineering_feasibility",
                "medium",
                "The approved requirements mention power, energy, EPS, duty cycle, solar-array generation or operational power feasibility.",
                ["power", "battery", "energy", "eps", "duty", "solar", "operation"],
            )
            for required_module_id in ["END-001", "END-003", "END-004"]:
                if required_module_id not in module_ids:
                    module_ids.append(required_module_id)

        if any(word in combined_text for word in ["reflectance", "light curve", "lightcurve",  "flux", "brightness", "photometry", "photometric",
            "apparent magnitude", "magnitude", "phase angle", "illumination", "optical detectability", "rendered frames", "unity simulation"]):
            add_output(
                "Generate reflectance, light-curve, flux or photometric simulation products based on orbit, attitude, illumination and observer geometry.",
                "simulation_product", "high",
                "The approved requirements mention reflectance, light-curve, flux, brightness, photometry, phase angle, illumination or optical detectability.",
                ["reflectance", "light curve", "flux", "brightness", "photometry", "phase angle", "illumination"]
            )

            if "END-003" not in module_ids:
                module_ids.append("END-003")

            if "END-010" not in module_ids:
                module_ids.append("END-010")

        # END-018 Components Thermal Analysis: CubeSats (1U-12U) only, needs the
        # END-001 orbits and the END-003 imaging passes / attitude upstream.
        if self.end018_thermal_requested(combined_text):
            add_output(
                "Compute the temperatures of the CubeSat faces, solar panels and internal nodes (central body, battery, SAR payload) along the orbit and the imaging passes, and flag the limits that are exceeded.",
                "engineering_feasibility",
                "medium",
                "The approved requirements describe a CubeSat and mention its thermal behaviour, temperatures or thermal limits.",
                ["thermal", "temperature", "overheat", "heat", "battery", "cubesat"],
            )
            for upstream_id in ("END-001", "END-003"):
                if upstream_id not in module_ids:
                    module_ids.append(upstream_id)
            module_ids.append("END-018")

        if any(word in combined_text for word in [
            "cubesat", "satellite design", "component selection", "select the components", "bill of materials", "form factor",
            "adcs", "attitude control subsystem", "pointing accuracy", "inter-satellite", "space situational awareness",
            "space debris", "payload accommodation", "subsystem selection",
        ]):
            add_output(
                "Select the satellite platform components (structure, OBC, EPS, battery, solar panels, radio, ADCS and payload) from real vendor datasheets and size the design.",
                "engineering_feasibility",
                "medium",
                "The approved requirements mention a CubeSat or small-satellite design, component or subsystem selection, an ADCS pointing requirement, payload accommodation or an inter-satellite link.",
                ["cubesat", "satellite design", "component", "bill of materials", "adcs", "pointing", "inter-satellite", "debris", "payload", "form factor"],
            )
            module_ids.append("END-019")

        if not outputs:
            add_output(
                "Produce a preliminary mission analysis package traceable to the approved requirements.",
                "mission_analysis_result",
                "high",
                "The approved requirements are generic and require a preliminary STAR analysis package.",
                [],
            )
            module_ids.append("END-001")

        ordered_modules = []
        seen_ids = set()
        for module_id in module_ids:
            if module_id in seen_ids:
                continue
            seen_ids.add(module_id)
            module = self.get_module_by_id(module_id)
            if module:
                ordered_modules.append(module)

        workflow: list[dict[str, Any]] = []
        for index, module in enumerate(sorted(ordered_modules, key=self.get_module_order_score), start=1):
            workflow.append(
                {
                    "step": index,
                    "module": module.get("module_name", module.get("module_id")),
                    "module_id": module.get("module_id", "unknown"),
                    "input_data_artifacts": self.build_workflow_input_summary(module, []),
                    "output_artifacts": self.build_workflow_output_summary(module),
                    "rationale": self.build_rule_based_planning_rationale(module, outputs),
                    "status": "proposed",
                    "reviewed_by_user": False,
                }
            )

        return outputs, workflow, rag_sources

    def get_module_by_id(self, module_id: str) -> dict[str, Any] | None:
        for module in self.modules:
            if str(module.get("module_id", "")).upper() == str(module_id).upper():
                return module
        return None

    def build_rule_based_planning_rationale(self, module: dict[str, Any], requested_outputs: list[dict[str, Any]]) -> str:
        module_name = str(module.get("module_name", ""))
        joined_outputs = "; ".join(output.get("description", "") for output in requested_outputs[:3])
        return f"Selected during mission planning because it can support requested outputs: {joined_outputs}. Module considered: {module_name}."

    def normalize_requested_outputs(self, raw_outputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not isinstance(raw_outputs, list):
            return []
        normalized: list[dict[str, Any]] = []
        seen_descriptions = set()
        allowed_types = {"mission_analysis_result", "data_product", "engineering_feasibility", "simulation_product", "report_artifact", "other"}
        allowed_priorities = {"high", "medium", "low"}
        for index, item in enumerate(raw_outputs, start=1):
            if not isinstance(item, dict):
                continue
            description = str(item.get("description", "")).strip()
            if not description:
                continue
            key = self.normalize_text(description)
            if key in seen_descriptions:
                continue
            seen_descriptions.add(key)
            output_type = str(item.get("output_type", "other")).strip()
            if output_type not in allowed_types:
                output_type = "other"
            priority = str(item.get("priority", "medium")).strip().lower()
            if priority not in allowed_priorities:
                priority = "medium"
            req_ids = item.get("derived_from_requirements", [])
            if not isinstance(req_ids, list):
                req_ids = [str(req_ids)] if req_ids else []
            valid_req_ids = {req.get("id") for req in self.requirements}
            req_ids = [str(req_id) for req_id in req_ids if str(req_id) in valid_req_ids]
            if not req_ids and self.requirements:
                req_ids = [self.requirements[0].get("id", "REQ-001")]
            normalized.append(
                {
                    "id": str(item.get("id") or f"OUT-{len(normalized) + 1:03d}"),
                    "description": description,
                    "output_type": output_type,
                    "priority": priority,
                    "derived_from_requirements": req_ids,
                    "rationale": str(item.get("rationale", "Derived from approved requirements and RAG planning context.")).strip(),
                    "status": str(item.get("status", "proposed")).strip() or "proposed",
                    "reviewed_by_user": False,
                }
            )
        for index, output in enumerate(normalized, start=1):
            output["id"] = f"OUT-{index:03d}"
        return normalized

    def workflow_text_matches_registry_field(self, text: Any, module: dict[str, Any], field_name: str) -> bool:
        """Return True if LLM-provided artifact text references declared registry fields."""
        normalized_text = self.normalize_text(str(text or ""))
        if not normalized_text:
            return False
        if field_name == "outputs":
            candidates = []
            for output in module.get("outputs", []) or []:
                candidates.extend([output.get("name"), output.get("artifact_name")])
        else:
            candidates = []
            for input_item in module.get("required_inputs", []) or []:
                candidates.extend([input_item.get("name"), input_item.get("artifact_name")])
                produced_by = input_item.get("produced_by")
                if isinstance(produced_by, dict):
                    candidates.extend([produced_by.get("module_id"), produced_by.get("output")])
                elif produced_by:
                    candidates.append(str(produced_by))
        for candidate in candidates:
            if not candidate:
                continue
            candidate_norm = self.normalize_text(str(candidate))
            if candidate_norm and candidate_norm in normalized_text:
                return True
        return False

    def clean_workflow_input_artifacts(self, module: dict[str, Any], raw_text: Any) -> str:
        if self.workflow_text_matches_registry_field(raw_text, module, "inputs"):
            return str(raw_text).strip()
        return self.build_workflow_input_summary(module, [])

    def clean_workflow_output_artifacts(self, module: dict[str, Any], raw_text: Any) -> str:
        if self.workflow_text_matches_registry_field(raw_text, module, "outputs"):
            return str(raw_text).strip()
        return self.build_workflow_output_summary(module)

    def normalize_planning_workflow(self, raw_steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not isinstance(raw_steps, list):
            return []
        module_by_name = {module.get("module_name"): module for module in self.modules}
        module_by_id = {module.get("module_id"): module for module in self.modules}
        normalized: list[dict[str, Any]] = []
        seen_module_ids = set()
        skipped = 0
        for item in raw_steps:
            if not isinstance(item, dict):
                skipped += 1
                continue
            module_name_raw = str(item.get("module", item.get("module_name", ""))).strip()
            module_id_raw = str(item.get("module_id", "")).strip()
            module = module_by_name.get(module_name_raw) or module_by_id.get(module_id_raw)
            if module is None:
                # Try to resolve from ID embedded in module field.
                match = re.search(r"END-\d{3}", module_name_raw.upper())
                if match:
                    module = module_by_id.get(match.group(0))
            if module is None:
                skipped += 1
                continue
            module_id = module.get("module_id", "unknown")
            if module_id in seen_module_ids:
                continue
            seen_module_ids.add(module_id)
            normalized.append(
                {
                    "step": len(normalized) + 1,
                    "module": module.get("module_name", module_id),
                    "module_id": module_id,
                    "input_data_artifacts": self.clean_workflow_input_artifacts(module, item.get("input_data_artifacts") or item.get("inputs")),
                    "output_artifacts": self.clean_workflow_output_artifacts(module, item.get("output_artifacts") or item.get("outputs")),
                    "rationale": str(item.get("rationale", item.get("reason", "Selected by mission planning."))).strip(),
                    "status": self.normalize_workflow_status(item.get("status", "proposed")),
                    "reviewed_by_user": False,
                }
            )
        if skipped:
            self.add_log("AI", f"Discarded {skipped} workflow step(s) not compliant with the registry.")
        return normalized

    def save_requested_outputs_json(
        self,
        requested_outputs: list[dict[str, Any]],
        review_status: str,
        output_filename: str,
        source: str,
        rag_sources: list[dict[str, Any]] | None = None,
    ) -> Path:
        if not self.current_run_path:
            raise RuntimeError("No active run folder is available.")
        output_path = self.current_run_path / "planning" / output_filename
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "run_id": self.current_run_id,
            "generated_at": datetime.now().isoformat(),
            **self.get_source_document_metadata(),
            "source": source,
            "review_status": review_status,
            "rag_sources": self.compact_rag_sources(rag_sources or []),
            "requested_outputs": requested_outputs,
        }
        output_path.write_text(json.dumps(payload, indent=4), encoding="utf-8")
        # Also keep a copy in intermediate for backward visibility.
        intermediate_path = self.current_run_path / "intermediate" / output_filename
        intermediate_path.write_text(json.dumps(payload, indent=4), encoding="utf-8")
        return output_path

    def compact_rag_sources(self, rag_sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "source_path": item.get("source_path"),
                "chunk_id": item.get("chunk_id"),
                "score": item.get("score"),
            }
            for item in rag_sources
        ]

    def save_mission_planning_package_json(
        self,
        requested_outputs: list[dict[str, Any]],
        workflow: list[dict[str, Any]],
        review_status: str,
        source: str,
        rag_sources: list[dict[str, Any]],
    ) -> Path:
        if not self.current_run_path:
            raise RuntimeError("No active run folder is available.")
        output_path = self.current_run_path / "planning" / "mission_planning_package.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "run_id": self.current_run_id,
            "generated_at": datetime.now().isoformat(),
            **self.get_source_document_metadata(),
            "source": source,
            "review_status": review_status,
            "rag_sources": self.compact_rag_sources(rag_sources),
            "requirements": self.requirements,
            "requested_outputs": requested_outputs,
            "workflow": workflow,
        }
        output_path.write_text(json.dumps(payload, indent=4), encoding="utf-8")
        return output_path

    # ------------------------------
    # Input resolution after workflow
    # ------------------------------
    def analyze_missing_information(self, mode: str = "Local LLM via Ollama (RAG)") -> dict[str, Any]:
        if not self.requirements:
            return {"ok": False, "error": "No active requirements are available. Extract and review requirements first.", "logs": self.logs}
        if not self.workflow_steps:
            return {"ok": False, "error": "Generate and review a workflow before resolving module inputs.", "logs": self.logs}
        if self.workflow_review_status == "edited_not_saved":
            return {"ok": False, "error": "Save the reviewed workflow before resolving module inputs.", "logs": self.logs}
        if not self.current_run_path:
            return {"ok": False, "error": "No active run is available.", "logs": self.logs}

        mode = mode or "Local LLM via Ollama (RAG)"
        self.add_log("AI", f"Resolving workflow inputs using mode: {mode}.")

        try:
            if "LLM" in mode or "RAG" in mode:
                missing_information = self.llm_assisted_workflow_input_resolution()
                source = "llm_rag_workflow_input_resolution"
                raw_source = "llm_rag_workflow_input_resolution_raw_output"
            else:
                missing_information = self.workflow_driven_missing_information_analysis()
                source = "workflow_driven_input_resolution"
                raw_source = "workflow_driven_input_resolution_raw_output"
        except Exception as exc:
            self.add_log("ERROR", f"Input resolution failed in {mode}: {exc}")
            self.add_log("AI", "Falling back to workflow-driven input resolution.")
            missing_information = self.workflow_driven_missing_information_analysis()
            source = "workflow_driven_input_resolution_after_llm_fallback"
            raw_source = "workflow_driven_input_resolution_raw_output_after_llm_fallback"

        self.missing_information = missing_information
        self.missing_information_review_status = "not_reviewed"
        self.assumptions_approved = False
        self.reset_downstream_from_assumptions()

        active_path = self.save_missing_information_json(
            missing_information=missing_information,
            review_status="not_reviewed",
            output_filename="missing_information.json",
            source=source,
        )
        extracted_path = self.save_missing_information_json(
            missing_information=missing_information,
            review_status="not_reviewed",
            output_filename="missing_information_extracted.json",
            source=raw_source,
        )

        self.add_log("AI", f"{len(missing_information)} workflow input(s) resolved or flagged.")
        self.add_log("SYSTEM", f"Input resolution saved: {active_path}")

        return {
            "ok": True,
            **self.state_payload(),
            "missing_information_path": str(active_path),
            "missing_information_extracted_path": str(extracted_path),
            "message": f"{len(missing_information)} workflow input(s) resolved or flagged using {mode}.",
        }

    def get_modules_for_current_workflow(self) -> list[dict[str, Any]]:
        workflow_module_ids = [str(step.get("module_id", "")).strip() for step in self.workflow_steps]
        workflow_module_names = [str(step.get("module", "")).strip() for step in self.workflow_steps]
        modules: list[dict[str, Any]] = []
        for module_id, module_name in zip(workflow_module_ids, workflow_module_names):
            module = self.get_module_by_id(module_id) or self.get_module_by_name(module_name)
            if module:
                modules.append(module)
        return modules

    def workflow_driven_missing_information_analysis(self) -> list[dict[str, Any]]:
        combined_text = self.normalize_text(" ".join([self.uploaded_text or ""] + [req.get("text", "") for req in self.requirements]))
        selected_modules = self.get_modules_for_current_workflow()

        items: list[dict[str, Any]] = []
        seen_keys = set()
        categories = {req.get("category", "functional") for req in self.requirements}

        for module in selected_modules:
            module_name = module.get("module_name", module.get("module_id", "unknown module"))
            module_id = module.get("module_id", "unknown_module")
            for input_item in module.get("required_inputs", []) or []:
                if not self.should_include_input_item(input_item, categories, combined_text):
                    continue
                parameter = str(input_item.get("name", "unknown_parameter")).strip()
                key = (module_id, parameter)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                proposed_value, status, source = self.infer_missing_information_value(
                    input_item=input_item,
                    module=module,
                    combined_text=combined_text,
                    selected_modules=selected_modules,
                )
                items.append(
                    {
                        "parameter": parameter,
                        "needed_by": module_name,
                        "needed_by_module_id": module_id,
                        "reason": str(input_item.get("missing_information_reason") or input_item.get("description") or "Required by the selected workflow module interface.").strip(),
                        "proposed_value": proposed_value,
                        "unit": str(input_item.get("unit", "-")),
                        "status": status,
                        "source": source,
                        "required": bool(input_item.get("required", False)),
                        "assumption_allowed": bool(input_item.get("assumption_allowed", False)),
                        "data_type": str(input_item.get("data_type", "unknown")),
                        "reviewed_by_user": False,
                    }
                )
        return items

    def llm_assisted_workflow_input_resolution(self) -> list[dict[str, Any]]:
        selected_modules = self.get_modules_for_current_workflow()
        registry_by_module = []
        for module in selected_modules:
            registry_by_module.append(
                {
                    "module_id": module.get("module_id"),
                    "module_name": module.get("module_name"),
                    "description": module.get("description", ""),
                    "required_inputs": module.get("required_inputs", []) or [],
                    "outputs": module.get("outputs", []) or [],
                    "execution": module.get("execution", {}),
                }
            )

        query = "\n".join([
            self.uploaded_text or "",
            json.dumps(self.requirements, ensure_ascii=False),
            json.dumps(self.requested_outputs, ensure_ascii=False),
            json.dumps(self.workflow_steps, ensure_ascii=False),
            json.dumps(registry_by_module, ensure_ascii=False),
        ])[:12000]
        rag_sources = self.retrieve_knowledge_context(query, max_chunks=8)
        self.rag_sources = rag_sources

        system_prompt = (
            "You are STAR's workflow input-resolution assistant. "
            "Resolve inputs for the already proposed workflow. "
            "Use RAG context as background knowledge but do not invent module parameters. "
            "Return only valid JSON."
        )
        user_prompt = f"""
TASK
For the selected workflow modules, identify all required inputs and relevant optional inputs needed to start execution. Classify each input as provided, proposed first guess, expected from upstream, requires user input, or not applicable.

INPUTS
1. Mission request excerpt:
\"\"\"
{(self.uploaded_text or "")[:7000]}
\"\"\"

2. Approved requirements:
{json.dumps(self.requirements, indent=2)}

3. Requested outputs:
{json.dumps(self.requested_outputs, indent=2)}

4. Proposed/reviewed workflow:
{json.dumps(self.workflow_steps, indent=2)}

5. Registry entries for selected workflow modules:
{json.dumps(registry_by_module, indent=2)}

6. Retrieved local knowledge-base context:
{self.format_rag_context_for_prompt(rag_sources)}

STRICT RULES
- Use only parameters that appear in required_inputs of the selected workflow modules.
- Do not invent parameters.
- Do not invent modules.
- If an input is explicitly or strongly implied by the mission request, status="provided" and source="mission_document".
- If an input has a registry default or a reasonable first guess, status="proposed" and source="module_registry_default". The proposed value must be clearly a first guess.
- If an input is produced by a previous workflow module, status="expected_from_upstream" and source="upstream_module_output".
- If an input is required and cannot be provided or assumed, status="requires_user_input" and source="module_registry_required_input".
- Use optional inputs only when relevant to the requested outputs and workflow.
- Do not turn missing files such as DEMs, external datasets or 3D models into assumptions unless the registry explicitly provides a default.

ALLOWED STATUSES
{json.dumps(ALLOWED_MISSING_INFORMATION_STATUSES)}

ALLOWED SOURCES
{json.dumps(ALLOWED_MISSING_INFORMATION_SOURCES)}

OUTPUT FORMAT
Return only valid JSON:
{{
  "missing_information": [
    {{
      "parameter": "exact registry input name",
      "needed_by": "exact module_name from workflow",
      "reason": "why this input is needed for the workflow",
      "proposed_value": "value, default, upstream reference, or TBD",
      "unit": "-",
      "status": "provided | proposed | requires_user_input | expected_from_upstream | not_applicable",
      "source": "mission_document | module_registry_default | module_registry_required_input | upstream_module_output | not_applicable"
    }}
  ]
}}
"""
        data = self.call_local_llm_json(system_prompt, user_prompt)
        raw_items = data.get("missing_information", data.get("missing_parameters", []))
        if not isinstance(raw_items, list):
            raise ValueError("LLM response does not contain a missing_information list.")
        normalized = self.normalize_llm_missing_information(raw_items)
        if not normalized:
            self.add_log("AI", "LLM input-resolution output was empty after registry validation.")
            return self.workflow_driven_missing_information_analysis()
        return normalized

    def approve_missing_information(self) -> dict[str, Any]:
        if not self.current_run_path:
            return {"ok": False, "error": "No active run is available.", "logs": self.logs}
        if not self.workflow_steps:
            return {"ok": False, "error": "No workflow is available. Generate mission planning before approving inputs.", "logs": self.logs}
        if not self.missing_information:
            return {"ok": False, "error": "No workflow input resolution is available to approve.", "logs": self.logs}

        approved_items = []
        for index, item in enumerate(self.missing_information, start=1):
            approved_item = dict(item)
            approved_item["assumption_id"] = f"ASS-{index:03d}"
            approved_item["technical_status_before_approval"] = approved_item.get("status")
            approved_item["approval_status"] = "approved_by_user"
            approved_item["status"] = "approved"
            approved_item["approved_by_user"] = True
            approved_items.append(approved_item)

        self.missing_information = approved_items
        self.missing_information_review_status = "approved_by_user"
        self.assumptions_approved = True
        self.reset_downstream_from_assumptions()

        approved_path = self.save_approved_assumptions_json(approved_items)
        active_path = self.save_missing_information_json(
            missing_information=approved_items,
            review_status="approved_by_user",
            output_filename="missing_information.json",
            source="approved_workflow_input_resolution",
        )
        planning_package_path = self.save_approved_planning_package_json()

        self.add_log("USER", "Workflow input resolution and assumptions approved by user.")
        self.add_log("SYSTEM", f"approved_assumptions.json saved: {approved_path}")
        self.add_log("SYSTEM", f"approved_planning_package.json saved: {planning_package_path}")
        self.add_log("SYSTEM", "Execution is now enabled if the workflow has also been approved.")

        return {
            "ok": True,
            **self.state_payload(),
            "approved_assumptions_path": str(approved_path),
            "missing_information_path": str(active_path),
            "approved_planning_package_path": str(planning_package_path),
            "message": "Workflow input resolution and first-guess assumptions approved.",
        }

    def approve_workflow(self) -> dict[str, Any]:
        if not self.workflow_steps:
            return {"ok": False, "error": "No workflow proposal is available to approve.", "logs": self.logs}
        if self.workflow_review_status == "edited_not_saved":
            return {"ok": False, "error": "Save the reviewed workflow before approving it.", **self.state_payload()}

        approved_steps = []
        approved_module_names = set()
        for step in self.workflow_steps:
            approved_step = dict(step)
            approved_step["status"] = "approved"
            approved_step["approved_by_user"] = True
            approved_steps.append(approved_step)
            approved_module_names.add(approved_step.get("module"))

        self.workflow_steps = approved_steps
        self.workflow_review_status = "approved_by_user"
        self.workflow_approved = True

        # Workflow approval invalidates any previous input resolution.
        self.missing_information = []
        self.missing_information_review_status = "not_available"
        self.assumptions_approved = False
        self.reset_downstream_from_workflow()

        for module in self.modules:
            module["status"] = "Ready" if module.get("module_name") in approved_module_names else "Idle"

        approved_path = self.save_workflow_json(
            workflow=approved_steps,
            review_status="approved_by_user",
            output_filename="approved_workflow.json",
            source="user_approved_workflow",
        )
        active_path = self.save_workflow_json(
            workflow=approved_steps,
            review_status="approved_by_user",
            output_filename="workflow_proposal.json",
            source="approved_active_workflow",
        )
        self.save_mission_planning_package_json(
            requested_outputs=self.requested_outputs,
            workflow=approved_steps,
            review_status="workflow_approved_by_user",
            source="user_approved_workflow",
            rag_sources=self.rag_sources,
        )

        self.add_log("USER", "Workflow approved by user. Input resolution is now required before execution.")
        self.add_log("SYSTEM", f"approved_workflow.json saved: {approved_path}")

        return {
            "ok": True,
            **self.state_payload(),
            "approved_workflow_path": str(approved_path),
            "workflow_proposal_path": str(active_path),
            "message": "Workflow approved. Resolve and approve workflow inputs before execution.",
        }

    def save_approved_planning_package_json(self) -> Path:
        if not self.current_run_path:
            raise RuntimeError("No active run folder is available.")
        output_path = self.current_run_path / "planning" / "approved_planning_package.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "run_id": self.current_run_id,
            "generated_at": datetime.now().isoformat(),
            **self.get_source_document_metadata(),
            "source": "user_approved_planning_package",
            "requirements": self.requirements,
            "requested_outputs": self.requested_outputs,
            "approved_workflow": self.workflow_steps,
            "approved_input_resolution": self.missing_information,
            "rag_sources": self.compact_rag_sources(self.rag_sources),
        }
        output_path.write_text(json.dumps(payload, indent=4), encoding="utf-8")
        (self.current_run_path / "intermediate" / "approved_planning_package.json").write_text(json.dumps(payload, indent=4), encoding="utf-8")
        return output_path

    # ------------------------------
    # Execution with module input files and runner hook
    # ------------------------------
    def validate_execution_preconditions(self) -> dict[str, Any] | None:
        if not self.workflow_approved:
            return {"ok": False, "error": "Approve the workflow before executing it.", "logs": self.logs}
        if not self.assumptions_approved:
            return {"ok": False, "error": "Approve workflow inputs and first-guess assumptions before executing the workflow.", "logs": self.logs}
        if not self.current_run_path:
            return {"ok": False, "error": "No active run is available.", "logs": self.logs}
        if not self.workflow_steps:
            return {"ok": False, "error": "No approved workflow steps are available.", "logs": self.logs}
        return None

    def execute_workflow_async(self) -> dict[str, Any]:
        validation_error = self.validate_execution_preconditions()
        if validation_error:
            return validation_error

        if self.execution_running:
            return {"ok": False, "error": "Workflow execution is already running.", **self.state_payload()}

        self.execution_running = True
        self.execution_error = None
        self.execution_result_payload = None
        self.execution_results = []
        self.execution_review_status = "not_available"
        self.execution_approved = False
        self.execution_stop_requested = False
        self.execution_stop_event.clear()
        self.active_module_name = None
        self.active_module_id = None

        selected_modules = {step.get("module") for step in self.workflow_steps}
        for module in self.modules:
            module["status"] = "Ready" if module.get("module_name") in selected_modules else "Idle"

        self.add_log("EXECUTION", "Workflow execution started in background mode.")
        self.add_log("EXECUTION", "Stop command is available during module execution.")

        self.execution_thread = threading.Thread(
            target=self._execute_workflow_background,
            name="STARWorkflowExecution",
            daemon=True,
        )
        self.execution_thread.start()

        return {
            "ok": True,
            **self.state_payload(),
            "execution_running": True,
            "message": "Workflow execution started. Selected modules are Ready and will run sequentially.",
        }

    def _execute_workflow_background(self) -> None:
        try:
            self.execution_result_payload = self._execute_workflow_impl()
        except Exception as exc:
            if self.execution_stop_event.is_set():
                self.execution_error = None
                self.add_log("EXECUTION", f"Workflow execution interrupted after stop request: {exc}")
                for module in self.modules:
                    if module.get("status") == "Running":
                        module["status"] = "Stopped"
            else:
                self.execution_error = str(exc)
                self.add_log("ERROR", f"Workflow execution crashed: {exc}")
                for module in self.modules:
                    if module.get("status") == "Running":
                        module["status"] = "Error"
        finally:
            self.active_module_name = None
            self.active_module_id = None
            self.execution_running = False
            # Once the background thread has stopped, the GUI must become usable again.
            self.execution_stop_requested = False

    def stop_workflow_execution(self) -> dict[str, Any]:
        """Request a cooperative stop of the running workflow.

        The backend stops immediately between modules. During a module run, the
        runner can stop early if it accepts the stop_event keyword and checks it.
        """
        if not self.execution_running:
            self.execution_stop_requested = False
            self.execution_stop_event.clear()
            self.add_log("EXECUTION", "Stop requested, but no workflow execution is currently running.")
            return {"ok": False, "error": "No workflow execution is currently running.", **self.state_payload()}

        self.execution_stop_requested = True
        self.execution_stop_event.set()
        module_label = self.active_module_name or "current module"
        self.add_log("USER", f"Stop requested during execution of {module_label}.")
        self.add_log("EXECUTION", "The current module will be stopped if its runner supports cooperative cancellation; otherwise execution will stop before the next module.")

        for module in self.modules:
            if module.get("status") == "Running":
                module["status"] = "Stopped"

        return {"ok": True, "message": "Stop requested for running workflow.", **self.state_payload()}

    def get_execution_progress(self) -> dict[str, Any]:
        """Return the live execution state used by the frontend poller.

        Important: when the workflow runs in a background thread,
        _execute_workflow_impl() builds its return payload before the thread
        finally block clears execution_running.  Therefore the cached
        execution_result_payload may contain stale runtime flags.  Do not let
        those stale flags overwrite the live state, otherwise the GUI remains
        stuck on "Executing..." after a stopped or completed run.
        """
        payload = {
            "ok": True,
            **self.state_payload(),
            "execution_running": self.execution_running,
            "execution_stop_requested": self.execution_stop_requested,
            "active_module_name": self.active_module_name,
            "active_module_id": self.active_module_id,
            "execution_error": self.execution_error,
        }

        if not self.execution_running and self.execution_result_payload:
            stale_runtime_keys = {
                "modules",
                "logs",
                "execution_results",
                "execution_running",
                "execution_stop_requested",
                "active_module_name",
                "active_module_id",
                "execution_error",
            }
            payload.update({
                key: value
                for key, value in self.execution_result_payload.items()
                if key not in stale_runtime_keys
            })

            # Re-assert the live values after merging the final payload.
            payload["execution_running"] = False
            payload["execution_stop_requested"] = self.execution_stop_requested
            payload["active_module_name"] = self.active_module_name
            payload["active_module_id"] = self.active_module_id
            payload["execution_error"] = self.execution_error
            payload["modules"] = self.modules
            payload["logs"] = self.logs
            payload["execution_results"] = self.execution_results

        return payload

    def recover_execution_ui_state(self) -> dict[str, Any]:
        """Synchronize the GUI after a stale frontend execution state.

        This does not kill any process. It only clears transient frontend/backend
        flags if no execution thread is alive.
        """
        thread_alive = bool(self.execution_thread and self.execution_thread.is_alive())
        if not thread_alive:
            self.execution_running = False
            self.execution_stop_requested = False
            self.execution_stop_event.clear()
            self.active_module_name = None
            self.active_module_id = None
            self.add_log("SYSTEM", "Execution UI state synchronized; no background workflow is running.")
        return {"ok": True, **self.state_payload()}

    def execute_workflow(self) -> dict[str, Any]:
        validation_error = self.validate_execution_preconditions()
        if validation_error:
            return validation_error
        return self._execute_workflow_impl()

    def _execute_workflow_impl(self) -> dict[str, Any]:
        if not self.current_run_path:
            raise RuntimeError("No active run is available.")

        workflow_started_perf = time.perf_counter()
        self.add_log("EXECUTION", "Starting workflow execution from approved planning package.")
        execution_results = []
        selected_modules = {step.get("module") for step in self.workflow_steps}

        for module in self.modules:
            module["status"] = "Ready" if module.get("module_name") in selected_modules else "Idle"

        for workflow_step in self.workflow_steps:
            self.get_module_output_layout(str(workflow_step.get("module_id", "UNKNOWN")))

        workflow_stopped = False

        for workflow_step in self.workflow_steps:
            module_name = workflow_step.get("module")
            module_id = workflow_step.get("module_id", "unknown")

            if self.execution_stop_event.is_set():
                self.add_log("EXECUTION", f"Workflow execution stopped before module step {workflow_step.get('step')}: {module_name}.")
                execution_results.append(self.build_stopped_execution_result(workflow_step, "Execution stopped before this module started."))
                self.execution_results = execution_results
                workflow_stopped = True
                break

            self.active_module_name = module_name
            self.active_module_id = module_id
            self.add_log("EXECUTION", f"Starting module step {workflow_step.get('step')}: {module_name} ({module_id}).")
            self.add_log("EXECUTION", f"Input artifacts declared for {module_name}: {workflow_step.get('input_data_artifacts', '-')}")
            self.add_log("EXECUTION", f"Expected outputs for {module_name}: {workflow_step.get('output_artifacts', '-')}")

            for module in self.modules:
                if module.get("module_name") == module_name:
                    module["status"] = "Running"

            module_started_perf = time.perf_counter()
            try:
                result = self.execute_workflow_step(workflow_step)
            except Exception as exc:
                duration = time.perf_counter() - module_started_perf
                if self.execution_stop_event.is_set():
                    result = self.build_stopped_execution_result(
                        workflow_step,
                        f"Execution stopped while running {module_name}: {exc}",
                    )
                    result["duration_seconds"] = round(duration, 3)
                    result["duration_human"] = self.format_duration(duration)
                else:
                    self.add_log("ERROR", f"Module {module_name} failed after {self.format_duration(duration)}: {exc}")
                    raise

            duration = time.perf_counter() - module_started_perf
            result["duration_seconds"] = round(duration, 3)
            result["duration_human"] = self.format_duration(duration)

            if self.execution_stop_event.is_set() and result.get("status") != "stopped":
                result["status"] = "stopped"
                result["evidence"] = f"Stop was requested while or immediately after executing {module_name}."

            execution_results.append(result)
            self.execution_results = execution_results

            for module in self.modules:
                if module.get("module_name") == module_name:
                    if result["status"] == "completed":
                        module["status"] = "Completed"
                    elif result["status"] == "stopped":
                        module["status"] = "Stopped"
                    else:
                        module["status"] = "Error"

            self.add_log("EXECUTION", f"Finished module step {workflow_step.get('step')}: {module_name} -> {result['status']}.")
            self.add_log("EXECUTION", f"Module {module_name} execution time: {self.format_duration(duration)} ({duration:.2f} s).")

            self.active_module_name = None
            self.active_module_id = None

            if result.get("status") == "stopped" or self.execution_stop_event.is_set():
                self.add_log("EXECUTION", "Workflow execution stopped by user request. Remaining modules were not executed.")
                workflow_stopped = True
                break

            if result.get("status") == "failed":
                self.add_log("ERROR", f"Workflow aborted after failed module: {module_name}. Remaining modules were not executed to avoid cascading path/input errors.")
                break

        for module in self.modules:
            if module.get("module_name") not in selected_modules:
                module["status"] = "Idle"

        total_duration = time.perf_counter() - workflow_started_perf
        self.execution_results = execution_results
        self.execution_review_status = "not_reviewed"
        self.execution_approved = False

        active_path = self.save_execution_results_json(
            execution_results=execution_results,
            review_status="not_reviewed",
            output_filename="execution_results.json",
            source="workflow_execution_with_module_input_files",
        )
        extracted_path = self.save_execution_results_json(
            execution_results=execution_results,
            review_status="not_reviewed",
            output_filename="execution_results_extracted.json",
            source="workflow_execution_with_module_input_files_raw_output",
        )

        if workflow_stopped:
            self.add_log("EXECUTION", f"Workflow stopped. Total elapsed time: {self.format_duration(total_duration)} ({total_duration:.2f} s).")
        else:
            self.add_log("EXECUTION", f"Workflow completed. Total elapsed time: {self.format_duration(total_duration)} ({total_duration:.2f} s).")
        self.add_log("EXECUTION", f"{len(execution_results)} workflow steps executed or simulated.")
        self.add_log("SYSTEM", f"Active execution results saved: {active_path}")

        # The stop request has been handled; clear it so the GUI buttons are re-enabled.
        self.execution_stop_requested = False

        return {
            "ok": True,
            **self.state_payload(),
            "execution_results_path": str(active_path),
            "execution_results_extracted_path": str(extracted_path),
            "message": "Workflow execution stopped by user." if workflow_stopped else f"{len(execution_results)} workflow step(s) executed from approved workflow.",
        }

    def build_stopped_execution_result(self, workflow_step: dict[str, Any], evidence: str) -> dict[str, Any]:
        now = datetime.now().isoformat()
        return {
            "step": workflow_step.get("step", ""),
            "module": workflow_step.get("module", ""),
            "module_id": workflow_step.get("module_id", "unknown"),
            "input_data_artifacts": workflow_step.get("input_data_artifacts", ""),
            "output_artifacts": workflow_step.get("output_artifacts", ""),
            "module_input_file": "",
            "generated_artifacts": "",
            "evidence": evidence,
            "status": "stopped",
            "started_at": now,
            "completed_at": now,
            "duration_seconds": 0.0,
            "duration_human": "0 ms",
            "reviewed_by_user": False,
        }

    def execute_workflow_step(self, workflow_step: dict[str, Any]) -> dict[str, Any]:
        started_at = datetime.now().isoformat()
        step = workflow_step.get("step", "")
        module_name = workflow_step.get("module", "")
        module_id = workflow_step.get("module_id", "unknown")
        input_data_artifacts = workflow_step.get("input_data_artifacts", "")
        output_artifacts = workflow_step.get("output_artifacts", "")

        module = self.get_module_by_id(module_id) or self.get_module_by_name(module_name) or {}

        if self.execution_stop_event.is_set():
            return self.build_stopped_execution_result(workflow_step, f"Execution stopped before preparing inputs for {module_name}.")

        self.add_log("EXECUTION", f"Preparing module input file for {module_name}.")
        module_input_file = self.generate_module_input_file(workflow_step, module)
        self.add_log("EXECUTION", f"Module input file for {module_name}: {module_input_file}")

        if self.execution_stop_event.is_set():
            return self.build_stopped_execution_result(workflow_step, f"Execution stopped after input-file generation for {module_name}.")

        self.add_log("EXECUTION", f"Invoking runner for {module_name}.")
        runner_result = self.call_module_runner_or_placeholder(workflow_step, module, module_input_file)
        generated_artifacts = runner_result.get("generated_artifacts", [])
        status = runner_result.get("status", "completed")
        if self.execution_stop_event.is_set() and status != "stopped":
            status = "stopped"
        evidence = runner_result.get("evidence", f"Workflow step completed for {module_name}.")
        completed_at = datetime.now().isoformat()

        self.add_log("EXECUTION", f"Runner for {module_name} returned status={status}; generated_artifacts={len(generated_artifacts)}.")

        return {
            "step": step,
            "module": module_name,
            "module_id": module_id,
            "input_data_artifacts": input_data_artifacts,
            "output_artifacts": output_artifacts,
            "module_input_file": module_input_file,
            "generated_artifacts": "; ".join(generated_artifacts),
            "evidence": evidence,
            "status": status,
            "started_at": started_at,
            "completed_at": completed_at,
            "reviewed_by_user": False,
        }

    def get_modules_output_root(self) -> Path:
        """Return the central per-run folder that contains all END module outputs."""
        if not self.current_run_path:
            raise RuntimeError("No active run folder is available.")
        path = self.current_run_path / "modules_output"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_module_output_dir(self, module_id: str) -> Path:
        """Return the output folder for one END module within the active run."""
        clean_module_id = str(module_id or "UNKNOWN").replace("/", "_").replace("\\", "_")
        path = self.get_modules_output_root() / clean_module_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_module_output_layout(self, module_id: str) -> dict[str, Path]:
        """Return the standard STAR output layout for one END module.

        Required structure:
            RUN_XXXXX/modules_output/END-XXX/output_<module>/
            RUN_XXXXX/modules_output/END-XXX/results_<module>/
        """
        module_root = self.get_module_output_dir(module_id)
        layout_names = {
            "END-001": ("output_constellation_optimizer", "results_constellation_optimizer"),
            "END-003": ("output_attitude_propagation", "results_attitude_propagator"),
            "END-004": ("output_power_budget", "results_power_budget"),
            "END-007": ("output_synthetic_data_generation", "results_synthetic_data_generation"),
            "END-010": ("output_reflectance_determination", "results_reflectance_determination"),
            "END-018": ("output_components_thermal_analysis", "results_components_thermal_analysis"),
            "END-019": ("output_component_selector", "results_component_selector"),
        }
        clean_id = str(module_id or "UNKNOWN").upper()
        output_name, results_name = layout_names.get(
            clean_id,
            (f"output_{clean_id.lower().replace('-', '_')}", f"results_{clean_id.lower().replace('-', '_')}"),
        )
        product_dir = module_root / output_name
        results_dir = module_root / results_name
        product_dir.mkdir(parents=True, exist_ok=True)
        results_dir.mkdir(parents=True, exist_ok=True)
        return {
            "module_root": module_root,
            "module_product_output_dir": product_dir,
            "module_results_dir": results_dir,
        }

    def generate_module_input_file(self, workflow_step: dict[str, Any], module: dict[str, Any]) -> str:
        if not self.current_run_path:
            raise RuntimeError("No active run folder is available.")
        module_id = str(workflow_step.get("module_id", module.get("module_id", "UNKNOWN"))).replace("/", "_")
        step = str(workflow_step.get("step", "X")).zfill(3)
        input_dir = self.current_run_path / "module_inputs"
        input_dir.mkdir(parents=True, exist_ok=True)
        input_path = input_dir / f"STEP_{step}_{module_id}_input.json"

        module_inputs = [item for item in self.missing_information if item.get("needed_by_module_id") == module_id or item.get("needed_by") == workflow_step.get("module")]
        upstream_artifacts = []
        upstream_artifacts_absolute = []
        current_step_number = int(str(workflow_step.get("step", 0)).strip() or 0)
        for result in self.execution_results:
            try:
                result_step = int(str(result.get("step", 0)).strip() or 0)
            except ValueError:
                result_step = 0
            if result_step < current_step_number:
                for artifact in [path.strip() for path in str(result.get("generated_artifacts", "")).split(";") if path.strip()]:
                    upstream_artifacts.append(artifact)
                    upstream_artifacts_absolute.append(str(self.resolve_run_artifact_path(artifact)))

        output_layout = self.get_module_output_layout(module_id)

        payload = {
            "run_id": self.current_run_id,
            "generated_at": datetime.now().isoformat(),
            "workflow_step": workflow_step,
            "module": {
                "module_id": module.get("module_id"),
                "module_name": module.get("module_name"),
                "owner": module.get("owner"),
            },
            "resolved_inputs": module_inputs,
            "upstream_artifacts": upstream_artifacts,
            "upstream_artifacts_absolute": upstream_artifacts_absolute,
            "star_root": str(self.star_root),
            "run_output_dir": str(self.current_run_path),
            "modules_output_root": str(self.get_modules_output_root()),
            "module_output_dir": str(output_layout["module_root"]),
            "module_product_output_dir": str(output_layout["module_product_output_dir"]),
            "module_results_dir": str(output_layout["module_results_dir"]),
            "requested_outputs": self.requested_outputs,
            "requirements": self.requirements,
        }
        input_path.write_text(json.dumps(payload, indent=4), encoding="utf-8")
        self.add_log("EXECUTION", f"Resolved {len(module_inputs)} input item(s) and {len(upstream_artifacts)} upstream artifact(s) for {module.get('module_name', module_id)}.")
        return input_path.relative_to(self.current_run_path).as_posix()


    def resolve_run_artifact_path(self, artifact_path: str | Path) -> Path:
        path = Path(str(artifact_path))
        if path.is_absolute():
            return path
        if self.current_run_path:
            return self.current_run_path / path
        return path

    def make_run_relative_or_absolute(self, artifact_path: str | Path) -> str:
        path = Path(str(artifact_path))
        try:
            if self.current_run_path and path.is_absolute():
                return path.relative_to(self.current_run_path).as_posix()
        except ValueError:
            pass
        return str(artifact_path)

    def collect_module_output_artifacts(self, module_output_dir: Path) -> list[str]:
        if not module_output_dir.exists():
            return []
        artifacts: list[str] = []
        for path in sorted(module_output_dir.rglob("*")):
            if path.is_file():
                artifacts.append(self.make_run_relative_or_absolute(path))
        return artifacts

    def validate_png_artifacts(self, artifact_paths: list[str], module_output_dir: Path, module_name: str) -> str | None:
        """Check that generated PNG files are real, non-empty PNG images.

        This catches the common failure mode where MATLAB creates a .png file
        name but the file is empty, truncated, or not encoded as PNG.  A JSON
        report is written only when PNG files are present.
        """
        png_items = []
        for artifact in artifact_paths:
            if not str(artifact).lower().endswith(".png"):
                continue
            path = self.resolve_run_artifact_path(artifact)
            item = {"artifact": str(artifact), "absolute_path": str(path), "exists": path.exists()}
            if path.exists():
                try:
                    data = path.read_bytes()[:16]
                    size = path.stat().st_size
                    item["size_bytes"] = size
                    item["valid_png_signature"] = data.startswith(b"\x89PNG\r\n\x1a\n")
                    item["status"] = "valid" if size > 8 and item["valid_png_signature"] else "invalid"
                except Exception as exc:
                    item["status"] = "unreadable"
                    item["error"] = str(exc)
            else:
                item["status"] = "missing"
            png_items.append(item)

        if not png_items:
            return None

        invalid = [item for item in png_items if item.get("status") != "valid"]
        report_path = module_output_dir / "png_validation_report.json"
        report_payload = {
            "generated_at": datetime.now().isoformat(),
            "module": module_name,
            "png_count": len(png_items),
            "invalid_png_count": len(invalid),
            "png_files": png_items,
        }
        report_path.write_text(json.dumps(report_payload, indent=4), encoding="utf-8")

        if invalid:
            self.add_log("WARNING", f"{module_name}: {len(invalid)} generated PNG file(s) are invalid or unreadable. See {report_path}.")
        else:
            self.add_log("EXECUTION", f"{module_name}: validated {len(png_items)} PNG artifact(s).")

        return self.make_run_relative_or_absolute(report_path)

    def call_module_runner_or_placeholder(self, workflow_step: dict[str, Any], module: dict[str, Any], module_input_file: str) -> dict[str, Any]:
        if not self.current_run_path:
            raise RuntimeError("No active run folder is available.")
        execution_cfg = module.get("execution", {}) or {}
        runner_module_name = execution_cfg.get("runner_module") or execution_cfg.get("python_module")
        runner_function_name = execution_cfg.get("runner_function") or execution_cfg.get("function") or "run"
        module_id = str(workflow_step.get("module_id", module.get("module_id", "UNKNOWN")))
        module_name = str(workflow_step.get("module", module.get("module_name", module_id)))
        output_layout = self.get_module_output_layout(module_id)
        output_dir = output_layout["module_root"]

        if runner_module_name:
            try:
                import importlib
                runner_module = importlib.import_module(str(runner_module_name))
                runner_function = getattr(runner_module, str(runner_function_name))

                runner_kwargs = {
                    "input_file": str(self.current_run_path / module_input_file),
                    "output_dir": str(output_dir),
                    "run_id": self.current_run_id,
                }
                try:
                    runner_signature = inspect.signature(runner_function)
                    runner_parameters = runner_signature.parameters
                    if "log_callback" in runner_parameters:
                        runner_kwargs["log_callback"] = self.add_log
                    if "stop_event" in runner_parameters:
                        runner_kwargs["stop_event"] = self.execution_stop_event
                    if "cancel_event" in runner_parameters:
                        runner_kwargs["cancel_event"] = self.execution_stop_event
                    if "star_root" in runner_parameters:
                        runner_kwargs["star_root"] = str(self.star_root)
                    if "star_output_root" in runner_parameters:
                        runner_kwargs["star_output_root"] = str(self.outputs_dir)
                    if "run_output_dir" in runner_parameters:
                        runner_kwargs["run_output_dir"] = str(self.current_run_path)
                    if "module_output_dir" in runner_parameters:
                        runner_kwargs["module_output_dir"] = str(output_dir)
                    if "module_product_output_dir" in runner_parameters:
                        runner_kwargs["module_product_output_dir"] = str(output_layout["module_product_output_dir"])
                    if "module_results_dir" in runner_parameters:
                        runner_kwargs["module_results_dir"] = str(output_layout["module_results_dir"])
                    if "modules_output_root" in runner_parameters:
                        runner_kwargs["modules_output_root"] = str(self.get_modules_output_root())
                    if "module_input_dir" in runner_parameters:
                        runner_kwargs["module_input_dir"] = str(self.current_run_path / "module_inputs")
                except (TypeError, ValueError):
                    pass

                self.add_log("EXECUTION", f"Calling Python runner {runner_module_name}.{runner_function_name} for {module_name}.")
                result = runner_function(**runner_kwargs)
                self.add_log("EXECUTION", f"Runner {runner_module_name}.{runner_function_name} completed for {module_name}.")
                generated = result.get("generated_artifacts", []) if isinstance(result, dict) else []
                generated_relative: list[str] = []
                for path in generated:
                    path_obj = Path(str(path))
                    if path_obj.is_absolute() and path_obj.exists():
                        generated_relative.append(self.make_run_relative_or_absolute(path_obj))
                    else:
                        generated_relative.append(str(path))

                # Always surface every file produced inside the module output
                # folder, even if the runner forgot to list it explicitly.
                for path in self.collect_module_output_artifacts(output_dir):
                    if path not in generated_relative:
                        generated_relative.append(path)

                png_report = self.validate_png_artifacts(generated_relative, output_dir, module_name)
                if png_report and png_report not in generated_relative:
                    generated_relative.append(png_report)

                runner_status = result.get("status", "completed") if isinstance(result, dict) else "completed"
                if self.execution_stop_event.is_set():
                    runner_status = "stopped"
                runner_evidence = result.get("evidence") if isinstance(result, dict) else None
                return {
                    "status": runner_status,
                    "generated_artifacts": generated_relative,
                    "evidence": runner_evidence or f"Python runner {runner_module_name}.{runner_function_name} executed for {module_name}.",
                }
            except Exception as exc:
                error_path = output_dir / "runner_error.json"
                error_path.write_text(json.dumps({"error": str(exc), "module_input_file": module_input_file}, indent=4), encoding="utf-8")
                if self.execution_stop_event.is_set():
                    self.add_log("EXECUTION", f"Runner for {module_name} stopped after user request: {exc}")
                    return {
                        "status": "stopped",
                        "generated_artifacts": [error_path.relative_to(self.current_run_path).as_posix()],
                        "evidence": f"Runner stopped for {module_name} after user request: {exc}",
                    }
                self.add_log("ERROR", f"Runner execution failed for {module_name}: {exc}")
                return {
                    "status": "failed",
                    "generated_artifacts": [error_path.relative_to(self.current_run_path).as_posix()],
                    "evidence": f"Runner execution failed for {module_name}: {exc}",
                }

        # Placeholder execution while module-specific runner hooks are not declared.
        if self.execution_stop_event.is_set():
            return {
                "status": "stopped",
                "generated_artifacts": [],
                "evidence": f"Placeholder execution for {module_name} was stopped before artifact generation.",
            }

        self.add_log("EXECUTION", f"No runner declared for {module_name}; generating placeholder metadata only.")
        artifact_names = self.parse_output_artifact_names(workflow_step.get("output_artifacts", ""))
        if not artifact_names:
            artifact_names = ["module_result.json"]
        generated_paths = []
        result_suffixes = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".fig", ".html", ".pdf"}
        for artifact_name in artifact_names:
            clean_name = self.sanitize_artifact_name(artifact_name)
            suffix = Path(clean_name).suffix.lower()

            # Do not create fake images or fake CSV files. When a real runner is
            # missing, write explicit JSON metadata instead of creating a .png/.csv
            # file containing JSON text.
            if suffix in result_suffixes:
                artifact_path = output_layout["module_results_dir"] / f"{Path(clean_name).stem}_placeholder.json"
            elif suffix == ".csv":
                artifact_path = output_layout["module_product_output_dir"] / f"{Path(clean_name).stem}_placeholder.json"
            elif suffix:
                artifact_path = output_layout["module_product_output_dir"] / clean_name
            else:
                artifact_path = output_layout["module_product_output_dir"] / f"{clean_name}.json"

            artifact_path.write_text(
                json.dumps(
                    {
                        "run_id": self.current_run_id,
                        "generated_at": datetime.now().isoformat(),
                        "module_id": module_id,
                        "module_name": module_name,
                        "module_input_file": module_input_file,
                        "intended_artifact_name": artifact_name,
                        "status": "completed_placeholder",
                        "note": "No module runner is declared in the registry yet. This is placeholder metadata, not the real module output.",
                    },
                    indent=4,
                ),
                encoding="utf-8",
            )
            generated_paths.append(artifact_path.relative_to(self.current_run_path).as_posix())
        return {
            "status": "completed",
            "generated_artifacts": generated_paths,
            "evidence": f"Input file generated and placeholder metadata completed for {module_name}. Add execution.runner_module and execution.runner_function to call the real module.",
        }



    def should_include_input_item(self, input_item: dict[str, Any], categories: set[str], combined_text: str) -> bool:
        """Decide whether a registry input is relevant for the selected workflow context."""
        required = bool(input_item.get("required", False))
        name = str(input_item.get("name", "")).lower()
        description = self.normalize_text(str(input_item.get("description", "")))
        text = self.normalize_text(combined_text)

        # Always include required inputs for selected workflow modules.
        if required:
            return True

        # Sensor-specific optional inputs must match the actual payload context.
        if "sar" in name or "radar" in description:
            return any(token in text for token in ["sar", "radar"])
        if "optical" in name:
            return any(token in text for token in ["optical", "multispectral", "hyperspectral", "image", "imaging"])

        # Terrain/scene optional inputs are relevant only for synthetic data or scenario customization.
        if any(token in name for token in ["terrain", "texture", "3d", "model", "event"]):
            return any(token in text for token in ["synthetic", "simulation", "scenario", "terrain", "dem", "3d", "scene", "volcanic event"])

        # Battery optional inputs depend on the requested EPS/health analysis mode.
        if any(token in name for token in ["training", "forecasting", "telemetry"]):
            return any(token in text for token in ["training", "forecast", "telemetry", "soh", "rul", "operational", "real time", "real-time"])
        if any(token in name for token in ["acquisition_timeline", "mission_specific_information"]):
            return any(token in text for token in ["power", "battery", "energy", "eps", "duty", "operational", "acquisition"])

        # Defaults/assumable optional inputs may be useful if they are clearly linked to requested outputs.
        if input_item.get("default_value") not in [None, "null", "None"] and bool(input_item.get("assumption_allowed", False)):
            return any(token in text for token in ["preliminary", "assess", "simulate", "generate", "monitor"])

        return False

    def infer_missing_information_value(
        self,
        input_item: dict[str, Any],
        module: dict[str, Any],
        combined_text: str,
        selected_modules: list[dict[str, Any]],
    ) -> tuple[str, str, str]:
        """Infer whether a selected workflow input is provided, upstream-produced, assumed, or missing."""
        name = str(input_item.get("name", "")).lower()
        produced_by = str(input_item.get("produced_by", "")).strip()
        default_value = input_item.get("default_value", None)
        assumption_allowed = bool(input_item.get("assumption_allowed", False))
        required = bool(input_item.get("required", False))
        text = self.normalize_text(combined_text)

        selected_aliases: set[str] = set()
        for selected in selected_modules:
            selected_aliases.add(str(selected.get("module_id", "")).lower())
            selected_aliases.add(str(selected.get("module_name", "")).lower())
            selected_aliases.add(str(selected.get("name", "")).lower())
            selected_aliases.update(self.normalize_text(cap) for cap in (selected.get("capabilities", []) or []))

        if produced_by:
            produced_norm = self.normalize_text(produced_by)
            if produced_norm in selected_aliases or any(produced_norm in alias or alias in produced_norm for alias in selected_aliases if alias):
                return f"generated by upstream module ({produced_by})", "expected_from_upstream", "upstream_module_output"
            if "constellation" in produced_norm and any("constellation" in alias for alias in selected_aliases):
                return f"generated by upstream module ({produced_by})", "expected_from_upstream", "upstream_module_output"
            if "observation" in produced_norm and any(("synthetic" in alias or "observation" in alias) for alias in selected_aliases):
                return f"generated by upstream module ({produced_by})", "expected_from_upstream", "upstream_module_output"
            if "scenario" in produced_norm and any("scenario" in alias for alias in selected_aliases):
                return f"generated by upstream module ({produced_by})", "expected_from_upstream", "upstream_module_output"

        if any(token in name for token in ["area_of_interest", "points_or_areas_of_interest", "target_area"]):
            if "etna" in text:
                return "Mount Etna", "provided", "mission_document"
            if "southern italy" in text:
                return "Southern Italy", "provided", "mission_document"
            if "target area" in text or "area of interest" in text:
                return "target area mentioned but geometry not specified", "requires_user_input", "module_registry_required_input"

        if "scenario_definition" in name:
            return "mission_request_document + requested simulation context", "provided", "mission_document"

        if "sensor_specifications" in name:
            sensor_bits = []
            if "multispectral" in text:
                sensor_bits.append("sensor_type=multispectral")
            elif "hyperspectral" in text:
                sensor_bits.append("sensor_type=hyperspectral")
            elif "optical" in text or "image" in text:
                sensor_bits.append("sensor_type=optical")
            elif "sar" in text or "radar" in text:
                sensor_bits.append("sensor_type=radar/SAR")
            if sensor_bits:
                return "; ".join(sensor_bits), "provided", "mission_document"

        if "terrain_data" in name or "dem" in name:
            return "TBD - external DEM/terrain dataset required", "requires_user_input", "module_registry_required_input"

        if "mission_specific_information" in name:
            return "preliminary mission profile derived from approved requirements and workflow", "proposed", "module_registry_default"

        if default_value not in [None, "null", "None"]:
            value = json.dumps(default_value) if isinstance(default_value, (dict, list)) else str(default_value)
            return value, "proposed", "module_registry_default"

        if assumption_allowed:
            return "TBD - first-guess assumption required", "requires_user_input", "module_registry_required_input"

        if required:
            return "TBD - required input", "requires_user_input", "module_registry_required_input"

        return "-", "not_applicable", "not_applicable"


    # ------------------------------------------------------------------
    # Chat
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # END-019 Satellite Design Component Selector (live GUI + orchestrator hooks)
    # ------------------------------------------------------------------
    def _component_selector_service(self):
        """Load the star_component_selector package once (STAR_COMPONENT_SELECTOR_ROOT, or a folder next to STAR)."""
        service = getattr(self, "_comp_selector_service", None)
        if service is not None:
            return service
        candidates: list[Path] = []
        env_root = os.environ.get("STAR_COMPONENT_SELECTOR_ROOT", "").strip()
        if env_root:
            candidates.append(Path(env_root).expanduser())
        # the module folder inside STAR, like the other END0XX modules
        candidates.append(self.star_root / "END019-ComponentSelector" / "star_component_selector")
        for base in [self.project_dir, self.star_root]:
            for parent in [base, *base.parents]:
                candidates.append(parent / "star_component_selector")
        root = next((c.resolve() for c in candidates if (c / "star_selector" / "api.py").is_file()), None)
        if root is None:
            raise RuntimeError("star_component_selector not found: set STAR_COMPONENT_SELECTOR_ROOT.")
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from star_selector.api import SelectorService

        self._comp_selector_service = SelectorService(root / "data" / "catalog.json")
        self.add_log("SYSTEM", f"Component selector loaded from {root} ({len(self._comp_selector_service.catalog)} components).")
        return self._comp_selector_service

    def component_selector_catalog(self) -> dict[str, Any]:
        """Catalogue overview for the END-019 GUI (CubeSat classes, subsystems, vendors)."""
        try:
            return self._component_selector_service().overview()
        except Exception as exc:
            self.add_log("ERROR", f"Component selector catalogue unavailable: {exc}")
            return {"error": str(exc), "classes": [], "subsystems": [], "vendors": []}

    def component_selector_select(self, params: dict[str, Any]) -> dict[str, Any]:
        """Run the selection (live, no RUN folder needed). params as in star_selector.api.SelectorService.select."""
        try:
            params = dict(params or {})
            with_images = bool(params.pop("with_images", True))
            return self._component_selector_service().select(params, with_images=with_images)
        except Exception as exc:
            self.add_log("ERROR", f"Component selector failed: {exc}")
            return {"ok": False, "error": str(exc), "subsystems": []}

    def component_selector_datasheet(self, component_id: str) -> dict[str, Any]:
        """Datasheet (PDF, base64) of a component for the END-019 drawer: the GUI runs without an HTTP server inside STAR."""
        try:
            return self._component_selector_service().datasheet_data(str(component_id))
        except KeyError:
            return {"ok": False, "error": "Not available in the database"}
        except Exception as exc:
            self.add_log("ERROR", f"Component selector datasheet failed: {exc}")
            return {"ok": False, "error": str(exc)}

    def component_selector_from_requirements(self) -> dict[str, Any]:
        """Selector parameters derived from the reviewed requirements of the current run (and the uploaded mission text)."""
        try:
            from star_selector.api import requirements_to_params

            self._component_selector_service()
            texts = [req.get("text", "") for req in self.requirements] or [self.uploaded_text or ""]
            return requirements_to_params(texts)
        except Exception as exc:
            return {"params": {}, "evidence": {}, "notes": [str(exc)], "out_of_scope": [], "applicable": False}

    def component_selector_save(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Save the design chosen in the GUI under the current RUN (modules_output/END-019/output_component_selector)."""
        if not self.current_run_path:
            return {"ok": False, "error": "No active run folder: the design was not saved."}
        out = self.get_module_output_layout("END-019")["module_product_output_dir"] / "component_selector_user_design.json"
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        self.add_log("EXECUTION", f"Component selector design saved to {out}.")
        return {"ok": True, "path": self.make_run_relative_or_absolute(out)}

    def send_chat_message(self, text: str) -> dict[str, Any]:
        normalized = text.strip().lower()

        if not normalized:
            return {"ok": False, "reply": "Empty message.", "logs": self.logs}

        self.add_log("USER", text)

        if normalized in {"help", "aiuto", "commands", "comandi"}:
            reply = (
                "Supported prototype commands: help, status, set ready, reset, run demo. "
                "Requirements, assumptions and workflow are managed from the central tabs."
            )
        elif normalized in {"status", "stato"}:
            module_status = ", ".join(f"{m['module_name']}: {m['status']}" for m in self.modules)
            run = self.current_run_id or "none"
            reply = (
                f"Run: {run}. Requirements: {len(self.requirements)} ({self.requirements_review_status}). "
                f"Missing parameters: {len(self.missing_information)} ({self.missing_information_review_status}). "
                f"Assumptions approved: {self.assumptions_approved}. "
                f"Workflow steps: {len(self.workflow_steps)} ({self.workflow_review_status}). "
                f"Workflow approved: {self.workflow_approved}. "
                f"Execution results: {len(self.execution_results)} ({self.execution_review_status}). "
                f"Execution approved: {self.execution_approved}. "
                f"Report status: {self.report_status}. "
                f"Module status: {module_status}"
            )
        elif normalized in {"set ready", "ready", "moduli ready"}:
            self.set_all_modules_ready()
            reply = "All modules were set to Ready."
        elif normalized in {"reset", "reset modules", "reset moduli"}:
            self.reset_modules()
            reply = "All modules were reset to Idle."
        elif normalized in {"run demo", "demo", "esegui demo"}:
            reply = "Press the Run Visual Demo button to animate module execution."
        else:
            reply = "This prototype chat is not yet connected to the full STAR command interpreter. Type 'help' for supported commands."

        self.add_log("STAR", reply)

        return {"ok": True, "reply": reply, "modules": self.modules, "logs": self.logs}


def build_results_frontend_html(web_dir: Path) -> str:
    """Assemble the results-workspace HTML from the on-disk shell template
    and per-module iframe files (web/star_results_shell_template_v3.html and
    web/modules/*.html), instead of one giant embedded Python string.

    Each module's HTML lives in its own real, editable file; this function
    re-encodes it into the iframe's srcdoc="..." attribute (escaping &, <,
    >, ") at generation time. Split out 2026-09-11 from a single ~487,000
    character STAR_RESULTS_FRONTEND_HTML literal for maintainability --
    verified (scratchpad split_and_verify.py) that the decoded content of
    every iframe is byte-identical to the pre-split original, so the
    rendered page is unchanged.
    """
    shell_path = web_dir / "star_results_shell_template_v3.html"
    modules_dir = web_dir / "modules"
    shell = shell_path.read_text(encoding="utf-8")

    frame_files = {
        "__SRCDOC_PLACEHOLDER_FRAME_POWER__": "end004_results.html",
        "__SRCDOC_PLACEHOLDER_FRAME_POWERVIZ__": "end004_power_insights.html",
        "__SRCDOC_PLACEHOLDER_FRAME_SYNTHETIC__": "end007_results.html",
        "__SRCDOC_PLACEHOLDER_FRAME_REFLECTANCE__": "end010_results.html",
        "__SRCDOC_PLACEHOLDER_FRAME_THERMAL__": "end018_results.html",
        "__SRCDOC_PLACEHOLDER_FRAME_COMPSEL__": "end019_results.html",
        "__SRCDOC_PLACEHOLDER_FRAME_CONSTELLATION__": "end001_results.html",
        "__SRCDOC_PLACEHOLDER_FRAME_ATTITUDE__": "end003_results.html",
        "__SRCDOC_PLACEHOLDER_FRAME_DIAGNOSTICS__": "run_diagnostics_results.html",
    }
    for placeholder, filename in frame_files.items():
        content = (modules_dir / filename).read_text(encoding="utf-8")
        escaped = html.escape(content, quote=True)
        if placeholder not in shell:
            raise RuntimeError(f"Placeholder {placeholder} not found in shell template")
        shell = shell.replace(placeholder, escaped)
    return shell



STAR_UNIFIED_SHELL_HTML = '<!DOCTYPE html>\n<html lang="en" data-theme="dark">\n<head>\n<meta charset="UTF-8" />\n<meta name="viewport" content="width=device-width, initial-scale=1.0" />\n<title>Space mission Twin for Architecture Representation (STAR) FrontEnd</title>\n<style>\n@import url(\'https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@400;600;700;800&display=swap\');\n\n:root{\n  --bg:#090a0d;\n  --panel:#11141c;\n  --panel-strong:#151925;\n  --panel-muted:#0d1017;\n  --border:#232838;\n  --border-soft:rgba(114,125,151,.22);\n  --text:#d7dde9;\n  --text-strong:#ffffff;\n  --muted:#7d879a;\n  --muted-2:#9aa3b4;\n  --accent:#e8ff47;\n  --accent-2:#4dffc3;\n  --danger:#ff5c7a;\n  --success:#61f6a8;\n  --shadow:0 24px 80px rgba(0,0,0,.32);\n  color-scheme:dark;\n}\n:root[data-theme="light"]{\n  --bg:#f3f5f8;\n  --panel:#ffffff;\n  --panel-strong:#f8fafc;\n  --panel-muted:#eef2f7;\n  --border:#d9e0eb;\n  --border-soft:rgba(45,55,72,.13);\n  --text:#222b3b;\n  --text-strong:#070b12;\n  --muted:#667085;\n  --muted-2:#475467;\n  --accent:#667c00;\n  --accent-2:#007a66;\n  --danger:#bd2450;\n  --success:#047857;\n  --shadow:0 18px 60px rgba(31,41,55,.12);\n  color-scheme:light;\n}\n*{box-sizing:border-box}\nhtml,body{height:100%;min-height:100%}\nbody{\n  margin:0;\n  background:\n    radial-gradient(circle at top left,rgba(77,255,195,.10),transparent 32rem),\n    radial-gradient(circle at top right,rgba(232,255,71,.08),transparent 36rem),\n    var(--bg);\n  color:var(--text);\n  font-family:\'Space Mono\',ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;\n  font-size:13px;\n  line-height:1.5;\n  overflow:hidden;\n}\nbutton{font:inherit;border:1px solid var(--border);background:var(--panel-strong);color:var(--text);border-radius:12px;padding:8px 13px;cursor:pointer;transition:transform .16s ease,border-color .16s ease,background .16s ease}\nbutton:hover{transform:translateY(-1px);border-color:var(--accent-2)}\nbutton.active{border-color:transparent;background:linear-gradient(135deg,var(--accent),var(--accent-2));color:#07100d;font-weight:800}\n.app-shell{height:100%;display:flex;flex-direction:column;width:min(1920px,100%);margin:0 auto;padding:18px;gap:18px}\n.header{\n  display:flex;\n  align-items:center;\n  justify-content:space-between;\n  gap:18px;\n  padding:16px 20px;\n  border:1px solid var(--border);\n  border-radius:22px;\n  background:color-mix(in srgb,var(--panel) 92%,transparent);\n  box-shadow:var(--shadow);\n  backdrop-filter:blur(18px);\n  flex:0 0 auto;\n}\n.header h1{\n  margin:0;\n  font-family:\'Syne\',Inter,system-ui,sans-serif;\n  font-size:clamp(20px,1.85vw,28px);\n  line-height:1.05;\n  color:var(--text-strong);\n  letter-spacing:-.03em;\n}\n.header-actions{display:flex;align-items:center;justify-content:flex-end;gap:10px;flex-wrap:wrap}\n.theme-toggle{display:inline-flex;align-items:center;gap:9px;padding:7px 11px;border:1px solid var(--border);border-radius:999px;background:var(--panel-muted);color:var(--muted-2);user-select:none}\n.switch{position:relative;width:48px;height:26px;display:inline-flex;align-items:center}\n.switch input{opacity:0;width:0;height:0}\n.slider-switch{position:absolute;inset:0;border-radius:999px;background:var(--border);transition:.22s ease;box-shadow:inset 0 0 0 1px var(--border-soft)}\n.slider-switch:before{content:\'\';position:absolute;width:20px;height:20px;left:3px;top:3px;border-radius:50%;background:var(--text-strong);transition:.22s ease}\n.switch input:checked+.slider-switch{background:linear-gradient(135deg,var(--accent),var(--accent-2))}\n.switch input:checked+.slider-switch:before{transform:translateX(22px);background:#07100d}\n.workspace{\n  min-height:0;\n  flex:1 1 auto;\n  border:1px solid var(--border);\n  border-radius:22px;\n  background:color-mix(in srgb,var(--panel) 95%,transparent);\n  box-shadow:var(--shadow);\n  overflow:hidden;\n  display:flex;\n  flex-direction:column;\n}\n.workspace-tabs{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:11px;border-bottom:1px solid var(--border);background:var(--panel-strong);flex:0 0 auto;flex-wrap:wrap}\n.tab-buttons{display:flex;gap:8px;flex-wrap:wrap}\n.workspace-tab{\n  display:inline-flex;\n  flex-direction:row;\n  align-items:center;\n  justify-content:center;\n  min-width:auto;\n  min-height:38px;\n  padding:8px 16px;\n  font-family:\'Space Mono\',ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;\n  text-transform:none;\n  letter-spacing:.01em;\n  font-size:12px;\n  line-height:1;\n  white-space:nowrap;\n  color:var(--muted-2);\n  background:var(--panel-muted);\n}\n.workspace-tab .tab-title{font-size:12px;font-weight:700;letter-spacing:.01em;white-space:nowrap}\n.status-strip{display:flex;align-items:center;gap:10px;color:var(--muted);font-size:11px;flex-wrap:wrap}\n.status-dot{width:10px;height:10px;border-radius:999px;background:var(--success);box-shadow:0 0 0 4px color-mix(in srgb,var(--success) 18%,transparent)}\n.frame-stage{min-height:0;flex:1 1 auto;background:var(--bg);position:relative}\n.workspace-frame{position:absolute;inset:0;width:100%;height:100%;border:0;display:none;background:transparent}\n.workspace-frame.active{display:block}\n.placeholder{position:absolute;inset:0;display:none;align-items:center;justify-content:center;padding:30px;text-align:center;color:var(--muted)}\n.placeholder.visible{display:flex}\n.placeholder-card{max-width:720px;border:1px dashed var(--border);border-radius:18px;background:var(--panel-muted);padding:22px;box-shadow:var(--shadow)}\n.placeholder-card h2{margin:0 0 10px;color:var(--text-strong);font-family:\'Syne\',Inter,system-ui,sans-serif;text-transform:uppercase;letter-spacing:.04em;font-size:16px}\ncode{color:var(--accent-2)}\n@media(max-width:980px){\n  body{overflow:auto}.app-shell{min-height:100%;height:auto;padding:10px}.header{align-items:flex-start;flex-direction:column}.header-actions{justify-content:flex-start;width:100%}.workspace{height:78vh;min-height:720px}.workspace-tab{font-size:11px;padding:8px 12px}\n}\n\n/* STAR v2 compact shell patch */\n.app-shell{padding:12px!important;gap:12px!important;}\n.header{padding:12px 16px!important;border-radius:18px!important;}\n.workspace{border-radius:18px!important;}\n.workspace-tabs{padding:7px 8px!important;gap:8px!important;}\n.workspace-tab{min-height:32px!important;padding:6px 12px!important;border-radius:10px!important;}\n.workspace-tab .tab-title{font-size:11px!important;}\n.frame-stage{min-height:0!important;}\n\n</style>\n</head>\n<body>\n<div class="app-shell">\n  <header class="header">\n    <div>\n      <h1>Space mission Twin for Architecture Representation (STAR) FrontEnd</h1>\n    </div>\n    <div class="header-actions">\n      <label class="theme-toggle" title="Switch interface theme">\n        <span id="theme-label">Dark</span>\n        <span class="switch">\n          <input id="theme-switch" type="checkbox" aria-label="Toggle light theme" />\n          <span class="slider-switch"></span>\n        </span>\n      </label>\n    </div>\n  </header>\n\n  <section class="workspace">\n    <div class="workspace-tabs">\n      <div class="tab-buttons" role="tablist" aria-label="STAR workspaces">\n        <button id="tab-execution" class="workspace-tab active" data-workspace="execution" type="button"><span class="tab-title">Workflow Execution</span></button>\n        <button id="tab-results" class="workspace-tab" data-workspace="results" type="button"><span class="tab-title">Outputs Results Visualisation</span></button>\n      </div>\n      <div class="status-strip"><span class="status-dot"></span><span id="workspace-status">Execution workspace active.</span></div>\n    </div>\n    <div class="frame-stage">\n      <iframe id="execution-frame" class="workspace-frame active" allow="file-system-access" src="star_execution_frontend_v3.html?v=2" title="STAR Execution Workspace"></iframe>\n      <iframe id="results-frame" class="workspace-frame" allow="file-system-access" src="star_results_frontend_v3.html?v=2" title="STAR Results Workspace"></iframe>\n      <div id="execution-placeholder" class="placeholder"><div class="placeholder-card"><h2>Execution interface unavailable</h2><p>The file <code>web/index.html</code> was not found. Keep the original <code>web</code> folder next to this Python entry point.</p></div></div>\n    </div>\n  </section>\n</div>\n<script>\n(() => {\n  \'use strict\';\n  const $ = id => document.getElementById(id);\n  const state = { active: \'execution\' };\n  const executionFrame = $(\'execution-frame\');\n  const resultsFrame = $(\'results-frame\');\n  const statusText = $(\'workspace-status\');\n\n  function setTheme(theme) {\n    const value = theme === \'light\' ? \'light\' : \'dark\';\n    document.documentElement.dataset.theme = value;\n    localStorage.setItem(\'star-integrated-theme\', value);\n    $(\'theme-switch\').checked = value === \'light\';\n    $(\'theme-label\').textContent = value === \'light\' ? \'Light\' : \'Dark\';\n    try { localStorage.setItem(\'star-ui-theme\', value); } catch (_) {}\n    try { localStorage.setItem(\'star-unified-theme\', value); } catch (_) {}\n    for (const frame of [executionFrame, resultsFrame]) {\n      try {\n        const doc = frame.contentDocument;\n        const win = frame.contentWindow;\n        if (doc && doc.documentElement) {\n          doc.documentElement.dataset.theme = value;\n          if (doc.body) doc.body.dataset.theme = value;\n        }\n        if (win && typeof win.setTheme === \'function\') { win.setTheme(value, false); }\n        else if (win && typeof win.applyTheme === \'function\') { win.applyTheme(value); }\n      } catch (_) {}\n    }\n  }\n\n  function initialiseTheme() {\n    setTheme(localStorage.getItem(\'star-integrated-theme\') || \'dark\');\n    $(\'theme-switch\').addEventListener(\'change\', event => setTheme(event.target.checked ? \'light\' : \'dark\'));\n  }\n\n  function injectPywebviewApi() {\n    try {\n      if (executionFrame.contentWindow && window.pywebview) {\n        executionFrame.contentWindow.pywebview = window.pywebview;\n        executionFrame.contentWindow.dispatchEvent(new Event(\'pywebviewready\'));\n      }\n    } catch (error) {\n      console.warn(\'Unable to expose the pywebview API to the execution workspace:\', error);\n    }\n  }\n\n  function activateWorkspace(name) {\n    state.active = name;\n    document.querySelectorAll(\'.workspace-tab\').forEach(button => {\n      button.classList.toggle(\'active\', button.dataset.workspace === name);\n    });\n    executionFrame.classList.toggle(\'active\', name === \'execution\');\n    resultsFrame.classList.toggle(\'active\', name === \'results\');\n    statusText.textContent = name === \'execution\'\n      ? \'Execution workspace active.\'\n      : \'Results workspace active. Select the required RUN_XXXXX folder inside the Results workspace.\';\n\n    if (name === \'execution\') {\n      setTimeout(injectPywebviewApi, 50);\n    } else {\n      try {\n        const w = resultsFrame.contentWindow;\n        if (w && typeof w.refreshAllDashboards === \'function\') w.refreshAllDashboards();\n      } catch (_) {}\n    }\n  }\n\n  function bindTabs() {\n    document.querySelectorAll(\'.workspace-tab\').forEach(button => {\n      button.addEventListener(\'click\', () => activateWorkspace(button.dataset.workspace));\n    });\n  }\n\n  function checkExecutionFile() {\n    fetch(\'star_execution_frontend_v3.html\', { cache: \'no-store\' }).catch(() => {\n      $(\'execution-placeholder\').classList.add(\'visible\');\n    });\n  }\n\n  window.addEventListener(\'pywebviewready\', () => {\n    injectPywebviewApi();\n    setTimeout(injectPywebviewApi, 200);\n  });\n  executionFrame.addEventListener(\'load\', () => {\n    injectPywebviewApi();\n    setTimeout(injectPywebviewApi, 100);\n    setTimeout(injectPywebviewApi, 500);\n    setTheme(localStorage.getItem(\'star-integrated-theme\') || \'dark\');\n  });\n  resultsFrame.addEventListener(\'load\', () => setTheme(localStorage.getItem(\'star-integrated-theme\') || \'dark\'));\n\n  document.addEventListener(\'DOMContentLoaded\', () => {\n    initialiseTheme();\n    bindTabs();\n    checkExecutionFile();\n    activateWorkspace(\'execution\');\n  });\n})();\n</script>\n</body>\n</html>\n'

STAR_EXECUTION_FRONTEND_PATCH_CSS = '\n<style id="star-v1-execution-ui-patch">\n.star-v1-hidden{display:none!important;visibility:hidden!important;max-height:0!important;overflow:hidden!important;margin:0!important;padding:0!important;border:0!important;}\n.star-v1-upload-normalized{\n  min-height:32px!important;\n  height:32px!important;\n  padding:0 14px!important;\n  border-radius:999px!important;\n  display:inline-flex!important;\n  align-items:center!important;\n  justify-content:center!important;\n  font-size:12px!important;\n  line-height:1!important;\n  white-space:nowrap!important;\n  flex:0 0 auto!important;\n}\n#star-v1-initial-hint{\n  margin:10px 0 0 0!important;\n  padding:10px 12px!important;\n  border:1px dashed rgba(140,156,190,.40)!important;\n  border-radius:12px!important;\n  background:rgba(10,14,22,.65)!important;\n  color:#9aa3b4!important;\n  font-size:12px!important;\n  line-height:1.4!important;\n  font-family:\'Space Mono\',ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace!important;\n}\n.star-v1-copy-log-button{\n  min-height:24px!important;\n  height:24px!important;\n  padding:0 9px!important;\n  margin-left:8px!important;\n  border-radius:999px!important;\n  font-size:10px!important;\n  line-height:1!important;\n  white-space:nowrap!important;\n  vertical-align:middle!important;\n}\n.star-v1-log-tab-parent{display:flex!important;align-items:center!important;gap:6px!important;}\n.star-v1-hide-title{display:none!important;}\n</style>\n'

STAR_EXECUTION_FRONTEND_PATCH_JS = '\n<script id="star-v1-execution-ui-patch-script">\n(function(){\n  \'use strict\';\n  const PATCH_ID = \'star-v1-execution-ui-patch-script\';\n  if (window.__STAR_V1_EXECUTION_PATCH_ACTIVE__) return;\n  window.__STAR_V1_EXECUTION_PATCH_ACTIVE__ = true;\n\n  function norm(value){return String(value || \'\').replace(/\\s+/g,\' \').trim();}\n  function lower(value){return norm(value).toLowerCase();}\n  function visible(el){\n    if (!el || !el.ownerDocument || !el.ownerDocument.defaultView) return false;\n    const cs = el.ownerDocument.defaultView.getComputedStyle(el);\n    return cs.display !== \'none\' && cs.visibility !== \'hidden\';\n  }\n  function ownText(el){\n    if (!el) return \'\';\n    let text = \'\';\n    for (const node of el.childNodes) {\n      if (node.nodeType === Node.TEXT_NODE) text += node.textContent + \' \';\n    }\n    return norm(text || el.textContent || \'\');\n  }\n  function all(selector){return Array.from(document.querySelectorAll(selector));}\n  function elementsWithText(text){\n    const target = lower(text);\n    return all(\'h1,h2,h3,p,span,div,label,button,[role="tab"]\').filter(el => lower(el.textContent) === target || lower(el.textContent).includes(target));\n  }\n  function safeHide(el){\n    if (!el || el === document.body || el === document.documentElement) return;\n    el.classList.add(\'star-v1-hidden\');\n  }\n  function compactContainerFor(el){\n    const selectors = [\'.field\',\'.control\',\'.controls\',\'.toolbar-item\',\'.form-field\',\'.select-wrapper\',\'.run-folder\',\'.theme-toggle\',\'.theme-selector\',\'.header-actions\'];\n    for (const selector of selectors) {\n      const match = el.closest(selector);\n      if (match && match !== document.body && norm(match.textContent).length < 260) return match;\n    }\n    let current = el;\n    for (let depth = 0; depth < 4 && current && current.parentElement; depth += 1) {\n      const parent = current.parentElement;\n      const text = norm(parent.textContent);\n      const controls = parent.querySelectorAll(\'input,select,button,label\').length;\n      if (parent !== document.body && text.length < 220 && controls <= 5) return parent;\n      current = parent;\n    }\n    return el;\n  }\n\n  function hideInternalTitles(){\n    all(\'h1,h2,h3,p,span,div\').forEach(el => {\n      const t = norm(el.textContent);\n      if (t === \'STAR-Local Desktop App\' || t === \'Space mission Twin for Architecture Representation\') {\n        el.classList.add(\'star-v1-hide-title\');\n      }\n    });\n  }\n\n  function hideInternalRunAndThemeControls(){\n    all(\'label,span,div,p\').forEach(el => {\n      const t = norm(el.textContent);\n      const ot = ownText(el);\n      if (/^Run folder$/i.test(ot) || /^Run folder$/i.test(t)) safeHide(compactContainerFor(el));\n      if (/^Theme$/i.test(ot) || /^Theme$/i.test(t)) safeHide(compactContainerFor(el));\n    });\n    all(\'input,select\').forEach(el => {\n      const text = lower(el.getAttribute(\'aria-label\') || el.id || el.name || el.title || \'\');\n      if (text.includes(\'run folder\') || text.includes(\'theme\')) safeHide(compactContainerFor(el));\n    });\n  }\n\n  function normalizeUploadButton(){\n    const button = all(\'button\').find(btn => /upload mission request document/i.test(norm(btn.textContent)));\n    if (!button) return null;\n    button.classList.add(\'star-v1-upload-normalized\');\n    button.style.whiteSpace = \'nowrap\';\n    return button;\n  }\n\n  function missionDocumentAppearsLoaded(){\n    const text = norm(document.body ? document.body.innerText : \'\');\n    return /document uploaded/i.test(text) || /mission request received/i.test(text) || /current run id/i.test(text) || /RUN_\\d{8}_\\d{6}/.test(text);\n  }\n\n  function ensureInitialHint(){\n    const uploadButton = normalizeUploadButton();\n    if (!uploadButton) return;\n    let hint = document.getElementById(\'star-v1-initial-hint\');\n    if (!hint) {\n      hint = document.createElement(\'div\');\n      hint.id = \'star-v1-initial-hint\';\n      hint.textContent = \'Select a mission request document to proceed.\';\n      const toolbar = uploadButton.closest(\'.toolbar,.step-actions,.actions,.controls,section,div\') || uploadButton.parentElement;\n      if (toolbar && toolbar.parentElement) toolbar.parentElement.insertBefore(hint, toolbar.nextSibling);\n      else uploadButton.insertAdjacentElement(\'afterend\', hint);\n    }\n    hint.style.display = missionDocumentAppearsLoaded() ? \'none\' : \'\';\n  }\n\n  function findLabelElement(label){\n    const target = lower(label);\n    return all(\'button,[role="tab"],.tab,.tab-button,.pill,.segmented-control button,label,span,div\')\n      .find(el => lower(el.textContent) === target && visible(el));\n  }\n\n  function collectLogText(){\n    const candidates = [];\n    all(\'textarea,pre,code,[id*="log" i],[class*="log" i],[id*="console" i],[class*="console" i]\').forEach(el => {\n      if (!visible(el)) return;\n      const text = el.value !== undefined ? el.value : el.innerText;\n      const cleaned = norm(text);\n      if (cleaned.length > 0) candidates.push({el, text: text || \'\', score: cleaned.length + (/\\[(SYSTEM|EXECUTION|ERROR|WARNING|AI|USER|STAR|END-\\d{3})\\]/i.test(cleaned) ? 10000 : 0)});\n    });\n    candidates.sort((a,b) => b.score - a.score);\n    if (candidates.length) return candidates[0].text;\n    const bodyText = document.body ? document.body.innerText : \'\';\n    const lines = bodyText.split(/\\r?\\n/).filter(line => /^\\s*\\[[0-9:]{5,8}\\]/.test(line) || /\\[(SYSTEM|EXECUTION|ERROR|WARNING|AI|USER|STAR|END-\\d{3})\\]/i.test(line));\n    return lines.length ? lines.join(\'\\n\') : bodyText;\n  }\n\n  async function copyLogText(button){\n    const text = collectLogText();\n    try {\n      if (navigator.clipboard && navigator.clipboard.writeText) {\n        await navigator.clipboard.writeText(text);\n      } else {\n        const area = document.createElement(\'textarea\');\n        area.value = text;\n        area.style.position = \'fixed\';\n        area.style.opacity = \'0\';\n        document.body.appendChild(area);\n        area.focus();\n        area.select();\n        document.execCommand(\'copy\');\n        area.remove();\n      }\n      const previous = button.textContent;\n      button.textContent = \'Copied\';\n      setTimeout(() => { button.textContent = previous; }, 1200);\n    } catch (error) {\n      const previous = button.textContent;\n      button.textContent = \'Copy failed\';\n      console.warn(\'Unable to copy STAR technical log:\', error);\n      setTimeout(() => { button.textContent = previous; }, 1600);\n    }\n  }\n\n  function reorderChatAndTechnicalLog(){\n    const chat = findLabelElement(\'Interactive Chat\');\n    const log = findLabelElement(\'Technical Log\');\n    if (chat && log && chat.parentElement === log.parentElement) {\n      const parent = chat.parentElement;\n      parent.classList.add(\'star-v1-log-tab-parent\');\n      if (parent.firstElementChild !== log) parent.insertBefore(log, chat);\n    }\n    if (log && !document.getElementById(\'star-v1-copy-log-button\')) {\n      const copy = document.createElement(\'button\');\n      copy.id = \'star-v1-copy-log-button\';\n      copy.className = \'star-v1-copy-log-button\';\n      copy.type = \'button\';\n      copy.textContent = \'Copy log\';\n      copy.title = \'Copy the full technical log to the clipboard\';\n      copy.addEventListener(\'click\', event => {\n        event.preventDefault();\n        event.stopPropagation();\n        copyLogText(copy);\n      });\n      log.insertAdjacentElement(\'afterend\', copy);\n    }\n  }\n\n  function applyPatch(){\n    hideInternalTitles();\n    hideInternalRunAndThemeControls();\n    normalizeUploadButton();\n    ensureInitialHint();\n    reorderChatAndTechnicalLog();\n  }\n\n  function schedulePatch(){\n    applyPatch();\n    setTimeout(applyPatch, 100);\n    setTimeout(applyPatch, 350);\n    setTimeout(applyPatch, 900);\n  }\n\n  document.addEventListener(\'DOMContentLoaded\', schedulePatch);\n  window.addEventListener(\'load\', schedulePatch);\n  window.addEventListener(\'pywebviewready\', schedulePatch);\n  const observer = new MutationObserver(() => {\n    if (window.__STAR_V1_PATCH_PENDING__) return;\n    window.__STAR_V1_PATCH_PENDING__ = true;\n    requestAnimationFrame(() => {\n      window.__STAR_V1_PATCH_PENDING__ = false;\n      applyPatch();\n    });\n  });\n  observer.observe(document.documentElement, {childList:true,subtree:true,characterData:true});\n  schedulePatch();\n})();\n</script>\n'



def write_execution_frontend_v3(web_dir: Path) -> Path | None:
    """Create a non-destructive patched copy of web/index.html for the execution tab."""
    source_path = web_dir / "index.html"
    target_path = web_dir / "star_execution_frontend_v3.html"

    if not source_path.exists():
        return None

    html = source_path.read_text(encoding="utf-8")

    # Rebuild the patched copy on each launch so stale browser/webview cache or
    # previous generated files cannot keep the old interface alive.
    html = html.replace(STAR_EXECUTION_FRONTEND_PATCH_CSS, "")
    html = html.replace(STAR_EXECUTION_FRONTEND_PATCH_JS, "")

    if "</head>" in html:
        html = html.replace("</head>", STAR_EXECUTION_FRONTEND_PATCH_CSS + "\n</head>", 1)
    else:
        html = STAR_EXECUTION_FRONTEND_PATCH_CSS + "\n" + html

    if "</body>" in html:
        html = html.replace("</body>", STAR_EXECUTION_FRONTEND_PATCH_JS + "\n</body>", 1)
    else:
        html = html + "\n" + STAR_EXECUTION_FRONTEND_PATCH_JS

    target_path.write_text(html, encoding="utf-8")
    return target_path


def write_unified_frontend_files() -> Path:
    """Create the integrated STAR HTML shell used by the pywebview window.

    The execution workspace uses a patched, non-destructive copy of web/index.html.
    The results workspace is written from the embedded STAR results frontend so
    this Python entry point can be used as a drop-in replacement for app_webview.py.
    """
    web_dir = Path(__file__).resolve().parent / "web"
    web_dir.mkdir(parents=True, exist_ok=True)

    write_execution_frontend_v3(web_dir)

    results_path = web_dir / "star_results_frontend_v3.html"
    results_path.write_text(build_results_frontend_html(web_dir), encoding="utf-8")

    shell_path = web_dir / "star_frontend_unified_v3.html"
    shell_path.write_text(STAR_UNIFIED_SHELL_HTML, encoding="utf-8")

    return shell_path


def main() -> None:
    api = StarApi()
    shell_path = write_unified_frontend_files()

    webview.create_window(
        title="Space mission Twin for Architecture Representation (STAR) FrontEnd v3",
        url=str(shell_path),
        js_api=api,
        width=1580,
        height=960,
        min_size=(1180, 780),
    )

    webview.start(debug=False)


if __name__ == "__main__":
    main()

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


FALLBACK_MODULES = [
    {
        "module_id": "END-001",
        "module_name": "constellation optimizer",
        "owner": "fallback",
        "description": "Fallback constellation optimizer.",
        "required_inputs": [],
        "outputs": [],
        "status": "Idle",
    },
    {
        "module_id": "END-003",
        "module_name": "attitude propagation",
        "owner": "fallback",
        "description": "Fallback attitude propagation.",
        "required_inputs": [],
        "outputs": [],
        "status": "Idle",
    },
    {
        "module_id": "END-004",
        "module_name": "power budget",
        "owner": "fallback",
        "description": "Fallback power budget module for EPS energy balance and duty-cycle analysis.",
        "required_inputs": [],
        "outputs": [],
        "status": "Idle",
    },
    {
        "module_id": "END-007",
        "module_name": "synthetic data generation",
        "owner": "fallback",
        "description": "Fallback synthetic data generation.",
        "required_inputs": [],
        "outputs": [],
        "status": "Idle",
    },
    {
        "module_id": "END-008",
        "module_name": "battery healt monitoring",
        "owner": "fallback",
        "description": "Fallback battery healt monitoring.",
        "required_inputs": [],
        "outputs": [],
        "status": "Idle",
    },
    {
        "module_id": "END-010",
        "module_name": "reflectance determination",
        "owner": "fallback",
        "description": "Fallback reflectance detemination.",
        "required_inputs": [],
        "outputs": [],
        "status": "Idle",
    }
]


def load_yaml_file(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    if not isinstance(data, dict):
        raise ValueError(f"YAML file does not contain a dictionary: {path}")

    return data


def normalize_module(raw: dict[str, Any], registry_path: Path) -> dict[str, Any]:
    module_id = str(raw.get("module_id", registry_path.stem))
    module_name = str(raw.get("module_name", module_id))

    # Keep the formal fields required by the orchestrator, but also preserve
    # planning-oriented metadata from the YAML files. The mission planner uses
    # aliases, activation_rules and planning_guidance to decide whether a module
    # is relevant; dropping these fields makes the LLM see only a partial module
    # description.
    normalized = {
        "module_id": module_id,
        "module_name": module_name,
        "owner": str(raw.get("owner", "unknown")),
        "description": str(raw.get("description", "No description available.")).strip(),
        "capabilities": raw.get("capabilities", []) or [],
        "required_inputs": raw.get("required_inputs", []) or [],
        "outputs": raw.get("outputs", []) or [],
        "domain_of_validity": raw.get("domain_of_validity", {}) or {},
        "execution": raw.get("execution", {}) or {},
        "interface_notes": str(raw.get("interface_notes", "")).strip(),
        "registry_path": str(registry_path),
        "status": "Idle",
    }

    optional_fields = [
        "aliases",
        "short_description",
        "activation_rules",
        "planning_guidance",
        "source_documents",
        "module_type",
        "module_version",
        "responsible",
        "interface_dependencies",
        "interface_plane",
        "constraints",
    ]
    for key in optional_fields:
        if key in raw:
            normalized[key] = raw.get(key)

    # Preserve any future registry keys without allowing them to overwrite the
    # normalized core fields above. This keeps the registry extensible.
    for key, value in raw.items():
        normalized.setdefault(key, value)

    # Phase B (2026-10-21): the registry declares `produces`; `outputs` (name, artifact_name, data_type, description) is
    # derived from it for the results tab and the planner text.
    if not normalized["outputs"]:
        products = list(raw.get("produces") or [])
        for block in (raw.get("phases") or {}).values():
            products.extend((block or {}).get("produces") or [])
        normalized["outputs"] = [
            {"name": p.get("product"), "artifact_name": p.get("path"), "data_type": p.get("format"),
             "description": p.get("description", ""), "guaranteed": bool(p.get("guaranteed"))}
            for p in products if isinstance(p, dict)
        ]

    return normalized


def load_module_registry(registry_dir: str | Path) -> list[dict[str, Any]]:
    registry_path = Path(registry_dir)

    if not registry_path.exists():
        return FALLBACK_MODULES

    yaml_files = sorted(
        list(registry_path.glob("*.yaml")) + list(registry_path.glob("*.yml"))
    )

    if not yaml_files:
        return FALLBACK_MODULES

    modules = []
    for yaml_file in yaml_files:
        raw = load_yaml_file(yaml_file)
        modules.append(normalize_module(raw, yaml_file))

    return modules

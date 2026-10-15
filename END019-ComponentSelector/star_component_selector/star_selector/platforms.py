"""Piattaforme satellitari complete (es. Tyvak): dati di riferimento, non usati dal selettore di componenti."""
from __future__ import annotations

import json
from pathlib import Path

REQUIRED = ("id", "vendor", "name", "launch_mass_kg_max", "payload_mass_kg_max", "solar_array_power_w_max", "modules", "source", "image")


def validate_platform(d: dict) -> list[str]:
    pid = d.get("id", "?")
    errs = [f"{pid}: campo mancante '{k}'" for k in REQUIRED if k not in d]
    src = d.get("source") or {}
    if not str(src.get("url", "")).startswith("https://"):
        errs.append(f"{pid}: source.url mancante")
    img = d.get("image") or {}
    if not (img.get("file") and str(img.get("image_url", "")).startswith("https://")):
        errs.append(f"{pid}: image senza file o fonte")
    for k in ("launch_mass_kg_max", "payload_mass_kg_max", "solar_array_power_w_max"):
        v = d.get(k)
        if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0):
            errs.append(f"{pid}: {k} non valido")
    return errs


def load_platforms(path: str | Path) -> list[dict]:
    items = json.loads(Path(path).read_text(encoding="utf-8"))["platforms"]
    errs = [e for d in items for e in validate_platform(d)]
    if errs:
        raise ValueError("Piattaforme non valide:\n  " + "\n  ".join(errs))
    return items

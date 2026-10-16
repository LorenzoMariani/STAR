from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any, Callable, Iterable

LogCallback = Callable[[str, str], Any]

# STAR run modes (2026-10-15): 'test' (default: the fastest settings of every
# module) and 'full' (the modules' complete settings, with an accuracy level
# 1-5 that sets how long the searches run, 3 = the modules' templates). The
# frontend writes them into every module input file ("run_mode", "run_level")
# and into STAR_RUN_MODE / STAR_RUN_LEVEL; each runner maps them onto its module
# (END-007 / Unreal always runs in full). The 'demo' mode existed until
# 2026-10-15 with the settings of test: old input files are read as test.
RUN_MODES = ("test", "full")
FULL_LEVELS = {1: "Low", 2: "Medium", 3: "High", 4: "Extra high", 5: "Max"}
DEFAULT_FULL_LEVEL = 3


def star_run_mode(star_payload: dict[str, Any] | None = None) -> str:
    """Run mode of this STAR run: the module input file's run_mode, else STAR_RUN_MODE, else 'test'."""
    import os
    for value in ((star_payload or {}).get("run_mode"), os.environ.get("STAR_RUN_MODE")):
        mode = str(value or "").strip().lower()
        if mode == "demo":
            return "test"
        if mode in RUN_MODES:
            return mode
    return "test"


def star_run_level(star_payload: dict[str, Any] | None = None) -> int:
    """Accuracy level (1-5) of a full run: the module input file's run_level, else STAR_RUN_LEVEL, else 3."""
    import os
    for value in ((star_payload or {}).get("run_level"), os.environ.get("STAR_RUN_LEVEL")):
        try:
            level = int(float(str(value).strip()))
        except (TypeError, ValueError):
            continue
        if level in FULL_LEVELS:
            return level
    return DEFAULT_FULL_LEVEL


MODULE_OUTPUT_LAYOUT: dict[str, tuple[str, str]] = {
    "END-001": ("output_constellation_optimizer", "results_constellation_optimizer"),
    "END-003": ("output_attitude_propagation", "results_attitude_propagator"),
    "END-007": ("output_synthetic_data_generation", "results_synthetic_data_generation"),
    "END-010": ("output_reflectance_determination", "results_reflectance_determination"),
}

RESULT_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif",
    ".svg", ".fig", ".html", ".htm", ".pdf", ".js",
}

PRODUCT_SUFFIXES = {
    ".csv", ".json", ".mat", ".xlsx", ".xls", ".txt", ".dat",
    ".npy", ".npz", ".nc", ".h5", ".hdf5", ".parquet", ".xml",
    ".log", ".yaml", ".yml",
}

# Filenames that are reporting/dashboard artifacts (registry "kind: result")
# despite having a suffix (.json) that PRODUCT_SUFFIXES would otherwise route
# to output_*/ instead of results_*/. Checked by exact name, not suffix, so
# this doesn't affect other .json files (e.g. per-satellite product JSONs)
# that are meant to stay in the product folder for downstream modules.
RESULT_FILENAMES_OVERRIDE = {
    "coverage_summary.json",
}


def emit(log_callback: LogCallback | None, level: str, message: str) -> None:
    if not callable(log_callback):
        return
    try:
        log_callback(level, message)
    except Exception:
        pass


def ensure_module_output_layout(module_root: Path, module_id: str) -> tuple[Path, Path]:
    """Create and return the standard product/results folders for a module."""
    module_id = str(module_id or "UNKNOWN").upper()
    output_name, results_name = MODULE_OUTPUT_LAYOUT.get(
        module_id,
        (f"output_{module_id.lower().replace('-', '_')}", f"results_{module_id.lower().replace('-', '_')}"),
    )
    product_dir = module_root / output_name
    results_dir = module_root / results_name
    product_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)
    return product_dir, results_dir


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=4), encoding="utf-8")


def make_runtime_input_copy(
    source_input: Path,
    destination: Path,
    module_root: Path,
    product_dir: Path,
    results_dir: Path,
    star_payload: dict[str, Any],
    extra: dict[str, Any] | None = None,
) -> Path:
    """Copy a module JSON input and append STAR runtime path metadata.

    Extra keys are intentionally non-destructive: existing module-specific fields
    are preserved, while STAR adds a star_runtime block and a few top-level path
    aliases that MATLAB scripts can read if they already support them.
    """
    data = load_json(source_input)
    data.setdefault("star_runtime", {})
    data["star_runtime"].update({
        "module_output_dir": str(module_root),
        "module_product_output_dir": str(product_dir),
        "module_results_dir": str(results_dir),
        "modules_output_root": str(star_payload.get("modules_output_root", "")),
        "run_output_dir": str(star_payload.get("run_output_dir", "")),
        "upstream_artifacts": star_payload.get("upstream_artifacts", []),
        "upstream_artifacts_absolute": star_payload.get("upstream_artifacts_absolute", []),
    })
    data.setdefault("module_output_dir", str(module_root))
    data.setdefault("module_product_output_dir", str(product_dir))
    data.setdefault("module_results_dir", str(results_dir))
    if extra:
        data["star_runtime"].update(extra)
        for key, value in extra.items():
            data.setdefault(key, value)
    write_json(destination, data)
    return destination


def find_upstream_artifact(
    star_payload: dict[str, Any],
    include_tokens: Iterable[str],
    suffixes: Iterable[str] = (".csv",),
) -> Path | None:
    tokens = [str(token).lower() for token in include_tokens]
    suffix_set = {str(suffix).lower() for suffix in suffixes}
    candidates = []
    for key in ("upstream_artifacts_absolute", "upstream_artifacts"):
        raw_items = star_payload.get(key, []) or []
        if isinstance(raw_items, str):
            raw_items = [raw_items]
        for item in raw_items:
            path = Path(str(item))
            name = path.name.lower()
            full = str(path).lower().replace("\\", "/")
            if suffix_set and path.suffix.lower() not in suffix_set:
                continue
            if all(token in full or token in name for token in tokens):
                candidates.append(path)
    for path in candidates:
        if path.exists():
            return path
    return candidates[0] if candidates else None


def normalize_direct_module_outputs(
    module_root: Path,
    product_dir: Path,
    results_dir: Path,
    keep_names: set[str] | None = None,
    log_callback: LogCallback | None = None,
    module_label: str = "module",
) -> list[str]:
    """Move direct files accidentally written in END-XXX/ into output_/results_.

    Runner bookkeeping files are left in the module root. Product-like files are
    moved to output_*, plot/report-like files to results_*.
    """
    keep_names = {name.lower() for name in (keep_names or set())}
    moved: list[str] = []
    for path in list(module_root.iterdir()) if module_root.exists() else []:
        if not path.is_file():
            continue
        if path.name.lower() in keep_names:
            continue
        if path.parent in {product_dir, results_dir}:
            continue
        suffix = path.suffix.lower()
        if suffix in RESULT_SUFFIXES or path.name in RESULT_FILENAMES_OVERRIDE:
            destination = results_dir / path.name
        elif suffix in PRODUCT_SUFFIXES:
            destination = product_dir / path.name
        else:
            continue
        if destination.exists():
            destination = destination.with_name(f"{destination.stem}_{int(time.time())}{destination.suffix}")
        try:
            shutil.move(str(path), str(destination))
            moved.append(str(destination))
            emit(log_callback, "EXECUTION", f"{module_label}: moved {path.name} to {destination.parent.name}/")
        except Exception as exc:
            emit(log_callback, "WARNING", f"{module_label}: could not move {path} to standard output folder: {exc}")
    return moved


def copy_recent_external_outputs(
    candidate_roots: Iterable[Path],
    module_root: Path,
    product_dir: Path,
    results_dir: Path,
    since_epoch: float,
    log_callback: LogCallback | None = None,
    module_label: str = "module",
) -> list[str]:
    """Copy recent files produced by legacy scripts in external Output folders.

    This is a compatibility safeguard for MATLAB/Unreal launchers that still
    write to their historical local Output folder instead of STAR's run folder.
    """
    copied: list[str] = []
    module_root_resolved = module_root.resolve()
    for root in candidate_roots:
        if not root or not root.exists() or not root.is_dir():
            continue
        try:
            if root.resolve() == module_root_resolved or module_root_resolved in root.resolve().parents:
                continue
        except Exception:
            pass
        for source in sorted(root.rglob("*")):
            if not source.is_file():
                continue
            try:
                if source.stat().st_mtime < since_epoch - 2:
                    continue
            except Exception:
                continue
            suffix = source.suffix.lower()
            if suffix in RESULT_SUFFIXES or source.name in RESULT_FILENAMES_OVERRIDE:
                destination = results_dir / source.name
            elif suffix in PRODUCT_SUFFIXES:
                destination = product_dir / source.name
            else:
                continue
            if destination.exists():
                destination = destination.with_name(f"{destination.stem}_{int(time.time())}{destination.suffix}")
            try:
                shutil.copy2(source, destination)
                copied.append(str(destination))
                emit(log_callback, "EXECUTION", f"{module_label}: copied legacy output {source} -> {destination}")
            except Exception as exc:
                emit(log_callback, "WARNING", f"{module_label}: could not copy legacy output {source}: {exc}")
    return copied

# ---------------------------------------------------------------------------
# STAR runtime adapters for legacy MATLAB modules
# ---------------------------------------------------------------------------
import base64
import csv
import math
from datetime import datetime, timedelta, timezone

_EMPTY_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def resolved_input_map(star_payload: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in star_payload.get("resolved_inputs", []) or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("parameter", "")).strip()
        if not key:
            continue
        result[key] = item.get("proposed_value")
    return result


def parse_star_value(value: Any, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list, int, float, bool)):
        return value
    text = str(value).strip()
    if not text or text == "-" or text.lower().startswith("tbd"):
        return default
    try:
        return json.loads(text)
    except Exception:
        return text


def input_value(star_payload: dict[str, Any], name: str, default: Any = None) -> Any:
    return parse_star_value(resolved_input_map(star_payload).get(name), default)


def coerce_float(value: Any, default: float) -> float:
    value = parse_star_value(value, default)
    try:
        return float(value)
    except Exception:
        return float(default)


def coerce_bool(value: Any, default: bool = False) -> bool:
    value = parse_star_value(value, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "si", "sì"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return default


def parse_datetime_like(value: Any, default: str = "2026-01-01 00:00:00") -> str:
    raw = parse_star_value(value, default)
    text = str(raw or default).strip()
    if not text or text.lower().startswith("tbd"):
        return default
    text = text.replace("T", " ").replace("Z", "")
    if len(text) == 10:
        text += " 00:00:00"
    try:
        dt = datetime.fromisoformat(text)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return default


def target_lat_lon(star_payload: dict[str, Any]) -> tuple[float, float]:
    # Defaults to Mount Etna, since the current SIU/STAR examples usually use Etna.
    default_lat, default_lon = 37.748, 14.999
    for key in ("target_site", "area_of_interest", "points_or_areas_of_interest", "target_area"):
        value = input_value(star_payload, key, None)
        if isinstance(value, dict):
            lat = value.get("lat", value.get("latitude", value.get("site_lat_deg")))
            lon = value.get("lon", value.get("longitude", value.get("site_lon_deg")))
            try:
                return float(lat), float(lon)
            except Exception:
                pass
        text = str(value or "").lower()
        if "etna" in text:
            return default_lat, default_lon
        if "southern italy" in text or "italy" in text:
            return 40.0, 15.0
    return default_lat, default_lon


def first_upstream_file(star_payload: dict[str, Any], suffix: str, contains: list[str] | None = None) -> Path | None:
    contains = [token.lower() for token in (contains or [])]
    candidates: list[Path] = []
    for key in ("upstream_artifacts_absolute", "upstream_artifacts"):
        items = star_payload.get(key, []) or []
        if isinstance(items, str):
            items = [items]
        for item in items:
            path = Path(str(item))
            text = str(path).lower().replace("\\", "/")
            if suffix and path.suffix.lower() != suffix.lower():
                continue
            if contains and not all(token in text for token in contains):
                continue
            candidates.append(path)
    for path in candidates:
        if path.exists():
            return path
    return candidates[0] if candidates else None


def write_valid_png(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(base64.b64decode(_EMPTY_PNG_BASE64))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def create_constellation_bridge_outputs(
    product_dir: Path,
    results_dir: Path,
    star_payload: dict[str, Any],
    reason: str,
) -> list[str]:
    product_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)
    sim_start = parse_datetime_like(input_value(star_payload, "simulation_start_date", None))
    sim_hours = coerce_float(input_value(star_payload, "propagation_time", 2.0), 2.0) * 24.0
    fov = coerce_float(input_value(star_payload, "optical_field_of_view_deg", 5.0), 5.0)
    sat = {
        "sim_start_date": sim_start,
        "sim_hours": sim_hours,
        "orbit": {
            "alt_perigee_m": 550000.0,
            "alt_apogee_m": 550000.0,
            "inclination_deg": 97.6,
            "raan_deg": 0.0,
            "omega_deg": 0.0,
            "nu_deg": 0.0,
        },
        "star_fallback": True,
        "fallback_reason": reason,
        "sensor": {"optical_field_of_view_deg": fov},
    }
    satellite_json = product_dir / "satellite_01.json"
    write_json(satellite_json, sat)
    csv_path = product_dir / "constellation_optimizer_output.csv"
    rows = [{
        "satellite_index": 1,
        "source_json": satellite_json.name,
        "sim_start_date": sim_start,
        "sim_hours": sim_hours,
        "alt_perigee_m": sat["orbit"]["alt_perigee_m"],
        "alt_apogee_m": sat["orbit"]["alt_apogee_m"],
        "inclination_deg": sat["orbit"]["inclination_deg"],
        "raan_deg": sat["orbit"]["raan_deg"],
        "omega_deg": sat["orbit"]["omega_deg"],
        "nu_deg": sat["orbit"]["nu_deg"],
        "fallback": True,
    }]
    write_csv(csv_path, rows)
    summary_path = product_dir / "constellation_optimizer_summary.json"
    write_json(summary_path, {"fallback": True, "reason": reason, "csv": str(csv_path), "satellites": [sat]})
    for name in [
        "01_optimization_summary.png",
        "02_constellation_groundtrack.png",
        "03_constellation_3d_eci.png",
        "04_constellation_3d_ecef.png",
    ]:
        write_valid_png(results_dir / name)
    return [str(p) for p in sorted(product_dir.rglob("*")) if p.is_file()] + [str(p) for p in sorted(results_dir.rglob("*")) if p.is_file()]


def read_constellation_first_orbit(star_payload: dict[str, Any]) -> dict[str, Any]:
    csv_path = first_upstream_file(star_payload, ".csv", ["constellation"])
    if csv_path and csv_path.exists():
        try:
            with csv_path.open("r", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            if rows:
                row = rows[0]
                return {
                    "sim_start_date": row.get("sim_start_date") or "2026-01-01 00:00:00",
                    "sim_hours": coerce_float(row.get("sim_hours"), 48.0),
                    "alt_perigee_m": coerce_float(row.get("alt_perigee_m"), 550000.0),
                    "alt_apogee_m": coerce_float(row.get("alt_apogee_m"), 550000.0),
                    "inclination_deg": coerce_float(row.get("inclination_deg"), 97.6),
                    "raan_deg": coerce_float(row.get("raan_deg"), 0.0),
                    "omega_deg": coerce_float(row.get("omega_deg"), 0.0),
                    "nu_deg": coerce_float(row.get("nu_deg"), 0.0),
                }
        except Exception:
            pass
    return {
        "sim_start_date": parse_datetime_like(input_value(star_payload, "simulation_start_date", None)),
        "sim_hours": coerce_float(input_value(star_payload, "simulation_duration_hours", 48.0), 48.0),
        "alt_perigee_m": 550000.0,
        "alt_apogee_m": 550000.0,
        "inclination_deg": 97.6,
        "raan_deg": 0.0,
        "omega_deg": 0.0,
        "nu_deg": 0.0,
    }


def create_attitude_bridge_outputs(
    product_dir: Path,
    results_dir: Path,
    star_payload: dict[str, Any],
    reason: str,
) -> list[str]:
    product_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)
    orbit = read_constellation_first_orbit(star_payload)
    sim_start = parse_datetime_like(orbit.get("sim_start_date"))
    try:
        start_dt = datetime.fromisoformat(sim_start)
    except Exception:
        start_dt = datetime(2026, 1, 1, 0, 0, 0)
    sim_hours = max(1.0, coerce_float(orbit.get("sim_hours"), 48.0))
    alt_km = coerce_float(orbit.get("alt_perigee_m"), 550000.0) / 1000.0
    inc = math.radians(coerce_float(orbit.get("inclination_deg"), 97.6))
    raan = math.radians(coerce_float(orbit.get("raan_deg"), 0.0))
    nu0 = math.radians(coerce_float(orbit.get("nu_deg"), 0.0))
    radius_km = 6378.137 + alt_km
    rows: list[dict[str, Any]] = []
    for k in range(0, 25):
        frac = k / 24.0
        theta = nu0 + 2.0 * math.pi * frac
        x_orb = radius_km * math.cos(theta)
        y_orb = radius_km * math.sin(theta)
        z_orb = 0.0
        # rotate by inclination and RAAN
        x1 = x_orb
        y1 = y_orb * math.cos(inc) - z_orb * math.sin(inc)
        z1 = y_orb * math.sin(inc) + z_orb * math.cos(inc)
        x = x1 * math.cos(raan) - y1 * math.sin(raan)
        y = x1 * math.sin(raan) + y1 * math.cos(raan)
        z = z1
        ts = (start_dt + timedelta(seconds=frac * sim_hours * 3600.0)).strftime("%Y-%m-%dT%H:%M:%SZ")
        rows.append({
            "timestamp_utc": ts,
            "eci_x_km": round(x, 3),
            "eci_y_km": round(y, 3),
            "eci_z_km": round(z, 3),
            "q_w": 1.0,
            "q_x": 0.0,
            "q_y": 0.0,
            "q_z": 0.0,
            "nadir_offset_deg": 0.0,
        })
    main_csv = product_dir / "output_attitude_propagation.csv"
    write_csv(main_csv, rows)
    write_csv(results_dir / "output_attitude_propagation_ECI.csv", rows)
    write_csv(results_dir / "output_attitude_propagation_Unity.csv", rows)
    write_json(results_dir / "attitude_propagation_summary.json", {"fallback": True, "reason": reason, "row_count": len(rows)})
    for name in [
        "01_telemetry.png",
        "02_tracking.png",
        "03_angular_momentum.png",
        "04_ground_track.png",
        "05_orbit_3d_ecef.png",
        "06_orbit_3d_eci.png",
    ]:
        write_valid_png(results_dir / name)
    return [str(p) for p in sorted(product_dir.rglob("*")) if p.is_file()] + [str(p) for p in sorted(results_dir.rglob("*")) if p.is_file()]


def create_reflectance_bridge_outputs(
    product_dir: Path,
    results_dir: Path,
    star_payload: dict[str, Any],
    reason: str,
) -> list[str]:
    product_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / "Plots").mkdir(parents=True, exist_ok=True)
    (results_dir / "Frames").mkdir(parents=True, exist_ok=True)
    input_csv = first_upstream_file(star_payload, ".csv", ["output_attitude_propagation"])
    rows: list[dict[str, Any]] = []
    if input_csv and input_csv.exists():
        try:
            with input_csv.open("r", encoding="utf-8") as f:
                attitude_rows = list(csv.DictReader(f))
            for idx, row in enumerate(attitude_rows[:25]):
                rows.append({
                    "timestamp_utc": row.get("timestamp_utc", idx),
                    "flux": round(1000.0 * max(0.0, math.cos(idx / max(1, len(attitude_rows[:25])) * math.pi / 2.0)), 6),
                    "apparent_magnitude": round(10.0 + idx * 0.05, 6),
                    "source": "star_bridge",
                })
        except Exception:
            rows = []
    if not rows:
        now = datetime(2026, 1, 1, 0, 0, 0)
        rows = [{"timestamp_utc": (now + timedelta(minutes=i * 10)).strftime("%Y-%m-%dT%H:%M:%SZ"), "flux": 1000 - i * 10, "apparent_magnitude": 10 + i * 0.05, "source": "star_bridge"} for i in range(10)]
    flux_csv = product_dir / "flux.csv"
    write_csv(flux_csv, rows)
    write_json(product_dir / "reflectance_summary.json", {"fallback": True, "reason": reason, "input_csv": str(input_csv) if input_csv else None, "rows": len(rows)})
    write_valid_png(results_dir / "Plots" / "reflectance_flux.png")
    write_valid_png(results_dir / "Frames" / "frame_0001.png")
    return [str(p) for p in sorted(product_dir.rglob("*")) if p.is_file()] + [str(p) for p in sorted(results_dir.rglob("*")) if p.is_file()]


def build_end001_config(star_payload: dict[str, Any]) -> dict[str, Any]:
    lat, lon = target_lat_lon(star_payload)
    start = parse_datetime_like(input_value(star_payload, "simulation_start_date", None))
    try:
        dt = datetime.fromisoformat(start)
    except Exception:
        dt = datetime(2026, 1, 1)
    fov = coerce_float(input_value(star_payload, "optical_field_of_view_deg", 5.0), 5.0)
    return {
        "TimeSettings": {
            "StartDate": [dt.year, dt.month, dt.day],
            "StartHour": dt.hour,
            "StartMin": dt.minute,
            "StartSec": dt.second,
        },
        "RegionSettings": {
            # Keep the legacy END-001 ROI_2.m interface happy.
            # ROI_2 first reads RegionSettings.AreaofInterest; older STAR
            # examples used this exact mixed-case field name.
            "AreaofInterest": "Point",
            "RegionType": "Point",
            "AreaType": "Point",
            "Name": "STAR target",
            "TargetName": "STAR target",
            # Multiple aliases are intentional because ROI_2 versions used in
            # different END-001 drops are not fully schema-stable.
            "lat": lat,
            "lon": lon,
            "latitude": lat,
            "longitude": lon,
            "Lat": lat,
            "Lon": lon,
            "Latitude": lat,
            "Longitude": lon,
            "CenterLat": lat,
            "CenterLon": lon,
            "TargetLat": lat,
            "TargetLon": lon,
            "Alt": 0.0,
            "alt": 0.0,
            "Mask": 10.0,
            "mask": 10.0,
            "Sites": [{"name": "STAR target", "lat": lat, "lon": lon, "alt": 0.0}],
            "Targets": [{"name": "STAR target", "lat": lat, "lon": lon, "alt": 0.0}],
            "Points": [{"name": "STAR target", "lat": lat, "lon": lon, "alt": 0.0}],
        },
        "GroundStations": [{"name": "STAR target", "lat": lat, "lon": lon, "alt": 0.0, "mask": 10.0}],
        "SensorSettings": {
            "Sun_Constraint": False,
            "Operative_Mode": "Single Sensor",
            "Single_Sensor_Type": "CON",
            "CON_FOV": fov,
            "PBS_FOV": fov,
            "SAR_LeftButton": False,
            "SAR_LeftRightButton": True,
            "SAR_RightButton": False,
            "SAR_theta_min": 20,
            "SAR_theta_max": 45,
        },
        "Weights": {
            "MaxRevisitTime": 1,
            "Percentile90RevisitTime": 1,
            "NumSatellites": 1,
            "NumPlanes": 1,
            "MaxLatency": 1,
            "Robustness": 1,
            "CollisionAvoidance": 1,
            "Launch": 1,
            "EndOfLife": 1,
            "AvgGSAccessTime": 1,
        },
        "OptimizerSettings": {
            "Population": 8,
            "Iterations": 2,
            "PlatEMO_Algorithm": "NSGAII",
            "Orbit_Type": "SSORGT",
            "Optimizer_Type": "MOGA NSGA-II",
        },
        "star_runtime": {
            "generated_from": "STAR module input payload",
            "note": "Runtime config generated because the STAR orchestration JSON is not the native MATLAB schema.",
        },
    }


def build_end003_config(star_payload: dict[str, Any]) -> dict[str, Any]:
    orbit = read_constellation_first_orbit(star_payload)
    lat, lon = target_lat_lon(star_payload)
    env_flags = input_value(star_payload, "environmental_flags", {}) or {}
    if not isinstance(env_flags, dict):
        env_flags = {}
    att_state = input_value(star_payload, "initial_attitude_state", {}) or {}
    if not isinstance(att_state, dict):
        att_state = {}
    return {
        "sim_start_date": parse_datetime_like(input_value(star_payload, "simulation_start_date", orbit.get("sim_start_date"))),
        "sim_hours": coerce_float(input_value(star_payload, "simulation_duration_hours", orbit.get("sim_hours", 48.0)), 48.0),
        "orbit": {
            "alt_perigee_m": coerce_float(orbit.get("alt_perigee_m"), 550000.0),
            "alt_apogee_m": coerce_float(orbit.get("alt_apogee_m"), 550000.0),
            "inclination_deg": coerce_float(orbit.get("inclination_deg"), 97.6),
            "raan_deg": coerce_float(orbit.get("raan_deg"), 0.0),
            "omega_deg": coerce_float(orbit.get("omega_deg"), 0.0),
            "nu_deg": coerce_float(orbit.get("nu_deg"), 0.0),
        },
        "target": {
            "site_lat_deg": lat,
            "site_lon_deg": lon,
            "elev_threshold": 10.0,
            "Sun_Constraint": False,
            "Sun_Constraint_Mode": "none",
            "Sun_Elevation_Threshold_Deg": -90.0,
        },
        "sat": {
            "attitude_mode": str(input_value(star_payload, "attitude_mode", "nadir") or "nadir"),
            "q0": att_state.get("q0", [1.0, 0.0, 0.0, 0.0]),
            "w0": att_state.get("w0_rad_s", att_state.get("w0", [0.0, 0.0, 0.0])),
            "m": 100.0,
            "A_ref": 1.0,
            "Cd": 2.2,
            "Cr": 1.5,
            "Ix": 10.0,
            "Iy": 10.0,
            "Iz": 10.0,
            "r_cp": [0.0, 0.0, 0.0],
        },
        "env": {
            "Re": 6378137.0,
            "flags": {
                "gg": coerce_bool(env_flags.get("gg"), True),
                "srp": coerce_bool(env_flags.get("srp"), False),
                "drag": coerce_bool(env_flags.get("drag"), False),
                "pert": coerce_bool(env_flags.get("pert"), True),
                "j2": coerce_bool(env_flags.get("j2"), True),
                "j3": coerce_bool(env_flags.get("j3"), False),
            },
        },
        "star_runtime": {"generated_from": "STAR module input payload"},
    }


def build_end010_config(star_payload: dict[str, Any], product_dir: Path, results_dir: Path, end003_csv: Path | None, star_root: Path) -> dict[str, Any]:
    # These defaults are intentionally conservative. If local data files exist in
    # the END-010 tree, MATLAB can use them; otherwise the runner will create a
    # deterministic bridge output instead of breaking the whole workflow.
    data_dir = star_root / "END010-ReflectanceDetermination" / "lib" / "data"
    start = parse_datetime_like(input_value(star_payload, "simulation_start_date", None))
    return {
        "paths": {
            "inputCsv": str(end003_csv) if end003_csv else "",
            "nutData": str(data_dir / "nut80.mat"),
            "deData": str(data_dir / "DE440Coeff.mat"),
            "stationsJson": str(data_dir / "stations.json"),
            "tleFile": str(data_dir / "tle.txt"),
            "eopFile": str(data_dir / "eop.txt"),
            "unityExe": "",
        },
        "flags": {
            "useInputCsv": bool(end003_csv),
            "orbitEphemeris": False,
            "sunEphemeris": False,
            "obsEphemeris": False,
            "attEphemeris": False,
        },
        "simulation": {
            "debug": False,
            "delta": 60,
            "duration": 3600,
            "mask": 10,
            "observatory": "default",
            "start": start,
        },
        "unityOpts": {"logFile": str(results_dir / "unity.log")},
        "star_runtime": {
            "module_product_output_dir": str(product_dir),
            "module_results_dir": str(results_dir),
            "end003_output_csv": str(end003_csv) if end003_csv else None,
        },
    }


def move_result_files_from_product(product_dir: Path, results_dir: Path) -> list[str]:
    moved: list[str] = []
    for path in list(product_dir.iterdir()) if product_dir.exists() else []:
        if not path.is_file():
            continue
        if path.suffix.lower() in RESULT_SUFFIXES or path.name in RESULT_FILENAMES_OVERRIDE:
            destination = results_dir / path.name
            if destination.exists():
                destination = destination.with_name(f"{destination.stem}_{int(time.time())}{destination.suffix}")
            shutil.move(str(path), str(destination))
            moved.append(str(destination))
    return moved


# ---------------------------------------------------------------------------
# V6 native-input adapter
# ---------------------------------------------------------------------------
# The legacy MATLAB modules already have their own native JSON schemas.  STAR's
# orchestration JSON is not passed directly to MATLAB anymore; it is used only
# to locate the active run folders and upstream artifacts.  The runtime JSON
# given to MATLAB starts from the native input template and receives only a
# non-invasive star_runtime metadata block.

import os as _os_v6
import re as _re_v6


def _load_json_relaxed_v6(path: Path) -> dict[str, Any]:
    if not path or not path.exists():
        return {}
    raw = path.read_text(encoding="utf-8-sig", errors="replace")
    try:
        data = json.loads(raw)
    except Exception:
        # Tolerate a few hand-edited JSON files with trailing commas.
        cleaned = _re_v6.sub(r",\s*([}\]])", r"\1", raw)
        data = json.loads(cleaned)
    return data if isinstance(data, dict) else {}


def _template_candidates_v6(
    star_payload: dict[str, Any],
    module_id: str,
    filenames: list[str],
    env_names: list[str],
    module_folder_names: list[str],
) -> list[Path]:
    candidates: list[Path] = []
    for env_name in env_names:
        raw = _os_v6.environ.get(env_name, "").strip()
        if raw:
            candidates.append(Path(raw).expanduser())

    for key in [
        "native_input_file", "template_input_file", "module_native_input_file",
        f"{module_id.lower().replace('-', '_')}_input_file",
    ]:
        raw = star_payload.get(key)
        if raw:
            candidates.append(Path(str(raw)).expanduser())

    root_raw = star_payload.get("star_root") or _os_v6.environ.get("STAR_PROJECT_ROOT", "")
    if root_raw:
        root = Path(str(root_raw)).expanduser()
        for filename in filenames:
            candidates.append(root / "Input" / filename)
            candidates.append(root / "input" / filename)
        for folder in module_folder_names:
            for filename in filenames:
                candidates.append(root / folder / "Input" / filename)
                candidates.append(root / folder / "input" / filename)
                candidates.append(root / folder / filename)

    # Packaged fallback templates copied from the user's previous working input files.
    template_dir = Path(__file__).resolve().parent / "templates"
    for filename in filenames:
        candidates.append(template_dir / filename)

    # Deduplicate preserving order.
    seen: set[str] = set()
    unique: list[Path] = []
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def _load_native_template_v6(
    star_payload: dict[str, Any],
    module_id: str,
    filenames: list[str],
    env_names: list[str],
    module_folder_names: list[str],
) -> tuple[dict[str, Any] | None, Path | None]:
    for candidate in _template_candidates_v6(star_payload, module_id, filenames, env_names, module_folder_names):
        if candidate.exists() and candidate.is_file():
            try:
                return _load_json_relaxed_v6(candidate), candidate
            except Exception:
                continue
    return None, None


def _attach_runtime_metadata_v6(
    data: dict[str, Any],
    star_payload: dict[str, Any],
    module_id: str,
    template_path: Path | None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    # Round-trip copy keeps nested native structures independent of the template.
    out = json.loads(json.dumps(data))
    runtime = out.setdefault("star_runtime", {})
    runtime.update({
        "module_id": module_id,
        "native_template_path": str(template_path) if template_path else None,
        "run_id": star_payload.get("run_id"),
        "star_root": star_payload.get("star_root"),
        "run_output_dir": star_payload.get("run_output_dir"),
        "modules_output_root": star_payload.get("modules_output_root"),
        "module_output_dir": star_payload.get("module_output_dir"),
        "module_product_output_dir": star_payload.get("module_product_output_dir"),
        "module_results_dir": star_payload.get("module_results_dir"),
        "upstream_artifacts": star_payload.get("upstream_artifacts", []),
        "upstream_artifacts_absolute": star_payload.get("upstream_artifacts_absolute", []),
    })
    if extra:
        runtime.update(extra)
    return out


def build_end001_config(star_payload: dict[str, Any]) -> dict[str, Any]:  # type: ignore[override]
    """Return a native END-001 JSON config.

    Prefer the previous working input_constellation_optimizer.json.  The old
    generated adapter is used only as a last-resort fallback and is explicitly
    marked as generated in star_runtime.
    """
    template, template_path = _load_native_template_v6(
        star_payload=star_payload,
        module_id="END-001",
        filenames=["input_constellation_optimizer.json"],
        env_names=["STAR_END001_NATIVE_INPUT", "STAR_END001_TEMPLATE_INPUT", "STAR_INPUT_CONSTELLATION_OPTIMIZER"],
        module_folder_names=["END001-ConstellationOptimizer", "END001-Constellation Optimizer", "END001"],
    )
    if template:
        # STAR mode (2026-10-14, end001_star_inputs.apply_star_mode): the
        # template's native fields, overridden by the STAR inputs that carry
        # mission information and by simple rules on the requirement texts, plus
        # the fixed STAR settings (surrogate engine, 'auto' window, 10 s step,
        # Sun constraint from the sensor). The decisions are listed in
        # star_runtime.end001_inputs.
        try:
            from .end001_star_inputs import apply_star_mode
        except ImportError:   # star_runner_io loaded outside the runners package
            from end001_star_inputs import apply_star_mode
        cfg, report = apply_star_mode(template, star_payload)
        return _attach_runtime_metadata_v6(cfg, star_payload, "END-001", template_path,
                                           {"mode": "STAR", "end001_inputs": report})

    # Emergency fallback only. This path should not be used on the workstation if
    # STAR/Input/input_constellation_optimizer.json exists or the packaged runner
    # templates were installed correctly.
    cfg = globals().get("_build_end001_config_fallback_v6")
    if cfg is None:
        # The previous implementation was overwritten by this definition; rebuild
        # the minimal safe config here rather than creating fake output products.
        lat, lon = target_lat_lon(star_payload)
        start = parse_datetime_like(input_value(star_payload, "simulation_start_date", None))
        try:
            dt = datetime.fromisoformat(start)
        except Exception:
            dt = datetime(2026, 5, 21, 13, 41, 10)
        return _attach_runtime_metadata_v6({
            "TimeSettings": {"StartDate": [dt.year, dt.month, dt.day], "StartHour": dt.hour, "StartMin": dt.minute, "StartSec": dt.second},
            "GroundStations": [{"name": "Matera", "lat": 40.6486, "lon": 16.5528, "alt": 536, "mask": 5}],
            "RegionSettings": {"AreaofInterest": "Italy", "Default_LATkm": 25, "Default_LONkm": 25, "CustomCoordinates": [[lat, lon]]},
            "SensorSettings": {"SAR_Configuration": "Left & Right", "SAR_Theta_min": 15, "SAR_Theta_max": 50, "Optic_Steerable": "Field of View", "Optic_CON_FOV": 15, "Optic_PBS_FOV": 10, "Operative_Mode": "Single Sensor", "Single_Sensor_Type": "PBS", "Sun_Constraint": True},
            "OptimizerSettings": {"Optimizer_Type": "MOGA NSGA-II", "Population": 10, "Iterations": 2, "PlatEMO_Algorithm": "NSGA-III", "Parallelize": True, "Num_Coworkers": 8, "Orbit_Type": "SSORGT", "PropagationDays": 7, "timeStep": 10},
            "Weights": {"MaxRevisitTime": 5, "Percentile90RevisitTime": 10, "NumSatellites": 8, "NumPlanes": 8, "MaxLatency": 5, "Robustness": 6, "CollisionAvoidance": 10, "Launch": 10, "EndOfLife": 8, "AvgGSAccessTime": 9},
        }, star_payload, "END-001", None, {"warning": "native input template not found; generated conservative fallback config"})
    return cfg(star_payload)


def build_end003_config(star_payload: dict[str, Any]) -> dict[str, Any]:  # type: ignore[override]
    """Return a native END-003 JSON config based on input_attitude_propagator.json."""
    template, template_path = _load_native_template_v6(
        star_payload=star_payload,
        module_id="END-003",
        filenames=["input_attitude_propagator.json", "input_attitude_propagation.json"],
        env_names=["STAR_END003_NATIVE_INPUT", "STAR_END003_TEMPLATE_INPUT", "STAR_INPUT_ATTITUDE_PROPAGATOR"],
        module_folder_names=["END003-AttitudePropagation", "END003-Attitude Propagation", "END003_AttitudePropagation", "END003"],
    )
    extra: dict[str, Any] = {}
    end001_csv = first_upstream_file(star_payload, ".csv", ["constellation_optimizer_output"])
    if end001_csv:
        extra["end001_output_csv"] = str(end001_csv)
    if template:
        return _attach_runtime_metadata_v6(template, star_payload, "END-003", template_path, extra)

    # Fall back to the old generated adapter only when no native template exists.
    orbit = read_constellation_first_orbit(star_payload)
    lat, lon = target_lat_lon(star_payload)
    cfg = {
        "sim_start_date": parse_datetime_like(input_value(star_payload, "simulation_start_date", orbit.get("sim_start_date"))),
        "sim_hours": coerce_float(input_value(star_payload, "simulation_duration_hours", orbit.get("sim_hours", 48.0)), 48.0),
        "orbit": {
            "alt_perigee_m": coerce_float(orbit.get("alt_perigee_m"), 550000.0),
            "alt_apogee_m": coerce_float(orbit.get("alt_apogee_m"), 550000.0),
            "inclination_deg": coerce_float(orbit.get("inclination_deg"), 97.6),
            "raan_deg": coerce_float(orbit.get("raan_deg"), 0.0),
            "omega_deg": coerce_float(orbit.get("omega_deg"), 0.0),
            "nu_deg": coerce_float(orbit.get("nu_deg"), 0.0),
        },
        "target": {"site_lat_deg": lat, "site_lon_deg": lon, "elev_threshold": 10.0, "Sun_Constraint": False, "Sun_Constraint_Mode": "none", "Sun_Elevation_Threshold_Deg": -90.0},
        "sat": {"attitude_mode": "nadir", "q0": [0, 0, 0, 1], "w0": [0.00015, 0.0008, 0.0004], "m": 4, "A_ref": 0.03, "Cr": 1.2, "Cd": 2.2, "r_cp": [0.002, 0.002, 0.005], "Ix": 0.03, "Iy": 0.03, "Iz": 0.01},
        "env": {"Re": 6371000, "flags": {"gg": True, "srp": True, "drag": True, "pert": True, "j2": True, "j3": True}},
    }
    return _attach_runtime_metadata_v6(cfg, star_payload, "END-003", None, {**extra, "warning": "native input template not found; generated conservative fallback config"})


def _end003_target_site_v6(end003_csv: Path) -> dict[str, float] | None:
    """Read the ground-site lat/lon END-003 actually computed the pass for.

    END-003 writes end003_runtime_input.json into its module root, one level
    above the output_attitude_propagation/ folder that end003_csv lives in.
    Returns None (never raises) if the file, or the target fields, are
    missing -- callers fall back to the named station in the END-010 template.
    """
    try:
        runtime_input_path = end003_csv.parent.parent / "end003_runtime_input.json"
        if not runtime_input_path.exists():
            return None
        data = json.loads(runtime_input_path.read_text(encoding="utf-8-sig"))
        target = data.get("target") or {}
        lat = target.get("site_lat_deg")
        lon = target.get("site_lon_deg")
        if lat is None or lon is None:
            return None
        return {"lat": float(lat), "lon": float(lon), "alt": float(target.get("site_alt_m", 0) or 0)}
    except Exception:
        return None


def build_end010_config(star_payload: dict[str, Any], product_dir: Path, results_dir: Path, end003_csv: Path | None, star_root: Path, selected_passes: dict[str, Any] | None = None) -> dict[str, Any]:  # type: ignore[override]
    """Return a native END-010 JSON config based on input_reflectance_determination.json.

    Besides paths.inputCsv, this also aligns END-010's observation ground site
    with the one END-003 actually computed the pass for (via
    _end003_target_site_v6). Without this, END-010 evaluates elevation/range
    against whatever named station is hardcoded in the native template (e.g.
    "SCUDO"), which in general has nothing to do with END-003's
    target.site_lat_deg/site_lon_deg -- same orbit segment, unrelated ground
    point, so the reported elevation does not correspond to the actual pass
    (e.g. a legitimate 49 deg peak elevation over the real target read back
    as a negative, below-horizon elevation from the mismatched station).

    When END-003 published selected_passes.json with a light-curve pass, that
    pass wins: END-010 then reads its dedicated ephemeris CSV (a sunlit
    satellite seen at night from the observer, e.g. Matera) and uses the
    observer coordinates END-003 screened the pass for.
    """
    template, template_path = _load_native_template_v6(
        star_payload=star_payload,
        module_id="END-010",
        filenames=["input_reflectance_determination.json"],
        env_names=["STAR_END010_NATIVE_INPUT", "STAR_END010_TEMPLATE_INPUT", "STAR_INPUT_REFLECTANCE_DETERMINATION"],
        module_folder_names=["END010-ReflectanceDetermination", "END010-Reflectance Determination", "END010"],
    )
    if template:
        cfg = json.loads(json.dumps(template))
    else:
        cfg = {
            "paths": {"inputCsv": ""},
            "simulation": {"debug": True, "observatory": "SCUDO", "mask": 10, "delta": 1, "duration": 180, "start": parse_datetime_like(input_value(star_payload, "simulation_start_date", None)).replace(" ", "T")},
            "flags": {"useInputCsv": True, "orbitEphemeris": False, "sunEphemeris": False, "attEphemeris": False, "obsEphemeris": False},
            "unityOpts": {"maxFrameToRender": 10000, "maxFrameToSave": 10000, "camWidth": 512, "camHeight": 512, "camSize": 20, "enableView": False, "saveFrames": True, "sumFlux": True, "useOrtographic": True, "useLinearSpace": True, "drawAxis": False, "UseRadiometricModel": False, "UseFacetSum": False, "lightCurveFilename": "flux.csv", "logFile": "unityLog.log"},
        }
    cfg.setdefault("paths", {})

    # These paths point at files inside the END-010 module installation itself
    # (Unity executable + reference data). They must always be recomputed from
    # star_root rather than trusted verbatim from a packaged/template JSON,
    # which may have been captured on a different machine or STAR install path.
    data_dir = star_root / "END010-ReflectanceDetermination" / "lib" / "data"
    # Unity player: the CubeSat build (unity_project, StarCubeSatBuild) renders the NASA-style CDS model of the class END-019 chose;
    # the old Aqua build is used only if the CubeSat build is not on this machine
    cubesat_exe = star_root / "END010-ReflectanceDetermination" / "lib" / "BuildCubeSat" / "UnityLightCurveInversion.exe"
    aqua_exe = star_root / "END010-ReflectanceDetermination" / "lib" / "BuildAqua" / "UnityLightCurveInversion.exe"
    cfg["paths"]["unityExe"] = str(cubesat_exe if cubesat_exe.exists() or not aqua_exe.exists() else aqua_exe)
    cubesat = end010_cubesat_options(star_payload, product_dir) if cubesat_exe.exists() or not aqua_exe.exists() else None
    if cubesat:
        cfg.setdefault("unityOpts", {}).update(cubesat["unityOpts"])
    cfg["paths"]["eopFile"] = str(data_dir / "EOP.txt")
    cfg["paths"]["tleFile"] = str(data_dir / "TLE_AQUA27052026.txt")
    cfg["paths"]["stationsJson"] = str(data_dir / "stations.json")
    cfg["paths"]["nutData"] = str(star_root / "END010-ReflectanceDetermination" / "lib" / "sgp4" / "nut80.dat")
    cfg["paths"]["deData"] = str(data_dir / "DE440.mat")

    lightcurve_pass = (selected_passes or {}).get("lightcurve_pass") or {}
    lightcurve_csv: Path | None = None
    if lightcurve_pass.get("found") and lightcurve_pass.get("ephemeris_csv"):
        source_path = (selected_passes or {}).get("_source_path")
        candidate = Path(str(source_path)).parent / str(lightcurve_pass["ephemeris_csv"]) if source_path else None
        if candidate is not None and candidate.exists():
            lightcurve_csv = candidate

    if lightcurve_csv is not None:
        cfg["paths"]["inputCsv"] = str(lightcurve_csv)
        cfg.setdefault("flags", {})["useInputCsv"] = True
        observer = lightcurve_pass.get("observer") or {}
        sim = cfg.setdefault("simulation", {})
        if observer.get("site_lat_deg") is not None and observer.get("site_lon_deg") is not None:
            sim["observatoryLat"] = float(observer["site_lat_deg"])
            sim["observatoryLon"] = float(observer["site_lon_deg"])
            sim["observatoryAlt"] = float(observer.get("site_alt_m") or 0.0)
            sim["observatory"] = str(observer.get("name") or "light-curve observer")
    elif end003_csv:
        cfg["paths"]["inputCsv"] = str(end003_csv)
        cfg.setdefault("flags", {})["useInputCsv"] = True

        end003_target = _end003_target_site_v6(end003_csv)
        if end003_target:
            sim = cfg.setdefault("simulation", {})
            sim["observatoryLat"] = end003_target["lat"]
            sim["observatoryLon"] = end003_target["lon"]
            sim["observatoryAlt"] = end003_target["alt"]
            sim["observatory"] = "END-003 target site"

    cfg = _attach_runtime_metadata_v6(cfg, star_payload, "END-010", template_path, {
        "module_product_output_dir": str(product_dir),
        "module_results_dir": str(results_dir),
        "end003_output_csv": str(end003_csv) if end003_csv else None,
        "lightcurve_pass_csv": str(lightcurve_csv) if lightcurve_csv else None,
        "lightcurve_pass": {k: v for k, v in lightcurve_pass.items() if k != "orbit"} if lightcurve_pass else None,
        "cubesat_model": None if not cubesat else {k: v for k, v in cubesat.items() if k != "unityOpts"},
    })
    return cfg


# END-010 CubeSat model (2026-10-16): CDS Rev. 14.1 envelope of the NASA-style models in Input/cubesat_3d_models (X x Y x Z, mm)
CUBESAT_ENVELOPE_MM = {1: (100.0, 100.0, 113.5), 2: (100.0, 100.0, 227.0), 3: (100.0, 100.0, 340.5), 6: (226.3, 100.0, 366.0), 12: (226.3, 226.3, 366.0)}
END010_DEFAULT_CLASS_U = 6
END010_SCENE_SCALE = 100.0      # STAR csv positions are in km: divided by 100 the camera stays thousands of units from a 0.1-0.4 m model


def end010_cubesat_options(star_payload: dict[str, Any], product_dir: Path) -> dict[str, Any]:
    """Unity options for the CubeSat of the run: the class chosen by END-019 when it ran before END-010 (registry: optional upstream),
    otherwise END010_DEFAULT_CLASS_U. camSize (orthographic half-height, m) = half the diagonal of the class envelope x 1.1, so the
    model stays in the frame whatever its attitude; sceneScale divides the km positions of the csv."""
    class_u, source = None, None
    found = find_upstream_artifact(star_payload, ["component_selector_results.json"], [".json"])
    candidates = [found] if found else []
    # modules_output/<END-010>/output_... -> modules_output/END-019/output_component_selector/component_selector_results.json
    for parent in Path(product_dir).resolve().parents:
        if parent.name == "modules_output":
            candidates.append(parent / "END-019" / "output_component_selector" / "component_selector_results.json")
            break
    for path in candidates:
        try:
            data = load_json(Path(path))
            u = int(((data.get("result") or {}).get("cubesat") or {}).get("class_u"))
        except Exception:
            continue
        if u in CUBESAT_ENVELOPE_MM:
            class_u, source = u, f"END-019 of this run ({Path(path).name})"
            break
    if class_u is None:
        class_u, source = END010_DEFAULT_CLASS_U, f"default {END010_DEFAULT_CLASS_U}U (END-019 is not in this run)"
    x, y, z = CUBESAT_ENVELOPE_MM[class_u]
    half_diagonal_m = 0.5 * math.sqrt(x * x + y * y + z * z) / 1000.0
    cam_size = round(1.1 * half_diagonal_m, 4)
    return {"class_u": class_u, "source": source, "model": f"CDS_{class_u}U_nasa_style", "envelope_mm": [x, y, z],
            "unityOpts": {"cubesatClass": class_u, "camSize": cam_size, "sceneScale": END010_SCENE_SCALE}}


# ---------------------------------------------------------------------------
# END-003 pass selection (constellation -> selected satellite/pass)
# ---------------------------------------------------------------------------
SELECTED_PASSES_FILENAME = "selected_passes.json"

# Defaults of the END-003 pass planner. Input/input_attitude_propagator.json may
# override any of them under "pass_selection"; the MATLAB planner has the same
# defaults, so this block only makes the effective configuration visible in
# end003_runtime_input.json.
DEFAULT_PASS_SELECTION: dict[str, Any] = {
    "screening_step_s": 20,
    "imaging": {"preferred_sun_elevation_deg": 20},
    "lightcurve": {
        "enabled": True,
        "observer": {"name": "Matera", "site_lat_deg": 40.6492, "site_lon_deg": 16.7039, "site_alt_m": 400},
        "elev_threshold_deg": 10,
        "elev_margin_deg": 1,
        "observer_sun_elevation_max_deg": -12,
        "require_satellite_sunlit": True,
        "min_duration_s": 120,
        "output_step_s": 10,
        "edge_margin_s": 10,
    },
}


def merge_pass_selection_defaults(configured: Any) -> dict[str, Any]:
    """Deep-merge a (possibly partial) pass_selection block over the defaults."""
    def merge(base: dict[str, Any], override: Any) -> dict[str, Any]:
        result = json.loads(json.dumps(base))
        if isinstance(override, dict):
            for key, value in override.items():
                if isinstance(value, dict) and isinstance(result.get(key), dict):
                    result[key] = merge(result[key], value)
                else:
                    result[key] = value
        return result

    return merge(DEFAULT_PASS_SELECTION, configured)


def load_end001_constellation(end001_csv: Path | str | None) -> tuple[list[dict[str, Any]], str | None]:
    """Read END-001's constellation_optimizer_output.csv (one row per satellite).

    Returns (satellites, epoch). Each satellite carries the Keplerian elements
    END-003 needs; epoch is END-001's sim_start_date ("YYYY-MM-DD HH:MM:SS"),
    which the RAAN/true-anomaly values refer to.
    """
    if not end001_csv:
        return [], None
    path = Path(end001_csv)
    if not path.exists():
        return [], None
    satellites: list[dict[str, Any]] = []
    epoch: str | None = None
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
    except Exception:
        return [], None
    for position, row in enumerate(rows, start=1):
        try:
            satellites.append({
                "satellite_index": int(float(row.get("satellite_index") or position)),
                "source_json": row.get("source_json") or "",
                "alt_perigee_m": float(row["alt_perigee_m"]),
                "alt_apogee_m": float(row["alt_apogee_m"]),
                "inclination_deg": float(row["inclination_deg"]),
                "raan_deg": float(row["raan_deg"]),
                "omega_deg": float(row["omega_deg"]),
                "nu_deg": float(row["nu_deg"]),
            })
        except (KeyError, TypeError, ValueError):
            continue
        epoch = epoch or (row.get("sim_start_date") or "").strip() or None
    return satellites, epoch


def load_selected_passes(
    star_payload: dict[str, Any] | None = None,
    near_csv: Path | str | None = None,
) -> dict[str, Any] | None:
    """Load END-003's selected_passes.json (None if this run does not have it)."""
    candidates: list[Path] = []
    if star_payload:
        found = find_upstream_artifact(star_payload, [SELECTED_PASSES_FILENAME], [".json"])
        if found:
            candidates.append(found)
    if near_csv:
        base = Path(near_csv).parent
        candidates.append(base / SELECTED_PASSES_FILENAME)
        candidates.append(base.parent / "output_attitude_propagation" / SELECTED_PASSES_FILENAME)
    for path in candidates:
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8-sig"))
                if isinstance(data, dict):
                    data["_source_path"] = str(path)
                    return data
        except Exception:
            continue
    return None


def describe_pass(entry: dict[str, Any] | None, site_key: str = "target_site") -> str:
    """One-line, human readable description of an END-003 selected pass."""
    if not entry or not entry.get("found", True):
        return "not available"
    label = entry.get("satellite_label") or f"satellite {entry.get('satellite_index')}"
    place = (entry.get("observer") or {}).get("name") or ("target site" if site_key == "target_site" else site_key)
    sun = entry.get("site_sun_elevation_at_peak_deg", entry.get("observer_sun_elevation_at_peak_deg"))
    sun_text = f" | Sun elevation {float(sun):.1f} deg" if isinstance(sun, (int, float)) else ""
    dur = entry.get("duration_min")
    dur_text = f" | duration {float(dur):.1f} min" if isinstance(dur, (int, float)) else ""
    peak = entry.get("peak_elevation_deg")
    peak_text = f" | peak elevation {float(peak):.1f} deg" if isinstance(peak, (int, float)) else ""
    return f"{label} over {place} | {entry.get('start_utc')} -> {entry.get('end_utc')}{dur_text}{peak_text}{sun_text}"

"""STAR-mode inputs of END-001 (Constellation Optimizer), 2026-10-14.

Inside STAR the MATLAB module runs from its native input JSON: the template
(STAR/Input/input_constellation_optimizer.json) adapted here by
``apply_star_mode``:

1. fixed settings (STAR mode): surrogate fitness engine (END-001 falls back to
   the full simulation by itself, and records why in coverage_summary.json,
   when the scenario is outside the surrogate's training domain), 'auto'
   propagation window (one repeat cycle for Sun-synchronous orbits, a whole
   lighting-drift cycle for inclined ones), 10 s time step, Sun constraint
   from the sensor type (optical yes, SAR no);
2. STAR inputs whose value comes from the mission (requirements document or
   the user), not from the registry defaults, mapped onto the native fields;
3. simple rules on the mission requirement texts: number of satellites and of
   orbital planes, altitude range, orbit family, inclination, sensor type,
   swath, start epoch, spacecraft mass and drag;
4. everything else: the template's values (automatic choice), with the GA
   size limits kept inside the surrogate's training domain.

Priority: STAR input > requirement text > template. Every decision is listed
in the report (star_runtime.end001_inputs). Standalone MATLAB runs do not go
through this file: there every native field stays under the user's control.
"""
from __future__ import annotations

import json
import math
import re
from typing import Any

# Sources of resolved_inputs that are NOT mission information: registry
# defaults the planner proposes when nothing was said about the parameter.
REGISTRY_SOURCES = {"module_registry_default", "module_registry_required_input"}

# Areas END-001's ROI_2 knows by name (RegionSettings.AreaofInterest).
NAMED_AREAS = ["Italy and Med", "Italian Coasts", "Mediterranean Area", "Mediterranean", "Europe (High Lat)",
               "Europe", "Italy", "Qatar", "Malaysia", "Artic"]

# Point targets the STAR planner names (FrontEnd star_frontend_v2.py), same
# coordinates as star_runner_io.target_lat_lon.
POINT_TARGETS = {"etna": (37.748, 14.999)}

# Surrogate training domain (END-001 surrogate_training_domain.m / USAGE.md section 5).
SSO_DOMAIN = {"planes": [3, 10], "sats": [2, 10], "total": [6, 100], "alt_km": [400, 1200]}
DELTA_DOMAIN = {"planes": [2, 10], "sats": [1, 10], "total": [2, 100], "alt_km": [400, 1200],
                "incl_deg": [35, 75], "kday": [1, 35]}

MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                      "september", "october", "november", "december"], start=1)}
NUM = r"(\d+(?:\.\d+)?)"


def _parse(value: Any) -> Any:
    """Parsed STAR value; None for empty / placeholder text."""
    if value is None:
        return None
    if isinstance(value, (dict, list, int, float, bool)):
        return value
    text = str(value).strip()
    if not text or text == "-" or text.lower().startswith(("tbd", "n/a", "none", "unknown")):
        return None
    try:
        return json.loads(text)
    except Exception:
        return text


def provided_inputs(payload: dict[str, Any]) -> dict[str, tuple[Any, str]]:
    """STAR inputs carrying mission information: {parameter: (value, source)}."""
    out: dict[str, tuple[Any, str]] = {}
    for item in payload.get("resolved_inputs", []) or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("parameter", "")).strip()
        source = str(item.get("source", "")).strip()
        value = _parse(item.get("proposed_value"))
        if name and value is not None and source not in REGISTRY_SOURCES:
            out[name] = (value, source or "star_input")
    return out


def _requirements(payload: dict[str, Any]) -> list[tuple[str, str]]:
    reqs = []
    for r in payload.get("requirements", []) or []:
        if isinstance(r, dict) and r.get("text"):
            reqs.append((str(r.get("id", "REQ")), str(r["text"])))
    return reqs


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def _area(value: Any) -> tuple[dict[str, Any] | None, str]:
    """RegionSettings update for an area_of_interest value, and a note."""
    if isinstance(value, dict):
        lat = value.get("lat", value.get("latitude"))
        lon = value.get("lon", value.get("longitude"))
        if _number(lat) is not None and _number(lon) is not None:
            value = [[float(lat), float(lon)]]
        elif isinstance(value.get("coordinates"), list):
            value = value["coordinates"]
    if isinstance(value, list) and value and all(isinstance(p, (list, tuple)) and len(p) >= 2 for p in value):
        pts = [[float(p[0]), float(p[1])] for p in value]
        if len(pts) == 1:   # a point target: a 1 x 1 deg square around it
            lat, lon = pts[0]
            pts = [[lat - 0.5, lon - 0.5], [lat - 0.5, lon + 0.5], [lat + 0.5, lon + 0.5], [lat + 0.5, lon - 0.5]]
            return {"AreaofInterest": "Custom", "CustomCoordinates": pts}, "point target: 1 x 1 deg square around it"
        if len(pts) >= 3:
            return {"AreaofInterest": "Custom", "CustomCoordinates": pts}, "polygon [lat, lon]"
    if isinstance(value, str):
        low = value.lower()
        for name in NAMED_AREAS:   # longest names first
            if name.lower() in low:
                return {"AreaofInterest": name}, f"named area '{name}'"
        for place, (lat, lon) in POINT_TARGETS.items():
            if place in low:
                upd, _ = _area([[lat, lon]])
                return upd, f"'{place}' ({lat}, {lon}): 1 x 1 deg square around it"
    return None, f"not a known area name or [lat, lon] list: {value!r}"


def _fov_from_swath(swath_km: float, alt_km: float) -> float:
    return math.degrees(2 * math.atan(swath_km / 2 / alt_km))


def apply_star_mode(cfg: dict[str, Any], payload: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Adapt the native END-001 config to the STAR run; returns (config, report)."""
    cfg = json.loads(json.dumps(cfg))
    opt = cfg.setdefault("OptimizerSettings", {})
    sens = cfg.setdefault("SensorSettings", {})
    report: list[dict[str, Any]] = []

    def note(field: str, value: Any, origin: str) -> None:
        report.append({"field": field, "value": value, "origin": origin})

    inp = provided_inputs(payload)
    reqs = _requirements(payload)

    # ---- orbit family -------------------------------------------------------
    orbit, orbitOrigin, single = None, "", False
    ctype = inp.get("constellation_type")
    if ctype:
        t = str(ctype[0]).lower()
        if "delta" in t:
            orbit = "RGT (generally inclined)"
        elif "star" in t or "single" in t or "train" in t:
            orbit = "SSORGT"
        single = "single" in t
        if orbit:
            orbitOrigin = f"STAR input constellation_type = {ctype[0]} ({ctype[1]})"
    for rid, text in reqs:
        low = text.lower()
        if orbit is None and re.search(r"sun[- ]synchronous|\bsso\b", low):
            orbit, orbitOrigin = "SSORGT", f"requirement {rid} (Sun-synchronous)"
        elif orbit is None and re.search(r"walker[- ]delta|inclined orbit", low):
            orbit, orbitOrigin = "RGT (generally inclined)", f"requirement {rid} (inclined / Walker delta)"
    if orbit:
        opt["Orbit_Type"] = orbit
        note("OptimizerSettings.Orbit_Type", orbit, orbitOrigin)
    else:
        note("OptimizerSettings.Orbit_Type", opt.get("Orbit_Type"), "automatic (template)")
    orbit = opt.get("Orbit_Type", "SSORGT")
    delta = orbit == "RGT (generally inclined)"

    # ---- requirement texts --------------------------------------------------
    found: dict[str, tuple[Any, str]] = {}
    for rid, text in reqs:
        low = text.lower().replace("–", "-")
        m = re.search(r"(?:at most|no more than|not more than|a maximum of|maximum of|up to)\s+(\d+)\s+satellites", low)
        if m and "sats_max" not in found:
            found["sats_max"] = (int(m.group(1)), rid)
        m = re.search(r"(?:at least|a minimum of|minimum of|no fewer than)\s+(\d+)\s+satellites", low)
        if m and "sats_min" not in found:
            found["sats_min"] = (int(m.group(1)), rid)
        m = re.search(r"\b(\d+)\s+(?:orbital\s+)?planes\b", low)
        if m and "planes" not in found:
            found["planes"] = (int(m.group(1)), rid)
        if re.search(r"altitude|orbit|height", low) and "alt" not in found:
            m = re.search(r"between\s+" + NUM + r"\s*(?:km)?\s+and\s+" + NUM + r"\s*km", low) or \
                re.search(NUM + r"\s*(?:-|to)\s*" + NUM + r"\s*km", low)
            if m:
                found["alt"] = ([float(m.group(1)), float(m.group(2))], rid)
            else:
                m = re.search(r"(?:altitude|height) of\s+" + NUM + r"\s*km", low)
                if m:
                    h = float(m.group(1))
                    found["alt"] = ([h - 25, h + 25], rid)
        m = re.search(r"inclination of\s+" + NUM + r"\s*(?:deg|degrees|°)", low)
        if m and "incl" not in found:
            found["incl"] = (float(m.group(1)), rid)
        if "sensor" not in found:
            if re.search(r"push[- ]?broom", low):
                found["sensor"] = ("PBS", rid)
            elif re.search(r"synthetic aperture|\bsar\b", low):
                found["sensor"] = ("SAR", rid)
            elif re.search(r"fram(?:e|ing) camera|area camera|matrix camera", low):
                found["sensor"] = ("RECT", rid)
        m = re.search(r"swath(?: width)? of\s+" + NUM + r"\s*km", low)
        if m and "swath" not in found:
            found["swath"] = (float(m.group(1)), rid)
        m = re.search(r"start(?:ing|s)? on\s+(\d{1,2})\s+([a-z]+)\s+(\d{4})(?:\s+at\s+(\d{1,2}):(\d{2}))?", low)
        if m and m.group(2) in MONTHS and "start" not in found:
            found["start"] = ([int(m.group(3)), MONTHS[m.group(2)], int(m.group(1)),
                               int(m.group(4) or 0), int(m.group(5) or 0)], rid)
        m = re.search(r"mass\s+(?:not exceeding|of|below|up to|lower than|less than)\s+" + NUM + r"\s*kg", low)
        if m and "mass" not in found:
            found["mass"] = (float(m.group(1)), rid)
        m = re.search(r"drag (?:cross[- ]section|area) of\s+" + NUM + r"\s*m", low)
        if m and "adrag" not in found:
            found["adrag"] = (float(m.group(1)), rid)
        m = re.search(r"drag coefficient of\s+" + NUM, low)
        if m and "cd" not in found:
            found["cd"] = (float(m.group(1)), rid)

    # ---- sensor ------------------------------------------------------------
    sarIn = [n for n in ("sar_frequency", "sar_field_of_regard_deg") if n in inp]
    if sarIn:
        sens["Single_Sensor_Type"] = "SAR"
        note("SensorSettings.Single_Sensor_Type", "SAR", f"STAR input {', '.join(sarIn)}")
        fr = inp.get("sar_field_of_regard_deg")
        if fr and isinstance(fr[0], list) and len(fr[0]) == 2:
            sens["SAR_Theta_min"], sens["SAR_Theta_max"] = float(fr[0][0]), float(fr[0][1])
            note("SensorSettings.SAR_Theta_min/max", fr[0], f"STAR input sar_field_of_regard_deg ({fr[1]})")
    elif "sensor" in found:
        sens["Single_Sensor_Type"] = found["sensor"][0]
        note("SensorSettings.Single_Sensor_Type", found["sensor"][0], f"requirement {found['sensor'][1]}")
    else:
        note("SensorSettings.Single_Sensor_Type", sens.get("Single_Sensor_Type"), "automatic (template)")
    sens["Operative_Mode"] = "Single Sensor"
    sar = sens.get("Single_Sensor_Type") == "SAR"
    sens["Sun_Constraint"] = not sar
    note("SensorSettings.Sun_Constraint", not sar, "fixed (STAR mode): optical sensors image in daylight, SAR does not need it")

    # ---- altitude, satellites, planes, inclination: GA limits ----------------
    dom = DELTA_DOMAIN if delta else SSO_DOMAIN
    pre = "RGT_" if delta else "SSORGT_"
    alt = list(dom["alt_km"])
    if "alt" in found:
        a = found["alt"][0]
        alt = [max(dom["alt_km"][0], min(a)), min(dom["alt_km"][1], max(a))]
        if alt[0] > alt[1]:
            alt = list(dom["alt_km"])
            note(pre + "AltitudeRange_km", alt, f"requirement {found['alt'][1]} outside 400-1200 km: full range")
        else:
            note(pre + "AltitudeRange_km", alt, f"requirement {found['alt'][1]}")
    else:
        note(pre + "AltitudeRange_km", alt, "automatic (whole orbit table / surrogate domain)")
    opt[pre + "AltitudeRange_km"] = alt

    planes, sats, total = list(dom["planes"]), list(dom["sats"]), list(dom["total"])
    origin = "automatic (surrogate training domain)"
    if single:
        planes, sats, total = [1, 1], [1, 1], [1, 1]
        origin = "STAR input constellation_type = single_satellite"
    else:
        if "sats_max" in found:
            n = found["sats_max"][0]
            total[1] = min(total[1], n)
            origin = f"requirement {found['sats_max'][1]} (at most {n} satellites)"
        if "sats_min" in found:
            total[0] = max(total[0], found["sats_min"][0])
            origin += f"; requirement {found['sats_min'][1]} (at least {found['sats_min'][0]})"
        if "planes" in found:
            planes = [found["planes"][0]] * 2
            origin += f"; requirement {found['planes'][1]} ({found['planes'][0]} planes)"
        if total[0] > total[1]:   # outside the surrogate domain: the requirement wins
            total[0] = 1
            planes[0], sats[0] = 1, 1
            origin += " (below the surrogate domain: END-001 will simulate)"
        planes[1] = min(planes[1], total[1]); sats[1] = min(sats[1], total[1])
    opt[pre + "PlanesRange"], opt[pre + "SatsPerPlaneRange"], opt[pre + "TotalSatellitesRange"] = planes, sats, total
    note(pre + "Planes / SatsPerPlane / TotalSatellites ranges", [planes, sats, total], origin)
    if delta:
        incl = list(dom["incl_deg"])
        if "incl" in found:
            incl = [found["incl"][0]] * 2
            note("RGT_InclinationRange_deg", incl, f"requirement {found['incl'][1]}")
        else:
            note("RGT_InclinationRange_deg", incl, "automatic (surrogate domain)")
        opt["RGT_InclinationRange_deg"] = incl
        opt["RGT_RepeatCycleRange_days"] = list(dom["kday"])

    # ---- field of view ------------------------------------------------------
    fov = inp.get("optical_field_of_view_deg")
    if fov and _number(fov[0]) is not None:
        f = float(fov[0])
        sens["Optic_PBS_FOV"] = sens["Optic_CON_FOV"] = sens["Optic_RECT_FOV_cross"] = f
        note("SensorSettings optical FOV (PBS / CON / RECT cross)", f, f"STAR input optical_field_of_view_deg ({fov[1]})")
    elif "swath" in found:
        h = sum(alt) / 2
        f = round(_fov_from_swath(found["swath"][0], h), 4)
        sens["Optic_PBS_FOV"] = sens["Optic_CON_FOV"] = sens["Optic_RECT_FOV_cross"] = f
        note("SensorSettings optical FOV (PBS / CON / RECT cross)", f,
             f"requirement {found['swath'][1]}: swath {found['swath'][0]} km at {h:.0f} km (mid altitude)")
    for name, field in (("optic_rect_fov_cross_deg", "Optic_RECT_FOV_cross"), ("optic_rect_fov_along_deg", "Optic_RECT_FOV_along")):
        if name in inp and _number(inp[name][0]) is not None:
            sens[field] = float(inp[name][0])
            note("SensorSettings." + field, sens[field], f"STAR input {name} ({inp[name][1]})")

    # ---- area of interest -----------------------------------------------------
    aoi = inp.get("area_of_interest")
    if aoi:
        upd, why = _area(aoi[0])
        if upd:
            cfg.setdefault("RegionSettings", {}).update(upd)
            note("RegionSettings", upd, f"STAR input area_of_interest ({aoi[1]}): {why}")
        else:
            note("RegionSettings.AreaofInterest", cfg.get("RegionSettings", {}).get("AreaofInterest"), f"automatic (template): {why}")
    else:
        note("RegionSettings.AreaofInterest", cfg.get("RegionSettings", {}).get("AreaofInterest"), "automatic (template)")

    # ---- epoch, spacecraft, evaluation -----------------------------------------
    start = inp.get("simulation_start_date")
    if start and isinstance(start[0], str) and re.match(r"\d{4}-\d{2}-\d{2}", start[0]):
        s = start[0].replace("T", " ").replace("Z", "")
        d, _, tm = s.partition(" ")
        y, mo, da = (int(v) for v in d.split("-"))
        hh, mi, ss = ([int(float(v)) for v in (tm.split(":") + ["0", "0", "0"])[:3]] if tm else [0, 0, 0])
        cfg["TimeSettings"] = {"StartDate": [y, mo, da], "StartHour": hh, "StartMin": mi, "StartSec": ss}
        note("TimeSettings", cfg["TimeSettings"], f"STAR input simulation_start_date ({start[1]})")
    elif "start" in found:
        y, mo, da, hh, mi = found["start"][0]
        cfg["TimeSettings"] = {"StartDate": [y, mo, da], "StartHour": hh, "StartMin": mi, "StartSec": 0}
        note("TimeSettings", cfg["TimeSettings"], f"requirement {found['start'][1]}")
    else:
        note("TimeSettings", cfg.get("TimeSettings"), "automatic (template)")
    sc = cfg.setdefault("SpacecraftProperties", {})
    for name, key, field in (("spacecraft_mass_kg", "mass", "Mass"), ("spacecraft_drag_area_m2", "adrag", "ADrag"),
                             ("spacecraft_drag_coefficient", "cd", "CD")):
        if name in inp and _number(inp[name][0]) is not None:
            sc[field] = float(inp[name][0]); note("SpacecraftProperties." + field, sc[field], f"STAR input {name} ({inp[name][1]})")
        elif key in found:
            sc[field] = found[key][0]; note("SpacecraftProperties." + field, sc[field], f"requirement {found[key][1]}")
    for name, field in (("evaluation_mode", "Evaluation_Mode"), ("surrogate_verify_top_k", "Surrogate_VerifyTopK"),
                        ("complete_eval_table_coverage", "CompleteEval_TableCoverage"), ("complete_eval_row_stride", "CompleteEval_RowStride"),
                        ("complete_eval_planes_list", "CompleteEval_PlanesList"), ("complete_eval_sats_per_plane", "CompleteEval_SatsPerPlane")):
        if name in inp:
            opt[field] = inp[name][0]; note("OptimizerSettings." + field, opt[field], f"STAR input {name} ({inp[name][1]})")
    pert = inp.get("perturbations")
    if pert and any(str(p).lower() not in ("j2", "none") for p in (pert[0] if isinstance(pert[0], list) else [pert[0]])):
        note("perturbations", pert[0], "END-001 propagates with J2 only: other perturbations are not modelled")

    # ---- fixed settings (STAR mode) ---------------------------------------------
    opt["Fitness_Engine"] = "Surrogate"
    note("OptimizerSettings.Fitness_Engine", "Surrogate",
         "fixed (STAR mode); END-001 falls back to the simulation outside the surrogate domain and records why")
    opt["PropagationDays"] = "auto"
    note("OptimizerSettings.PropagationDays", "auto",
         "fixed (STAR mode): one repeat cycle (Sun-synchronous) or a whole lighting-drift cycle (inclined orbits)")
    if "propagation_time" in inp:
        note("propagation_time", inp["propagation_time"][0], "ignored: the module chooses the steady-state window ('auto')")
    opt["timeStep"] = 10
    note("OptimizerSettings.timeStep", 10, "fixed (STAR mode)")
    return cfg, report

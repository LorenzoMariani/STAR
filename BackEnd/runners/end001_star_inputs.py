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
   swath, start epoch, spacecraft mass and drag; with no orbit family in the
   call Orbit_Type is "Auto" (END-001 optimises a Sun-synchronous and a Walker
   delta constellation and keeps the better one), with no revisit the revisit
   thresholds are "auto" (from what the design space achieves), 2026-10-18;
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
from pathlib import Path
from typing import Any

# Sources of resolved_inputs that are NOT mission information: registry
# defaults the planner proposes when nothing was said about the parameter.
REGISTRY_SOURCES = {"module_registry_default", "module_registry_required_input"}

# Areas END-001's ROI_2 knows by name (RegionSettings.AreaofInterest).
NAMED_AREAS = ["Italy and Med", "Italian Coasts", "Mediterranean Area", "Mediterranean", "Europe (High Lat)",
               "Europe", "Italy", "Qatar", "Malaysia", "Artic"]

# Point targets the STAR planner names (FrontEnd star_frontend_v5.py), same
# coordinates as star_runner_io.target_lat_lon.
POINT_TARGETS = {"etna": (37.748, 14.999)}

# Surrogate training domain (END-001 surrogate_training_domain.m / USAGE.md section 5).
SSO_DOMAIN = {"planes": [3, 10], "sats": [2, 10], "total": [6, 100], "alt_km": [400, 1200]}
DELTA_DOMAIN = {"planes": [2, 10], "sats": [1, 10], "total": [2, 100], "alt_km": [400, 1200],
                "incl_deg": [35, 75], "kday": [1, 35]}

MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                      "september", "october", "november", "december"], start=1)}
NUM = r"(\d+(?:\.\d+)?)"

# GA sizes per STAR run mode (star_runner_io.star_run_mode / star_run_level).
# Surrogate_* apply when the surrogate fitness engine is used (population x
# generations x restarts, then the best VerifyTopK designs re-simulated);
# Population / Iterations when END-001 falls back to the simulation (scenario
# outside the surrogate domain). Full level 3 = the template
# (Input/input_constellation_optimizer.json); more search lowers the chance of
# missing the best design the simulation would confirm.
END001_TEST_PROFILE: dict[str, Any] = {"Surrogate_Population": 20, "Surrogate_Iterations": 5, "Surrogate_Restarts": 1,
                                       "Surrogate_VerifyTopK": 1, "Population": 8, "Iterations": 1, "Parallelize": False}
END001_FULL_LEVELS: dict[int, dict[str, Any]] = {
    1: {"Surrogate_Population": 60, "Surrogate_Iterations": 40, "Surrogate_Restarts": 1, "Surrogate_VerifyTopK": 10,
        "Population": 24, "Iterations": 2, "Parallelize": True},
    2: {"Surrogate_Population": 80, "Surrogate_Iterations": 60, "Surrogate_Restarts": 2, "Surrogate_VerifyTopK": 20,
        "Population": 36, "Iterations": 3, "Parallelize": True},
    3: {"Surrogate_Population": 100, "Surrogate_Iterations": 100, "Surrogate_Restarts": 3, "Surrogate_VerifyTopK": 30,
        "Population": 50, "Iterations": 3, "Parallelize": True},
    4: {"Surrogate_Population": 150, "Surrogate_Iterations": 120, "Surrogate_Restarts": 4, "Surrogate_VerifyTopK": 50,
        "Population": 64, "Iterations": 4, "Parallelize": True},
    5: {"Surrogate_Population": 200, "Surrogate_Iterations": 150, "Surrogate_Restarts": 6, "Surrogate_VerifyTopK": 80,
        "Population": 80, "Iterations": 6, "Parallelize": True},
}
# Measured 2026-10-15 (8 workers; wall time of END-001 -> selected design re-simulated, weighted score, lower = better):
#   up to 60 satellites, 400-1200 km: test 52 s -> 0.4616; full 1 94 s -> 0.4316; 2 168 s -> 0.4316; 3 325 s -> 0.4319;
#     4 472 s -> 0.4317; 5 651 s -> 0.4316 (all levels: 3 x 2 at 1200 km); the GA time is ~0.65-0.85 s per generation
#     (generations x restarts), almost independent of the population, plus ~65 s fixed
#   v6 proposal (6U, <= 12 satellites, 500-650 km): full 3 309 s, full 1 ~90 s, test ~50 s, all the same design
#   simulation fallback (v5 proposal, swath 12 km outside the surrogate domain): full 3 96 s, full 1 72 s, test 50 s


def end001_run_profile(mode: str, level: int) -> dict[str, Any]:
    """GA sizes of END-001 for a STAR run mode and full accuracy level."""
    return dict(END001_TEST_PROFILE) if mode != "full" else dict(END001_FULL_LEVELS[level])


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
        try:   # Italian regions, cities and sites (config/italy_places.json), or coordinates in the text
            from . import star_text_rules as rules
        except ImportError:
            import star_text_rules as rules
        named = rules.area_of_interest([value])
        if named["region_settings"]:
            return named["region_settings"], named["why"]
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

    # ---- requirement texts (2026-10-17: shared English / Italian parsers, runners/star_text_rules.py) -----------
    try:
        from . import star_text_rules as rules
    except ImportError:
        import star_text_rules as rules
    found: dict[str, tuple[Any, str]] = dict(rules.mission_parameters(reqs))
    if "alt" in found:
        lo, hi = found["alt"][0]
        if lo is not None and hi is not None and lo == hi:     # a single altitude: a 50 km window around it
            lo, hi = lo - 25, hi + 25
        found["alt"] = ([lo if lo is not None else 400.0, hi if hi is not None else 1200.0], found["alt"][1])
    if "mass" in found:
        found["mass"] = (found["mass"][0][0], found["mass"][1])

    # ---- orbit family -------------------------------------------------------
    orbit, orbitOrigin, single, singleOrigin = None, "", False, ""
    ctype = inp.get("constellation_type")
    if ctype:
        t = str(ctype[0]).lower()
        if "delta" in t:
            orbit = "RGT (generally inclined)"
        elif "star" in t or "single" in t or "train" in t:
            orbit = "SSORGT"
        single = "single" in t
        if single:
            singleOrigin = f"STAR input constellation_type = {ctype[0]} ({ctype[1]})"
        if orbit:
            orbitOrigin = f"STAR input constellation_type = {ctype[0]} ({ctype[1]})"
    if orbit is None and "orbit" in found:
        orbit = found["orbit"][0]
        orbitOrigin = f"requirement {found['orbit'][1]} (" + ("Sun-synchronous" if orbit == "SSORGT" else
                                                              "inclined / Walker delta or a non Sun-synchronous inclination") + ")"
    if not single and "single" in found:
        single, singleOrigin = True, f"requirement {found['single'][1]}"
    if not single and payload.get("mission_request_text"):
        # a single satellite stated in the mission request but lost when the requirements were rephrased (LLM extraction)
        doc = rules.mission_parameters([("mission request", s) for s in rules.sentences(str(payload["mission_request_text"]))])
        if "single" in doc and "sats_max" not in found and "sats_min" not in found:
            single, singleOrigin = True, "mission request (a single satellite)"
    if orbit:
        opt["Orbit_Type"] = orbit
        note("OptimizerSettings.Orbit_Type", orbit, orbitOrigin)
    else:
        # 2026-10-18 (user): the orbit type is END-001's choice when the call does not name it
        opt["Orbit_Type"] = orbit = "Auto"
        note("OptimizerSettings.Orbit_Type", "Auto", "automatic: the call names no orbit type; END-001 optimises a Sun-synchronous "
             "and a Walker delta constellation and keeps the one with the better simulated weighted score")
    families = ["SSORGT", "RGT (generally inclined)"] if orbit == "Auto" else [orbit]

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
    # one set of limits per orbit family END-001 searches (both with Orbit_Type "Auto")
    outside_by_family: dict[str, list[str]] = {}
    for fam in families:
        delta = fam == "RGT (generally inclined)"
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

        # The requirements win over the surrogate training domain (2026-10-17): a range reaching outside it is
        # searched with the simulation (slower, never an extrapolated surrogate value); without requirements the
        # ranges are the domain itself.
        planes, sats, total = list(dom["planes"]), list(dom["sats"]), list(dom["total"])
        origin = "automatic (surrogate training domain)"
        if single:
            planes, sats, total = [1, 1], [1, 1], [1, 1]
            origin = "single satellite (" + (singleOrigin or "STAR input constellation_type") + ")"
        else:
            parts = []
            if "sats_max" in found:
                n = found["sats_max"][0]
                total[1] = min(total[1], n)
                parts.append(f"requirement {found['sats_max'][1]} (at most {n} satellites)")
            if "sats_min" in found:
                total[0] = found["sats_min"][0]
                parts.append(f"requirement {found['sats_min'][1]} (at least {found['sats_min'][0]})")
            elif total[0] > total[1]:
                total[0] = 1                     # "at most N" below the domain minimum, no minimum given
            if "planes" in found:
                planes = [found["planes"][0]] * 2
                parts.append(f"requirement {found['planes'][1]} ({found['planes'][0]} planes)")
            if total[0] < planes[0] * sats[0]:   # smaller constellations than the domain minimum are allowed
                sats[0] = 1
                if "planes" not in found:
                    planes[0] = 1
            planes[1] = max(planes[0], min(planes[1], total[1])); sats[1] = max(sats[0], min(sats[1], total[1]))
            if parts:
                origin = "; ".join(parts)
        outside = []
        if planes[0] < dom["planes"][0] or planes[1] > dom["planes"][1]:
            outside.append(f"planes {planes[0]}-{planes[1]} (trained {dom['planes'][0]}-{dom['planes'][1]})")
        if sats[0] < dom["sats"][0] or sats[1] > dom["sats"][1]:
            outside.append(f"satellites per plane {sats[0]}-{sats[1]} (trained {dom['sats'][0]}-{dom['sats'][1]})")
        if outside and not single and "sats_min" not in found:
            # simulated anyway: the domain minimum is not a requirement, smaller compliant constellations are searched too
            total[0], sats[0] = 1, 1
            if "planes" not in found:
                planes[0] = 1
        opt[pre + "PlanesRange"], opt[pre + "SatsPerPlaneRange"], opt[pre + "TotalSatellitesRange"] = planes, sats, total
        note(pre + "Planes / SatsPerPlane / TotalSatellites ranges", [planes, sats, total], origin)
        if delta:
            incl = list(dom["incl_deg"])
            if "incl" in found:
                incl = [found["incl"][0]] * 2
                note("RGT_InclinationRange_deg", incl, f"requirement {found['incl'][1]}")
                if incl[0] < dom["incl_deg"][0] or incl[1] > dom["incl_deg"][1]:
                    outside.append(f"inclination {incl[0]:g} deg (trained {dom['incl_deg'][0]}-{dom['incl_deg'][1]} deg)")
            else:
                note("RGT_InclinationRange_deg", incl, "automatic (surrogate domain): the outer range of the search")
            opt["RGT_InclinationRange_deg"] = incl
            # 2026-10-18: with no inclination in the call END-001 searches only the inclinations compatible with the area of
            # interest (farthest AOI latitude minus the sensor reach, up to 20 deg above it; aoi_inclination_range.m)
            opt["RGT_InclinationFromAOI"] = "incl" not in found
            if "incl" not in found:
                note("RGT_InclinationFromAOI", True, "automatic: END-001 narrows the Walker delta inclinations to the latitudes of "
                     "the area of interest (from its farthest site minus the sensor reach to 20 deg above it)")
            opt["RGT_RepeatCycleRange_days"] = list(dom["kday"])
        outside_by_family[fam] = outside

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
    # STAR input first, else the Italian area the requirements or the mission request name (2026-10-17), else the
    # template (the whole of Italy: the STAR domain check has already stopped requests outside Italy)
    aoi = inp.get("area_of_interest")
    upd, why = _area(aoi[0]) if aoi else (None, "")
    if upd:
        cfg.setdefault("RegionSettings", {}).update(upd)
        note("RegionSettings", upd, f"STAR input area_of_interest ({aoi[1]}): {why}")
    else:
        named = rules.area_of_interest([t for _, t in reqs] + [str(payload.get("mission_request_text") or "")])
        if named["region_settings"]:
            cfg.setdefault("RegionSettings", {}).update(named["region_settings"])
            note("RegionSettings", named["region_settings"], f"requirements / mission request: {named['why']}"
                 + (f" (STAR input area_of_interest not usable: {why})" if aoi else ""))
        else:
            note("RegionSettings.AreaofInterest", cfg.get("RegionSettings", {}).get("AreaofInterest"),
                 "automatic (template): the request names no Italian area" + (f"; STAR input not usable: {why}" if aoi else ""))

    # ---- requirement thresholds (2026-10-17): the revisit / latency the call states drive the optimiser ------------
    # "ok" = the call value, "bad" = twice it (user rule). A revisit metric the call does not give follows a stated
    # one that bounds it (mean <= 90th percentile <= maximum), else its weight is 0: it does not drive the design.
    mreq = cfg.setdefault("MissionRequirements", {})
    weights = cfg.setdefault("Weights", {})
    keys = [("revisit_mean_h", "MeanRevisit_h", "MeanRevisitTime"), ("revisit_p90_h", "P90Revisit_h", "Percentile90RevisitTime"),
            ("revisit_max_h", "MaxRevisit_h", "MaxRevisitTime")]
    given = {k: found[k] for k, _, _ in keys if k in found and found[k][0]}
    for k, field, wkey in keys:
        if k in given:
            v, rid = given[k]
            mreq[field] = [round(v, 4), round(2 * v, 4)]
            note(f"MissionRequirements.{field}", mreq[field], f"requirement {rid}: {v:g} h ok, {2 * v:g} h (twice) bad")
    if given:
        order = [k for k, _, _ in keys]
        for i, (k, field, wkey) in enumerate(keys):
            if k in given:
                continue
            bound = next((order[j] for j in range(i + 1, len(order)) if order[j] in given), None)
            if bound:
                bf = dict((kk, ff) for kk, ff, _ in keys)[bound]
                mreq[field] = list(mreq[bf])
                note(f"MissionRequirements.{field}", mreq[field], f"not in the call: the thresholds of {bf} (stated, and always larger)")
            else:
                weights[wkey] = 0
                note(f"Weights.{wkey}", 0, "not in the call and not bounded by a stated revisit: it does not drive the design")
    else:
        # 2026-10-18: never the template's fixed hours (5.5-6 h max revisit is impossible imaging only in daylight, and
        # thresholds no design reaches make every design score the same, so the GA just minimised the satellites)
        for _, field, _ in keys:
            mreq[field] = "auto"
        note("MissionRequirements (revisit)", "auto",
             "automatic: the call states no revisit; END-001 takes the thresholds from what the design space achieves "
             "(ok = 2nd percentile, bad = 90th percentile of the feasible designs), so the revisit objectives never saturate")
    if "latency_h" in found and found["latency_h"][0]:
        v, rid = found["latency_h"]
        mreq["MaxLatency_h"] = [round(v, 4), round(2 * v, 4)]
        note("MissionRequirements.MaxLatency_h", mreq["MaxLatency_h"], f"requirement {rid}: {v:g} h ok, {2 * v:g} h (twice) bad")
    else:
        note("MissionRequirements.MaxLatency_h", mreq.get("MaxLatency_h"), "automatic (template): the call states no latency")

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
    # the satellite of the END-006 initial design (2026-10-17): the same mass, area and Cd for every module
    try:
        from .star_runner_io import load_spacecraft_definition
    except ImportError:
        from star_runner_io import load_spacecraft_definition
    sat = load_spacecraft_definition(payload)
    sat_vals = {"mass": sat["mass_kg"], "adrag": sat["area_mean_projected_m2"], "cd": sat["cd"]} if sat else {}
    for name, key, field in (("spacecraft_mass_kg", "mass", "Mass"), ("spacecraft_drag_area_m2", "adrag", "ADrag"),
                             ("spacecraft_drag_coefficient", "cd", "CD")):
        if name in inp and _number(inp[name][0]) is not None:
            sc[field] = float(inp[name][0]); note("SpacecraftProperties." + field, sc[field], f"STAR input {name} ({inp[name][1]})")
        elif key in sat_vals:
            sc[field] = round(float(sat_vals[key]), 6)
            note("SpacecraftProperties." + field, sc[field], f"END-006 initial design ({sat.get('form_factor')}, spacecraft_definition.json)")
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

    # ---- ground stations (2026-10-17): Italian stations, never the template one by default ------------------------
    try:
        from . import star_ground_stations as gsl
    except ImportError:
        import star_ground_stations as gsl
    texts = [t for _, t in reqs] + [str(payload.get("mission_request_text") or "")]
    gs_in = inp.get("ground_stations")
    chosen, gs_origin = [], ""
    if gs_in:
        chosen, missing = gsl.lookup(gs_in[0], "communication")
        gs_origin = f"STAR input ground_stations ({gs_in[1]})" + (f"; {missing}" if missing else "")
    if not chosen:
        named_gs = gsl.named_in_request(texts, "communication")
        if named_gs:
            chosen, gs_origin = named_gs, "named in the mission request"
    if not chosen:
        bands = [str(r.get("band") or "") for r in ((sat or {}).get("radios") or {}).values()]
        best, why = gsl.choose_communication(cfg.get("RegionSettings"), bands)
        chosen, gs_origin = [best], "automatic: " + why
    cfg["GroundStations"] = [gsl.end001_station(s) for s in chosen]
    note("GroundStations", cfg["GroundStations"], gs_origin + ("" if len(chosen) == 1 else
                                                              "; several stations: END-001 simulates (the surrogate models one)"))

    # ---- run mode (test by default inside STAR) ---------------------------------
    try:
        from .star_runner_io import FULL_LEVELS, star_run_level, star_run_mode
    except ImportError:
        from star_runner_io import FULL_LEVELS, star_run_level, star_run_mode
    mode = star_run_mode(payload)
    level = star_run_level(payload)
    cfg["StarRunMode"] = mode
    if mode == "full":
        cfg["StarRunLevel"] = level
    origin = f"STAR run mode '{mode}'" + (f", accuracy level {level} ({FULL_LEVELS[level]})" if mode == "full" else "")
    explicit = {r["field"] for r in report if str(r["origin"]).startswith("STAR input")}
    for field, value in end001_run_profile(mode, level).items():
        if "OptimizerSettings." + field in explicit:     # a value the user or the mission gave wins
            continue
        opt[field] = value
        note("OptimizerSettings." + field, value, origin)

    # ---- fixed settings (STAR mode) ---------------------------------------------
    # what END-001 would find outside the surrogate scenario itself (surrogate_domain_check), said here so that the
    # STAR preview is exact: a sub-area of Italy, several or off-outline stations, a SAR sensor are simulated
    try:
        from . import star_domain
    except ImportError:
        import star_domain
    common: list[str] = []
    aoi_name = cfg.get("RegionSettings", {}).get("AreaofInterest")
    if aoi_name in ("Italy and Med", "Mediterranean Area", "Mediterranean", "Europe", "Europe (High Lat)", "Qatar", "Malaysia", "Artic"):
        common.append(f"area of interest '{aoi_name}' extends beyond Italy (the surrogates are trained on Italy)")
    else:
        # 2026-10-18: a sub-area of Italy (region, city, point target) uses the per-site surrogate; END-001 checks that
        # every site lies inside Italy and otherwise simulates (surrogate_domain_check). Since 2026-10-19 the whole of
        # Italy too (OptimizerSettings.Surrogate_PerSite, default true: more accurate than the whole-Italy model)
        note("Fitness engine (area of interest)", "Surrogate (per-site)",
             "END-001 aggregates the per-site surrogate over the sites of the area of interest (all inside Italy); "
             "ground-station KPIs from the whole-Italy surrogate")
    if len(cfg.get("GroundStations", [])) != 1:
        common.append(f"{len(cfg.get('GroundStations', []))} ground stations (the surrogate models one)")
    elif not star_domain.in_surrogate_area(cfg["GroundStations"][0]["lat"], cfg["GroundStations"][0]["lon"]):
        common.append("ground station outside the surrogate Italy outline")
    if sens.get("Single_Sensor_Type") not in ("PBS", "RECT"):
        common.append(f"sensor {sens.get('Single_Sensor_Type')} (the surrogate covers optical push-broom / rectangular FOV)")
    if orbit == "Auto":
        # a family whose limits leave the trained ranges is simulated by END-001 alone (surrogate_domain_check)
        for fam, out in outside_by_family.items():
            if out and not common:
                note(f"Fitness engine ({fam})", "Simulation", "limits outside the surrogate training domain (" + "; ".join(out) +
                     "): END-001 simulates this family, the other one keeps the surrogate")
        outside = common
    else:
        outside = outside_by_family[orbit] + common
    if outside:
        opt["Fitness_Engine"] = "Simulation"
        note("OptimizerSettings.Fitness_Engine", "Simulation",
             "the requirements reach outside the surrogate training domain (" + "; ".join(outside) +
             "): full simulation, slower but never an extrapolated value")
    else:
        opt["Fitness_Engine"] = "Surrogate"
        note("OptimizerSettings.Fitness_Engine", "Surrogate",
             "fixed (STAR mode); END-001 falls back to the simulation outside the surrogate domain (AOI, sensor, "
             "ground stations, FOV) and records why")
    opt["PropagationDays"] = "auto"
    note("OptimizerSettings.PropagationDays", "auto",
         "fixed (STAR mode): one repeat cycle (Sun-synchronous) or a whole lighting-drift cycle (inclined orbits)")
    if "propagation_time" in inp:
        note("propagation_time", inp["propagation_time"][0], "ignored: the module chooses the steady-state window ('auto')")
    opt["timeStep"] = 10
    note("OptimizerSettings.timeStep", 10, "fixed (STAR mode)")

    # ---- passes for the downstream modules (2026-10-17) -------------------------
    # END-001 selects the imaging pass over the AOI (END-007) and the first night
    # pass visible from the observatory (END-010): pass_selection.json.
    lc = cfg.setdefault("PassSelection", {}).setdefault("LightCurve", {})
    obs_in = inp.get("observatory")
    obs, why = _observatory(obs_in[0]) if obs_in else (None, "")
    lc.pop("Candidates", None)
    if obs:
        lc["Observer"] = obs
        note("PassSelection.LightCurve.Observer", obs, f"STAR input observatory ({obs_in[1]}): {why}")
    else:
        named_obs = gsl.named_in_request(texts, "optical")
        if named_obs:
            lc["Observer"] = gsl.observer(named_obs[0])
            note("PassSelection.LightCurve.Observer", lc["Observer"], "named in the mission request"
                 + (f" (STAR input observatory not usable: {why})" if why else ""))
        else:
            lc["Candidates"] = gsl.observer_candidates()
            note("PassSelection.LightCurve.Candidates", [c["name"] for c in lc["Candidates"]],
                 "automatic: no observatory named; END-001 keeps the Italian telescope with the most convenient first night pass "
                 "(darkest sky, then earliest, then highest)" + (f"; STAR input observatory not usable: {why}" if why else ""))

    # ---- mission life of the eclipse envelope (phase D, 2026-10-21) --------------
    # eclipse_summary.json: longest eclipse (END-004 battery) and hot / cold cases (END-019) over the mission life
    life = _number((inp.get("mission_lifetime_years") or inp.get("lifetime_years") or (None,))[0])
    if life and life > 0:
        cfg["MissionLifetimeYears"] = life
        src = inp.get("mission_lifetime_years") or inp.get("lifetime_years")
        note("MissionLifetimeYears", life, f"STAR input ({src[1]})")
    elif "lifetime_years" in found and _number(found["lifetime_years"][0]):
        cfg["MissionLifetimeYears"] = float(found["lifetime_years"][0])
        note("MissionLifetimeYears", cfg["MissionLifetimeYears"], f"requirement {found['lifetime_years'][1]}")
    else:
        cfg["MissionLifetimeYears"] = 1.0
        note("MissionLifetimeYears", 1.0, "default: mission life not stated, 1 year (a whole seasonal cycle and node drift)")
    return cfg, report


def _stations() -> dict[str, dict[str, Any]]:
    """Observatories END-010 knows (END010-ReflectanceDetermination/lib/data/stations.json)."""
    path = Path(__file__).resolve().parents[2] / "END010-ReflectanceDetermination" / "lib" / "data" / "stations.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _observatory(value: Any) -> tuple[dict[str, Any] | None, str]:
    """PassSelection.LightCurve.Observer for an observatory value: {name, lat, lon, alt}, [lat, lon(, alt_m)],
    "lat, lon" or the name / city of an END-010 station (e.g. SPADE, Matera, SCUDO)."""
    value = _parse(value)
    if isinstance(value, dict):
        lat = next((value[k] for k in ("lat_deg", "lat", "latitude", "site_lat_deg") if value.get(k) is not None), None)
        lon = next((value[k] for k in ("lon_deg", "lon", "longitude", "site_lon_deg") if value.get(k) is not None), None)
        if _number(lat) is not None and _number(lon) is not None:
            alt = _number(value.get("alt_m", value.get("alt", 0))) or 0.0
            return {"name": str(value.get("name") or "Observatory"), "lat_deg": float(lat), "lon_deg": float(lon), "alt_m": alt}, "coordinates"
        value = value.get("name") or ""
    if isinstance(value, (list, tuple)) and len(value) >= 2 and all(_number(v) is not None for v in value[:2]):
        alt = float(value[2]) if len(value) > 2 and _number(value[2]) is not None else 0.0
        return {"name": "Observatory", "lat_deg": float(value[0]), "lon_deg": float(value[1]), "alt_m": alt}, "coordinates"
    text = str(value or "").strip()
    nums = re.findall(r"[-+]?\d+(?:\.\d+)?", text)
    if len(nums) >= 2 and -90 <= float(nums[0]) <= 90:
        return {"name": text[:60], "lat_deg": float(nums[0]), "lon_deg": float(nums[1]), "alt_m": 0.0}, "coordinates"
    low = text.lower()
    try:   # Italian telescopes (config/italian_ground_stations.json) first
        from . import star_ground_stations as gsl
    except ImportError:
        import star_ground_stations as gsl
    hits = [h for h in gsl.lookup(text, "optical")[0] if not str(h.get("name", "")).startswith("Station (")] if text else []
    if hits:
        return gsl.observer(hits[0]), "Italian telescope list (italian_ground_stations.json)"
    for name, st in _stations().items():
        city = str(st.get("city", ""))
        if low and (low == name.lower() or low in city.lower() or name.lower() in low):
            label = f"{city.split('(')[0].strip()} ({name})" if city else name
            return {"name": label, "lat_deg": float(st["lat"]), "lon_deg": float(st["lon"]), "alt_m": float(st.get("alt", 0))}, \
                f"END-010 station {name}"
    return None, (f"'{text}' is not a known observatory" if text else "")

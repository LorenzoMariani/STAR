"""STAR domain check (2026-10-17).

STAR gives valid results only inside its domain (Input/input_base_knowledge/config/star_domain.json): an area of
interest in Italy (the END-001 surrogate is trained there), Earth orbits from 400 to 1200 km, a CubeSat of 1U-12U up
to 24 kg (END-006 designs the satellite every module uses), Italian ground stations and observatories. Outside it
STAR stops and gives the reasons (user decision) instead of running the modules on default values.

``check_mission(document_text, requirements)`` reads the request; ``check_inputs(resolved_inputs)`` the module inputs
the user approves. Both return {"ok", "violations": [{"kind", "reason", "evidence"}], "notes": [...]}.
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from typing import Any

try:
    from . import star_text_rules as R
except ImportError:  # imported with BackEnd/runners on sys.path
    import star_text_rules as R

MISSION_CONTEXT = ("satellite", "satellites", "spacecraft", "cubesat", "cubesats", "constellation", "orbit", "orbits", "orbital", "mission",
                   "payload", "satelliti", "costellazione", "orbita", "orbite", "missione", "carico utile", "operate", "operating", "operare")


@lru_cache(maxsize=1)
def domain() -> dict[str, Any]:
    return json.loads((R.CONFIG_DIR / "star_domain.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def italy_polygon() -> list[list[float]]:
    return json.loads((R.CONFIG_DIR / domain()["area"]["polygon_file"]).read_text(encoding="utf-8"))["polygon"]


def _inside(lat: float, lon: float, poly: list[list[float]]) -> bool:
    c = False
    n = len(poly)
    for i in range(n):
        y1, x1 = poly[i]
        y2, x2 = poly[(i + 1) % n]
        if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
            c = not c
    return c


def _distance_km(lat: float, lon: float, poly: list[list[float]]) -> float:
    """Distance from a point to the polygon outline (local equirectangular projection, fine at these distances)."""
    k = math.cos(math.radians(lat))
    px, py = lon * k * 111.32, lat * 110.57
    best = float("inf")
    n = len(poly)
    for i in range(n):
        y1, x1 = poly[i][0] * 110.57, poly[i][1] * k * 111.32
        y2, x2 = poly[(i + 1) % n][0] * 110.57, poly[(i + 1) % n][1] * k * 111.32
        dx, dy = x2 - x1, y2 - y1
        t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
        best = min(best, math.hypot(px - (x1 + t * dx), py - (y1 + t * dy)))
    return best


def in_italy(lat: float, lon: float, tolerance_km: float | None = None) -> bool:
    """Inside the END-001 Italy outline, or within tolerance_km of it (the outline is coarse along coasts and borders)."""
    poly = italy_polygon()
    tol = domain()["area"].get("tolerance_km", 30) if tolerance_km is None else tolerance_km
    return _inside(lat, lon, poly) or _distance_km(lat, lon, poly) <= tol


def in_surrogate_area(lat: float, lon: float) -> bool:
    """Strictly inside the outline: a ground station there keeps the END-001 surrogate usable."""
    return _inside(lat, lon, italy_polygon())


def summary() -> str:
    d = domain()
    return (f"area of interest in {d['area']['name']}, Earth orbit {d['orbit']['altitude_km'][0]}-{d['orbit']['altitude_km'][1]} km, "
            f"{d['spacecraft']['type']} {'/'.join(str(c) + 'U' for c in d['spacecraft']['classes_u'])} up to "
            f"{d['spacecraft']['max_mass_kg']} kg, Italian ground stations and observatories")


def _req_items(requirements) -> list[tuple[str, str]]:
    out = []
    for r in requirements or []:
        if isinstance(r, dict) and r.get("text"):
            out.append((str(r.get("id", "REQ")), str(r["text"])))
    return out


def _short(text: str, n: int = 160) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 3] + "..."


def check_mission(document_text: str, requirements) -> dict[str, Any]:
    d = domain()
    reqs = _req_items(requirements)
    violations: list[dict[str, str]] = []
    notes: list[str] = []
    seen = set()

    def violate(kind: str, reason: str, evidence: str) -> None:
        key = (kind, reason)
        if key not in seen:
            seen.add(key)
            violations.append({"kind": kind, "reason": reason, "evidence": _short(evidence)})

    texts = [t for _, t in reqs] + R.sentences(document_text or "")
    # orbit regime and body
    for s in texts:
        if R.has_any(s, MISSION_CONTEXT) or R.has_any(s, d["outside_orbit_words"]):
            hits = R.find_all(s, d["outside_orbit_words"])
            if hits:
                violate("orbit", f"the mission is not in low Earth orbit ({', '.join(hits)}): STAR designs Earth orbits from "
                                 f"{d['orbit']['altitude_km'][0]} to {d['orbit']['altitude_km'][1]} km", s)
    params = R.mission_parameters(reqs)
    if "alt" in params:
        lo, hi = params["alt"][0]
        a0, a1 = d["orbit"]["altitude_km"]
        if (lo is not None and lo < a0) or (hi is not None and hi > a1) or (lo is not None and lo > a1) or (hi is not None and hi < a0):
            rid = params["alt"][1]
            violate("orbit", f"altitude {lo if lo is not None else ''}-{hi if hi is not None else ''} km outside {a0}-{a1} km "
                             f"(END-001 orbit table and surrogate)", f"{rid}: " + dict(reqs).get(rid, ""))
    # spacecraft
    if "class_u" in params:
        bad = [c for c in params["class_u"][0] if c not in d["spacecraft"]["classes_u"]]
        if bad and not [c for c in params["class_u"][0] if c in d["spacecraft"]["classes_u"]]:
            rid = params["class_u"][1]
            violate("spacecraft", f"CubeSat class {', '.join(str(c) + 'U' for c in bad)} not available: END-006 designs "
                                  f"{'/'.join(str(c) + 'U' for c in d['spacecraft']['classes_u'])} CubeSats", f"{rid}: " + dict(reqs).get(rid, ""))
    if "mass" in params:
        value, kind = params["mass"][0]
        if kind == "exact" and value > d["spacecraft"]["max_mass_kg"]:
            rid = params["mass"][1]
            violate("spacecraft", f"satellite mass {value:g} kg above the {d['spacecraft']['max_mass_kg']} kg of a 12U CubeSat",
                    f"{rid}: " + dict(reqs).get(rid, ""))
    whole = " ".join(texts)
    if not R.has_any(whole, ("cubesat", "cubesats", "nanosatellite", "nanosatellites", "nanosatellite", "nanosatelliti")):
        for s in texts:
            hits = R.find_all(s, d["outside_spacecraft_words"])
            if hits and R.has_any(s, MISSION_CONTEXT + tuple(d["outside_spacecraft_words"])):
                violate("spacecraft", f"the satellite is a {hits[0]}, not a CubeSat: END-006 designs only CubeSats up to "
                                      f"{d['spacecraft']['max_mass_kg']} kg", s)
                break
        if "mass" in params and params["mass"][0][1] == "max" and params["mass"][0][0] > d["spacecraft"]["max_mass_kg"] and \
                not any(v["kind"] == "spacecraft" for v in violations):
            notes.append(f"the request allows up to {params['mass'][0][0]:g} kg and names no CubeSat: STAR designs a CubeSat up to "
                         f"{d['spacecraft']['max_mass_kg']} kg (END-006)")
    # area of interest
    for s in texts:
        if R.has_any(s, R.AOI_CONTEXT) and not R.has_any(s, R.STATION_CONTEXT):
            hits = R.find_all(s, d["outside_italy_names"])
            if hits:
                violate("area", f"area outside Italy ({', '.join(hits)}): the END-001 surrogate is valid only for Italy", s)
            g = R.find_all(s, d["global_area_words"])
            if g:
                violate("area", f"global coverage ({', '.join(g)}): STAR analyses areas in Italy", s)
    aoi = R.area_of_interest([t for _, t in reqs] + [document_text or ""])
    for lat, lon in aoi["points"]:
        if not in_italy(lat, lon):
            violate("area", f"target ({lat:g}, {lon:g}) outside Italy", f"coordinates ({lat:g}, {lon:g})")
    if not aoi["region_settings"] and not any(v["kind"] == "area" for v in violations):
        notes.append("the request names no Italian area: END-001 analyses the whole of Italy")
    # ground stations and observatories
    for s in texts:
        if R.has_any(s, R.STATION_CONTEXT):
            hits = R.find_all(s, d["outside_italy_names"])
            if hits:
                violate("station", f"ground station or observatory outside Italy ({', '.join(hits)}): STAR uses the Italian "
                                   f"stations and telescopes of italian_ground_stations.json", s)
    for lat, lon in aoi["station_points"]:
        if not in_italy(lat, lon):
            violate("station", f"ground station or observatory at ({lat:g}, {lon:g}) outside Italy", f"coordinates ({lat:g}, {lon:g})")
    return {"ok": not violations, "violations": violations, "notes": notes, "domain": summary(),
            "area_of_interest": aoi.get("region_settings"), "area_why": aoi.get("why")}


def check_inputs(resolved_inputs) -> dict[str, Any]:
    """Approved module inputs: area of interest coordinates or names, observatory and ground stations inside Italy."""
    violations, notes = [], []
    inside_names = [n.lower() for n in domain()["area"]["end001_named_areas_inside"]]
    for item in resolved_inputs or []:
        if not isinstance(item, dict) or str(item.get("source", "")) in ("module_registry_default", "module_registry_required_input"):
            continue
        name = str(item.get("parameter", ""))
        value = item.get("proposed_value")
        try:
            parsed = json.loads(value) if isinstance(value, str) and value.strip()[:1] in "[{" else value
        except Exception:
            parsed = value
        pts: list[tuple[float, float]] = []
        if isinstance(parsed, list) and parsed and all(isinstance(p, (list, tuple)) and len(p) >= 2 for p in parsed):
            pts = [(float(p[0]), float(p[1])) for p in parsed]
        elif isinstance(parsed, dict):
            lat = next((parsed[k] for k in ("lat", "latitude", "lat_deg", "site_lat_deg") if k in parsed), None)
            lon = next((parsed[k] for k in ("lon", "longitude", "lon_deg", "site_lon_deg") if k in parsed), None)
            if lat is not None and lon is not None:
                pts = [(float(lat), float(lon))]
        elif isinstance(parsed, str):
            pts = R.coordinates(parsed)
        if name in ("area_of_interest", "observatory", "ground_stations") and pts:
            out = [p for p in pts if not in_italy(*p)]
            if out:
                violations.append({"kind": "area" if name == "area_of_interest" else "station",
                                   "reason": f"{name}: point(s) {out[:3]} outside Italy", "evidence": _short(str(value))})
        if name == "area_of_interest" and isinstance(parsed, str) and not pts:
            low = parsed.lower()
            if R.has_any(low, domain()["outside_italy_names"]) or R.has_any(low, domain()["global_area_words"]):
                violations.append({"kind": "area", "reason": f"area_of_interest '{_short(parsed, 60)}' is outside Italy",
                                   "evidence": _short(parsed)})
            elif not (low in inside_names or R.area_of_interest([parsed])["region_settings"]):
                notes.append(f"area_of_interest '{_short(parsed, 60)}' is not an Italian place STAR knows: END-001 uses the whole of Italy")
    return {"ok": not violations, "violations": violations, "notes": notes, "domain": summary()}


def stop_message(result: dict[str, Any]) -> str:
    lines = [f"STAR stops: the mission is outside its domain ({result.get('domain') or summary()})."]
    for v in result.get("violations", []):
        lines.append(f"- {v['kind']}: {v['reason']} [{v['evidence']}]")
    lines.append("Change the requirements (or the module inputs) to stay inside the domain, or widen the domain in "
                 "Input/input_base_knowledge/config/star_domain.json when the modules are extended.")
    return "\n".join(lines)

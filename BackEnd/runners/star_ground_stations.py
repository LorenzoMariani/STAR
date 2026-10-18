"""Italian ground stations and telescopes for END-001 / END-004 / END-010 (2026-10-17).

The list is Input/input_base_knowledge/config/italian_ground_stations.json (sources in it). Priority:
1. STAR input (ground_stations / observatory): names or aliases of the list, coordinates, or {name, lat, lon};
2. stations or telescopes the mission request names (names, aliases or coordinates in a station / observatory sentence);
3. automatic choice: the communication station nearest to the area of interest among those supporting the downlink band
   of the CubeSat radios (END-006 spacecraft_definition.json; a single station also keeps the END-001 surrogate usable
   when it lies inside its Italy outline); every confirmed telescope as LightCurve.Candidates, END-001 keeping the one
   with the most convenient first night pass (darkest sky, earliest, highest).
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from typing import Any

try:
    from . import star_text_rules as R
except ImportError:
    import star_text_rules as R

COMM_CONTEXT = ("ground station", "ground stations", "ground segment", "teleport", "downlink", "downlinked", "uplink", "antenna",
                "space centre", "space center", "centro spaziale", "stazione di terra", "stazioni di terra", "segmento di terra",
                "scaricati", "scaricate", "scarico", "telecommand", "telecomando", "tt&c")
OPTICAL_CONTEXT = ("observatory", "observatories", "telescope", "telescopes", "osservatorio", "osservatori", "telescopio", "telescopi",
                   "seen from", "visto da", "visti da", "observed from", "osservato da", "osservati da", "cross the sky", "sky of",
                   "visible from", "visibile da", "visibili da", "cielo di", "night pass", "passaggio notturno")
BAND_ORDER = {"VHF": 0, "UHF": 1, "L": 2, "S": 3, "C": 4, "X": 5, "KU": 6, "K": 7, "KA": 8}


@lru_cache(maxsize=1)
def stations() -> dict[str, Any]:
    return json.loads((R.CONFIG_DIR / "italian_ground_stations.json").read_text(encoding="utf-8"))


def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(min(1.0, a)))


def end001_station(st: dict[str, Any]) -> dict[str, Any]:
    return {"name": st["name"], "lat": float(st["lat"]), "lon": float(st["lon"]), "alt": float(st.get("alt_m", 0)), "mask": float(st.get("mask_deg", 5))}


def observer(st: dict[str, Any]) -> dict[str, Any]:
    return {"name": st["name"], "lat_deg": float(st["lat"]), "lon_deg": float(st["lon"]), "alt_m": float(st.get("alt_m", 0))}


def _match(text: str, group: str) -> list[dict[str, Any]]:
    out = []
    for st in stations().get(group, []):
        if R.has_any(text, list(st.get("aliases", [])) + [st["name"]]):
            out.append(st)
    return out


def lookup(value: Any, group: str) -> tuple[list[dict[str, Any]], str]:
    """Stations for a STAR input value: names / aliases (string or list), coordinates, or dicts with lat / lon."""
    value = value if not isinstance(value, str) else (json.loads(value) if value.strip()[:1] in "[{" else value)
    items = value if isinstance(value, list) and not (len(value) >= 2 and all(isinstance(v, (int, float)) for v in value[:2])) else [value]
    found, missing = [], []
    for item in items:
        if isinstance(item, dict) and item.get("lat") is not None and item.get("lon") is not None:
            found.append({"name": str(item.get("name") or "Station"), "lat": float(item["lat"]), "lon": float(item["lon"]),
                          "alt_m": float(item.get("alt", item.get("alt_m", 0)) or 0), "mask_deg": float(item.get("mask", item.get("mask_deg", 5)) or 5)})
        elif isinstance(item, (list, tuple)) and len(item) >= 2 and all(isinstance(v, (int, float)) for v in item[:2]):
            found.append({"name": f"Station ({item[0]:g}, {item[1]:g})", "lat": float(item[0]), "lon": float(item[1]),
                          "alt_m": float(item[2]) if len(item) > 2 else 0.0, "mask_deg": 5.0})
        else:
            hits = _match(str(item), group)
            pts = R.coordinates(str(item))
            if hits:
                found.extend(h for h in hits if h not in found)
            elif pts:
                found.extend({"name": f"Station ({lat:g}, {lon:g})", "lat": lat, "lon": lon, "alt_m": 0.0, "mask_deg": 5.0} for lat, lon in pts)
            else:
                missing.append(str(item))
    return found, ("not in the Italian station list: " + ", ".join(missing)) if missing else ""


def named_in_request(texts, group: str) -> list[dict[str, Any]]:
    """Stations (group 'communication') or telescopes ('optical') the mission request names: aliases or coordinates in
    a sentence about ground stations (or observatories)."""
    context = COMM_CONTEXT if group == "communication" else OPTICAL_CONTEXT
    found = []
    for t in texts:
        for s in R.sentences(t) or [t]:
            if not R.has_any(s, context):
                continue
            for st in _match(s, group):
                if st not in found:
                    found.append(st)
            if not _match(s, group):
                for lat, lon in R.coordinates(s):
                    found.append({"name": f"{'Station' if group == 'communication' else 'Observatory'} ({lat:g}, {lon:g})",
                                  "lat": lat, "lon": lon, "alt_m": 0.0, "mask_deg": 5.0})
    return found


def aoi_centre(region_settings: dict[str, Any] | None) -> tuple[float, float]:
    rs = region_settings or {}
    pts = rs.get("CustomCoordinates") if rs.get("AreaofInterest") == "Custom" else None
    if not pts:
        try:
            pts = json.loads((R.CONFIG_DIR / "italy_aoi_polygon.json").read_text(encoding="utf-8"))["sites"]
        except Exception:
            return 42.0, 12.8
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


def choose_communication(region_settings: dict[str, Any] | None, radio_bands: list[str]) -> tuple[dict[str, Any], str]:
    """Nearest station to the area of interest among those supporting the downlink band of the CubeSat (the highest band
    of its radios); without a match, those supporting any of its bands, then those with undeclared bands, then all."""
    lat0, lon0 = aoi_centre(region_settings)
    comm = [s for s in stations().get("communication", []) if s.get("status") == "operational"]
    import re
    bands = sorted({part.strip() for b in radio_bands if b for part in re.split(r"[/,+ ]+", str(b).upper().replace("-BAND", "")) if part.strip()},
                   key=lambda b: BAND_ORDER.get(b, 9))      # "S/X" radio: S and X
    downlink = bands[-1] if bands else None
    tiers = []
    if downlink:
        tiers.append((f"support the {downlink}-band downlink of the CubeSat", [s for s in comm if downlink in (s.get("bands") or [])]))
        tiers.append((f"support one of the CubeSat bands ({', '.join(bands)})", [s for s in comm if set(bands) & set(s.get("bands") or [])]))
        tiers.append(("have no bands declared by their sources", [s for s in comm if not s.get("bands")]))
    tiers.append(("are operational" + ("" if downlink else " (the CubeSat radios are not known yet)"), comm))
    try:
        from . import star_domain
    except ImportError:
        import star_domain
    for why, group in tiers:
        if group:
            best = min(group, key=lambda s: (_km(lat0, lon0, s["lat"], s["lon"]), not star_domain.in_surrogate_area(s["lat"], s["lon"])))
            d = _km(lat0, lon0, best["lat"], best["lon"])
            return best, f"nearest to the area of interest ({d:.0f} km from its centre {lat0:.2f}, {lon0:.2f}) among the stations that {why}"
    raise ValueError("no Italian ground station in italian_ground_stations.json")


def observer_candidates() -> list[dict[str, Any]]:
    return [observer(s) for s in stations().get("optical", []) if s.get("status_confirmed")]

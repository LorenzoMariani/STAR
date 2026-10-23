"""Text rules shared by the STAR planner, the END-001 inputs, the domain check and the compliance check (2026-10-17).

Every keyword is matched as a whole word or phrase (``has_any``): "necessary" no longer means SAR, "steps" no longer
means EPS. English and Italian forms; accents, typographic quotes and dashes are normalised first (``norm``).

- ``requirement_sentences``: the sentences of a mission request that are requirements (a modal verb such as shall /
  must / dovra' / deve, or a requirement identifier such as REQ-04), kept verbatim with their numbers;
- ``mission_parameters``: numbers and choices END-001 and the other modules need (altitude, satellites, planes, orbit
  family, inclination, sensor, swath, GSD, mass, CubeSat class, pointing accuracy, revisit and latency thresholds,
  re-entry and lifetime, depth of discharge, magnitude, temperatures, single satellite);
- ``area_of_interest``: the Italian area named in the request (config/italy_places.json) or its coordinates, the
  foreign areas and the global coverage words (for the domain check);
- ``MODULE_KEYWORDS``: what the planner looks for to propose a module.
"""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

STAR_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = STAR_ROOT / "Input" / "input_base_knowledge" / "config"

NUM = r"(\d+(?:[.,]\d+)?)"
SNUM = r"(-?\d+(?:[.,]\d+)?)"


def norm(text: Any) -> str:
    """Lower case, accents removed, typographic quotes and dashes replaced, spaces collapsed."""
    t = unicodedata.normalize("NFKD", str(text or ""))
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    t = (t.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
         .replace("–", "-").replace("—", "-").replace("−", "-").replace("≤", "<=").replace("≥", ">=")
         .replace(" ", " "))
    return re.sub(r"[ \t]+", " ", t.lower()).strip()


def num(value: str) -> float:
    return float(str(value).replace(",", "."))


@lru_cache(maxsize=4096)
def _phrase_re(words: tuple[str, ...]) -> re.Pattern:
    parts = []
    for w in words:
        tokens = [re.escape(tok) for tok in re.split(r"[\s\-]+", norm(w)) if tok]
        if tokens:
            parts.append(r"[\s\-]+".join(tokens))
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(parts) + r")(?![a-z0-9])")


def has_any(text: str, words) -> bool:
    """True when one of the words/phrases occurs as a whole word in the (normalised) text."""
    words = tuple(words)
    return bool(words) and _phrase_re(words).search(norm(text)) is not None


def find_all(text: str, words) -> list[str]:
    words = tuple(words)
    return sorted({m.group(0) for m in _phrase_re(words).finditer(norm(text))}) if words else []


# --------------------------------------------------------------------------- sentences and requirements
MODALS = ("shall", "must", "should", "is required to", "are required to", "will have to", "has to", "have to", "needs to",
          "need to", "is to be", "are to be", "dovra", "dovranno", "deve", "devono", "e richiesto", "e richiesta", "sono richiesti",
          "sono richieste", "si richiede", "occorre", "sara necessario", "dovra essere", "dovranno essere")
REQ_ID = re.compile(r"^\s*\(?((?:req|rq|mr|fr|pr|sr|dr|or|tr|r)[-_.]?\s?\d+[a-z0-9.\-]*)\)?[\s:.\-)]+", re.I)
PROGRAMMATIC = ("proposal shall be submitted", "proposals shall be submitted", "submission", "deadline", "scadenza", "euro", "eur",
                "financial budget", "total budget", "budget ceiling", "maximum budget", "importo", "contract", "contratto", "consortium", "consorzio", "page limit", "numero di pagine", "eligibility", "ammissibilita",
                "evaluation criteria", "criteri di valutazione", "tender", "offerente", "offerta economica", "bidder", "proposer", "proponente",
                "kick-off", "co-funding", "cofinanziamento", "intellectual property", "proprieta intellettuale")
CATEGORY_WORDS = (
    ("environmental", ("debris", "collision", "collisions", "close approach", "close approaches", "re-entry", "reentry", "re-enter", "deorbit",
                "de-orbit", "disposal", "end of life", "safe separation", "detriti", "collisione", "collisioni", "rientro", "fine vita",
                "smaltimento", "avvicinamenti")),
    ("mission", ("revisit", "latency", "resolution", "gsd", "ground sampling distance", "swath", "accuracy", "magnitude", "coverage",
                     "access time", "rivisita", "latenza", "risoluzione", "strisciata", "accuratezza", "magnitudine", "copertura")),
    ("design", ("cubesat", "mass", "payload", "propulsion", "battery", "power budget", "solar", "thermal", "temperature", "component",
                "components", "subsystem", "subsystems", "attitude", "pointing", "massa", "propulsione", "batteria", "bilancio di potenza",
                "termico", "temperatura", "componenti", "sottosistemi", "assetto", "puntamento")),
    ("operational", ("ground station", "ground stations", "downlink", "uplink", "contact", "contacts", "stazione di terra", "stazioni di terra",
                    "scaricati", "scarico dati", "telecomando", "telemetria")),
    ("mission", ("monitor", "monitoring", "observe", "observation", "area of interest", "territory", "target", "image", "images", "imaging",
                 "monitoraggio", "osservazione", "area di interesse", "territorio", "immagini")),
)


def _units(text: str) -> list[str]:
    """Paragraph pieces with wrapped lines joined; list items and requirement identifiers start new pieces."""
    units, cur = [], []

    def flush():
        if cur:
            units.append(" ".join(cur))
            cur.clear()

    for line in str(text or "").replace("\r", "").split("\n"):
        s = line.strip()
        if not s:
            flush()
            continue
        new_item = bool(REQ_ID.match(s) or re.match(r"^(?:[-*•▪●]|\d{1,2}[.)]\s|[a-z][.)]\s)", s, re.I))
        if new_item or (cur and cur[-1].endswith((".", ":")) and s[:1].isupper()):
            flush()
        cur.append(s)
    flush()
    return units


def sentences(text: str) -> list[str]:
    """Sentences of a document (original case), split on . ! ? followed by an upper-case letter or a digit."""
    out = []
    for u in _units(text):
        for s in re.split(r"(?<=[.!?])\s+(?=[A-Z(\d])", u):
            s = s.strip()
            if len(s) > 3:
                out.append(s)
    return out


def category(text: str) -> str:
    for cat, words in CATEGORY_WORDS:
        if has_any(text, words):
            return cat
    return "functional"


def requirement_sentences(text: str) -> list[dict[str, Any]]:
    """Requirements of a mission request: sentences with a modal verb or a requirement identifier, verbatim."""
    reqs, seen_ids = [], set()
    for s in sentences(text):
        m = REQ_ID.match(s)
        body = s[m.end():].strip() if m else s
        if not body:
            continue
        if not m and not has_any(body, MODALS):
            continue
        if has_any(body, PROGRAMMATIC):
            continue
        rid = m.group(1).upper().replace(" ", "") if m else None
        if not rid or rid in seen_ids:
            rid = None
        reqs.append({"id": rid, "text": body.rstrip() if body.rstrip().endswith(".") else body.rstrip() + ".", "category": category(body)})
        if rid:
            seen_ids.add(rid)
    n = 0
    for r in reqs:
        if not r["id"]:
            n += 1
            while f"REQ-{n:03d}" in seen_ids:
                n += 1
            r["id"] = f"REQ-{n:03d}"
    return reqs


# --------------------------------------------------------------------------- numbers and choices
NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
                "eleven": 11, "twelve": 12, "uno": 1, "due": 2, "tre": 3, "quattro": 4, "cinque": 5, "sei": 6, "sette": 7,
                "otto": 8, "nove": 9, "dieci": 10, "undici": 11, "dodici": 12}
SAT_WORDS = r"(?:satellites|satellite|spacecraft|cubesats|cubesat|satelliti|nanosatellites|nanosatelliti|platforms|unita)"
UP_TO = r"(?:at most|no more than|not more than|a maximum of|maximum of|maximum|max\.?|up to|not exceeding|al massimo|non piu di|non oltre|un massimo di|massimo di|massimo|fino a|<=|<)"
AT_LEAST = r"(?:at least|a minimum of|minimum of|minimum|no fewer than|not less than|almeno|non meno di|un minimo di|minimo di|minimo|>=)"
LESS = r"(?:lower than|less than|below|under|shall not exceed|not exceed(?:ing)?|not to exceed|within|of at most|at most|no more than|better than|inferiore a|inferiori a|minore di|non superiore a|non superiori a|entro|al massimo|non oltre|<=|<|of|di|pari a|=|:|is|e|sia)"
TIME_UNIT = r"(hours|hour|hrs|h|ore|ora|days|day|giorni|giorno|minutes|minute|min|minuti|minuto)"
ALT_WORDS = ("altitude", "altitudes", "height", "orbit altitude", "orbital altitude", "quota", "quote", "altezza", "orbita a", "operating altitude")


def _hours(value: float, unit: str) -> float:
    u = unit.lower()
    if u.startswith(("day", "giorn")):
        return value * 24.0
    if u.startswith("min"):
        return value / 60.0
    return value


def _words_to_digits(text: str) -> str:
    return _phrase_re(tuple(NUMBER_WORDS)).sub(lambda m: str(NUMBER_WORDS[m.group(0)]), text)


def _clauses(text: str) -> list[str]:
    return [c for c in re.split(r";|\s-\s", norm(text)) if c.strip()]


def _altitude(t: str) -> list[float] | None:
    for m in _phrase_re(ALT_WORDS).finditer(t):
        w = t[max(0, m.start() - 70): m.end() + 90]     # "between 500 km and 650 km of altitude" puts the numbers first
        r = (re.search(r"between\s+" + NUM + r"\s*(?:km)?\s+and\s+" + NUM + r"\s*km", w)
             or re.search(r"(?:tra|fra)\s+" + NUM + r"\s*(?:km)?\s+e\s+" + NUM + r"\s*km", w)
             or re.search(r"(?:from|da)\s+" + NUM + r"\s*(?:km)?\s+(?:to|a)\s+" + NUM + r"\s*km", w)
             or re.search(NUM + r"\s*(?:km)?\s*(?:-|to)\s*" + NUM + r"\s*km", w))
        if r:
            a, b = sorted([num(r.group(1)), num(r.group(2))])
            return [a, b]
        r = re.search(r"(?:below|lower than|under|less than|not exceeding|inferiore a|sotto(?: i)?|non superiore a)\s+" + NUM + r"\s*km", w)
        if r:
            return [None, num(r.group(1))]
        r = re.search(r"(?:above|higher than|over|greater than|superiore a|sopra(?: i)?|non inferiore a)\s+" + NUM + r"\s*km", w)
        if r:
            return [num(r.group(1)), None]
        r = re.search(r"^[a-z ]{0,30}?(?:of|di|pari a|=|:|at|a|is|around|about|circa|approximately|approx\.?)?\s*\(?\s*" + NUM + r"\s*km", t[m.end(): m.end() + 90])
        if r:
            v = num(r.group(1))
            return [v, v]
    return None


def _threshold(clause: str, keys: str) -> float | None:
    m = re.search(keys + r"[^;]{0,60}?" + LESS + r"\s*(?:about\s+|circa\s+)?" + NUM + r"\s*" + TIME_UNIT + r"(?![a-z])", clause)
    if m:
        return _hours(num(m.group(1)), m.group(2))
    return None


REVISIT_MAX = r"(?:maximum revisit(?: time)?|max(?:imum)?\.? revisit|worst[- ]case revisit(?: time)?|revisit(?: time)? \(maximum\)|tempo di rivisita massimo|tempo massimo di rivisita|rivisita massima|massimo tempo di rivisita)"
REVISIT_MEAN = r"(?:mean revisit(?: time)?|average revisit(?: time)?|tempo medio di rivisita|tempo di rivisita medio|rivisita media)"
REVISIT_P90 = r"(?:90(?:th)?[- ]percentile(?: of the)? revisit(?: time)?|p90 revisit(?: time)?|revisit(?: time)? at (?:the )?90(?:th)? percentile|90[^a-z]{0,3}percentile del(?:la)? (?:tempo di )?rivisita)"
REVISIT_ANY = r"(?:revisit(?: time)?|rivisita|tempo di rivisita|revisited|rivisitat[ao])"
LATENCY = r"(?:data latency|latency|latenza(?: dei dati)?|age of information)"
DELIVERY = r"(?:downlinked|delivered|made available|available|transmitted|scaricati|scaricate|consegnati|consegnate|disponibili|trasmessi)"


def mission_parameters(requirements) -> dict[str, tuple[Any, str]]:
    """{name: (value, requirement id)} from requirement texts [(id, text)] or [{"id", "text"}]: the first requirement
    stating a parameter wins. Units: km, deg, kg, hours, years, metres, percent, deg C."""
    found: dict[str, tuple[Any, str]] = {}

    def put(key, value, rid):
        if key not in found and value is not None:
            found[key] = (value, rid)

    items = [(r.get("id", "REQ"), r.get("text", "")) if isinstance(r, dict) else (r[0], r[1]) for r in requirements]
    whole = " ".join(norm(t) for _, t in items)
    constellation_words = has_any(whole, ("constellation", "costellazione", "constellations", "costellazioni"))
    for rid, text in items:
        t = _words_to_digits(norm(text))
        # altitude
        alt = _altitude(t)
        if alt:
            put("alt", alt, rid)
        # satellites
        m = re.search(AT_LEAST + r"\s+" + NUM + r"\s+(?:and|e|,)\s+" + UP_TO + r"\s+" + NUM + r"\s+(?:[a-z]+\s+){0,3}?" + SAT_WORDS, t)
        if m:
            put("sats_min", int(num(m.group(1))), rid); put("sats_max", int(num(m.group(2))), rid)
        m = re.search(r"(?:between|tra|fra|from|da)\s+" + NUM + r"\s+(?:and|e|to|a)\s+" + NUM + r"\s+(?:[a-z]+\s+){0,3}?" + SAT_WORDS, t)
        if m:
            put("sats_min", int(num(m.group(1))), rid); put("sats_max", int(num(m.group(2))), rid)
        m = re.search(UP_TO + r"\s+" + NUM + r"\s+(?:[a-z]+\s+){0,3}?" + SAT_WORDS, t)
        if m:
            put("sats_max", int(num(m.group(1))), rid)
        m = re.search(AT_LEAST + r"\s+" + NUM + r"\s+(?:[a-z]+\s+){0,3}?" + SAT_WORDS, t)
        if m:
            put("sats_min", int(num(m.group(1))), rid)
        if "sats_min" not in found and "sats_max" not in found:
            m = re.search(r"(?<![a-z0-9.,])" + NUM + r"\s+(?:small\s+|identical\s+|optical\s+|piccoli\s+)?" + SAT_WORDS + r"(?!\s+per\s+(?:plane|piano))", t)
            if m and num(m.group(1)) > 1 and "u" not in t[max(0, m.start() - 1): m.start()]:
                n = int(num(m.group(1)))
                put("sats_min", n, rid); put("sats_max", n, rid)
        if re.search(r"(?:single|1|a single|un solo|un singolo|singolo|unico)\s+(?:\d{1,2}\s*u\s+)?(?:cubesat|satellite|spacecraft|nanosatellite)(?!\s+per\s+(?:plane|piano))", t) \
                and not constellation_words:
            put("single", True, rid)
        # planes
        m = re.search(r"(?<![a-z0-9.,])" + NUM + r"\s+(?:different\s+|separate\s+|distinct\s+)?(?:orbital\s+)?planes?\b", t) or \
            re.search(r"(?<![a-z0-9.,])" + NUM + r"\s+piani(?:\s+orbitali)?\b", t)
        if m:
            put("planes", int(num(m.group(1))), rid)
        elif re.search(r"(?:single|one|1|un unico|un solo|unico)\s+(?:orbital\s+)?(?:plane|piano)", t):
            put("planes", 1, rid)
        # orbit family and inclination
        if has_any(t, ("sun-synchronous", "sun synchronous", "sso", "heliosynchronous", "eliosincrona", "eliosincrono", "eliosincrone",
                       "sincrona con il sole")):
            put("orbit", "SSORGT", rid)
        elif has_any(t, ("walker", "walker delta", "walker-delta", "inclined orbit", "inclined orbits", "orbita inclinata", "orbite inclinate")):
            put("orbit", "RGT (generally inclined)", rid)
        m = (re.search(r"inclination\s+(?:of\s+)?(?:about\s+|approximately\s+)?" + NUM + r"\s*(?:deg|degrees|°)", t)
             or re.search(NUM + r"\s*(?:deg|degrees|°)\s+inclination", t)
             or re.search(r"inclined at\s+" + NUM, t)
             or re.search(r"inclinazione\s+(?:di\s+|pari a\s+|circa\s+)?" + NUM + r"\s*(?:gradi|°|deg)?", t))
        if m:
            put("incl", num(m.group(1)), rid)
        # sensor
        if has_any(t, ("push-broom", "pushbroom", "push broom", "line scan", "line-scan", "scansione a spinta")):
            put("sensor", "PBS", rid)
        elif has_any(t, ("sar", "synthetic aperture radar", "synthetic-aperture radar", "radar ad apertura sintetica", "radar")):
            put("sensor", "SAR", rid)
        elif has_any(t, ("frame camera", "framing camera", "area camera", "matrix camera", "snapshot camera", "staring camera",
                         "camera a matrice", "sensore matriciale")):
            put("sensor", "RECT", rid)
        # swath, GSD
        m = (re.search(r"(?:swath(?: width)?|larghezza (?:della )?(?:strisciata|fascia|striscia)|ampiezza della strisciata|strisciata)\s+(?:of\s+|di\s+|pari a\s+|shall be\s+)?(?:at least\s+|almeno\s+|about\s+)?" + NUM + r"\s*km", t)
             or re.search(NUM + r"\s*km\s+(?:wide\s+)?swath", t))
        if m:
            put("swath", num(m.group(1)), rid)
        m = (re.search(r"(?:ground sampl(?:e|ing) distance|gsd|spatial resolution|ground resolution|resolution|risoluzione(?: spaziale| a terra| al suolo)?)\s*(?:\([a-z]+\)\s*)?(?:of\s+|di\s+|pari a\s+|shall be\s+|at nadir\s+|al nadir\s+)?(?:at least\s+|better than\s+|of at most\s+|non superiore a\s+|migliore di\s+|<=\s*|<\s*)?" + NUM + r"\s*(m|metres|meters|metri|cm|km)\b", t)
             or re.search(NUM + r"\s*(m|metres|meters|metri|km)\s+(?:gsd|spatial resolution|resolution|risoluzione)", t))
        if m:
            unit = m.group(2)
            v = num(m.group(1)) * (0.01 if unit == "cm" else 1000.0 if unit == "km" else 1.0)
            put("gsd", v, rid)
        # mass, class
        m = (re.search(r"mass(?: at launch| of each satellite| of the satellite)?\s+(?:shall be\s+|will be\s+)?(not exceeding|below|up to|lower than|less than|at most|under|no more than|of at most|<=|<)\s+" + NUM + r"\s*kg", t)
             or re.search(r"massa(?: al lancio)?\s+(?:dovra essere\s+)?(non superiore a|inferiore a|massima di|fino a|non oltre|al massimo di|<=|<)\s+" + NUM + r"\s*kg", t)
             or re.search(r"(below|under|up to|sotto i|inferiore a|fino a)\s+" + NUM + r"\s*kg", t))
        if m:
            put("mass", (num(m.group(2)), "max"), rid)
        else:
            m = re.search(r"mass(?:a)?\s+(?:of|di|pari a|=|:)\s+(?:about\s+|circa\s+)?" + NUM + r"\s*kg", t)
            if m:
                put("mass", (num(m.group(1)), "exact"), rid)
        classes = sorted({int(c) for c in re.findall(r"(?<![a-z0-9.,])(\d{1,2})\s*-?\s*u(?![a-z0-9])", t)}) if has_any(t, ("cubesat", "cubesats", "u cubesat")) or re.search(r"\d\s*u\s+cubesat", t) else []
        if classes:
            put("class_u", classes, rid)
        # pointing accuracy (phase E): "a pointing accuracy better than 0.1 deg", in degrees
        m = re.search(r"(?:pointing (?:accuracy|error)|accuratezza di puntamento|precisione di puntamento|errore di puntamento)[^.;]{0,30}?"
                      r"(?:better than|of at most|at most|below|lower than|less than|within|under|not exceeding|migliore di|inferiore a|"
                      r"entro|non superiore a|of|di|<=|<)\s*" + NUM + r"\s*(deg|degrees|degree|°|gradi|grado|arcsec|arcmin)(?![a-z])", t)
        if m:
            put("pointing_deg", num(m.group(1)) / {"arcsec": 3600.0, "arcmin": 60.0}.get(m.group(2), 1.0), rid)
        # thresholds
        for c in _clauses(t):
            if re.search(REVISIT_MEAN, c):
                put("revisit_mean_h", _threshold(c, REVISIT_MEAN), rid)
            elif re.search(REVISIT_P90, c):
                put("revisit_p90_h", _threshold(c, REVISIT_P90), rid)
            elif re.search(REVISIT_MAX, c):
                put("revisit_max_h", _threshold(c, REVISIT_MAX), rid)
            elif re.search(REVISIT_ANY, c):
                v = _threshold(c, REVISIT_ANY)
                if v is None:
                    m = re.search(r"every\s+" + NUM + r"\s*" + TIME_UNIT + r"(?![a-z])|ogni\s+" + NUM + r"\s*" + TIME_UNIT + r"(?![a-z])", c)
                    if m:
                        g = [x for x in m.groups() if x]
                        v = _hours(num(g[0]), g[1])
                put("revisit_max_h", v, rid)
            if re.search(LATENCY, c):
                put("latency_h", _threshold(c, LATENCY), rid)
            elif re.search(DELIVERY, c):
                m = re.search(DELIVERY + r"[^;]{0,90}?(?:within|in less than|entro|in meno di)\s+" + NUM + r"\s*" + TIME_UNIT + r"(?![a-z])", c)
                if m:
                    put("latency_h", _hours(num(m.group(1)), m.group(2)), rid)
        m = re.search(r"(?:re-?enter|re-?entry|deorbit|de-orbit|disposal|rientr[a-z]*|deorbit[a-z]*|smaltiment[a-z]*)[^.;]{0,60}?(?:within|in less than|no later than|entro|in meno di|non oltre)\s+" + NUM + r"\s*(years|year|anni|anno)", t)
        if m:
            put("reentry_years", num(m.group(1)), rid)
        m = re.search(r"(?:mission lifetime|mission duration|design life|lifetime|operational life|vita operativa|durata della missione|vita di progetto|vita utile)\s+(?:shall be\s+|of\s+|di\s+|pari a\s+)?(?:at least\s+|almeno\s+)?" + NUM + r"\s*(years|year|anni|anno|months|month|mesi|mese)", t) \
            or re.search(r"(?:for|per)\s+" + NUM + r"\s*(years|year|anni|months|month|mesi)\b", t)
        if m:
            v = num(m.group(1))
            put("lifetime_years", v / 12.0 if m.group(2).startswith(("month", "mes")) else v, rid)
        m = re.search(r"(?:depth of discharge|dod|profondita di scarica)[^.;]{0,50}?(?:below|lower than|not exceed[a-z]*|of at most|at most|under|<=|<|inferiore a|non superiore a|non (?:dovra |deve )?superare(?: il| l')?|massima del|del|of)\s*" + NUM + r"\s*(?:%|percent|per cent|per cento)", t)
        if m:
            put("dod_max_pct", num(m.group(1)), rid)
        m = re.search(r"(?:fainter than|dimmer than|magnitude (?:greater|higher|larger) than|magnitude above|magnitudine (?:superiore|maggiore) (?:a|di)|piu debole (?:della|di))\s*(?:magnitude\s+|magnitudine\s+|the\s+)?" + SNUM, t)
        if m:
            put("magnitude_min", num(m.group(1)), rid)
        m = (re.search(r"between\s+" + SNUM + r"\s*(?:°\s*)?c\s+and\s+" + SNUM + r"\s*(?:°\s*)?c\b", t)
             or re.search(r"(?:tra|fra)\s+" + SNUM + r"\s*(?:°\s*)?c\s+e\s+" + SNUM + r"\s*(?:°\s*)?c\b", t))
        if m:
            what = "battery" if has_any(t, ("battery", "batteries", "batteria", "batterie")) else "payload" if has_any(t, ("payload", "clock", "camera", "instrument", "strumento")) else "spacecraft"
            put("temp_range_c", {"min": num(m.group(1)), "max": num(m.group(2)), "item": what}, rid)
        if has_any(t, ("positive energy balance", "positive power balance", "energy balance shall be positive", "bilancio energetico positivo",
                       "bilancio di potenza positivo", "energy balance shall not be negative", "power budget shall be closed",
                       "shall be closed in sunlight", "bilancio energetico non negativo", "bilancio di potenza chiuso")) or                 re.search(r"(?:energy|power) (?:balance|budget)[^.;]{0,40}(?:not be negative|be closed|non (?:dovra essere|sia) negativo|chiuso)", t) or \
                re.search(r"bilancio (?:di potenza|energetico)[^.;]{0,40}(?:chiuso|non (?:dovra essere |deve essere |sia )?negativo|positivo)", t):
            put("energy_balance_positive", True, rid)
        if has_any(t, ("safe separation", "no close approaches", "close approaches", "avvicinamenti pericolosi", "separazione sicura", "collision", "collisions", "collisioni")):
            put("separation_check", True, rid)
        m = re.search(r"(?:start(?:ing|s)? on|launch(?:ed)? on|a partire dal|dal)\s+(\d{1,2})\s+([a-z]+)\s+(\d{4})(?:\s+(?:at|alle)\s+(\d{1,2}):(\d{2}))?", t)
        if m and m.group(2) in MONTHS:
            put("start", [int(m.group(3)), MONTHS[m.group(2)], int(m.group(1)), int(m.group(4) or 0), int(m.group(5) or 0)], rid)
        m = re.search(r"drag (?:cross[- ]section|area) of\s+" + NUM + r"\s*m", t)
        if m:
            put("adrag", num(m.group(1)), rid)
        m = re.search(r"drag coefficient of\s+" + NUM, t)
        if m:
            put("cd", num(m.group(1)), rid)
    # an inclination that is not Sun-synchronous with no family stated: an inclined repeat ground track
    if "orbit" not in found and "incl" in found and not 94.0 <= found["incl"][0] <= 106.0:
        found["orbit"] = ("RGT (generally inclined)", found["incl"][1])
    return found


MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
                                      "november", "december"], start=1)}
MONTHS.update({m: i for i, m in enumerate(["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre",
                                           "ottobre", "novembre", "dicembre"], start=1)})

# --------------------------------------------------------------------------- places
AOI_CONTEXT = ("area", "areas", "region", "regions", "territory", "target", "targets", "coverage", "cover", "covering", "monitor", "monitoring",
               "observe", "observation", "observations", "image", "images", "imaging", "imagery", "over", "scene", "site", "sites", "zone",
               "land", "coast", "coasts", "basin", "country", "countries", "interest", "regione", "regioni", "territorio", "copertura",
               "monitoraggio", "osservazione", "immagini", "sopra", "sito", "siti", "zona", "zone", "coste", "bacino", "paese", "interesse",
               "acquisizioni", "acquisitions", "acquire", "mapping", "map", "mappatura")
STATION_CONTEXT = ("ground station", "ground stations", "station", "stations", "teleport", "downlink", "downlinked", "uplink", "antenna",
                   "space centre", "space center", "centro spaziale", "stazione", "stazioni", "stazione di terra", "stazioni di terra",
                   "observatory", "observatories", "telescope", "telescopes", "osservatorio", "osservatori", "telescopio", "telescopi",
                   "seen from", "visto da", "visti da", "scaricati", "scaricate")
COORD = re.compile(r"(?<![\d.])(\d{1,2}(?:[.,]\d+)?)\s*°?\s*(?:deg\s+)?(n|s|nord|sud)\b\s*,?\s*(?:and\s+|e\s+|longitude\s+|longitudine\s+)?"
                   r"(\d{1,3}(?:[.,]\d+)?)\s*°?\s*(?:deg\s+)?(e|w|o|est|ovest)\b")


@lru_cache(maxsize=1)
def italy_places() -> dict[str, Any]:
    try:
        return json.loads((CONFIG_DIR / "italy_places.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def coordinates(text: str) -> list[tuple[float, float]]:
    out = []
    t = re.sub(r"\b(?:latitude|latitudine|lat\.?)\s+", "", norm(text))
    for m in COORD.finditer(t):
        # corners of a latitude / longitude range ("36 deg N to 47 deg N, longitude 6 deg E to 19 deg E") are not points
        if re.search(r"(?:[ns]|nord|sud)\s+(?:to|-|a|fino a)\s*$", t[max(0, m.start() - 30): m.start()]) or \
                re.match(r"\s*(?:to|-|a|fino a)\s*\d", t[m.end(): m.end() + 12]):
            continue
        lat = num(m.group(1)) * (-1 if m.group(2).startswith("s") else 1)
        lon = num(m.group(3)) * (-1 if m.group(4) in ("w", "o", "ovest") else 1)
        if abs(lat) <= 90 and abs(lon) <= 180:
            out.append((lat, lon))
    return out


def _bbox_poly(b):
    la0, la1, lo0, lo1 = b
    return [[la0, lo0], [la0, lo1], [la1, lo1], [la1, lo0]]


def area_of_interest(texts) -> dict[str, Any]:
    """Italian area named in the texts (requirements and the description of the call). Returns
    {"region_settings": END-001 RegionSettings update or None, "places": [names], "points": [[lat, lon]],
     "station_points": [[lat, lon]], "why": text}. Station and observatory sentences are kept apart."""
    pl = italy_places()
    aoi_sents, station_sents = [], []
    for t in texts:
        for s in sentences(t) or [t]:
            if has_any(s, STATION_CONTEXT):
                station_sents.append(s)
            if has_any(s, AOI_CONTEXT) or not has_any(s, STATION_CONTEXT):
                aoi_sents.append(s)
    aoi_text = " \n ".join(aoi_sents)
    aoi_orig = "".join(ch for ch in unicodedata.normalize("NFKD", " \n ".join(aoi_sents)) if not unicodedata.combining(ch))

    def named(item) -> bool:
        if item.get("case_sensitive"):     # e.g. Potenza: "potenza" is the Italian word for power
            return any(re.search(r"(?<![A-Za-z0-9])" + re.escape(n) + r"(?![A-Za-z0-9])", aoi_orig) for n in item.get("names_case", []))
        return has_any(aoi_text, item["names"])

    station_pts = [p for s in station_sents for p in coordinates(s)]
    points = [p for s in aoi_sents if not has_any(s, STATION_CONTEXT) for p in coordinates(s)]
    found_boxes, found_points, names = [], [], []
    coasts = has_any(aoi_text, (pl.get("italian_coasts") or {}).get("names", []))
    longer = [n for g in ("macro_areas", "regions") for item in (pl.get(g) or {}).values() for n in item["names"]] + \
        list((pl.get("italian_coasts") or {}).get("names", []))
    italy = has_any(_phrase_re(tuple(longer)).sub(" ", norm(aoi_text)), (pl.get("italy") or {}).get("names", []))   # "southern italy" is not Italy
    for group in ("macro_areas", "regions"):
        for key, item in (pl.get(group) or {}).items():
            if named(item):
                found_boxes.append(item["bbox"]); names.append(key)
    for group in ("cities", "sites"):
        for key, item in (pl.get(group) or {}).items():
            if named(item) and not any(has_any(s, item["names"]) and has_any(s, STATION_CONTEXT) and not has_any(s, AOI_CONTEXT) for s in station_sents):
                found_points.append(item["lat_lon"]); names.append(key)
    if coasts:
        return {"region_settings": {"AreaofInterest": "Italian Coasts"}, "places": ["italian coasts"], "points": points,
                "station_points": station_pts, "why": "named area 'Italian Coasts'"}
    if italy:
        # the whole country is named: places and coordinates in it are examples or reference targets
        return {"region_settings": {"AreaofInterest": "Italy"}, "places": ["italy"] + names, "points": points, "station_points": station_pts,
                "why": "named area 'Italy'" + (" (" + ", ".join(names) + " inside it)" if names else "")}
    boxes = list(found_boxes)
    for lat, lon in list(found_points) + [list(p) for p in points]:
        boxes.append([lat - 0.5, lat + 0.5, lon - 0.5, lon + 0.5])
    if len(boxes) == 1 and not found_boxes:
        lat, lon = (list(found_points) + [list(p) for p in points])[0]
        return {"region_settings": {"AreaofInterest": "Custom", "CustomCoordinates": _bbox_poly(boxes[0])}, "places": names, "points": points,
                "station_points": station_pts, "why": f"point target ({lat}, {lon}): 1 x 1 deg square around it"}
    if boxes:
        b = [min(x[0] for x in boxes), max(x[1] for x in boxes), min(x[2] for x in boxes), max(x[3] for x in boxes)]
        return {"region_settings": {"AreaofInterest": "Custom", "CustomCoordinates": _bbox_poly([round(v, 3) for v in b])}, "places": names,
                "points": points, "station_points": station_pts,
                "why": "bounding box of " + ", ".join(names + [f"({p[0]}, {p[1]})" for p in points])}
    return {"region_settings": None, "places": [], "points": points, "station_points": station_pts, "why": "no Italian area named"}


# --------------------------------------------------------------------------- planner keywords
MODULE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "END-001": ("revisit", "coverage", "access", "constellation", "orbit", "orbits", "orbital", "acquisition opportunities", "latency",
                "ground station", "ground stations", "rivisita", "copertura", "costellazione", "orbita", "orbite", "latenza", "stazione di terra"),
    "END-003": ("attitude", "pointing", "quaternion", "quaternions", "attitude ephemeris", "aem", "slew", "line of sight", "nadir pointing",
                "assetto", "puntamento", "quaternioni"),
    "END-004": ("power", "power budget", "energy", "energy balance", "battery", "batteries", "solar array", "solar arrays", "solar panel",
                "solar panels", "duty cycle", "depth of discharge", "eps", "electrical power", "potenza", "bilancio di potenza", "energia",
                "bilancio energetico", "batteria", "batterie", "pannelli solari", "pannello solare", "ciclo di lavoro", "profondita di scarica"),
    "END-007": ("synthetic image", "synthetic images", "synthetic imagery", "simulated image", "simulated images", "simulated imagery",
                "simulated acquisition", "simulated acquisitions", "image simulation", "synthetic data", "synthetic dataset", "training dataset",
                "ground truth", "rendering", "rendered images", "immagini sintetiche", "immagini simulate", "simulazione delle immagini",
                "dati sintetici", "dataset sintetico",
                # scenario generation, part of END-007 since 2026-10-18 (the former END-006 Scenario Generation)
                "scenario generation", "scene generation", "terrain model", "digital terrain model", "digital elevation model",
                "3d scene", "generazione dello scenario", "generazione della scena", "modello del terreno",
                "modello digitale del terreno", "scena 3d"),
    "END-010": ("brightness", "apparent magnitude", "magnitude", "light curve", "light curves", "lightcurve", "photometry", "photometric",
                "reflectance", "albedo", "dark sky", "dark skies", "quiet skies", "light pollution", "astronomical observations",
                "astronomical observatory", "astronomical observatories", "night sky", "luminosita", "magnitudine", "curva di luce",
                "curve di luce", "fotometria", "riflettanza", "cielo buio", "inquinamento luminoso", "osservatorio astronomico",
                "osservatori astronomici", "osservazioni astronomiche"),
    "END-016": ("collision", "collisions", "conjunction", "conjunctions", "close approach", "close approaches", "space debris", "debris",
                "debris mitigation", "space safety", "space sustainability", "deorbit", "de-orbit", "disposal", "end of life", "post-mission",
                "re-enter", "reenter", "re-entry", "reentry", "orbital lifetime", "safe separation", "collisione", "collisioni", "detriti",
                "rientro", "rientrare", "fine vita", "smaltimento", "deorbitazione", "avvicinamenti", "separazione sicura", "vita orbitale"),
    "END-008": ("state of health", "battery health", "battery degradation", "battery ageing", "battery aging", "capacity fade",
                "remaining useful life", "battery end of life", "salute della batteria", "stato di salute", "degrado della batteria"),
    "END-019": ("thermal", "temperature", "temperatures", "overheating", "heat dissipation", "heat load", "termico", "termica", "termici",
                "termiche", "temperatura", "temperature", "surriscaldamento"),
    "END-006": ("cubesat", "cubesats", "satellite design", "component", "components", "subsystem", "subsystems", "bill of materials",
                "form factor", "platform", "componenti", "sottosistemi", "piattaforma"),
}


def modules_requested(text: str) -> dict[str, list[str]]:
    """{module_id: [matched words]} for the planner (whole words)."""
    return {mid: hits for mid, words in MODULE_KEYWORDS.items() if (hits := find_all(text, words))}

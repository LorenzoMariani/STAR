"""Progetto di un CubeSat per una missione (STAR, 2026-10-15): quali sottosistemi servono, quali componenti soddisfano i requisiti, la classe
piu' piccola che li porta tutti e i sottosistemi non richiesti, elencati a parte.

Ogni decisione e' una regola dichiarata applicata al testo dei requisiti o un confronto con i dati pubblicati dei fornitori, e cita il requisito
da cui viene. Nessun valore e' stimato: un componente che non pubblica il dato non puo' dimostrare di soddisfare il requisito.

Sottosistemi richiesti (regole dichiarate):
  * bus, sempre: struttura, OBC, EPS, batteria, celle solari, una radio con la sua antenna;
  * radio e antenna: una coppia per ogni banda nominata nei requisiti (UHF, VHF, S, X), altrimenti una;
  * ADCS: stabilizzazione, puntamento, assetto, oppure un payload che riprende immagini. Le unita' ADCS del catalogo sono sistemi completi
    (sensori e attuatori): ruote, magnetorquer, star tracker e sensori solari separati entrano solo se un requisito li nomina;
  * GNSS (ricevitore e antenna): posizione a bordo, determinazione orbitale, geolocalizzazione, sincronizzazione, formazione, separazione
    sicura o collisioni, oppure propulsione nel progetto;
  * propulsione: manovre (mantenimento dell'orbita, phasing, formazione, compensazione della resistenza, delta-v, rientro controllato),
    oppure END-016 nella stessa run: delta-v di smaltimento per la scadenza scritta nei requisiti, o orbita che decade prima della fine
    della missione;
  * imager: immagini, camera, GSD, swath; terminale ottico: link ottico o laser.
Requisiti verificati con i dati pubblicati:
  * GSD e swath dell'imager alla quota dell'orbita (al nadir sono proporzionali alla quota): quote di END-001 se ci sono, altrimenti la quota
    peggiore dell'intervallo dei requisiti (la piu' alta per il GSD, la piu' bassa per lo swath);
  * precisione di puntamento pubblicata dell'unita' ADCS; tre assi (escluse le unita' a ruota singola "Y-Momentum");
  * banda della radio e dell'antenna; delta-v del propulsore (impulso totale / somma delle masse pubblicate); massa massima del satellite;
  * pannello solare dispiegabile se i requisiti lo chiedono (nome del prodotto); la faccia del pannello segue sempre la classe
    (selector.CLASS_PANEL_FACES);
  * batteria: con END-004 nella stessa run, energia che la batteria da' in un'orbita (la scarica peggiore tra i modi volati, con il
    margine di END-004) diviso la profondita' di scarica massima dei requisiti (o della batteria, se pubblicata): capacita' minima. Se
    la batteria integrata in un EPS basta, il progetto senza batteria separata e' preferito a parita' di classe (un componente in meno);
  * radio: quella della banda piu' bassa riceve i telecomandi (ricevitore pubblicato); con un imager quella della banda piu' alta scarica
    le immagini: velocita' >= quella dei requisiti, altrimenti la piu' alta pubblicata tra le radio della sola banda che entra nel progetto;
    una radio che comprende la sua antenna ("+ ANT..." nel nome del prodotto) non ha l'antenna separata della sua banda;
  * propulsore: delta-v (impulso totale / massa), classe minima dichiarata dal fornitore, un propulsore elettrico deve funzionare con la
    potenza di picco del pannello solare scelto (selector, electric_power_check), propellente non tossico se richiesto; se nessuno da' il
    delta-v, quello con l'impulso piu' alto che entra nella classe scelta;
  * payload: classe minima dichiarata dal fornitore (selector), tipo di immagine (bande spettrali pubblicate: pancromatico, visibile,
    multi/iperspettrale, SWIR, infrarosso termico, RGB, video; push-broom = non "snapshot" nel nome), poi GSD e swath; terminale ottico:
    tipo di collegamento (verso terra o tra satelliti) e velocita';
  * OBC: almeno un'interfaccia dati in comune con ogni componente che pubblica le sue (selector, interface_check, vincolo nella ricerca
    esatta); dose totale di radiazione dei requisiti <= quella pubblicata;
  * EPS: classi dichiarate, almeno un ingresso solare, alimenta ogni componente che pubblica le tensioni (uscite regolate o batteria
    integrata), accetta la tensione del pannello e la batteria esterna, potenza massima >= componente piu' esigente (selector,
    power_supply_check, vincolo nella ricerca esatta);
  * ruote di reazione (quando nel progetto o suggerite tra i non richiesti): classe dichiarata dal fornitore (come l'ADCS), tre ruote
    con il controllo su tre assi (una per asse), momento di ciascuna >= inerzia x velocita' di rotazione richiesta (blocco uniforme con la
    massa limite e l'ingombro della classe, per eccesso).
  Se nessun componente del catalogo soddisfa tutti i requisiti di un posto si tengono quelli che ne soddisfano di piu' (nell'ordine in cui
  sono elencati: per l'imager il GSD prima dello swath) e il requisito mancato e' segnalato.
Classe: la piu' piccola tra 1U, 3U, 6U e 12U in cui i componenti richiesti stanno insieme (massa, volume, pila) e l'ingombro risulta "Fits";
una classe scelta dall'utente prevale. Una classe scritta nei requisiti e' solo riportata."""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Any, Callable

from .fit import check_fit
from .models import Component
from .rows import subsystem_of
from .selector import (CLASSES, LABELS, SUBSYSTEMS, Selection, Slot, battery_ok, eps_rails, firing_power_w, interfaces, is_electric, panel_ok,
                       panel_on_structure, panel_voltages, powered_by, structure_envelope, supply_ranges, total_impulse_ns,
                       wheel_momentum_needed_mnms)
from .selector import select as _select


def select(*args: Any, **kwargs: Any) -> Selection:
    """La selezione del progetto per la missione: un propulsore elettrico deve funzionare con la potenza del pannello solare scelto e l'OBC
    deve avere un'interfaccia dati in comune con ogni componente che pubblica le sue."""
    kwargs.setdefault("electric_power_check", True)
    kwargs.setdefault("interface_check", True)
    kwargs.setdefault("power_supply_check", True)
    return _select(*args, **kwargs)

NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
             "fifteen": 15, "twenty": 20, "twenty-five": 25, "thirty": 30}
BANDS = (("UHF", r"\buhf\b"), ("VHF", r"\bvhf\b"), ("S", r"\bs[- ]band\b"), ("X", r"\bx[- ]band\b"))
BAND_ORDER = {"VHF": 0, "UHF": 1, "S": 2, "X": 3, "COMMS": 1}     # dalla frequenza piu' bassa; "comms" = una sola radio senza banda nominata
BUS = ("structure", "obc", "eps", "battery", "solar_panel", "comms", "antenna")
# esiti del controllo di ingombro con cui una classe e' accettata: "undetermined" = a un componente mancano le quote pubblicate (massa,
# volume e pila noti entro i limiti; non e' dimostrato che non entri: l'avviso resta nell'esito)
ACCEPTED_FIT = ("fits", "undetermined")
ADCS_PARTS = ("magnetorquer", "reaction_wheel", "star_tracker", "sun_sensor")
NUM = r"(\d+(?:\.\d+)?)"

RULES: dict[str, tuple[str, str]] = {   # sottosistema -> (espressione sul testo dei requisiti, motivo)
    "adcs": (r"\b(three-axis|3-axis|stabili[sz]\w*|pointing|point\w* (nominally )?at nadir|nadir[- ]pointing|attitude)\b",
             "the mission asks for attitude control"),
    "payload_imager": (r"\b(camera|imager|images?|imaging|push-?broom|ground sample distance|gsd|swath|multispectral|hyperspectral|panchromatic)\b",
                       "the mission takes images"),
    "payload_optical": (r"\b(optical|laser)[- ](communication|terminal|link|downlink)s?\b|\blasercom\b", "the mission asks for an optical link"),
    "propulsion": (r"\b(man(o)?euv\w*|orbit (maintenance|raising|lowering|transfer|control)|station[- ]keeping|drag (compensation|make-?up)|"
                   r"phasing|formation[- ](flying|keeping)|delta-?v|controlled re-?entry|de-?orbit\w* (burn|manoeuvre|maneuver))\b",
                   "the mission asks for manoeuvres"),
    "gps": (r"\b(gnss|gps|position knowledge|on-?board position|orbit determination|geolocat\w*|georeferenc\w*|time[- ]tagg\w*|"
            r"formation|safe separation|collision\w*|close approach\w*)\b", "the mission needs the satellite position on board"),
    "magnetorquer": (r"\b(magnetorquer|magnetic torquer|torque rod)s?\b", "named in the requirements"),
    "reaction_wheel": (r"\breaction wheels?\b", "named in the requirements"),
    "star_tracker": (r"\bstar trackers?\b", "named in the requirements"),
    "sun_sensor": (r"\bsun sensors?\b", "named in the requirements"),
}
# tipo di immagine chiesto dai requisiti -> bande spettrali pubblicate che lo danno (specs.spectral_bands del catalogo)
IMAGE_TYPES = (
    (r"\bpanchromatic\b", {"PAN", "MONO"}, "panchromatic channel"),
    (r"\bvisible\b", {"PAN", "RGB", "VNIR", "MONO", "MS", "HS"}, "visible spectrum"),
    (r"\bmulti-?spectral\b", {"MS"}, "multispectral bands"),
    (r"\bhyper-?spectral\b", {"HS"}, "hyperspectral bands"),
    (r"\bswir\b|\bshort-?wave infra-?red\b", {"SWIR"}, "short-wave infrared"),
    (r"\bthermal infra-?red\b|\btir\b|\blwir\b|\blong-?wave infra-?red\b", {"TIR", "LWIR"}, "thermal infrared"),
    (r"\brgb\b|\bcolou?r (images?|camera)\b", {"RGB"}, "colour (RGB)"),
    (r"\bvideo\b", {"VIDEO"}, "video"),
)
NOUNS = {"payload_imager": "payload imager", "payload_optical": "optical terminal", "comms": "radio", "antenna": "antenna", "adcs": "ADCS unit",
         "propulsion": "thruster", "gps": "GNSS receiver", "gnss_antenna": "GNSS antenna", "solar_panel": "solar panel"}
NOT_REQUIRED = {
    "adcs": "no requirement asks for attitude control or images",
    "payload_imager": "no requirement asks for images",
    "payload_optical": "no requirement asks for an optical link",
    "propulsion": "no requirement asks for manoeuvres and no delta-v is needed",
    "gps": "no requirement needs the satellite position on board", "gnss_antenna": "no requirement needs the satellite position on board",
}


@dataclass
class Req:
    id: str
    text: str

    @property
    def low(self) -> str:
        return re.sub(r"\s+", " ", self.text.lower())

    def as_dict(self) -> dict[str, str]:
        return {"id": self.id, "text": self.text}


@dataclass
class Check:
    """Un requisito verificabile con i dati pubblicati. test(componente) -> True/False (None = dato non pubblicato) per i requisiti di un posto."""
    key: str
    slot: str | None
    req: Req | None
    what: str
    test: Callable[[Component], bool | None] | None = None
    value: Callable[[Component], str | None] | None = None
    status: str = "met"            # met | not_met | not_verifiable
    message: str = ""


@dataclass
class Need:
    slot: Slot
    why: str
    req: Req | None
    source: str                    # bus | requirement | END-016 | rule
    checks: list[Check] = field(default_factory=list)


def _reqs(requirements: Any) -> list[Req]:
    if isinstance(requirements, str):
        requirements = [requirements]
    out = []
    for i, r in enumerate(requirements or [], start=1):
        if isinstance(r, dict):
            out.append(Req(str(r.get("id") or f"REQ-{i:03d}"), str(r.get("text") or "")))
        else:
            out.append(Req(f"REQ-{i:03d}", str(r)))
    return [r for r in out if r.text.strip()]


def _find(reqs: list[Req], rx: str) -> tuple[Req, re.Match] | None:
    for r in reqs:
        m = re.search(rx, r.low)
        if m:
            return r, m
    return None


def _num(word: str) -> float | None:
    try:
        return float(word)
    except ValueError:
        return NUM_WORDS.get(word.lower())


def _scaled(c: Component, key: str, h_km: float) -> float | None:
    """GSD o swath pubblicato alla quota di riferimento del fornitore, riportato alla quota h (al nadir sono proporzionali alla quota)."""
    v, ref = c.spec(key), c.spec("reference_altitude_km")
    if v is None or not ref:
        return None
    return float(v) * h_km / float(ref)


def altitude_from_requirements(reqs: list[Req]) -> tuple[float, float, Req] | None:
    for r in reqs:
        if "altitude" not in r.low and "orbit" not in r.low:
            continue
        m = re.search(rf"{NUM}\s*km\s*(?:and|to|-|–)\s*{NUM}\s*km", r.low) or re.search(rf"between {NUM} and {NUM}\s*km", r.low)
        if m:
            a, b = float(m.group(1)), float(m.group(2))
            return min(a, b), max(a, b), r
        m = re.search(rf"(?:altitude of|at an altitude of|at) {NUM}\s*km", r.low) or re.search(rf"{NUM}\s*km (?:of )?altitude", r.low)
        if m:
            return float(m.group(1)), float(m.group(1)), r
    return None


# --------------------------------------------------------------------------- analisi dei requisiti


def analyse(requirements: Any, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Sottosistemi richiesti (posti), requisiti verificabili, delta-v e massa massima. context: {"altitude_km": [min, max], "altitude_source",
    "end016": riepilogo di END-016 (space_safety_summary.json)}."""
    ctx = context or {}
    reqs = _reqs(requirements)
    needs: dict[str, Need] = {}
    notes: list[str] = []

    # quota dell'orbita: END-001 della stessa run, altrimenti l'intervallo dei requisiti
    alt = None
    if ctx.get("altitude_km"):
        v = ctx["altitude_km"]
        lo, hi = (v, v) if isinstance(v, (int, float)) else (min(v), max(v))
        alt = {"min_km": float(lo), "max_km": float(hi), "source": ctx.get("altitude_source") or "END-001 (designed orbits)", "req": None}
    elif (a := altitude_from_requirements(reqs)):
        alt = {"min_km": a[0], "max_km": a[1], "source": f"{a[2].id} (altitude range of the requirements)", "req": a[2]}

    def need(sid: str, why: str, req: Req | None, source: str, slot_id: str | None = None, label: str | None = None) -> Need:
        sid_slot = slot_id or sid
        if sid_slot not in needs:
            needs[sid_slot] = Need(Slot(sid_slot, sid, label or LABELS[sid]), why, req, source)
        return needs[sid_slot]

    # bus; radio e antenna per banda
    bands = []
    for band, rx in BANDS:
        hit = _find(reqs, rx)
        if hit:
            bands.append((band, hit[0]))
    for sid in BUS:
        if sid in ("comms", "antenna") and bands:
            continue
        need(sid, "every CubeSat needs it", None, "bus")
    for band, r in bands:
        tag = band.lower()
        radio = need("comms", f"{band}-band link of the mission", r, "requirement", f"comms_{tag}", f"COMMS RADIO · {band}")
        radio.checks.append(Check("band", radio.slot.id, r, f"radio in {band} band",
                                  lambda c, b=band: None if not c.spec("band") else b in str(c.spec("band")).upper().replace("-BAND", "").split("/"),
                                  lambda c: c.spec("band")))
        ant = need("antenna", f"antenna of the {band} radio", r, "requirement", f"antenna_{tag}", f"ANTENNA · {band}")
        ant.checks.append(Check("band", ant.slot.id, r, f"antenna in {band} band",
                                lambda c, b=band: None if not c.spec("bands") else b in [str(x).upper() for x in c.spec("bands")],
                                lambda c: ", ".join(c.spec("bands") or []) or None))

    # sottosistemi richiesti dai requisiti
    for sid in ("payload_imager", "payload_optical", "adcs", "magnetorquer", "reaction_wheel", "star_tracker", "sun_sensor", "gps", "propulsion"):
        rx, why = RULES[sid]
        hit = _find(reqs, rx)
        if hit:
            need(sid, why, hit[0], "requirement")
    if "payload_imager" in needs and "adcs" not in needs:
        need("adcs", "an imaging payload needs pointing", needs["payload_imager"].req, "rule")

    # radio (regole dichiarate): la radio della banda piu' bassa riceve i telecomandi (ricetrasmettitore); con un imager, la radio della
    # banda piu' alta scarica le immagini: la velocita' scritta nei requisiti, altrimenti la piu' alta pubblicata che entra nel progetto
    radio_slots = sorted([nd for nd in needs.values() if nd.slot.subsystem == "comms"], key=lambda nd: BAND_ORDER.get(nd.slot.id.split("_")[-1].upper(), 9))
    ttc_radio = radio_slots[0] if radio_slots else None
    data_radio = radio_slots[-1] if radio_slots and "payload_imager" in needs else None
    if ttc_radio:
        hit = _find(reqs, r"\b(uplink|telecommand\w*|tele-?command\w*|commanded|commands)\b")
        ttc_radio.checks.append(Check("receiver", ttc_radio.slot.id, hit[0] if hit else None, "receiver for the telecommands",
                                      lambda c: None if c.spec("has_receiver") is None else bool(c.spec("has_receiver")),
                                      lambda c: None if c.spec("has_receiver") is None else ("transceiver" if c.spec("has_receiver") else "transmitter only")))
        if len(radio_slots) > 1:
            ttc_radio.why += "; it receives the telecommands"
    data_rate = None
    if data_radio:
        if (hit := _find(reqs, rf"(?:data rate|downlink rate|bit rate)[^.\d]{{0,30}}?{NUM}\s*(kbps|kbit/s|mbps|mbit/s|gbps|gbit/s)")):
            kbps = float(hit[1].group(1)) * {"k": 1.0, "m": 1e3, "g": 1e6}[hit[1].group(2)[0]]
            data_rate = {"kbps": kbps, "req": hit[0]}
            data_radio.checks.append(Check("data_rate", data_radio.slot.id, hit[0], f"data rate >= {kbps / 1e3:g} Mbps",
                                           lambda c, k=kbps: None if c.spec("data_rate_kbps_max") is None else float(c.spec("data_rate_kbps_max")) >= k - 1e-9,
                                           lambda c: None if c.spec("data_rate_kbps_max") is None else f"{float(c.spec('data_rate_kbps_max')) / 1e3:g} Mbps"))
        data_radio.why += "; it downlinks the images"

    # delta-v: scritto nei requisiti, oppure calcolato da END-016 per la scadenza di smaltimento dei requisiti
    dv: dict[str, Any] | None = None
    if (hit := _find(reqs, rf"delta-?v[^.\d]{{0,30}}?{NUM}\s*m/s")):
        dv = {"dv_m_s": float(hit[1].group(1)), "why": f"delta-v of {float(hit[1].group(1)):g} m/s", "req": hit[0], "source": "requirement"}
    e16 = ctx.get("end016") or None
    if dv is None and e16:
        k = e16.get("kpis") or {}
        total, parts, req = 0.0, [], None
        hit = _find(reqs, r"(?:re-?enter|de-?orbit|dispos)\w*[^.]*?within (\d+|[a-z-]+) years")
        if hit and (years := _num(hit[1].group(1))):
            d = k.get(f"disposal_dv_m_s_{int(years)}y_rule_mean_activity")
            if isinstance(d, (int, float)) and d > 0:
                total += float(d)
                life = k.get("passive_lifetime_years_mean_activity")
                parts.append(f"re-entry within {int(years)} years ({hit[0].id}) needs {d:.1f} m/s"
                             + (f": passive lifetime {life:.1f} years at mean solar activity" if isinstance(life, (int, float)) else ""))
                req = hit[0]
            elif d is None:
                notes.append(f"END-016 has no disposal delta-v for the {int(years)}-year deadline of {hit[0].id}.")
        if k.get("orbit_maintenance_needed"):
            years = (e16.get("config") or {}).get("mission_lifetime_years")
            rate = k.get("drag_makeup_dv_m_s_per_year_mean_activity")
            if isinstance(years, (int, float)) and isinstance(rate, (int, float)):
                total += rate * years
                parts.append(f"the orbit decays before the end of the mission: drag make-up {rate:.2f} m/s per year for {years:g} years")
        if total > 0:
            dv = {"dv_m_s": total, "why": "END-016 of this run: " + "; ".join(parts) + " (spacecraft mass and drag area of END-001)", "req": req, "source": "END-016"}
    if dv is not None and "propulsion" not in needs:
        need("propulsion", dv["why"], dv["req"], dv["source"])
    if "propulsion" in needs:
        for sid in ("gps",):
            need(sid, "manoeuvres need the orbit on board", needs["propulsion"].req, "rule")
    if "gps" in needs:
        need("gnss_antenna", "antenna of the GNSS receiver", needs["gps"].req, needs["gps"].source)

    # requisiti verificabili dei posti
    if "payload_imager" in needs:
        img = needs["payload_imager"]
        # tipo di immagine prima del GSD e dello swath (se nessuna camera li soddisfa tutti, conta prima il tipo): bande spettrali
        # pubblicate, push-broom (una camera "snapshot" nel nome del prodotto non lo e')
        for rx, bands, what in IMAGE_TYPES:
            if (hit := _find(reqs, rx)):
                img.checks.append(Check("bands", img.slot.id, hit[0], what,
                                        lambda c, b=bands: None if not c.spec("spectral_bands") else bool({str(x).upper() for x in c.spec("spectral_bands")} & b),
                                        lambda c: ", ".join(c.spec("spectral_bands") or []) or None))
        if (hit := _find(reqs, r"\bpush-?broom\b")):
            img.checks.append(Check("pushbroom", img.slot.id, hit[0], "push-broom camera (not a snapshot camera)",
                                    lambda c: "snapshot" not in str(c.raw.get("name", "")).lower(),
                                    lambda c: "snapshot camera" if "snapshot" in str(c.raw.get("name", "")).lower() else "not a snapshot camera"))
        if (hit := _find(reqs, rf"(?:ground sample distance|gsd)[^.\d]{{0,40}}?{NUM}\s*m\b")):
            g = float(hit[1].group(1))
            if alt:
                h = alt["max_km"]
                img.checks.append(Check("gsd", img.slot.id, hit[0], f"GSD <= {g:g} m at {h:.0f} km",
                                        lambda c, h=h, g=g: None if (v := _scaled(c, "gsd_m_at_ref", h)) is None else v <= g + 1e-9,
                                        lambda c, h=h: None if (v := _scaled(c, "gsd_m_at_ref", h)) is None else f"{v:.2f} m at {h:.0f} km"))
            else:
                img.checks.append(Check("gsd", img.slot.id, hit[0], f"GSD <= {g:g} m", status="not_verifiable",
                                        message=f"{hit[0].id}: GSD {g:g} m not verifiable: the orbit altitude is not known (no END-001 orbits, no altitude in the requirements)."))
        if (hit := _find(reqs, rf"swath[^.\d]{{0,30}}?{NUM}\s*km")):
            s = float(hit[1].group(1))
            if alt:
                h = alt["min_km"]
                img.checks.append(Check("swath", img.slot.id, hit[0], f"swath >= {s:g} km at {h:.0f} km",
                                        lambda c, h=h, s=s: None if (v := _scaled(c, "swath_km_at_ref", h)) is None else v >= s - 1e-9,
                                        lambda c, h=h: None if (v := _scaled(c, "swath_km_at_ref", h)) is None else f"{v:.1f} km at {h:.0f} km"))
            else:
                img.checks.append(Check("swath", img.slot.id, hit[0], f"swath >= {s:g} km", status="not_verifiable",
                                        message=f"{hit[0].id}: swath {s:g} km not verifiable: the orbit altitude is not known."))
    # OBC: dose totale di radiazione dei requisiti <= quella pubblicata (tid_krad)
    if (hit := _find(reqs, rf"(?:total ionizing dose|total ionising dose|\btid\b|radiation)[^.\d]{{0,40}}?{NUM}\s*krad")):
        krad = float(hit[1].group(1))
        ob = needs["obc"]
        ob.checks.append(Check("tid", ob.slot.id, hit[0], f"radiation tolerance >= {krad:g} krad (TID)",
                               lambda c, k=krad: None if c.raw.get("tid_krad") is None else float(c.raw["tid_krad"]) >= k - 1e-9,
                               lambda c: None if c.raw.get("tid_krad") is None else f"{c.raw['tid_krad']:g} krad"))
    if "payload_optical" in needs:      # terminale ottico: tipo di collegamento e velocita' pubblicati
        op = needs["payload_optical"]
        if (hit := _find(reqs, r"\binter-?satellite\b|\bcross-?links?\b|\bsatellite-to-satellite\b")):
            op.checks.append(Check("link", op.slot.id, hit[0], "inter-satellite optical link",
                                   lambda c: None if not c.spec("link_type") else c.spec("link_type") in ("inter_satellite", "both"),
                                   lambda c: str(c.spec("link_type") or "").replace("_", " ") or None))
        elif (hit := _find(reqs, r"(optical|laser)[^.]*\b(downlink|to the ground|ground station)")):
            op.checks.append(Check("link", op.slot.id, hit[0], "optical link to the ground",
                                   lambda c: None if not c.spec("link_type") else c.spec("link_type") in ("space_to_ground", "both"),
                                   lambda c: str(c.spec("link_type") or "").replace("_", " ") or None))
        if (hit := _find(reqs, rf"(?:optical|laser)[^.]*?{NUM}\s*(gbps|gbit/s|mbps|mbit/s)")):
            mbps = float(hit[1].group(1)) * (1e3 if hit[1].group(2).startswith("g") else 1.0)
            op.checks.append(Check("optical_rate", op.slot.id, hit[0], f"optical link rate >= {mbps:g} Mbps",
                                   lambda c, r=mbps: None if c.spec("link_data_rate_mbps") is None else float(c.spec("link_data_rate_mbps")) >= r - 1e-9,
                                   lambda c: None if c.spec("link_data_rate_mbps") is None else f"{float(c.spec('link_data_rate_mbps')):g} Mbps"))
    if "adcs" in needs:
        ad = needs["adcs"]
        if (hit := _find(reqs, rf"pointing accuracy[^.\d]{{0,30}}?{NUM}\s*(deg|degrees?|arcsec|arc-?seconds?)")):
            acc = float(hit[1].group(1)) / (3600.0 if hit[1].group(2).startswith("arc") else 1.0)
            ad.checks.append(Check("pointing", ad.slot.id, hit[0], f"pointing accuracy <= {acc:g} deg",
                                   lambda c, a=acc: None if c.spec("pointing_accuracy_deg") is None else float(c.spec("pointing_accuracy_deg")) <= a + 1e-12,
                                   lambda c: None if c.spec("pointing_accuracy_deg") is None else f"{c.spec('pointing_accuracy_deg'):g} deg"))
        if (hit := _find(reqs, r"\b(three-axis|3-axis)\b")):
            ad.checks.append(Check("three_axis", ad.slot.id, hit[0], "three-axis control",
                                   lambda c: "y-momentum" not in str(c.raw.get("name", "")).lower(),
                                   lambda c: "single-wheel momentum bias" if "y-momentum" in str(c.raw.get("name", "")).lower() else "three-axis"))
    if (hit := _find(reqs, r"deployable (solar )?(panel|array)s?|solar (panel|array)s?[^.]{0,40}deployable")):
        sp = needs["solar_panel"]       # il pannello e' gia' quello della faccia della classe (selector.CLASS_PANEL_FACES); qui: dispiegabile
        sp.checks.append(Check("deployable", sp.slot.id, hit[0], "deployable solar panel",
                               lambda c: "deployable" in str(c.raw.get("name", "")).lower(),
                               lambda c: "deployable" if "deployable" in str(c.raw.get("name", "")).lower() else "body-mounted"))
    # batteria: energia che deve dare in un'orbita (END-004 della stessa run, con il suo margine) e profondita' di scarica massima dei
    # requisiti: capacita' x min(DoD dei requisiti, DoD massima pubblicata) >= energia per orbita
    dod = None
    if (hit := _find(reqs, rf"depth of discharge[^.\d]{{0,40}}?{NUM}\s*(?:%|percent|per cent)")):
        dod = {"fraction": float(hit[1].group(1)) / 100.0, "req": hit[0]}
    battery = None
    e4 = ctx.get("end004") or None
    if e4:
        cap4 = (e4.get("orbit") or {}).get("batteryCapacityWh") or ((e4.get("input_config") or {}).get("battery") or {}).get("capacity_Wh")
        modes = [m for m in e4.get("mode_summaries") or [] if (m.get("orbits_per_day") or 0) > 0] or list(e4.get("mode_summaries") or [])
        vals = [(float(m["orbital_DoD"]) * float(cap4), str(m.get("mode") or m.get("mode_key"))) for m in modes
                if isinstance(m.get("orbital_DoD"), (int, float)) and cap4]
        if vals:
            e_wh, mode = max(vals)
            limit = dod["fraction"] if dod else 1.0
            battery = {"energy_wh": e_wh, "mode": mode, "dod": limit, "need_wh": e_wh / limit, "req": dod["req"] if dod else None,
                       "why": f"END-004 of this run: the battery gives up to {e_wh:.2f} Wh in an orbit ({mode}, END-004 subsystem powers, "
                              f"duty cycles and margin)" + (f"; depth of discharge <= {100 * limit:g}% ({dod['req'].id})" if dod else "")}
            bat = needs["battery"]
            bat.checks.append(Check("battery", bat.slot.id, battery["req"], f"capacity >= {battery['need_wh']:.1f} Wh",
                                    lambda c, b=battery: None if not c.spec("capacity_wh") else
                                    float(c.spec("capacity_wh")) * min(b["dod"], float(c.spec("max_dod") or 1.0)) >= b["energy_wh"] - 1e-9,
                                    lambda c: None if not c.spec("capacity_wh") else f"{c.spec('capacity_wh'):g} Wh"))
    elif dod:
        bat = needs["battery"]
        bat.checks.append(Check("battery", bat.slot.id, dod["req"], f"depth of discharge <= {100 * dod['fraction']:g}%", status="not_verifiable",
                                message=f"{dod['req'].id}: the battery capacity is not verifiable: the energy per orbit comes from END-004 Power Budget, "
                                        "which is not in this run."))
    if "propulsion" in needs and (hit := _find(reqs, r"\b(non-?toxic|green) propellants?|\bhydrazine[- ]free\b|\bno hydrazine\b|\bwithout hydrazine\b")):
        needs["propulsion"].checks.append(Check("green", "propulsion", hit[0], "non-toxic propellant (no hydrazine)",
                                                lambda c: None if c.spec("propellant") is None else "hydrazine" not in str(c.spec("propellant")).lower(),
                                                lambda c: c.spec("propellant")))
    if dv is not None:
        needs["propulsion"].checks.append(Check("dv", "propulsion", dv["req"], f"delta-v >= {dv['dv_m_s']:.1f} m/s",
                                                lambda c: None if total_impulse_ns(c) is None else True,
                                                lambda c: None if total_impulse_ns(c) is None else f"total impulse {total_impulse_ns(c):g} N·s"))
    mass_limit = None
    if (hit := _find(reqs, rf"mass[^.\d]{{0,40}}?(?:not exceeding|not exceed|of at most|at most|no more than|below|up to|less than|<=?)\s*{NUM}\s*kg")):
        mass_limit = {"kg": float(hit[1].group(1)), "req": hit[0]}

    stated = None
    if (hit := _find(reqs, r"\b(1|3|6|12)\s*-?\s*u\b(?!\w)") or _find(reqs, r"\b(1|3|6|12)\s*-?\s*unit\s+cubesat")):
        stated = {"class_u": int(hit[1].group(1)), "req": hit[0]}

    order = {sid: n for n, (sid, _, _) in enumerate(SUBSYSTEMS)}
    ordered = sorted(needs.values(), key=lambda nd: (order[nd.slot.subsystem], nd.slot.id))
    # ruote di reazione: una per asse con il controllo su tre assi (altrimenti una, a momento costante); la velocita' di rotazione richiesta
    # fissa il momento di ciascuna (selector.wheel_momentum_needed_mnms)
    slew = _find(reqs, rf"slew(?:ing)?[^.\d]{{0,40}}?{NUM}\s*(?:deg|degrees?|°)\s*(?:/|per )\s*s")
    wheels = {"quantity": 3 if _find(reqs, r"\b(three-axis|3-axis)\b") else 1,
              "slew_deg_s": float(slew[1].group(1)) if slew else None, "req": slew[0] if slew else None}
    if "reaction_wheel" in needs:
        nd = needs["reaction_wheel"]
        nd.slot = replace(nd.slot, quantity=wheels["quantity"], slew_rate_deg_s=wheels["slew_deg_s"])
    return {"reqs": reqs, "needs": ordered, "wheels": wheels, "dv": dv, "mass_limit": mass_limit, "stated": stated, "altitude": alt, "battery": battery,
            "data_radio": data_radio.slot.id if data_radio else None, "data_rate": data_rate, "notes": notes}


# --------------------------------------------------------------------------- componenti ammessi per posto


def _allowed(catalog: list[Component], nd: Need) -> tuple[frozenset[str] | None, list[Check]]:
    """Componenti del posto che soddisfano i suoi requisiti; se nessuno li soddisfa tutti, quelli che ne soddisfano di piu' (nell'ordine dei
    requisiti). Restituisce (id ammessi o None = tutti, requisiti non soddisfatti da nessun componente del catalogo)."""
    tests = [ck for ck in nd.checks if ck.test is not None and ck.status != "not_verifiable"]
    if not tests:
        return None, []
    members = [c for c in catalog if subsystem_of(c) == nd.slot.subsystem]
    scored = [(tuple(bool(ck.test(c)) for ck in tests), c) for c in members]
    full = tuple(True for _ in tests)
    ok = [c for s, c in scored if s == full]
    if ok:
        return frozenset(c.id for c in ok), []
    if not scored:
        return None, tests
    best = max(s for s, _ in scored)
    unmet = [ck for ck, met in zip(tests, best) if not met]
    return frozenset(c.id for s, c in scored if s == best), unmet


# --------------------------------------------------------------------------- progetto


def _class_reason(sel: Selection, fit: dict[str, Any], dv: float | None, catalog, slots, mass_limit) -> str:
    missing = [r for r in sel.subsystems if r.selected is None]
    if missing:
        larger = [r.label for r in missing if r.note and "for larger CubeSats" in r.note]
        other = [r.label for r in missing if r.label not in larger]
        return "; ".join(filter(None, [f"{', '.join(larger)} declared by the vendor for larger CubeSats only" if larger else "",
                                       f"no component fits for {', '.join(other)}" if other else ""]))
    cls = sel.cubesat
    if not sel.within_limits:
        idx = [r for r in sel.subsystems if r.selected]
        lo_mass = sum(min((k.mass_kg or 0.0) for k in [r.selected, *r.alternatives]) for r in idx)
        lo_vol = sum(min((k.volume_m3 or 0.0) for k in [r.selected, *r.alternatives]) for r in idx)
        if lo_mass > cls.mass_limit_kg + 1e-9:
            return f"even the lightest components weigh {lo_mass:.2f} kg > {cls.mass_limit_kg:g} kg"
        if lo_vol > cls.volume_limit_m3 + 1e-15:
            return f"even the smallest internal components need {lo_vol:.3e} m³ > {cls.volume_limit_m3:.3e} m³"
        if dv and select(catalog, cls.units, 1.0, slots=slots, mass_limit_kg=mass_limit).within_limits:
            return f"no thruster that fits gives {dv:.1f} m/s to the whole satellite"
        return "the components do not fit together (mass, volume or stack)"
    return fit["label"] if fit["state"] != "fits" else "fits"


def design(catalog: list[Component], requirements: Any, context: dict[str, Any] | None = None, forced_class_u: int | None = None,
           time_budget_s: float = 2.0) -> tuple[Selection, dict[str, Any]]:
    """Selezione dei soli sottosistemi richiesti nella classe piu' piccola che li porta (o in quella scelta dall'utente) + il blocco "mission"."""
    a = analyse(requirements, context)
    needs: list[Need] = a["needs"]
    unmet: list[Check] = []
    slots: list[Slot] = []
    for nd in needs:
        allowed, bad = _allowed(catalog, nd)
        for ck in bad:
            ck.status = "not_met"
        unmet += bad
        slots.append(replace(nd.slot, allowed=allowed))
    dv = a["dv"]["dv_m_s"] if a["dv"] else None
    mass_limit = a["mass_limit"]["kg"] if a["mass_limit"] else None
    classes = [forced_class_u] if forced_class_u else sorted(CLASSES)

    # batteria: con il fabbisogno di END-004 si prova anche il progetto senza batteria separata, con un EPS la cui batteria integrata basta
    # (un componente in meno: preferito a parita' di classe)
    bat = a["battery"]
    variants: list[tuple[str, list[Slot]]] = [("separate", slots)]
    eps_wh: dict[str, float] = {}
    if bat:
        eps_wh = {c.id: float(c.spec("integrated_battery_wh")) for c in catalog
                  if subsystem_of(c) == "eps" and c.spec("integrated_battery_wh") and float(c.spec("integrated_battery_wh")) * bat["dod"] >= bat["energy_wh"] - 1e-9}
        if eps_wh:
            ok_eps = frozenset(eps_wh)
            variants.insert(0, ("eps", [replace(s, allowed=ok_eps if s.allowed is None else s.allowed & ok_eps) if s.subsystem == "eps" else s
                                        for s in slots if s.subsystem != "battery"]))

    def search(slots_x, dv_x, ml_x):
        log, found = [], None
        for u in classes:
            sel = select(catalog, u, time_budget_s, slots=slots_x, dv_m_s=dv_x, mass_limit_kg=ml_x)
            fit = check_fit(sel)
            ok = sel.within_limits and all(r.selected for r in sel.subsystems) and fit["state"] in ACCEPTED_FIT
            log.append({"class_u": u, "ok": ok, "why": "fits" if ok else _class_reason(sel, fit, dv_x, catalog, slots_x, ml_x),
                        "mass_kg": round(sel.mass_kg, 3), "volume_m3": sel.volume_m3, "fit": fit["state"]})
            if ok:
                found = (u, sel)
                break
        return found, log

    tried = [(n, name, sl, *search(sl, dv, mass_limit)) for n, (name, sl) in enumerate(variants)]
    good = [t for t in tried if t[3] is not None]
    if good:
        _, battery_variant, slots, found, log = min(good, key=lambda t: (t[3][0], t[0]))    # classe piu' piccola, poi meno componenti
    else:
        _, battery_variant, slots, found, log = tried[-1]                                     # il progetto con la batteria separata
    relaxed: list[str] = []
    if found is None and dv:
        alt_found, _ = search(slots, None, mass_limit)
        if alt_found:
            found, relaxed = alt_found, ["dv"]
    if found is None and mass_limit:
        alt_found, _ = search(slots, dv if "dv" not in relaxed else None, None)
        if alt_found:
            found, relaxed = alt_found, relaxed + ["mass"]
    if found is None:       # nemmeno la classe piu' grande li porta: si mostra quella, con il motivo
        u = classes[-1]
        found = (u, select(catalog, u, time_budget_s, slots=slots, dv_m_s=dv, mass_limit_kg=mass_limit))
    units, sel = found
    dv_eff = dv if "dv" not in relaxed else None
    ml_eff = mass_limit if "mass" not in relaxed else None

    def ok_sel(s: Selection) -> bool:
        return s.within_limits and all(r.selected for r in s.subsystems) and check_fit(s)["state"] in ACCEPTED_FIT

    # delta-v che nessun propulsore da': nella classe scelta il propulsore con l'impulso totale piu' alto che entra (quello che piu' si avvicina)
    if "dv" in relaxed:
        psl = next((s for s in slots if s.subsystem == "propulsion"), None)
        if psl is not None:
            cands = [c for c in catalog if subsystem_of(c) == "propulsion" and (psl.allowed is None or c.id in psl.allowed) and total_impulse_ns(c)]
            for imp in sorted({total_impulse_ns(c) for c in cands}, reverse=True):
                keep = frozenset(c.id for c in cands if total_impulse_ns(c) >= imp - 1e-9)
                trial_slots = [replace(s, allowed=keep) if s.id == psl.id else s for s in slots]
                trial = select(catalog, units, time_budget_s, slots=trial_slots, mass_limit_kg=ml_eff)
                if ok_sel(trial):
                    sel, slots = trial, trial_slots
                    break

    # radio delle immagini: senza una velocita' scritta nei requisiti, la piu' alta pubblicata che entra nel progetto (nella classe scelta)
    radio_info = None
    dr = a["data_radio"]
    if dr and not a["data_rate"]:
        sl = next(s for s in slots if s.id == dr)
        band = dr.split("_", 1)[1].upper() if "_" in dr else None
        # solo le radio della sola banda delle immagini: la velocita' massima pubblicata di una radio multibanda (es. S/X) e' quella della
        # banda piu' veloce, non di quella che la missione usa
        cands = [c for c in catalog if subsystem_of(c) == "comms" and (sl.allowed is None or c.id in sl.allowed) and c.spec("data_rate_kbps_max")
                 and (band is None or str(c.spec("band")).upper() == band)]
        cur = next((r.selected for r in sel.subsystems if r.id == dr and r.selected), None)
        cur_rate = float(cur.comp.spec("data_rate_kbps_max") or 0.0) if cur and (band is None or str(cur.comp.spec("band")).upper() == band) else 0.0
        for rate in sorted({float(c.spec("data_rate_kbps_max")) for c in cands}, reverse=True):
            if rate <= cur_rate + 1e-9:
                break
            keep = frozenset(c.id for c in cands if float(c.spec("data_rate_kbps_max")) >= rate - 1e-9)
            trial_slots = [replace(s, allowed=keep) if s.id == dr else s for s in slots]
            trial = select(catalog, units, time_budget_s, slots=trial_slots, dv_m_s=dv_eff, mass_limit_kg=ml_eff)
            if ok_sel(trial):
                sel, slots = trial, trial_slots
                break
        chosen = next((r.selected for r in sel.subsystems if r.id == dr and r.selected), None)
        if chosen:
            radio_info = {"slot": dr, "name": chosen.comp.raw["name"], "data_rate_kbps": chosen.comp.spec("data_rate_kbps_max"),
                          "why": "the radio that downlinks the images has the highest published data rate that fits the design "
                                 "(the requirements state no data rate)"}

    # una radio che comprende la sua antenna (nel nome del prodotto: "... + ANT...") non ha bisogno dell'antenna separata della sua banda
    dropped: list[dict[str, Any]] = []
    for r in list(sel.subsystems):
        if r.subsystem != "comms" or not r.selected or not re.search(r"\+\s*ANT", str(r.selected.comp.raw.get("name", ""))):
            continue
        ant_id = "antenna" + r.id[len("comms"):]          # comms_s -> antenna_s, comms -> antenna
        prev = next((x for x in sel.subsystems if x.id == ant_id), None)
        if prev is None:
            continue
        trial_slots = [replace(s, allowed=frozenset({r.selected.comp.id})) if s.id == r.id else s for s in slots if s.id != ant_id]
        trial = select(catalog, units, time_budget_s, slots=trial_slots, dv_m_s=dv_eff, mass_limit_kg=ml_eff)
        if ok_sel(trial):
            name = r.selected.comp.raw["name"]
            sel, slots = trial, trial_slots
            dropped.append({"id": ant_id, "subsystem": "antenna", "label": prev.label, "why_not": f"included in the radio {name} (the product comes with its antenna)",
                            "n_database": prev.n_database, "n_fit": prev.n_fit, "best": None if prev.selected is None else
                            {"id": prev.selected.comp.id, "name": prev.selected.comp.raw["name"], "vendor": prev.selected.comp.raw["vendor"], "mass_kg": prev.selected.mass_kg},
                            "fits_with_design": True})
            for nd in needs:
                if nd.slot.id == ant_id:
                    for ck in nd.checks:
                        ck.what += " (antenna included in the radio)"

    # requisiti del progetto (delta-v, massa) e della classe
    checks: list[Check] = [ck for nd in needs for ck in nd.checks]
    prop = next((r for r in sel.subsystems if r.subsystem == "propulsion" and r.selected), None)
    dv_info = None
    if a["dv"]:
        ck = next(c for c in checks if c.key == "dv")
        given = (total_impulse_ns(prop.selected.comp) or 0.0) / sel.mass_kg if prop and sel.mass_kg > 0 else None
        dv_info = {"dv_m_s": dv, "why": a["dv"]["why"], "source": a["dv"]["source"], "given_m_s": given,
                   "requirement": a["dv"]["req"].as_dict() if a["dv"]["req"] else None}
        if "dv" in relaxed or given is None or given < dv - 1e-9:
            ck.status = "not_met"
            if ck not in unmet:
                unmet.append(ck)
    eps_sel = next((r.selected for r in sel.subsystems if r.subsystem == "eps" and r.selected), None)
    bat_info = None
    if bat:
        ck = next(c for c in checks if c.key == "battery")
        bat_info = {"energy_wh": bat["energy_wh"], "mode": bat["mode"], "dod": bat["dod"], "need_wh": bat["need_wh"], "why": bat["why"],
                    "requirement": bat["req"].as_dict() if bat["req"] else None, "variant": battery_variant}
        if battery_variant == "eps" and eps_sel is not None:
            wh = eps_wh.get(eps_sel.comp.id)
            bat_info["integrated_wh"] = wh
            ck.what = f"battery capacity >= {bat['need_wh']:.1f} Wh (battery integrated in the EPS)"
            ck.status, ck.message = "met", ""
            unmet = [u for u in unmet if u is not ck]
    if a["mass_limit"]:
        ml = a["mass_limit"]
        ck = Check("mass", None, ml["req"], f"satellite mass <= {ml['kg']:g} kg")
        if "mass" in relaxed or sel.mass_kg > ml["kg"] + 1e-9:
            ck.status = "not_met"
            unmet.append(ck)
        checks.append(ck)
    if a["wheels"]["slew_deg_s"] and any(s.subsystem == "reaction_wheel" for s in slots):
        w = a["wheels"]
        rw = next((r.selected for r in sel.subsystems if r.subsystem == "reaction_wheel" and r.selected), None)
        need_h = wheel_momentum_needed_mnms(sel.cubesat, w["slew_deg_s"])
        ck = Check("slew", next(s.id for s in slots if s.subsystem == "reaction_wheel"), w["req"], f"wheel momentum for a slew of {w['slew_deg_s']:g} deg/s")
        if rw is None or (rw.comp.spec("momentum_mnms") or 0.0) < need_h - 1e-9:
            ck.status = "not_met"
            ck.message = (f"Does not satisfy {w['req'].id if w['req'] else 'the slew rate'} ({ck.what}): no reaction wheel in the database that fits "
                          f"stores {need_h:.2f} mN m s.")
            unmet.append(ck)
        checks.append(ck)
    for ck in unmet:
        nd = next((n for n in needs if n.slot.id == ck.slot), None)
        what = "component"
        if nd:
            what = NOUNS.get(nd.slot.subsystem, LABELS[nd.slot.subsystem].lower())
            if nd.slot.id != nd.slot.subsystem and nd.slot.subsystem in ("comms", "antenna"):
                what = nd.slot.id.split("_", 1)[1].upper() + " " + what
        if ck.key == "dv":
            ck.message = (f"Does not satisfy {ck.req.id if ck.req else 'the delta-v need'} ({ck.what}): no thruster in the database gives "
                          f"{dv:.1f} m/s to this satellite" + (f" (the selected one gives {dv_info['given_m_s']:.1f} m/s)." if dv_info and dv_info['given_m_s'] else "."))
        elif ck.key == "mass":
            ck.message = f"Does not satisfy {ck.req.id} ({ck.what}): the lightest selection that the mission needs weighs {sel.mass_kg:.2f} kg."
        elif ck.key == "slew":
            pass                                                # messaggio gia' scritto (momento richiesto dalla classe)
        else:
            others = [c.what for c in (nd.checks if nd else []) if c is not ck and c.status == "met" and c.test is not None]
            ck.message = (f"Does not satisfy {ck.req.id if ck.req else 'a requirement'} ({ck.what}): no {what} in the database meets it"
                          + (f" together with {' and '.join(others)}." if others else "."))
    for ck in checks:
        if ck.status == "not_verifiable" and ck not in unmet:
            unmet.append(ck)

    # schede del progetto: motivo e requisiti verificati sul componente scelto
    by_slot = {nd.slot.id: nd for nd in needs}
    per_slot = {}
    for r in sel.subsystems:
        nd = by_slot[r.id]
        rows = []
        for ck in nd.checks:
            if ck.test is None or ck.status == "not_verifiable":
                continue
            met = bool(ck.test(r.selected.comp)) if r.selected else False
            val = ck.value(r.selected.comp) if (r.selected and ck.value) else None
            if ck.key == "dv" and dv_info and dv_info["given_m_s"] is not None:
                met = dv_info["given_m_s"] >= dv - 1e-9
                val = f"{dv_info['given_m_s']:.1f} m/s ({val})"
            rows.append({"requirement": ck.req.id if ck.req else None, "what": ck.what, "value": val, "met": met})
        if r.subsystem == "eps" and bat_info and bat_info.get("integrated_wh") is not None:
            rows.append({"requirement": bat["req"].id if bat["req"] else None, "what": f"integrated battery >= {bat['need_wh']:.1f} Wh",
                         "value": f"{bat_info['integrated_wh']:g} Wh", "met": True})
        why = nd.why
        if r.subsystem == "reaction_wheel" and r.selected:      # una ruota per asse; classe dichiarata; momento per la rotazione richiesta
            rw = r.selected.comp
            rng = rw.spec("form_factor_range_u")
            why += f"; {r.selected.quantity} wheel(s)" + (", one per axis" if r.selected.quantity == 3 else "")
            why += (f"; declared by its vendor for {rng[0]:g}U-{rng[1]:g}U CubeSats" if rng else "; CubeSat class not declared by its vendor")
            w = a["wheels"]
            if w["slew_deg_s"]:
                need_h = wheel_momentum_needed_mnms(sel.cubesat, w["slew_deg_s"])
                have = rw.spec("momentum_mnms")
                rows.append({"requirement": w["req"].id if w["req"] else None, "what": f"momentum for a slew of {w['slew_deg_s']:g} deg/s",
                             "value": f"{have:g} of {need_h:.2f} mN m s needed" if have is not None else None,
                             "met": have is not None and have >= need_h - 1e-9})
        if r.subsystem == "structure" and r.selected:      # selector.structure_envelope: la pila usa le quote della struttura scelta
            env = structure_envelope(r.selected.comp, sel.cubesat)
            faces = r.selected.comp.raw["specs"].get("panel_faces") or {}
            panel = next((x.selected.comp for x in sel.subsystems if x.subsystem == "solar_panel" and x.selected), None)
            rows.append({"requirement": None, "what": "holds the stack of the internal components",
                         "value": f"{env[0]:g} x {env[1]:g} x {env[2]:g} mm", "met": sel.within_limits})
            if faces and panel is not None and panel.raw["specs"].get("face"):
                rows.append({"requirement": None, "what": "a face for the solar panel",
                             "value": f"{panel.raw['specs']['face']} panel on " + ", ".join(f"{k} x{v}" for k, v in faces.items()) + " faces",
                             "met": panel_on_structure(panel, r.selected.comp)})
        if r.subsystem == "eps" and r.selected:      # selector: l'EPS alimenta i componenti, accetta pannello e batteria, copre la potenza
            eps = r.selected.comp
            rails = eps_rails(eps)
            others = [x for x in sel.subsystems if x.selected and x.id != r.id]
            fed = [x for x in others if x.subsystem not in ("battery", "solar_panel") and supply_ranges(x.selected.comp)]
            bad = [x.label for x in fed if not powered_by(x.selected.comp, eps)]
            used = sorted({rv for x in fed for rv in rails for lo, hi in supply_ranges(x.selected.comp) if lo <= rv[1] + 1e-9 and rv[0] <= hi + 1e-9})
            fmt = lambda a, b: f"{a:g}" if a == b else f"{a:g}-{b:g}"      # noqa: E731
            if rails and fed:
                rows.append({"requirement": None, "what": "powers every component that publishes its supply voltages",
                             "value": ("rails " + ", ".join(fmt(a, b) for a, b in used) + " V") if not bad else "not: " + ", ".join(bad), "met": not bad})
            panel = next((x.selected.comp for x in others if x.subsystem == "solar_panel"), None)
            pv, vs = eps.raw["specs"].get("pv_voltage_v"), panel_voltages(panel) if panel else []
            if panel is not None and pv and vs:
                rows.append({"requirement": None, "what": "solar input accepts the panel voltage",
                             "value": f"{', '.join(f'{v:g}' for v in vs)} V in {fmt(*pv)} V", "met": panel_ok(panel, eps)})
            batt = next((x.selected.comp for x in others if x.subsystem == "battery"), None)
            s = eps.raw["specs"]
            if batt is not None and (s.get("battery_voltage_v") or s.get("battery_families")):
                rows.append({"requirement": None, "what": "accepts the battery (voltage, family)", "value": batt.raw["name"], "met": battery_ok(batt, eps)})
            if s.get("output_power_w_max") is not None:
                peak = max((x.selected.power_w or 0.0 for x in others), default=0.0)
                rows.append({"requirement": None, "what": "maximum output power covers the most demanding component",
                             "value": f"{peak:g} W of {float(s['output_power_w_max']):g} W", "met": peak <= float(s["output_power_w_max"]) + 1e-9})
            unfed = [x.label for x in others if x.subsystem not in ("structure", "battery", "solar_panel", "antenna") and not supply_ranges(x.selected.comp)]
            if unfed:
                why += f" (supply voltages not published: {', '.join(unfed)})"
        if r.subsystem == "obc" and r.selected:      # selector.interfaces: l'OBC parla con ogni componente che pubblica le sue interfacce
            oi = interfaces(r.selected.comp) or frozenset()
            others = [x for x in sel.subsystems if x.selected and x.id != r.id]
            used = sorted({i for x in others for i in ((interfaces(x.selected.comp) or frozenset()) & oi)})
            missing = [x.label for x in others if interfaces(x.selected.comp) and not (interfaces(x.selected.comp) & oi)]
            unknown = [x.label for x in others if x.subsystem not in ("structure", "battery", "solar_panel", "antenna", "gnss_antenna")
                       and not interfaces(x.selected.comp)]
            rows.append({"requirement": None, "what": "data interfaces in common with every component that publishes them",
                         "value": ", ".join(used) if not missing else "none with " + ", ".join(missing), "met": not missing})
            why += f"; it talks to the other components through {', '.join(used)}" if used and not missing else ""
            if unknown:
                why += f" (interfaces not published: {', '.join(unknown)})"
        if r.subsystem == "propulsion" and r.selected:      # selector: propulsori elettrici alimentati dal pannello solare
            thr = r.selected.comp
            if is_electric(thr):
                panel = next((x.selected.comp for x in sel.subsystems if x.subsystem == "solar_panel" and x.selected), None)
                peak = panel.spec("peak_power_w") if panel else None
                fire = firing_power_w(thr)
                rows.append({"requirement": None, "what": "electric thruster: firing power <= peak power of the solar panel",
                             "value": f"{fire:g} W of {float(peak):g} W" if fire is not None and peak is not None else None,
                             "met": fire is not None and peak is not None and fire <= float(peak) + 1e-9})
                why += "; electric thruster, powered by the solar panel"
            else:
                why += f"; {str(thr.spec('propulsion_type') or 'chemical').replace('_', ' ')} thruster: short burns powered by the battery"
        if r.subsystem == "adcs" and r.selected:      # selector.adcs_tier: l'unita' dichiarata per la classe del progetto
            rng = r.selected.comp.spec("form_factor_range_u")
            why += ("; declared by its vendor for " + (f"{rng[0]:g}U" if rng[0] == rng[1] else f"{rng[0]:g}U-{rng[1]:g}U") + " CubeSats"
                    + ("" if rng[0] <= units <= rng[1] else f" (none is declared for a {units}U)")) if rng else "; CubeSat class not declared by its vendor"
        if radio_info and r.id == radio_info["slot"] and radio_info.get("data_rate_kbps"):
            why = f"{nd.why}; highest published data rate that fits the design ({float(radio_info['data_rate_kbps']) / 1e3:g} Mbps)"
        if r.subsystem == "eps" and bat_info and bat_info.get("integrated_wh") is not None:
            why += "; its integrated battery is the satellite battery"
        per_slot[r.id] = {"why": why, "source": nd.source, "requirement": nd.req.as_dict() if nd.req else None, "checks": rows}

    # sottosistemi non richiesti: miglior componente che entra nella classe e se starebbe insieme al progetto
    needed = {s.subsystem for s in slots}
    extras = []
    for sid, _, label in SUBSYSTEMS:
        if sid in needed or (sid == "antenna" and dropped):      # l'antenna compresa nella radio e' elencata sotto (dropped)
            continue
        if sid == "battery" and bat_info and bat_info.get("integrated_wh") is not None:
            reason = (f"the battery integrated in the EPS ({bat_info['integrated_wh']:g} Wh) covers the {bat['need_wh']:.1f} Wh the mission needs "
                      f"({bat['energy_wh']:.2f} Wh per orbit from END-004" + (f", depth of discharge <= {100 * bat['dod']:g}%)" if bat["req"] else ")"))
        elif sid in ADCS_PARTS and "adcs" in needed:
            reason = "contained in the integrated ADCS unit of the design (the catalogue's ADCS units include their sensors and actuators)"
        elif sid in ADCS_PARTS:
            reason = "no requirement asks for attitude control"
        else:
            reason = NOT_REQUIRED.get(sid, "not required by the mission")
        extra_slot = Slot(sid, sid, label, quantity=a["wheels"]["quantity"], slew_rate_deg_s=a["wheels"]["slew_deg_s"]) if sid == "reaction_wheel" else Slot(sid, sid, label)
        trial = select(catalog, units, 1.0, slots=[*slots, extra_slot],
                       dv_m_s=dv if "dv" not in relaxed else None, mass_limit_kg=mass_limit if "mass" not in relaxed else None)
        rec = next(r for r in trial.subsystems if r.id == sid)
        alone = rec.selected if rec.selected is not None else None
        together = trial.within_limits and rec.selected is not None and check_fit(trial)["state"] in ACCEPTED_FIT
        extras.append({"id": sid, "subsystem": sid, "label": label, "why_not": reason, "n_database": rec.n_database, "n_fit": rec.n_fit,
                       "best": None if alone is None else {"id": alone.comp.id, "name": alone.comp.raw["name"], "vendor": alone.comp.raw["vendor"],
                                                           "mass_kg": alone.mass_kg, "quantity": alone.quantity},
                       "fits_with_design": together})
    extras += dropped          # antenne comprese nella radio scelta

    stated = a["stated"]
    notes = list(a["notes"])
    if stated and stated["class_u"] != units and not forced_class_u:
        notes.append(f"{stated['req'].id} states a {stated['class_u']}U CubeSat: the subsystems the mission needs fit a {units}U, the smallest class"
                     + (f" ({units}U is larger: a smaller class cannot carry them)." if units > stated["class_u"] else "."))
    if a["dv"] and a["dv"]["source"] == "END-016":
        notes.append("The disposal delta-v comes from END-016 for the spacecraft mass and drag area END-001 used; a lighter satellite decays differently.")
    alt = a["altitude"]
    mission = {
        "class_search": log,
        "chosen_class_u": units, "forced_class_u": forced_class_u,
        "stated_class": None if not stated else {"class_u": stated["class_u"], "requirement": stated["req"].as_dict()},
        "relaxed": relaxed,
        "altitude": None if not alt else {"min_km": alt["min_km"], "max_km": alt["max_km"], "source": alt["source"]},
        "dv": dv_info,
        "battery": bat_info,
        "radio": radio_info,
        "mass_limit": None if not a["mass_limit"] else {"kg": a["mass_limit"]["kg"], "requirement": a["mass_limit"]["req"].as_dict()},
        "requirements": [{"requirement": ck.req.as_dict() if ck.req else None, "what": ck.what, "slot": ck.slot, "status": ck.status,
                          "message": ck.message} for ck in checks],
        "unmet": [ck.message for ck in unmet if ck.message],
        "subsystems": per_slot,
        "extras": extras,
        "notes": notes,
        "rules": "Bus always; other subsystems only when a requirement asks for them (or END-016 needs a delta-v); one radio and antenna per band; "
                 "smallest CubeSat class that carries them (mass, volume, stack, envelope fit).",
    }
    return sel, mission

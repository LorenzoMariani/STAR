"""Selezione dei componenti di un CubeSat: almeno un componente per ciascun sottosistema, nel rispetto dei limiti di massa e volume.

Regole (nessuna ipotesi di progetto):
  * classe del CubeSat (1U, 3U, 6U, 12U): limite di massa e ingombro dalla CubeSat Design Specification Rev. 14.1; il limite di volume e' il
    volume dell'ingombro esterno;
  * un componente e' candidato di un sottosistema se ha la massa pubblicata e le sue dimensioni (se pubblicate) entrano nell'ingombro, in una
    qualunque orientazione; la struttura deve essere della classe richiesta. Un componente senza massa pubblicata entra solo se il
    sottosistema non ha candidati con massa nota;
  * tra i candidati si scelgono quelli con piu' dati fondamentali pubblicati (poi i piu' leggeri) tali che la somma delle masse e dei volumi noti
    non superi i limiti e che i componenti interni si impilino nelle colonne della classe (layout.py: altezze lungo Z, impronta nella sezione di una
    colonna); il volume e' quello dei soli componenti interni (pannelli solari e antenne si montano sulle facce: regola dichiarata);
  * un valore che il fornitore non pubblica resta `None` (la GUI scrive "Not publicly available"): non si stima e non si usano valori di default.
Non ci sono bilancio energetico, compatibilita' di tensioni o interfacce. I requisiti di missione (quali sottosistemi servono, quali componenti li
soddisfano, il delta-v, la massa massima) arrivano da mission.py attraverso i parametri facoltativi di select(): `slots`, `dv_m_s`, `mass_limit_kg`."""
from __future__ import annotations

import itertools
import math
import time
from dataclasses import dataclass, field, replace
from typing import Any

from . import layout
from .models import Component
from .rows import completeness, declared_power_w, sci, subsystem_of, volume_m3

CDS_SOURCE = "CubeSat Design Specification Rev. 14.1 (Cal Poly), Table 1 (mass) and Section 3 (envelope)"


@dataclass(frozen=True)
class CubeSatClass:
    units: int
    mass_limit_kg: float
    envelope_mm: tuple[float, float, float]

    @property
    def volume_limit_m3(self) -> float:
        a, b, c = self.envelope_mm
        return a * b * c * 1e-9


CLASSES = {
    1: CubeSatClass(1, 2.0, (100.0, 100.0, 113.5)),
    3: CubeSatClass(3, 6.0, (100.0, 100.0, 340.5)),
    6: CubeSatClass(6, 12.0, (100.0, 226.3, 366.0)),
    12: CubeSatClass(12, 24.0, (226.3, 226.3, 366.0)),
}

# (id, categoria del catalogo, etichetta della scheda)
SUBSYSTEMS = (
    ("structure", "structure", "STRUCTURE"),
    ("obc", "obc", "OBC"),
    ("eps", "eps", "EPS"),
    ("battery", "battery", "BATTERY"),
    ("solar_panel", "solar_panel", "SOLAR CELLS"),
    ("comms", "comms", "COMMS RADIO"),
    ("antenna", "antenna", "ANTENNA"),
    ("adcs", "adcs", "ADCS"),
    ("magnetorquer", "magnetorquer", "MAGNETORQUER"),
    ("reaction_wheel", "reaction_wheel", "REACTION WHEEL"),
    ("star_tracker", "star_tracker", "STAR TRACKER"),
    ("sun_sensor", "sun_sensor", "SUN SENSOR"),
    ("gps", "gps", "GNSS RECEIVER"),
    ("gnss_antenna", "gnss_antenna", "GNSS ANTENNA"),
    ("propulsion", "propulsion", "PROPULSION"),
    ("payload_imager", "payload", "PAYLOAD · IMAGER"),
    ("payload_optical", "payload", "PAYLOAD · OPTICAL TERMINAL"),
)
LABELS = {sid: label for sid, _, label in SUBSYSTEMS}
# Regola dichiarata (non un dato del fornitore): questi sottosistemi si montano sulle facce del CubeSat e non occupano il volume interno
EXTERNAL_SUBSYSTEMS = ("solar_panel", "antenna", "sun_sensor", "gnss_antenna")
NO_POWER_SUBSYSTEMS = ("structure", "battery", "solar_panel", "antenna")   # non assorbono potenza (o non e' un dato significativo)


# faccia di una struttura CubeSat (larghezza x lunghezza, mm): un pannello "3U" e' fatto per la faccia 100 x 340.5 mm
FACE_MM = {"1U": (100.0, 113.5), "1U Z": (100.0, 100.0), "2U": (100.0, 227.0), "3U": (100.0, 340.5), "6U": (226.3, 340.5)}   # "1U Z" = faccia superiore o inferiore


# Regola dichiarata (2026-10-15): il pannello solare e' quello fatto per la faccia della classe (campo `face` del catalogo): 1U -> "1U" o
# "1U Z", 3U -> "3U", 6U -> "6U", 12U -> "6U" (le facce lunghe di un 12U, 226.3 x 366 mm, sono quelle grandi di un 6U). I pannelli per facce
# piu' piccole che pure entrano si usano solo se la classe non ne ha uno suo.
CLASS_PANEL_FACES = {1: ("1U", "1U Z"), 3: ("3U",), 6: ("6U",), 12: ("6U",)}


def panel_for_class(c: Component, units: int) -> bool:
    return str(c.raw["specs"].get("face")) in CLASS_PANEL_FACES.get(units, ())


# Regola dichiarata (2026-10-16): l'unita' ADCS e' quella che il fornitore dichiara per la classe (specs.form_factor_range_u). Se la classe
# non ne ha, quelle dichiarate per classi piu' grandi o senza dichiarazione (piu' momento del necessario, o da verificare); mai quelle
# dichiarate solo per classi piu' piccole (ruote con meno momento e coppia di quanto serve). A pari livello i prodotti non piu' in vendita
# (status "nla") solo se non c'e' altro.
CLASS_RANGE_SUBSYSTEMS = ("adcs", "reaction_wheel")      # stessa regola per le ruote di reazione (tools/add_rw_form_factors.py)


def wheel_momentum_needed_mnms(cls: CubeSatClass, slew_rate_deg_s: float) -> float:
    """Momento di una ruota per ruotare il satellite a slew_rate attorno all'asse di inerzia massima: inerzia di un blocco uniforme con la
    massa limite e l'ingombro della classe (regola dichiarata, per eccesso: il satellite reale pesa meno o uguale) x velocita' angolare."""
    b, c = sorted(cls.envelope_mm)[1:]
    inertia = cls.mass_limit_kg * ((b / 1000.0) ** 2 + (c / 1000.0) ** 2) / 12.0
    return inertia * math.radians(slew_rate_deg_s) * 1000.0


def adcs_tier(c: Component, units: int) -> int:
    """0 = dichiarata per la classe, 1 = per classi piu' grandi o non dichiarata, 2 = solo per classi piu' piccole (esclusa)."""
    r = c.spec("form_factor_range_u")
    if not r:
        return 1
    lo, hi = r
    return 0 if lo <= units <= hi else (1 if lo > units else 2)


# Regole dichiarate per i propulsori (2026-10-16):
#  * la classe minima che il fornitore dichiara (specs.min_form_factor_u) va rispettata;
#  * con electric_power_check un propulsore elettrico (acceso per ore o giorni) deve funzionare con la potenza del pannello solare del
#    progetto: potenza in accensione pubblicata <= potenza di picco pubblicata del pannello. I propulsori chimici e a gas fanno accensioni
#    brevi alimentate dalla batteria e non hanno questo limite.
ELECTRIC_PROPULSION = ("gridded_ion", "feep", "pulsed_plasma", "hall", "electrospray")


def is_electric(c: Component) -> bool:
    return c.category == "propulsion" and str(c.spec("propulsion_type")) in ELECTRIC_PROPULSION


def firing_power_w(c: Component) -> float | None:
    v = c.spec("power_w_firing") if c.category == "propulsion" else None
    return float(v) if v is not None else None


# Interfacce dati (regola dichiarata, 2026-10-16): con interface_check l'OBC deve avere almeno un'interfaccia in comune con ogni componente
# del progetto che pubblica le sue (specs.data_interfaces); un componente che non le pubblica non si puo' verificare e non blocca la scelta.
IFACE_ALIASES = {"RS422": "RS-422", "RS485": "RS-485", "RS232": "RS-232", "I²C": "I2C", "RS-422 UART": "RS-422", "RS-485 UART": "RS-485",
                 "TTL UART": "UART", "ANALOGUE": "ADC", "ANALOG": "ADC"}


def interfaces(c: Component) -> frozenset[str] | None:
    """Interfacce dati pubblicate, con i nomi normalizzati (None = non pubblicate)."""
    v = c.raw["specs"].get("data_interfaces")
    if not v:
        return None
    return frozenset(IFACE_ALIASES.get(str(x).strip().upper(), str(x).strip().upper()) for x in v)


# Alimentazione (regole dichiarate, 2026-10-16):
#  * sempre: un EPS che dichiara le classi compatibili (compatible_form_factors_u) le rispetta; un EPS senza ingressi solari (pv_channels 0)
#    non carica la batteria dai pannelli e si usa solo se non c'e' altro;
#  * con power_supply_check: ogni componente che pubblica le tensioni di alimentazione (supply_voltage_ranges_v) e' alimentato da
#    un'uscita regolata dell'EPS (output_voltage_ranges_v) o dalla tensione della sua batteria integrata (gli intervalli si sovrappongono); la
#    tensione del pannello (voltage_options_v, altrimenti quella a vuoto) entra nell'ingresso solare dell'EPS (pv_voltage_v); una batteria
#    esterna ha la tensione e la famiglia che l'EPS ammette (battery_voltage_v, battery_families); la potenza massima in uscita dell'EPS
#    (output_power_w_max) copre la potenza dichiarata piu' alta di un componente. Dati non pubblicati: non si verifica e non si blocca.
def _ranges(v) -> list[tuple[float, float]]:
    return [(float(r[0]), float(r[1])) for r in v] if v else []


def supply_ranges(c: Component) -> list[tuple[float, float]]:
    return _ranges(c.raw["specs"].get("supply_voltage_ranges_v"))


def eps_rails(eps: Component) -> list[tuple[float, float]]:
    rails = _ranges(eps.raw["specs"].get("output_voltage_ranges_v"))
    iv = eps.raw["specs"].get("integrated_battery_voltage_v")
    return rails + ([(float(iv), float(iv))] if iv else [])


def powered_by(c: Component, eps: Component) -> bool:
    sr, rails = supply_ranges(c), eps_rails(eps)
    return not sr or not rails or any(lo <= rhi + 1e-9 and rlo <= hi + 1e-9 for lo, hi in sr for rlo, rhi in rails)


def panel_voltages(c: Component) -> list[float]:
    s = c.raw["specs"]
    if s.get("voltage_options_v"):
        return [float(v) for v in s["voltage_options_v"]]
    return [float(s["open_circuit_voltage_v"])] if s.get("open_circuit_voltage_v") else []


def panel_ok(panel: Component, eps: Component) -> bool:
    pv, vs = eps.raw["specs"].get("pv_voltage_v"), panel_voltages(panel)
    return not pv or not vs or any(pv[0] - 1e-9 <= v <= pv[1] + 1e-9 for v in vs)


def battery_ok(batt: Component, eps: Component) -> bool:
    s = eps.raw["specs"]
    bv, fam, br = s.get("battery_voltage_v"), s.get("battery_families"), batt.raw["specs"].get("voltage_range_v")
    if bv and br and not (bv[0] - 1e-9 <= br[0] and br[1] <= bv[1] + 1e-9):
        return False
    return not fam or batt.raw.get("family") in fam


def eps_class_ok(c: Component, units: int) -> bool:
    ff = c.raw["specs"].get("compatible_form_factors_u")
    return not ff or units in [int(round(float(x))) for x in ff]


def _covers_supply(b: Candidate, a: Candidate) -> bool:
    """b e' alimentato da ogni EPS che alimenta a: tensioni non pubblicate, oppure ogni intervallo di a sta in un intervallo di b."""
    rb, ra = supply_ranges(b.comp), supply_ranges(a.comp)
    return not rb or (bool(ra) and all(any(blo <= lo + 1e-9 and hi <= bhi + 1e-9 for blo, bhi in rb) for lo, hi in ra))


# Struttura (regole dichiarate, 2026-10-16): la pila dei componenti interni e il controllo di ingombro usano le dimensioni pubblicate della
# struttura scelta (non l'ingombro massimo della classe: un 6U puo' essere lungo 366 o 340.5 mm); il pannello solare si monta su una faccia
# che la struttura offre (specs.panel_faces).
def structure_envelope(struct: Component | None, cls: CubeSatClass) -> tuple[float, float, float]:
    """Ingombro della struttura scelta (lati della sezione, lunghezza), entro quello della classe; senza quote pubblicate quello della classe."""
    d = struct.dimensions_mm if struct is not None else None
    if not d or any(x is None for x in d):
        return cls.envelope_mm
    return tuple(min(float(a), float(b)) for a, b in zip(sorted(float(x) for x in d), cls.envelope_mm))


def panel_on_structure(panel: Component, struct: Component) -> bool:
    faces, face = struct.raw["specs"].get("panel_faces"), panel.raw["specs"].get("face")
    return not faces or not face or str(face).replace(" Z", "") in faces


# sottosistemi in cui il catalogo pubblica la classe minima dichiarata dal fornitore (specs.min_form_factor_u): propulsori, imager e
# terminali ottici (2026-10-16). Inoltre, per ogni sottosistema, i prodotti non piu' in vendita (status "nla") solo se non c'e' altro.
MIN_CLASS_SUBSYSTEMS = ("propulsion", "payload_imager", "payload_optical")


def min_class_ok(c: Component, units: int) -> bool:
    v = c.raw["specs"].get("min_form_factor_u")
    return v is None or float(v) <= units + 1e-9


def panel_face(c: Component) -> tuple[float, float] | None:
    """Impronta (mm) di un pannello solare senza tutte e tre le quote: le due quote pubblicate se ci sono (lo spessore manca), altrimenti la faccia dichiarata."""
    if c.category != "solar_panel":
        return None
    known = [float(x) for x in (c.dimensions_mm or []) if x is not None]
    if len(known) == 2:
        return known[0], known[1]
    return FACE_MM.get(str(c.raw["specs"].get("face")))


def fits_envelope(c: Component, env: tuple[float, float, float]) -> bool:
    """Le dimensioni pubblicate entrano nell'ingombro in una qualunque orientazione. Se non sono pubblicate si usa, per i pannelli solari, l'impronta pubblicata
    o la faccia per cui il fornitore li dichiara (campo `face`); senza nemmeno quella non si puo' escludere."""
    d = c.dimensions_mm
    if not d or any(x is None for x in d):
        face = panel_face(c)
        if face:
            return any(face[0] <= x + 1e-9 and face[1] <= y + 1e-9 for x, y in itertools.permutations(env, 2))
        return True
    return any(all(p[i] <= env[i] + 1e-9 for i in range(3)) for p in itertools.permutations(d))


@dataclass
class Candidate:
    comp: Component
    mass_kg: float | None
    volume_m3: float | None
    power_w: float | None
    completeness: float
    height_mm: float | None = None      # altezza lungo l'asse della pila (layout.py); None se le quote non sono tutte pubblicate o non e' un componente della pila
    quantity: int = 1                   # unita' dello stesso prodotto nel posto (es. tre ruote, una per asse): massa, volume, potenza e altezza sono gia' moltiplicati
    span: tuple = (1, 1)                # colonne della pila occupate (in X, in Y): piu' di una se l'impronta supera la sezione di una colonna
    parts: tuple = ()                   # altre scatole del prodotto nella pila: ((altezza, span), ...), es. l'elettronica separata dall'ottica
    column_mm: float | None = None      # lunghezza di colonna occupata in tutto: altezza x colonne + altre scatole (limite della ricerca esatta)


@dataclass
class SubsystemResult:
    id: str
    category: str
    label: str
    n_database: int
    n_fit: int
    n_fit_without_mass: int
    selected: Candidate | None
    alternatives: list[Candidate] = field(default_factory=list)
    note: str | None = None
    subsystem: str | None = None        # sottosistema del posto (id e' il posto: "comms", "comms_s" per una seconda radio...)


@dataclass(frozen=True)
class Slot:
    """Un posto del progetto: un componente del sottosistema `subsystem`, scelto tra `allowed` (id del catalogo; None = tutti), in `quantity`
    unita' dello stesso prodotto (impilate lungo l'asse della pila); slew_rate_deg_s: velocita' di rotazione che ciascuna ruota di reazione deve
    dare al satellite (momento >= inerzia x velocita', inerzia di un blocco uniforme con la massa limite e l'ingombro della classe)."""
    id: str
    subsystem: str
    label: str
    allowed: frozenset[str] | None = None
    quantity: int = 1
    slew_rate_deg_s: float | None = None
    axes_needed: int | None = None          # magnetorquer: assi da coprire (3): una scheda a tre assi oppure tre barre a un asse
    dump_am2_per_nms: float | None = None   # magnetorquer: dipolo per scaricare 1 N m s di una ruota in un'orbita, 1 / (B x T)


def default_slots() -> list[Slot]:
    return [Slot(sid, sid, label) for sid, _, label in SUBSYSTEMS]


def total_impulse_ns(c: Component) -> float | None:
    v = c.spec("total_impulse_ns") if c.category == "propulsion" else None
    return float(v) if v is not None else None


@dataclass
class Selection:
    cubesat: CubeSatClass
    subsystems: list[SubsystemResult]
    within_limits: bool
    mass_kg: float
    volume_m3: float
    power_w: float
    mass_unknown: list[str]
    volume_unknown: list[str]
    power_unknown: list[str]
    messages: list[str]
    truncated: bool = False


def _candidate(c: Component, env) -> Candidate:
    # la struttura e' il contenitore (il suo ingombro e' quello del satellite) e i componenti esterni stanno sulle facce: nessuno dei due entra nel volume interno
    sid = subsystem_of(c)
    vol = None if c.category == "structure" or sid in EXTERNAL_SUBSYSTEMS else volume_m3(c)
    st = layout.spec(c, sid, env) if sid in layout.ORDER else None
    parts: tuple = ()
    if st and c.extra_boxes_mm:
        specs = [layout.dims_spec(b, sid, {}, env) for b in c.extra_boxes_mm]
        parts = tuple((s["height"], s["span"]) for s in specs if s and s["perm"] is not None)
    h = st["height"] if st else None
    span = tuple(st.get("span") or (1, 1)) if st else (1, 1)
    column = None if h is None else h * span[0] * span[1] + sum(ph * ps[0] * ps[1] for ph, ps in parts)
    return Candidate(c, c.mass_kg, vol, declared_power_w(c), completeness(c), h, span=span, parts=parts, column_mm=column)


def _times(k: Candidate, q: int) -> Candidate:
    """q unita' dello stesso prodotto nel posto: massa, volume, potenza e altezza nella pila moltiplicate."""
    if q <= 1:
        return k
    mul = lambda v: None if v is None else v * q      # noqa: E731
    return replace(k, mass_kg=mul(k.mass_kg), volume_m3=mul(k.volume_m3), power_w=mul(k.power_w), height_mm=mul(k.height_mm), quantity=q,
                   parts=k.parts * q, column_mm=mul(k.column_mm))


def _admissible(c: Component, sid: str, cls: CubeSatClass) -> bool:
    """Scarto immediato dei componenti che non entrano: massa oltre il limite e, per i componenti della pila, impronta oltre la sezione di una colonna o altezza oltre Z."""
    if c.mass_kg is not None and c.mass_kg > cls.mass_limit_kg:
        return False
    if sid in layout.ORDER:
        st = layout.spec(c, sid, cls.envelope_mm)
        if st is not None and st["perm"] is None:          # senza quote complete non si puo' escludere
            return False
        return all((s := layout.dims_spec(b, sid, {}, cls.envelope_mm)) is not None and s["perm"] is not None for b in c.extra_boxes_mm)
    return fits_envelope(c, cls.envelope_mm)


def _order(cands: list[Candidate], mass_first: bool = False) -> list[Candidate]:
    if mass_first:      # objective "mass": il piu' leggero prima, a parita' di massa quello con piu' dati pubblicati
        return sorted(cands, key=lambda k: (k.mass_kg if k.mass_kg is not None else 1e9, -k.completeness, k.comp.id))
    return sorted(cands, key=lambda k: (-k.completeness, k.mass_kg if k.mass_kg is not None else 1e9, k.comp.id))


def _covers_interfaces(b: Candidate, a: Candidate) -> bool:
    """b e' compatibile con l'OBC (o, per un OBC, con i componenti) ogni volta che lo e' a: interfacce non pubblicate (non si verifica) oppure
    un insieme che contiene quello di a."""
    ib, ia = interfaces(b.comp), interfaces(a.comp)
    return ib is None or (ia is not None and ib >= ia)


def _pareto(pool: list[Candidate], extra=None, covers=None, mass_first: bool = False) -> list[Candidate]:
    """Per la ricerca esatta: toglie i candidati battuti da un altro con completezza >= e massa, volume e altezza <= (non servono mai per l'ottimo).
    extra(k) aggiunge le grandezze dei vincoli attivi (piu' piccolo = meglio): con il delta-v l'impulso totale (cambiato di segno), con la
    potenza dei propulsori elettrici la potenza in accensione del propulsore e la potenza di picco del pannello (cambiata di segno)."""
    def key(k):
        return ((k.mass_kg or 0.0, k.volume_m3 or 0.0, k.column_mm or 0.0, k.span[0], k.span[1], len(k.parts))
                + (tuple(extra(k)) if extra else ()))

    def better_or_equal(b, a) -> bool:
        # con objective "mass" la completezza conta solo a parita' di massa: un candidato piu' leggero (e non peggiore sui vincoli) basta
        return b.completeness >= a.completeness - 1e-12 or (mass_first and (b.mass_kg or 0.0) < (a.mass_kg or 0.0) - 1e-12)
    keep: list[Candidate] = []
    for a in pool:      # il pool e' ordinato per completezza decrescente, poi massa (con objective "mass": massa, poi completezza)
        if not any(better_or_equal(b, a) and all(x <= y + 1e-15 for x, y in zip(key(b), key(a))) and (covers is None or covers(b, a))
                   for b in keep):
            keep.append(a)
    return keep


CATEGORY_OF = {sid: cat for sid, cat, _ in SUBSYSTEMS}


def _slot_pool(catalog: list[Component], sl: Slot, units: int, cls: CubeSatClass, dv: float | None, mass_first: bool = False):
    """I candidati di un posto nella classe, con le regole di select: (membri del sottosistema, ammessi dai requisiti, che entrano nella classe,
    solo per classi piu' grandi, solo per classi piu' piccole, candidati con massa pubblicata, senza, candidati considerati dalla ricerca)."""
    sid = sl.subsystem
    members = [c for c in catalog if subsystem_of(c) == sid]
    allowed = [c for c in members if sl.allowed is None or c.id in sl.allowed]
    if sid == "structure":
        fitting = [c for c in allowed if c.spec("form_factor_u") == units]
    else:
        fitting = [c for c in allowed if _admissible(c, sid, cls)]
    larger_only = False
    if sid in MIN_CLASS_SUBSYSTEMS and fitting:                     # classe minima dichiarata dal fornitore
        larger_only = not any(min_class_ok(c, units) for c in fitting)
        fitting = [c for c in fitting if min_class_ok(c, units)]
    if dv and sid == "propulsion":
        fitting = [c for c in fitting if total_impulse_ns(c)]      # senza impulso totale pubblicato il delta-v non si puo' mostrare
    if sid == "solar_panel":
        fitting = [c for c in fitting if panel_for_class(c, units)] or fitting     # il pannello fatto per la faccia della classe
    if sid == "eps":                                                                # classi dichiarate, almeno un ingresso solare
        fitting = [c for c in fitting if eps_class_ok(c, units)]
        fitting = [c for c in fitting if c.raw["specs"].get("pv_channels") != 0] or fitting
    if sid == "reaction_wheel" and sl.slew_rate_deg_s:                              # momento di ciascuna ruota per la rotazione richiesta
        h_req = wheel_momentum_needed_mnms(cls, sl.slew_rate_deg_s)
        fitting = [c for c in fitting if (c.spec("momentum_mnms") or 0.0) >= h_req - 1e-12]
    adcs_small_only = False
    if sid in CLASS_RANGE_SUBSYSTEMS and fitting:                                   # l'unita' ADCS o la ruota dichiarata per la classe
        # la regola "senza massa pubblicata solo se non c'e' altro" viene prima della classe dichiarata
        fitting = [c for c in fitting if c.mass_kg is not None] or fitting
        tiers = [adcs_tier(c, units) for c in fitting]
        best = min((t for t in tiers if t < 2), default=None)
        adcs_small_only = best is None
        fitting = [] if best is None else [c for c, t in zip(fitting, tiers) if t == best]
    fitting = [c for c in fitting if c.raw.get("status") != "nla"] or fitting          # i prodotti non piu' in vendita solo se non c'e' altro

    def units_of(c: Component) -> int:
        """Unita' del prodotto nel posto: per i magnetorquer quante ne servono per coprire gli assi richiesti."""
        if sl.subsystem == "magnetorquer" and sl.axes_needed:
            return max(1, math.ceil(sl.axes_needed / max(1, int(c.spec("axes") or 1))))
        return sl.quantity
    known = [_times(_candidate(c, cls.envelope_mm), units_of(c)) for c in fitting if c.mass_kg is not None]
    unknown = [_times(_candidate(c, cls.envelope_mm), units_of(c)) for c in fitting if c.mass_kg is None]
    pool = _order(known, mass_first) or _order(unknown, mass_first)    # senza massa pubblicata un componente e' ammesso solo se non c'e' di meglio
    if sid in layout.ORDER and any(k.height_mm is not None for k in pool):
        pool = [k for k in pool if k.height_mm is not None]    # idem senza quote: non si scavalca il vincolo della pila con un componente di cui non si conosce l'altezza
    return members, allowed, fitting, larger_only, adcs_small_only, known, unknown, pool


def admitted(catalog: list[Component], slot: Slot, units: int, mass_limit_kg: float | None = None, dv_m_s: float | None = None) -> list[Component]:
    """I componenti che select considera per il posto nella classe `units` (stesse regole: ingombro, classe dichiarata, massa pubblicata...)."""
    cls = CLASSES[units]
    if mass_limit_kg is not None and mass_limit_kg < cls.mass_limit_kg:
        cls = replace(cls, mass_limit_kg=float(mass_limit_kg))
    return [k.comp for k in _slot_pool(catalog, slot, units, cls, float(dv_m_s) if dv_m_s else None)[-1]]


def select(*args: Any, battery_mass_tolerance: float | None = None, **kwargs: Any) -> Selection:
    """select_once con la tolleranza di massa della batteria (vedi `select_once`): se con quel restringimento il progetto non sta nei limiti
    si ripete senza, cosi' la tolleranza non rende irrealizzabile una classe che lo e'."""
    sel = select_once(*args, battery_mass_tolerance=battery_mass_tolerance, **kwargs)
    if battery_mass_tolerance is not None and not sel.within_limits:
        return select_once(*args, battery_mass_tolerance=None, **kwargs)
    return sel


def select_once(catalog: list[Component], units: int, time_budget_s: float = 3.0, slots: list[Slot] | None = None,
                dv_m_s: float | None = None, mass_limit_kg: float | None = None, electric_power_check: bool = False,
                interface_check: bool = False, power_supply_check: bool = False, objective: str = "completeness", require_all: bool = False,
                battery_mass_tolerance: float | None = None) -> Selection:
    """Selezione per la classe `units`. Senza parametri facoltativi: un posto per ciascuno dei 17 sottosistemi, tutti i componenti, limiti CDS.
    slots: i posti del progetto (mission.py: solo i sottosistemi che la missione chiede, una radio per banda, i componenti che soddisfano i requisiti);
    dv_m_s: il propulsore scelto deve dare questo delta-v al satellite intero (impulso totale pubblicato / somma delle masse pubblicate);
    mass_limit_kg: massa massima chiesta dalla missione, se sotto il limite CDS della classe;
    electric_power_check: un propulsore elettrico deve funzionare con la potenza di picco del pannello solare scelto (mission.py lo attiva);
    interface_check: l'OBC ha almeno un'interfaccia dati in comune con ogni componente che pubblica le sue (mission.py lo attiva);
    power_supply_check: l'EPS alimenta ogni componente, accetta il pannello e la batteria e ne copre la potenza (mission.py lo attiva);
    objective: "completeness" (predefinito: massima completezza dei dati pubblicati, poi massa minima) oppure "mass" (massa minima al lancio,
    poi completezza: mission.py, filosofia dell'utente 2026-10-16: meno massa e volume lanciati, meno costi);
    require_all: un posto senza candidati nella classe rende il progetto incompleto (mission.py): la ricerca esatta non si fa e ogni scheda
    mostra il componente che entra da solo (within_limits False);
    battery_mass_tolerance (solo con objective "mass"): frazione di massa, es. 0.35 = +35 %: per la batteria sono ammesse tutte quelle con massa
    entro la tolleranza dalla piu' leggera e tra queste vince quella con piu' dati pubblicati (a parita' la piu' leggera); la massa totale
    resta minimizzata sugli altri sottosistemi (richiesta dell'utente 2026-10-24: privilegiare i componenti con piu' informazioni utili)."""
    if objective not in ("completeness", "mass"):
        raise ValueError(f"unsupported objective {objective!r} (allowed: completeness, mass)")
    mass_first = objective == "mass"
    if units not in CLASSES:
        raise ValueError(f"unsupported CubeSat class {units}U (allowed: {', '.join(f'{u}U' for u in CLASSES)})")
    cls = CLASSES[units]
    if mass_limit_kg is not None and mass_limit_kg < cls.mass_limit_kg:
        cls = replace(cls, mass_limit_kg=float(mass_limit_kg))
    slots = list(slots) if slots is not None else default_slots()
    dv = float(dv_m_s) if dv_m_s else None
    results: list[SubsystemResult] = []
    pools: list[list[Candidate]] = []
    for sl in slots:
        sid = sl.subsystem
        members, allowed, fitting, larger_only, adcs_small_only, known, unknown, pool = _slot_pool(catalog, sl, units, cls, dv, mass_first)
        note = None
        if not members:
            note = "No component of this subsystem is in the database."
        elif not allowed:
            note = "No component of this subsystem in the database meets the mission requirements."
        elif larger_only:
            note = f"The components of this subsystem that fit a {units}U are declared by their vendors for larger CubeSats only."
        elif adcs_small_only:
            note = f"The components of this subsystem that fit a {units}U are declared by their vendors for smaller CubeSats only (less momentum and torque than needed)."
        elif not fitting:
            note = f"No component of this subsystem in the database fits a {units}U" + (" and publishes its total impulse." if dv and sid == "propulsion" else ".")
        elif not known:
            note = "Only components without a published mass are in the database for this subsystem."
        results.append(SubsystemResult(sl.id, CATEGORY_OF.get(sid, sid), sl.label, len(members), len(pool), len(unknown), None, [], note, subsystem=sid))
        pools.append(pool)
    all_pools = list(pools)             # le alternative mostrate sono tutti i candidati, anche quelli esclusi dalla tolleranza di massa
    if mass_first and battery_mass_tolerance is not None:
        for i, sl in enumerate(slots):
            known = [k for k in pools[i] if k.mass_kg is not None]
            if sl.subsystem == "battery" and known:
                limit = min(k.mass_kg for k in known) * (1.0 + battery_mass_tolerance) + 1e-12
                band = [k for k in known if k.mass_kg <= limit]
                top = max(k.completeness for k in band)
                pools[i] = [k for k in band if k.completeness >= top - 1e-12]

    # scelta: massimizza la completezza totale (poi minimizza la massa) con somma delle masse e dei volumi noti entro i limiti
    idx = [i for i, p in enumerate(pools) if p]
    prop = [j for j, i in enumerate(idx) if results[i].subsystem == "propulsion"] if dv else []
    jp = next((j for j, i in enumerate(idx) if results[i].subsystem == "propulsion"), None) if electric_power_check else None
    js = next((j for j, i in enumerate(idx) if results[i].subsystem == "solar_panel"), None) if electric_power_check else None

    def fire_key(k: Candidate) -> float:
        if not is_electric(k.comp):
            return 0.0
        p = firing_power_w(k.comp)
        return p if p is not None else 1e9

    # scarico delle ruote: il dipolo del magnetorquer scarica in un'orbita il momento di una ruota (dump_am2_per_nms del posto del magnetorquer)
    jm = next((j for j, i in enumerate(idx) if results[i].subsystem == "magnetorquer"), None)
    jr = next((j for j, i in enumerate(idx) if results[i].subsystem == "reaction_wheel"), None)
    dump = slots[idx[jm]].dump_am2_per_nms if jm is not None and jr is not None else None

    def dump_ok(cands) -> bool:
        if not dump:
            return True
        dip, h = cands[jm].comp.spec("magnetic_moment_am2"), cands[jr].comp.spec("momentum_mnms")
        return h is None or (dip is not None and float(dip) >= float(h) / 1000.0 * dump - 1e-12)

    def extra_of(i: int):
        sid = results[i].subsystem
        parts = []
        if sid == "magnetorquer" and dump:
            parts.append(lambda k: -float(k.comp.spec("magnetic_moment_am2") or 0.0))
        if sid == "reaction_wheel" and dump:
            parts.append(lambda k: float(k.comp.spec("momentum_mnms") or 0.0))
        if sid == "propulsion" and prop:
            parts.append(lambda k: -(total_impulse_ns(k.comp) or 0.0))
        if sid == "propulsion" and jp is not None:
            parts.append(fire_key)
        if sid == "solar_panel" and jp is not None:
            parts.append(lambda k: -float(k.comp.spec("peak_power_w") or 0.0))
        return (lambda k: [f(k) for f in parts]) if parts else None
    jo = next((j for j, i in enumerate(idx) if results[i].subsystem == "obc"), None) if interface_check else None
    jx = next((j for j, i in enumerate(idx) if results[i].subsystem == "eps"), None) if power_supply_check else None

    def covers_of(i: int):
        sid, fs = results[i].subsystem, []
        if sid in ("structure", "solar_panel"):
            return lambda b, a: False           # lunghezza della struttura e facce per il pannello: nessun taglio (insiemi piccoli)
        if jx is not None and sid in ("eps", "battery", "solar_panel"):
            return lambda b, a: False           # vincoli di coppia con l'EPS: nessun taglio (insiemi piccoli)
        if jo is not None:
            fs.append(_covers_interfaces)
        if jx is not None:
            fs.append(_covers_supply)
        return (lambda b, a: all(f(b, a) for f in fs)) if fs else None
    spools = {i: _pareto(pools[i], extra_of(i), covers_of(i), mass_first) for i in idx}

    def fits_eps(k: Candidate, eps: Component) -> bool:
        """Il componente funziona con questo EPS: batteria (tensione, famiglia), pannello (ingresso solare), altrimenti tensione di alimentazione."""
        sid = subsystem_of(k.comp)
        if sid == "battery":
            return battery_ok(k.comp, eps)
        if sid == "solar_panel":
            return panel_ok(k.comp, eps)
        return powered_by(k.comp, eps)

    # la ricerca esatta chiede le stesse coppie milioni di volte: interfacce e compatibilita' con l'EPS calcolate una volta per componente
    eps_memo: dict[tuple[str, str], bool] = {}
    iface_memo: dict[str, frozenset[str] | None] = {}

    def fits_eps_memo(k: Candidate, eps: Component) -> bool:
        key = (k.comp.id, eps.id)
        if key not in eps_memo:
            eps_memo[key] = fits_eps(k, eps)
        return eps_memo[key]

    def iface_of(c: Component) -> frozenset[str] | None:
        if c.id not in iface_memo:
            iface_memo[c.id] = interfaces(c)
        return iface_memo[c.id]
    min_mass = [min((k.mass_kg or 0.0) for k in spools[i]) for i in idx]
    min_vol = [min((k.volume_m3 or 0.0) for k in spools[i]) for i in idx]
    max_score = [max(k.completeness for k in spools[i]) for i in idx]
    suffix_mass = [sum(min_mass[j:]) for j in range(len(idx) + 1)]
    suffix_vol = [sum(min_vol[j:]) for j in range(len(idx) + 1)]
    min_h = [min((k.column_mm or 0.0) for k in spools[i]) for i in idx]
    suffix_h = [sum(min_h[j:]) for j in range(len(idx) + 1)]
    stack_room = layout.columns(cls.envelope_mm) * cls.envelope_mm[2]       # somma delle altezze al piu' colonne x lunghezza (condizione necessaria)
    sids = [results[i].subsystem for i in idx]

    jst = next((j for j, i in enumerate(idx) if results[i].subsystem == "structure"), None)
    jsp = next((j for j, i in enumerate(idx) if results[i].subsystem == "solar_panel"), None)

    def stack_ok(cands) -> bool:
        """La pila dei componenti interni entra nella struttura scelta (le sue quote pubblicate, entro l'ingombro della classe)."""
        env = structure_envelope(cands[jst].comp, cls) if jst is not None else cls.envelope_mm
        # i payload ottici sul fondo, obiettivo verso la faccia -Z senza componenti davanti; le altre scatole del prodotto no
        return layout.stack_feasible([(sid, k.height_mm, k.span, sid in layout.APERTURE_SUBSYSTEMS) for sid, k in zip(sids, cands)]
                                     + [(sid, ph, ps, False) for sid, k in zip(sids, cands) for ph, ps in k.parts], env)

    def faces_ok(cands) -> bool:
        """Il pannello solare si monta su una faccia che la struttura offre."""
        return jst is None or jsp is None or panel_on_structure(cands[jsp].comp, cands[jst].comp)

    def dv_ok(cands, mass: float) -> bool:
        """Il propulsore da' il delta-v richiesto al satellite intero: impulso totale / massa (somma delle masse pubblicate dei componenti scelti)."""
        return all(mass > 0 and (total_impulse_ns(cands[j].comp) or 0.0) / mass >= dv - 1e-9 for j in prop)

    def power_ok(cands) -> bool:
        """Un propulsore elettrico funziona con la potenza di picco pubblicata del pannello solare scelto."""
        if jp is None or not is_electric(cands[jp].comp):
            return True
        fire = firing_power_w(cands[jp].comp)
        peak = cands[js].comp.spec("peak_power_w") if js is not None else None
        return fire is not None and peak is not None and fire <= float(peak) + 1e-9

    def iface_ok(cands) -> bool:
        """L'OBC ha almeno un'interfaccia dati in comune con ogni altro componente che pubblica le sue."""
        if jo is None:
            return True
        oi = iface_of(cands[jo].comp)
        if oi is None:
            return True
        return all(not (ci := iface_of(k.comp)) or (ci & oi) for j, k in enumerate(cands) if j != jo)

    def supply_ok(cands) -> bool:
        """L'EPS alimenta ogni componente, accetta pannello e batteria e la sua potenza massima copre il componente piu' esigente."""
        if jx is None:
            return True
        eps = cands[jx].comp
        if not all(fits_eps_memo(k, eps) for j, k in enumerate(cands) if j != jx):
            return False
        pmax = eps.raw["specs"].get("output_power_w_max")
        return pmax is None or max((k.power_w or 0.0 for j, k in enumerate(cands) if j != jx), default=0.0) <= float(pmax) + 1e-9
    suffix_score = [sum(max_score[j:]) for j in range(len(idx) + 1)]
    best: dict = {"key": None, "pick": None}
    mode = {"mass": mass_first}             # chiave dell'ottimo: (completezza, -massa) oppure (-massa, completezza)
    deadline = time.monotonic() + time_budget_s
    truncated = False

    # objective "mass": scelti l'OBC e l'EPS (primi livelli), il limite inferiore della massa che resta usa solo i candidati che comunicano
    # con quell'OBC e che quell'EPS alimenta (stessi filtri della ricerca): molto piu' stretto della somma dei minimi di tutti i candidati
    j_pair = max((x for x in (jo, jx) if x is not None), default=None)
    pair_suffix: dict = {}

    def suffix_for(pick: list[int]) -> list[float]:
        key = (pick[jo] if jo is not None else None, pick[jx] if jx is not None else None)
        if key not in pair_suffix:
            oi = iface_of(spools[idx[jo]][key[0]].comp) if jo is not None else None
            eps = spools[idx[jx]][key[1]].comp if jx is not None else None
            mins = []
            for t, i in enumerate(idx):
                ok = [k for k in spools[i] if (t == jo or oi is None or not (ci := iface_of(k.comp)) or (ci & oi))
                      and (t == jx or eps is None or fits_eps_memo(k, eps))]
                mins.append(min(((k.mass_kg or 0.0) for k in ok), default=math.inf))
            pair_suffix[key] = [sum(mins[s:]) for s in range(len(idx) + 1)]
        return pair_suffix[key]

    def rec(j: int, mass: float, vol: float, score: float, pick: list[int], hsum: float = 0.0) -> None:
        nonlocal truncated
        if time.monotonic() > deadline:
            truncated = True
            return
        if mass + suffix_mass[j] > cls.mass_limit_kg + 1e-12 or vol + suffix_vol[j] > cls.volume_limit_m3 + 1e-15:
            return      # vale anche per la foglia (j == len(idx), suffissi nulli): la combinazione completa deve stare nei limiti
        if hsum + suffix_h[j] > stack_room + 1e-9:
            return
        if j == len(idx):
            cands = [spools[idx[t]][pick[t]] for t in range(len(idx))]
            if not stack_ok(cands) or (prop and not dv_ok(cands, mass)) or not power_ok(cands) or not iface_ok(cands) or not supply_ok(cands) or not faces_ok(cands) or not dump_ok(cands):
                return
            key = (-round(mass, 9), round(score, 9)) if mode["mass"] else (round(score, 9), -mass)
            if best["key"] is None or key > best["key"]:
                best["key"], best["pick"] = key, list(pick)
            return
        if mode["mass"] and j_pair is not None and j > j_pair:
            rest = suffix_for(pick)[j]
            if mass + rest > cls.mass_limit_kg + 1e-12:
                return      # anche i candidati compatibili piu' leggeri superano il limite (o un livello non ha candidati compatibili)
        else:
            rest = suffix_mass[j]
        bound = ((-round(mass + rest, 9), round(score + suffix_score[j], 9)) if mode["mass"]
                 else (round(score + suffix_score[j], 9), -(mass + suffix_mass[j])))
        if best["key"] is not None and bound <= best["key"]:
            return
        # con l'OBC o l'EPS gia' scelti (livelli jo, jx) i componenti che non comunicano con l'OBC o che l'EPS non alimenta si scartano subito
        oi = iface_of(spools[idx[jo]][pick[jo]].comp) if jo is not None and j > jo else None
        eps = spools[idx[jx]][pick[jx]].comp if jx is not None and j > jx else None
        for n, k in enumerate(spools[idx[j]]):
            if oi is not None and (ci := iface_of(k.comp)) and not (ci & oi):
                continue
            if eps is not None and not fits_eps_memo(k, eps):
                continue
            pick.append(n)
            rec(j + 1, mass + (k.mass_kg or 0.0), vol + (k.volume_m3 or 0.0), score + k.completeness, pick, hsum + (k.column_mm or 0.0))
            pick.pop()

    # prima prova: il miglior candidato di ogni sottosistema (piu' dati pubblicati, poi il piu' leggero; con objective "mass" il piu' leggero,
    # poi piu' dati pubblicati); se rientra nei limiti e' la scelta
    greedy = [pools[i][0] for i in idx]
    g_mass = sum((k.mass_kg or 0.0) for k in greedy)
    g_vol = sum((k.volume_m3 or 0.0) for k in greedy)
    if require_all and len(idx) < len(pools):
        chosen = None       # un posto senza candidati: nessun progetto completo in questa classe
    elif g_mass <= cls.mass_limit_kg + 1e-12 and g_vol <= cls.volume_limit_m3 + 1e-15 and stack_ok(greedy) and (not prop or dv_ok(greedy, g_mass)) and power_ok(greedy) and iface_ok(greedy) and supply_ok(greedy) and faces_ok(greedy) and dump_ok(greedy):
        chosen = greedy
    else:   # altrimenti la ricerca esatta: massima completezza totale (con objective "mass": massa minima) con masse e volumi entro i limiti
        if mass_first:      # prima l'ottimo di completezza (il taglio sul punteggio e' rapido), poi la massa minima con quello come limite
            mode["mass"] = False
            rec(0, 0.0, 0.0, 0.0, [])
            if best["pick"] is not None:
                start = [spools[i][best["pick"][j]] for j, i in enumerate(idx)]
                best["key"] = (-round(sum((k.mass_kg or 0.0) for k in start), 9), round(sum(k.completeness for k in start), 9))
            mode["mass"] = True
        rec(0, 0.0, 0.0, 0.0, [])
        chosen = None if best["pick"] is None else [spools[i][best["pick"][j]] for j, i in enumerate(idx)]
    messages: list[str] = []
    within = chosen is not None
    if not within:   # tutti i sottosistemi insieme non stanno in questa classe: ogni scheda mostra il miglior componente che ci sta da solo e il totale e' segnalato
        chosen = greedy
        messages.append(f"The {len(idx)} subsystems together do not fit the limits of a {units}U ({cls.mass_limit_kg:g} kg, {sci(cls.volume_limit_m3)} m³, "
                        f"{layout.columns(cls.envelope_mm)} stack column(s) of {cls.envelope_mm[2]:g} mm"
                        + (f", a thruster that gives {dv:g} m/s to the whole satellite" if prop else "") + "): each card shows the component that fits on its own; "
                        "a {u}U cannot carry all of them at once.".replace("{u}", str(units)))
    for j, i in enumerate(idx):
        results[i].selected = chosen[j]
        results[i].alternatives = [k for k in all_pools[i] if k is not chosen[j]]
    if truncated:
        messages.append("The search stopped at the time limit: the selection may not be the one with the most complete data.")

    sel = [r.selected for r in results if r.selected]
    mass = sum(k.mass_kg or 0.0 for k in sel)
    vol = sum(k.volume_m3 or 0.0 for k in sel)
    power = sum(k.power_w or 0.0 for k in sel)
    mass_unknown = [k.comp.id for k in sel if k.mass_kg is None]
    vol_unknown = [k.comp.id for k in sel if k.volume_m3 is None and k.comp.category != "structure" and subsystem_of(k.comp) not in EXTERNAL_SUBSYSTEMS]
    power_unknown = [k.comp.id for k in sel if k.power_w is None and k.comp.category not in NO_POWER_SUBSYSTEMS]
    for r in results:
        if r.selected is None:
            messages.append(f"{r.label}: {r.note}")
    return Selection(cls, results, within, mass, vol, power, mass_unknown, vol_unknown, power_unknown, messages, truncated)

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
import time
from dataclasses import dataclass, field, replace

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
    """Un posto del progetto: un componente del sottosistema `subsystem`, scelto tra `allowed` (id del catalogo; None = tutti)."""
    id: str
    subsystem: str
    label: str
    allowed: frozenset[str] | None = None


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
    return Candidate(c, c.mass_kg, vol, declared_power_w(c), completeness(c), st["height"] if st else None)


def _admissible(c: Component, sid: str, cls: CubeSatClass) -> bool:
    """Scarto immediato dei componenti che non entrano: massa oltre il limite e, per i componenti della pila, impronta oltre la sezione di una colonna o altezza oltre Z."""
    if c.mass_kg is not None and c.mass_kg > cls.mass_limit_kg:
        return False
    if sid in layout.ORDER:
        st = layout.spec(c, sid, cls.envelope_mm)
        return st is None or st["perm"] is not None       # senza quote complete non si puo' escludere
    return fits_envelope(c, cls.envelope_mm)


def _order(cands: list[Candidate]) -> list[Candidate]:
    return sorted(cands, key=lambda k: (-k.completeness, k.mass_kg if k.mass_kg is not None else 1e9, k.comp.id))


def _covers_interfaces(b: Candidate, a: Candidate) -> bool:
    """b e' compatibile con l'OBC (o, per un OBC, con i componenti) ogni volta che lo e' a: interfacce non pubblicate (non si verifica) oppure
    un insieme che contiene quello di a."""
    ib, ia = interfaces(b.comp), interfaces(a.comp)
    return ib is None or (ia is not None and ib >= ia)


def _pareto(pool: list[Candidate], extra=None, covers=None) -> list[Candidate]:
    """Per la ricerca esatta: toglie i candidati battuti da un altro con completezza >= e massa, volume e altezza <= (non servono mai per l'ottimo).
    extra(k) aggiunge le grandezze dei vincoli attivi (piu' piccolo = meglio): con il delta-v l'impulso totale (cambiato di segno), con la
    potenza dei propulsori elettrici la potenza in accensione del propulsore e la potenza di picco del pannello (cambiata di segno)."""
    def key(k):
        return (k.mass_kg or 0.0, k.volume_m3 or 0.0, k.height_mm or 0.0) + (tuple(extra(k)) if extra else ())
    keep: list[Candidate] = []
    for a in pool:      # il pool e' ordinato per completezza decrescente, poi massa
        if not any(b.completeness >= a.completeness - 1e-12 and all(x <= y + 1e-15 for x, y in zip(key(b), key(a))) and (covers is None or covers(b, a))
                   for b in keep):
            keep.append(a)
    return keep


CATEGORY_OF = {sid: cat for sid, cat, _ in SUBSYSTEMS}


def select(catalog: list[Component], units: int, time_budget_s: float = 3.0, slots: list[Slot] | None = None,
           dv_m_s: float | None = None, mass_limit_kg: float | None = None, electric_power_check: bool = False,
           interface_check: bool = False, power_supply_check: bool = False) -> Selection:
    """Selezione per la classe `units`. Senza parametri facoltativi: un posto per ciascuno dei 17 sottosistemi, tutti i componenti, limiti CDS.
    slots: i posti del progetto (mission.py: solo i sottosistemi che la missione chiede, una radio per banda, i componenti che soddisfano i requisiti);
    dv_m_s: il propulsore scelto deve dare questo delta-v al satellite intero (impulso totale pubblicato / somma delle masse pubblicate);
    mass_limit_kg: massa massima chiesta dalla missione, se sotto il limite CDS della classe;
    electric_power_check: un propulsore elettrico deve funzionare con la potenza di picco del pannello solare scelto (mission.py lo attiva);
    interface_check: l'OBC ha almeno un'interfaccia dati in comune con ogni componente che pubblica le sue (mission.py lo attiva);
    power_supply_check: l'EPS alimenta ogni componente, accetta il pannello e la batteria e ne copre la potenza (mission.py lo attiva)."""
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
        adcs_small_only = False
        if sid == "adcs" and fitting:                                                   # l'unita' ADCS dichiarata per la classe
            tiers = [adcs_tier(c, units) for c in fitting]
            best = min((t for t in tiers if t < 2), default=None)
            adcs_small_only = best is None
            fitting = [] if best is None else [c for c, t in zip(fitting, tiers) if t == best]
        fitting = [c for c in fitting if c.raw.get("status") != "nla"] or fitting          # i prodotti non piu' in vendita solo se non c'e' altro
        known = [_candidate(c, cls.envelope_mm) for c in fitting if c.mass_kg is not None]
        unknown = [_candidate(c, cls.envelope_mm) for c in fitting if c.mass_kg is None]
        pool = _order(known) or _order(unknown)    # senza massa pubblicata un componente e' ammesso solo se non c'e' di meglio
        if sid in layout.ORDER and any(k.height_mm is not None for k in pool):
            pool = [k for k in pool if k.height_mm is not None]    # idem senza quote: non si scavalca il vincolo della pila con un componente di cui non si conosce l'altezza
        note = None
        if not members:
            note = "No component of this subsystem is in the database."
        elif not allowed:
            note = "No component of this subsystem in the database meets the mission requirements."
        elif larger_only:
            note = f"The components of this subsystem that fit a {units}U are declared by their vendors for larger CubeSats only."
        elif adcs_small_only:
            note = f"The ADCS units that fit a {units}U are declared by their vendors for smaller CubeSats only (less momentum and torque than needed)."
        elif not fitting:
            note = f"No component of this subsystem in the database fits a {units}U" + (" and publishes its total impulse." if dv and sid == "propulsion" else ".")
        elif not known:
            note = "Only components without a published mass are in the database for this subsystem."
        results.append(SubsystemResult(sl.id, CATEGORY_OF.get(sid, sid), sl.label, len(members), len(pool), len(unknown), None, [], note, subsystem=sid))
        pools.append(pool)

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

    def extra_of(i: int):
        sid = results[i].subsystem
        parts = []
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
        if jx is not None and sid in ("eps", "battery", "solar_panel"):
            return lambda b, a: False           # vincoli di coppia con l'EPS: nessun taglio (insiemi piccoli)
        if jo is not None:
            fs.append(_covers_interfaces)
        if jx is not None:
            fs.append(_covers_supply)
        return (lambda b, a: all(f(b, a) for f in fs)) if fs else None
    spools = {i: _pareto(pools[i], extra_of(i), covers_of(i)) for i in idx}

    def fits_eps(k: Candidate, eps: Component) -> bool:
        """Il componente funziona con questo EPS: batteria (tensione, famiglia), pannello (ingresso solare), altrimenti tensione di alimentazione."""
        sid = subsystem_of(k.comp)
        if sid == "battery":
            return battery_ok(k.comp, eps)
        if sid == "solar_panel":
            return panel_ok(k.comp, eps)
        return powered_by(k.comp, eps)
    min_mass = [min((k.mass_kg or 0.0) for k in spools[i]) for i in idx]
    min_vol = [min((k.volume_m3 or 0.0) for k in spools[i]) for i in idx]
    max_score = [max(k.completeness for k in spools[i]) for i in idx]
    suffix_mass = [sum(min_mass[j:]) for j in range(len(idx) + 1)]
    suffix_vol = [sum(min_vol[j:]) for j in range(len(idx) + 1)]
    min_h = [min((k.height_mm or 0.0) for k in spools[i]) for i in idx]
    suffix_h = [sum(min_h[j:]) for j in range(len(idx) + 1)]
    stack_room = layout.columns(cls.envelope_mm) * cls.envelope_mm[2]       # somma delle altezze al piu' colonne x lunghezza (condizione necessaria)
    sids = [results[i].subsystem for i in idx]

    def stack_ok(cands) -> bool:
        return layout.stack_feasible([(sid, k.height_mm) for sid, k in zip(sids, cands)], cls.envelope_mm)

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
        oi = interfaces(cands[jo].comp)
        if oi is None:
            return True
        return all(not (ci := interfaces(k.comp)) or (ci & oi) for j, k in enumerate(cands) if j != jo)

    def supply_ok(cands) -> bool:
        """L'EPS alimenta ogni componente, accetta pannello e batteria e la sua potenza massima copre il componente piu' esigente."""
        if jx is None:
            return True
        eps = cands[jx].comp
        if not all(fits_eps(k, eps) for j, k in enumerate(cands) if j != jx):
            return False
        pmax = eps.raw["specs"].get("output_power_w_max")
        return pmax is None or max((k.power_w or 0.0 for j, k in enumerate(cands) if j != jx), default=0.0) <= float(pmax) + 1e-9
    suffix_score = [sum(max_score[j:]) for j in range(len(idx) + 1)]
    best: dict = {"key": None, "pick": None}
    deadline = time.monotonic() + time_budget_s
    truncated = False

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
            if not stack_ok(cands) or (prop and not dv_ok(cands, mass)) or not power_ok(cands) or not iface_ok(cands) or not supply_ok(cands):
                return
            key = (round(score, 9), -mass)
            if best["key"] is None or key > best["key"]:
                best["key"], best["pick"] = key, list(pick)
            return
        if best["key"] is not None and (round(score + suffix_score[j], 9), -(mass + suffix_mass[j])) <= best["key"]:
            return
        # con l'OBC o l'EPS gia' scelti (livelli jo, jx) i componenti che non comunicano con l'OBC o che l'EPS non alimenta si scartano subito
        oi = interfaces(spools[idx[jo]][pick[jo]].comp) if jo is not None and j > jo else None
        eps = spools[idx[jx]][pick[jx]].comp if jx is not None and j > jx else None
        for n, k in enumerate(spools[idx[j]]):
            if oi is not None and (ci := interfaces(k.comp)) and not (ci & oi):
                continue
            if eps is not None and not fits_eps(k, eps):
                continue
            pick.append(n)
            rec(j + 1, mass + (k.mass_kg or 0.0), vol + (k.volume_m3 or 0.0), score + k.completeness, pick, hsum + (k.height_mm or 0.0))
            pick.pop()

    # prima prova: il miglior candidato di ogni sottosistema (piu' dati pubblicati, poi il piu' leggero); se rientra nei limiti e' la scelta
    greedy = [pools[i][0] for i in idx]
    g_mass = sum((k.mass_kg or 0.0) for k in greedy)
    g_vol = sum((k.volume_m3 or 0.0) for k in greedy)
    if g_mass <= cls.mass_limit_kg + 1e-12 and g_vol <= cls.volume_limit_m3 + 1e-15 and stack_ok(greedy) and (not prop or dv_ok(greedy, g_mass)) and power_ok(greedy) and iface_ok(greedy) and supply_ok(greedy):
        chosen = greedy
    else:   # altrimenti la ricerca esatta: massima completezza totale con somma delle masse e dei volumi entro i limiti
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
        results[i].alternatives = [k for k in pools[i] if k is not chosen[j]]
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

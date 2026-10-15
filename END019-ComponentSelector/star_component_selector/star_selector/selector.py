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
Non ci sono bilancio energetico, compatibilita' di tensioni o interfacce, ne' requisiti di missione."""
from __future__ import annotations

import itertools
import time
from dataclasses import dataclass, field

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


def _pareto(pool: list[Candidate]) -> list[Candidate]:
    """Per la ricerca esatta: toglie i candidati battuti da un altro con completezza >= e massa, volume e altezza <= (non servono mai per l'ottimo)."""
    def key(k):
        return (k.mass_kg or 0.0, k.volume_m3 or 0.0, k.height_mm or 0.0)
    keep: list[Candidate] = []
    for a in pool:      # il pool e' ordinato per completezza decrescente, poi massa
        if not any(b.completeness >= a.completeness - 1e-12 and all(x <= y + 1e-15 for x, y in zip(key(b), key(a))) for b in keep):
            keep.append(a)
    return keep


def select(catalog: list[Component], units: int, time_budget_s: float = 3.0) -> Selection:
    if units not in CLASSES:
        raise ValueError(f"unsupported CubeSat class {units}U (allowed: {', '.join(f'{u}U' for u in CLASSES)})")
    cls = CLASSES[units]
    results: list[SubsystemResult] = []
    pools: list[list[Candidate]] = []
    for sid, cat, label in SUBSYSTEMS:
        members = [c for c in catalog if subsystem_of(c) == sid]
        if sid == "structure":
            fitting = [c for c in members if c.spec("form_factor_u") == units]
        else:
            fitting = [c for c in members if _admissible(c, sid, cls)]
        known = [_candidate(c, cls.envelope_mm) for c in fitting if c.mass_kg is not None]
        unknown = [_candidate(c, cls.envelope_mm) for c in fitting if c.mass_kg is None]
        pool = _order(known) or _order(unknown)    # senza massa pubblicata un componente e' ammesso solo se non c'e' di meglio
        if sid in layout.ORDER and any(k.height_mm is not None for k in pool):
            pool = [k for k in pool if k.height_mm is not None]    # idem senza quote: non si scavalca il vincolo della pila con un componente di cui non si conosce l'altezza
        note = None
        if not members:
            note = "No component of this subsystem is in the database."
        elif not fitting:
            note = f"No component of this subsystem in the database fits a {units}U."
        elif not known:
            note = "Only components without a published mass are in the database for this subsystem."
        results.append(SubsystemResult(sid, cat, label, len(members), len(pool), len(unknown), None, [], note))
        pools.append(pool)

    # scelta: massimizza la completezza totale (poi minimizza la massa) con somma delle masse e dei volumi noti entro i limiti
    idx = [i for i, p in enumerate(pools) if p]
    spools = {i: _pareto(pools[i]) for i in idx}       # candidati della ricerca esatta (senza quelli battuti)
    min_mass = [min((k.mass_kg or 0.0) for k in spools[i]) for i in idx]
    min_vol = [min((k.volume_m3 or 0.0) for k in spools[i]) for i in idx]
    max_score = [max(k.completeness for k in spools[i]) for i in idx]
    suffix_mass = [sum(min_mass[j:]) for j in range(len(idx) + 1)]
    suffix_vol = [sum(min_vol[j:]) for j in range(len(idx) + 1)]
    min_h = [min((k.height_mm or 0.0) for k in spools[i]) for i in idx]
    suffix_h = [sum(min_h[j:]) for j in range(len(idx) + 1)]
    stack_room = layout.columns(cls.envelope_mm) * cls.envelope_mm[2]       # somma delle altezze al piu' colonne x lunghezza (condizione necessaria)
    sids = [results[i].id for i in idx]

    def stack_ok(cands) -> bool:
        return layout.stack_feasible({sid: k.height_mm for sid, k in zip(sids, cands)}, cls.envelope_mm)
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
            if not stack_ok([spools[idx[t]][pick[t]] for t in range(len(idx))]):
                return
            key = (round(score, 9), -mass)
            if best["key"] is None or key > best["key"]:
                best["key"], best["pick"] = key, list(pick)
            return
        if best["key"] is not None and (round(score + suffix_score[j], 9), -(mass + suffix_mass[j])) <= best["key"]:
            return
        for n, k in enumerate(spools[idx[j]]):
            pick.append(n)
            rec(j + 1, mass + (k.mass_kg or 0.0), vol + (k.volume_m3 or 0.0), score + k.completeness, pick, hsum + (k.height_mm or 0.0))
            pick.pop()

    # prima prova: il miglior candidato di ogni sottosistema (piu' dati pubblicati, poi il piu' leggero); se rientra nei limiti e' la scelta
    greedy = [0] * len(idx)
    g_mass = sum((pools[i][0].mass_kg or 0.0) for i in idx)
    g_vol = sum((pools[i][0].volume_m3 or 0.0) for i in idx)
    if g_mass <= cls.mass_limit_kg + 1e-12 and g_vol <= cls.volume_limit_m3 + 1e-15 and stack_ok([pools[i][0] for i in idx]):
        best["pick"] = greedy
    else:   # altrimenti la ricerca esatta: massima completezza totale con somma delle masse e dei volumi entro i limiti
        rec(0, 0.0, 0.0, 0.0, [])
    messages: list[str] = []
    within = best["pick"] is not None
    if within:
        chosen = [spools[i][best["pick"][j]] for j, i in enumerate(idx)]
    else:   # tutti i sottosistemi insieme non stanno in questa classe: ogni scheda mostra il miglior componente che ci sta da solo e il totale e' segnalato
        chosen = [pools[i][0] for i in idx]
        messages.append(f"The {len(idx)} subsystems together do not fit the limits of a {units}U ({cls.mass_limit_kg:g} kg, {sci(cls.volume_limit_m3)} m³, "
                        f"{layout.columns(cls.envelope_mm)} stack column(s) of {cls.envelope_mm[2]:g} mm): each card shows the component that fits on its own; "
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

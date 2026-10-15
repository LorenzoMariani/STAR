"""Controllo di ingombro: i componenti interni scelti, come parallelepipedi con le quote pubblicate, entrano nell'ingombro CDS della classe?

Esiti (stati):
  fits           trovata una disposizione senza sovrapposizioni dentro l'ingombro (e' una dimostrazione, non una disposizione di progetto);
  does_not_fit   il volume interno supera il volume dell'ingombro: nessuna disposizione puo' esistere (esito certo);
  not_shown      il volume basterebbe ma l'euristica non ha trovato una disposizione: non e' dimostrato che sia impossibile;
  undetermined   a un componente interno scelto mancano le quote pubblicate: non verificabile.
Non modellati (non pubblicati dai fornitori): pareti e guide della struttura, connettori, cablaggio, zone di rispetto, baricentro.
Pannelli solari e antenne sono esterni (regola dichiarata): si appoggiano a una faccia e non entrano nella disposizione interna.
La selezione non cambia: il controllo riporta soltanto l'esito."""
from __future__ import annotations

import itertools
import random
from typing import Any

from . import layout
from .rows import subsystem_of
from .selector import EXTERNAL_SUBSYSTEMS, FACE_MM, Selection

EPS = 1e-9
LABELS = {"fits": "Fits the CDS envelope", "does_not_fit": "Does not fit", "not_shown": "Not shown to fit", "undetermined": "Undetermined"}
SHUFFLES = 60           # ordini casuali provati dopo quello per volume decrescente (seme fisso: risultato ripetibile)
VISUAL_THICKNESS_MM = 2.0   # solo per il disegno di un pannello esterno senza spessore pubblicato


def _full_dims(c) -> tuple[float, float, float] | None:
    d = c.dimensions_mm
    return tuple(float(x) for x in d) if d and all(x is not None for x in d) else None


def _overlap(a, b) -> bool:
    return all(a[i] < b[i] + b[i + 3] - EPS and a[i] + a[i + 3] > b[i] + EPS for i in range(3))


def _orients(d):
    """Le orientazioni distinte di una scatola: [(dimensioni orientate, perm)], con perm[asse] = indice della quota originale su quell'asse."""
    seen: dict = {}
    for perm in itertools.permutations(range(3)):
        seen.setdefault(tuple(d[k] for k in perm), perm)
    return sorted(seen.items())


def pack(env: tuple[float, float, float], boxes: list[tuple[str, tuple[float, float, float]]], shuffles: int = SHUFFLES):
    """Euristica a punti estremi con le sei orientazioni. Restituisce [(id, x, y, z, dx, dy, dz, perm)] oppure None se non trova una disposizione."""

    def attempt(seq):
        placed: list[tuple] = []
        points = [(0.0, 0.0, 0.0)]
        for name, d in seq:
            for px, py, pz in sorted(points, key=lambda p: (p[2], p[1], p[0])):
                hit = next(((o, perm) for o, perm in _orients(d)
                            if px + o[0] <= env[0] + EPS and py + o[1] <= env[1] + EPS and pz + o[2] <= env[2] + EPS
                            and not any(_overlap((px, py, pz) + o, q[1:7]) for q in placed)), None)
                if hit:
                    o, perm = hit
                    placed.append((name, px, py, pz) + o + (perm,))
                    points += [(px + o[0], py, pz), (px, py + o[1], pz), (px, py, pz + o[2])]
                    break
            else:
                return None
        return placed

    base = sorted(boxes, key=lambda b: (-b[1][0] * b[1][1] * b[1][2], b[0]))
    found = attempt(base)
    rng = random.Random(1)
    for _ in range(shuffles):
        if found:
            break
        seq = base[:]
        rng.shuffle(seq)
        found = attempt(seq)
    return found


PLANAR = ("board", "stack", "panel", "patch", "coil_board")     # hanno una normale: la quota piu' piccola


def shape_for(c, dims, perm) -> dict[str, Any]:
    """Forma semplificata del componente espressa negli assi della disposizione (axis e normal = asse orientato 0, 1 o 2)."""
    sh = c.raw.get("shape") or {}
    kind = sh.get("type") or "box"
    inv = {local: axis for axis, local in enumerate(perm)}
    out: dict[str, Any] = {"type": kind, "basis": sh.get("basis"), "axis": None, "normal": None}
    if sh.get("axis") is not None and dims is not None:
        out["axis"] = inv[sh["axis"]]
    if kind in PLANAR and dims is not None:
        out["normal"] = inv[min(range(3), key=lambda k: (dims[k], -k))]
    return out


def _faces(env):
    x, y, z = env
    # (nome, assi della faccia (indice, lunghezza) x2, indice dell'asse normale): visibili nella vista fissa: +X, +Y, +Z
    return [("+Y", ((0, x), (2, z)), 1), ("+X", ((1, y), (2, z)), 0), ("+Z", ((0, x), (1, y)), 2)]


def _place_external(c, env, taken: set[str]):
    """Appoggia un componente esterno alla faccia piu' piccola su cui entra (centrato; in un angolo se la faccia e' gia' occupata)."""
    dims = _full_dims(c)
    published = dims is not None
    if dims is None:
        face = FACE_MM.get(str(c.raw["specs"].get("face"))) if c.category == "solar_panel" else None
        if not face:
            return None
        dims = (face[0], face[1], VISUAL_THICKNESS_MM)
    order = sorted(range(3), key=lambda k: (-dims[k], k))       # indici delle quote: lunga, media, sottile
    a, b, t = (dims[k] for k in order)
    fits = []
    for name, ((i, li), (j, lj)), n in _faces(env):
        for da, db in ((a, b), (b, a)):
            if da <= li + EPS and db <= lj + EPS:
                fits.append((li * lj, name, i, j, n, da, db))
                break
    if not fits:
        return None
    _, name, i, j, n, da, db = min(fits)
    size = [0.0, 0.0, 0.0]
    size[i], size[j], size[n] = da, db, t
    perm = [0, 0, 0]
    perm[i], perm[j] = (order[0], order[1]) if da == a and db == b else (order[1], order[0])
    perm[n] = order[2]
    pos = [0.0, 0.0, 0.0]
    li, lj = env[i], env[j]
    corner = name in taken
    pos[i] = 0.0 if corner else (li - da) / 2
    pos[j] = 0.0 if corner else (lj - db) / 2
    pos[n] = env[n]
    taken.add(name)
    return {"face": name, "pos": [round(v, 1) for v in pos], "size": [round(v, 2) for v in size], "size_published": published,
            "shape": shape_for(c, dims if published else None, perm) if published else {**shape_for(c, dims, perm), "axis": None}}


def stack_arrangement(env, internal):
    """Pila lungo Z nell'ordine dichiarato di layout.ORDER, a serpentina nelle colonne della classe. Restituisce le stesse tuple di pack() oppure None."""
    items = {sid: (k, d) for sid, k, d in internal}
    seq, specs = [], {}
    for sid in layout.ORDER:
        if sid in items:
            st = layout.spec(items[sid][0].comp, sid, env)
            if st is None or st["perm"] is None:
                return None
            specs[sid] = st
            seq.append((sid, st["height"]))
    if set(specs) != set(items):
        return None                       # un componente interno fuori dall'elenco della pila
    slots = layout.serpentine(seq, env[2], layout.columns(env))
    if slots is None:
        return None
    nx, _, cx, cy = layout.grid(env)
    placed = []
    for sid, col, z_low in slots:
        perm, d = specs[sid]["perm"], items[sid][1]
        size = tuple(d[perm[a]] for a in range(3))
        x, y = (col % nx) * cx + (cx - size[0]) / 2, (col // nx) * cy + (cy - size[1]) / 2
        placed.append((sid, x, y, z_low) + size + (perm,))
    return placed


def check_fit(sel: Selection) -> dict[str, Any]:
    cls = sel.cubesat
    env = cls.envelope_mm
    internal, unknown, external = [], [], []
    for r in sel.subsystems:
        k = r.selected
        if not k or r.id == "structure":
            continue
        if r.id in EXTERNAL_SUBSYSTEMS:
            external.append((r.id, k))
            continue
        d = _full_dims(k.comp)
        if d is None:
            unknown.append(k.comp.id)
        else:
            internal.append((r.id, k, d))
    vol = sum(d[0] * d[1] * d[2] for _, _, d in internal) * 1e-9
    out: dict[str, Any] = {"state": None, "label": None, "envelope_mm": list(env), "internal_volume_m3": vol, "volume_limit_m3": cls.volume_limit_m3,
                           "internal_volume_fraction": vol / cls.volume_limit_m3, "unknown_size": unknown, "placed": [], "external": [], "message": ""}
    if unknown:
        out["state"] = "undetermined"
        out["message"] = "The size is not publicly available for: " + ", ".join(unknown) + ". The fit cannot be verified."
    elif vol > cls.volume_limit_m3 + 1e-15:
        out["state"] = "does_not_fit"
        out["message"] = f"The internal components alone need {100 * out['internal_volume_fraction']:.0f}% of the volume of the CDS envelope: no arrangement can exist."
    else:
        placed = stack_arrangement(env, internal)
        out["arrangement"] = "stack" if placed else "generic"
        if placed is None:
            placed = pack(env, [(sid, d) for sid, _, d in internal])
        if placed:
            out["state"] = "fits"
            names = {sid: k for sid, k, _ in internal}
            dims_of = {sid: d for sid, _, d in internal}
            out["placed"] = [{"subsystem": n, "id": names[n].comp.id, "name": names[n].comp.raw["name"], "pos": [round(x, 3), round(y, 3), round(z, 3)],
                              "size": [round(dx, 3), round(dy, 3), round(dz, 3)], "shape": shape_for(names[n].comp, dims_of[n], perm)}
                             for n, x, y, z, dx, dy, dz, perm in placed]
            how = ("The internal components are stacked along the long axis in the declared order (radio, OBC, GPS, EPS, battery, ADCS, magnetorquer, wheel, star tracker, "
                   f"propulsion, payload) in {layout.columns(env)} column(s) of {env[2]:g} mm." if out["arrangement"] == "stack" else
                   "The arrangement does not follow the stacking convention: it was found by a generic search.")
            out["message"] = (f"{how} Walls, guides, connectors and keep-out zones are not modelled: it shows that the parts can be accommodated, it is not an engineering layout.")
        else:
            out["state"] = "not_shown"
            out["message"] = (f"The internal volume is {100 * out['internal_volume_fraction']:.0f}% of the envelope and no arrangement was found: "
                              "it is not proved impossible. Walls and keep-out zones are not known.")
    out["label"] = LABELS[out["state"]]
    taken: set[str] = set()
    for sid, k in sorted(external, key=lambda e: e[0] != "solar_panel"):     # il pannello solare sceglie prima la faccia
        spot = _place_external(k.comp, env, taken)
        if spot:
            out["external"].append({"subsystem": sid, "id": k.comp.id, "name": k.comp.raw["name"], **spot})
    return out

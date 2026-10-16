"""Controllo di ingombro: i componenti interni scelti, come parallelepipedi con le quote pubblicate, entrano nell'ingombro CDS della classe?

Esiti (stati):
  fits           trovata una disposizione senza sovrapposizioni dentro l'ingombro (e' una dimostrazione, non una disposizione di progetto);
  does_not_fit   il volume interno supera il volume dell'ingombro: nessuna disposizione puo' esistere (esito certo);
  not_shown      il volume basterebbe ma l'euristica non ha trovato una disposizione: non e' dimostrato che sia impossibile;
  undetermined   a un componente interno scelto mancano le quote pubblicate: non verificabile.
Non modellati (non pubblicati dai fornitori): pareti e guide della struttura, connettori, cablaggio, zone di rispetto, baricentro.
Pannelli solari e antenne sono esterni (regola dichiarata): si appoggiano a una faccia e non entrano nella disposizione interna.
La selezione non cambia: il controllo riporta soltanto l'esito.
Quando l'ingombro non e' dimostrato (2026-10-16) "placed" resta vuoto e "preview" porta un'anteprima da disegnare, che non e' una dimostrazione:
i componenti con le quote pubblicate nella pila dichiarata (allungata oltre il fondo quanto serve, con i pezzi che sporgono segnati "outside"),
lo spazio libero rimasto nelle colonne e l'elenco dei componenti senza quote pubblicate (non disegnati)."""
from __future__ import annotations

import itertools
import random
from typing import Any

from . import layout
from .rows import subsystem_of
from .selector import EXTERNAL_SUBSYSTEMS, Selection, panel_face, structure_envelope

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
    known = [float(x) for x in (c.dimensions_mm or []) if x is not None]
    if dims is None:
        face = panel_face(c)
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
    return {"face": name, "pos": [round(v, 1) for v in pos], "size": [round(v, 2) for v in size], "size_published": published, "published_mm": known,
            "shape": shape_for(c, dims if published else None, perm) if published else {**shape_for(c, dims, perm), "axis": None}}


def stack_arrangement(env, internal):
    """Pila lungo Z nell'ordine dichiarato di layout.ORDER, a serpentina nelle colonne della classe. Restituisce le stesse tuple di pack() oppure None.
    internal: [(posto, sottosistema, candidato, quote)]; il posto distingue due componenti dello stesso sottosistema (es. due radio)."""
    items = {slot: (sid, k, d) for slot, sid, k, d in internal}
    if any(sid not in layout.ORDER for sid, _, _ in items.values()):
        return None                       # un componente interno fuori dall'elenco della pila
    seq, specs = [], {}
    for sid, slot in layout.stack_order([(sid, slot) for slot, (sid, _, _) in items.items()]):
        st = layout.spec(items[slot][1].comp, sid, env)
        if st is None or st["perm"] is None:
            return None
        specs[slot] = st
        seq.append((slot, st["height"] * items[slot][1].quantity))         # q unita' impilate lungo Z
    cells = layout.serpentine(seq, env[2], layout.columns(env))
    if cells is None:
        return None
    nx, _, cx, cy = layout.grid(env)
    placed = []
    for slot, col, z_low in cells:
        perm, d = specs[slot]["perm"], items[slot][2]
        size = tuple(d[perm[a]] for a in range(3))
        x, y = (col % nx) * cx + (cx - size[0]) / 2, (col // nx) * cy + (cy - size[1]) / 2
        placed.append((slot, x, y, z_low) + size + (perm,))
    return placed


def _stack_specs(env, internal):
    """[(posto, altezza, perm)] nell'ordine della pila (sottosistemi fuori da layout.ORDER in fondo); un'impronta che non entra nella sezione di
    una colonna tiene la quota preferita lungo Z e sporge di lato."""
    items = {slot: (sid, k, d) for slot, sid, k, d in internal}
    keys = [(sid, slot) for slot, (sid, _, _) in items.items()]
    ordered = layout.stack_order(keys) + [it for it in keys if it[0] not in layout.ORDER]
    out = []
    for sid, slot in ordered:
        _, k, d = items[slot]
        st = layout.spec(k.comp, sid, env)
        if st is not None and st["perm"] is not None:
            perm = st["perm"]
        else:
            h = layout.height_index(k.comp, sid, d) if layout.full_dims(k.comp) else min(range(3), key=lambda i: d[i])
            a, b = sorted((i for i in range(3) if i != h), key=lambda i: -d[i])
            perm = (a, b, h)
        out.append((slot, d[perm[2]], perm))
    return out


def extended_stack(env, internal):
    """La pila dichiarata allungata quanto serve: la lunghezza minima L >= Z dell'ingombro con cui la serpentina entra nelle colonne della classe
    (next-fit: con colonne piu' lunghe non servono piu' colonne, quindi la ricerca per bisezione e' esatta a 0.1 mm), con la cima della pila sulla
    faccia superiore. Restituisce (tuple come pack() con z < 0 per i pezzi oltre il fondo, L)."""
    specs = _stack_specs(env, internal)
    if not specs:
        return [], env[2]
    seq = [(slot, h) for slot, h, _ in specs]
    ncol = layout.columns(env)
    lo, hi = max(env[2], max(h for _, h in seq)), max(env[2], sum(h for _, h in seq))
    if layout.serpentine(seq, lo, ncol) is None:
        while hi - lo > 0.1:
            mid = (lo + hi) / 2
            lo, hi = (lo, mid) if layout.serpentine(seq, mid, ncol) is not None else (mid, hi)
        lo = hi
    cells = layout.serpentine(seq, lo, ncol)
    perm_of = {slot: perm for slot, _, perm in specs}
    dims_of = {slot: d for slot, _, _, d in internal}
    nx, _, cx, cy = layout.grid(env)
    placed = []
    for slot, col, z_low in cells:
        perm, d = perm_of[slot], dims_of[slot]
        size = tuple(d[perm[a]] for a in range(3))
        x, y = (col % nx) * cx + (cx - size[0]) / 2, (col // nx) * cy + (cy - size[1]) / 2
        placed.append((slot, x, y, z_low - (lo - env[2])) + size + (perm,))
    return placed, lo


def _free_columns(env, placed):
    """Spazio libero sotto la pila in ogni colonna (la pila si riempie dall'alto): [{"pos", "size"}] in mm."""
    nx, _, cx, cy = layout.grid(env)
    free = []
    for col in range(layout.columns(env)):
        x0, y0 = (col % nx) * cx, (col // nx) * cy
        inside = [p for p in placed if x0 - EPS <= p[1] + p[4] / 2 <= x0 + cx + EPS and y0 - EPS <= p[2] + p[5] / 2 <= y0 + cy + EPS]
        bottom = min((p[3] for p in inside), default=env[2])
        if bottom > 1.0:
            free.append({"pos": [round(x0, 1), round(y0, 1), 0.0], "size": [round(cx, 1), round(cy, 1), round(bottom, 1)]})
    return free


def _preview(env, internal, state):
    """Anteprima per gli stati senza dimostrazione: (tuple come pack(), dizionario preview senza "placed"). Con quote mancanti si prova prima la pila
    dichiarata e poi la ricerca generica dentro l'ingombro; altrimenti (o se non entrano) la pila allungata."""
    if not internal:
        return [], {"kind": "stack", "free": [{"pos": [0.0, 0.0, 0.0], "size": [round(v, 1) for v in env]}], "stack_length_mm": None}
    if state == "undetermined":
        placed = stack_arrangement(env, internal)
        if placed is not None:
            return placed, {"kind": "stack", "free": _free_columns(env, placed), "stack_length_mm": None}
        placed = pack(env, [(slot, d) for slot, _, _, d in internal])
        if placed:
            return placed, {"kind": "generic", "free": [], "stack_length_mm": None}
    placed, length = extended_stack(env, internal)
    return placed, {"kind": "extended_stack", "free": [], "stack_length_mm": round(length, 1)}


def _outside(env, x, y, z, dx, dy, dz) -> bool:
    return x < -0.05 or y < -0.05 or z < -0.05 or x + dx > env[0] + 0.05 or y + dy > env[1] + 0.05 or z + dz > env[2] + 0.05


def check_fit(sel: Selection) -> dict[str, Any]:
    cls = sel.cubesat
    struct = next((r.selected.comp for r in sel.subsystems if (r.subsystem or r.id) == "structure" and r.selected), None)
    env = structure_envelope(struct, cls)          # le quote della struttura scelta (2026-10-16), entro l'ingombro della classe
    internal, unknown, missing, external = [], [], [], []
    for r in sel.subsystems:
        k = r.selected
        sid = r.subsystem or r.id
        if not k or sid == "structure":
            continue
        if sid in EXTERNAL_SUBSYSTEMS:
            external.append((r.id, sid, k))
            continue
        d = _full_dims(k.comp)
        if d is not None and k.quantity > 1:          # q unita' dello stesso prodotto impilate lungo l'asse della pila
            st = layout.spec(k.comp, sid, env) if sid in layout.ORDER else None
            h = st["perm"][2] if st and st["perm"] else min(range(3), key=lambda i: d[i])
            d = tuple(v * k.quantity if i == h else v for i, v in enumerate(d))
        if d is None:
            unknown.append(k.comp.id)
            missing.append((r.id, sid, k))
        else:
            internal.append((r.id, sid, k, d))
    vol = sum(d[0] * d[1] * d[2] for _, _, _, d in internal) * 1e-9
    vlim = env[0] * env[1] * env[2] * 1e-9          # volume dell'ingombro della struttura scelta (<= quello della classe)
    out: dict[str, Any] = {"state": None, "label": None, "envelope_mm": list(env), "internal_volume_m3": vol, "volume_limit_m3": vlim,
                           "internal_volume_fraction": vol / vlim, "unknown_size": unknown, "placed": [], "external": [], "message": "",
                           "preview": None}
    names = {slot: k for slot, _, k, _ in internal}
    dims_of = {slot: d for slot, _, _, d in internal}
    sub_of = {slot: sid for slot, sid, _, _ in internal}

    def entries(placed):
        return [{"subsystem": sub_of[n], "slot": n, "id": names[n].comp.id, "name": names[n].comp.raw["name"], "pos": [round(x, 3), round(y, 3), round(z, 3)],
                 "size": [round(dx, 3), round(dy, 3), round(dz, 3)], "shape": shape_for(names[n].comp, dims_of[n], perm)}
                for n, x, y, z, dx, dy, dz, perm in placed]
    if unknown:
        out["state"] = "undetermined"
        out["message"] = "The size is not publicly available for: " + ", ".join(unknown) + ". The fit cannot be verified."
    elif vol > vlim + 1e-15:
        out["state"] = "does_not_fit"
        out["message"] = f"The internal components alone need {100 * out['internal_volume_fraction']:.0f}% of the volume of the CDS envelope: no arrangement can exist."
    else:
        placed = stack_arrangement(env, internal)
        out["arrangement"] = "stack" if placed else "generic"
        if placed is None:
            placed = pack(env, [(slot, d) for slot, _, _, d in internal])
        if placed:
            out["state"] = "fits"
            out["placed"] = entries(placed)
            how =("The internal components are stacked along the long axis in the declared order (radio, OBC, GPS, EPS, battery, ADCS, magnetorquer, wheel, star tracker, "
                   f"propulsion, payload) in {layout.columns(env)} column(s) of {env[2]:g} mm." if out["arrangement"] == "stack" else
                   "The arrangement does not follow the stacking convention: it was found by a generic search.")
            out["message"] = (f"{how} Walls, guides, connectors and keep-out zones are not modelled: it shows that the parts can be accommodated, it is not an engineering layout.")
        else:
            out["state"] = "not_shown"
            out["message"] = (f"The internal volume is {100 * out['internal_volume_fraction']:.0f}% of the envelope and no arrangement was found: "
                              "it is not proved impossible. Walls and keep-out zones are not known.")
    out["label"] = LABELS[out["state"]]
    if out["state"] != "fits":
        pv_placed, pv = _preview(env, internal, out["state"])
        pv["placed"] = [{**e, "outside": _outside(env, *e["pos"], *e["size"])} for e in entries(pv_placed)]
        pv["not_drawn"] = [{"subsystem": sid, "slot": slot, "id": k.comp.id, "name": k.comp.raw["name"], "quantity": k.quantity} for slot, sid, k in missing]
        free_l = sum(b["size"][0] * b["size"][1] * b["size"][2] for b in pv["free"]) * 1e-6
        pv["free_volume_l"] = round(free_l if pv["kind"] == "stack" else max(0.0, vlim - vol) * 1e3, 2)
        n_out = sum(e["outside"] for e in pv["placed"])
        parts = []
        if pv["kind"] == "stack":
            parts.append(f"the {len(pv['placed'])} component(s) with a published size are drawn in the declared stack; the space left below the stack "
                         f"({pv['free_volume_l']:g} L, dashed) is free")
        elif pv["kind"] == "generic":
            parts.append(f"the {len(pv['placed'])} component(s) with a published size are drawn where a generic search placed them (not the stacking "
                         f"convention); {pv['free_volume_l']:g} L of the envelope are left")
        else:
            parts.append(f"the declared stack of the {len(pv['placed'])} component(s) with a published size would need {pv['stack_length_mm']:g} mm of length in "
                         f"{layout.columns(env)} column(s) against the {env[2]:g} mm of the envelope"
                         + (f"; the {n_out} part(s) outlined in red stick out of the envelope" if n_out else ""))
        if missing:
            parts.append("not drawn, size not publicly available: " + ", ".join(k.comp.raw["name"] for _, _, k in missing)
                         + ((f"; whether {'they fit' if len(missing) > 1 else 'it fits'} in the free space cannot be verified") if pv["kind"] != "extended_stack" else ""))
        pv["message"] = "Preview, not a proof of fit: " + "; ".join(parts) + "."
        out["preview"] = pv
    taken: set[str] = set()
    for slot, sid, k in sorted(external, key=lambda e: e[1] != "solar_panel"):     # il pannello solare sceglie prima la faccia
        spot = _place_external(k.comp, env, taken)
        if spot:
            out["external"].append({"subsystem": sid, "slot": slot, "id": k.comp.id, "name": k.comp.raw["name"], **spot})
    return out

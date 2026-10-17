"""Pila dei componenti interni lungo l'asse lungo del CubeSat (convenzione di visualizzazione dichiarata, non un dato del fornitore).

Come nelle immagini di riferimento (CubeSat con schede PC/104 impilate): i componenti interni stanno in colonne lungo Z, nell'ordine ORDER dall'alto
(antenna esterna e radio) al basso (payload). La classe fissa a priori la lunghezza Z e il numero di colonne; ogni componente ha un'altezza ricavata dalle
sue quote pubblicate (regola per forma) e un'impronta che deve entrare nella sezione di una colonna. Le colonne si riempiono a serpentina: quando il
componente successivo non entra nella lunghezza rimasta si passa alla colonna dopo. Non si modellano interfacce, cablaggi, zone di rispetto o baricentro."""
from __future__ import annotations

import math
from typing import Any

EPS = 1e-9
COLUMN_MM = 100.0            # lato di una colonna: 1U e 3U una colonna, 6U due, 12U quattro
# dall'alto (faccia con l'antenna) al basso (payload), come nelle immagini di riferimento: radio, OBC, GPS, EPS e batteria vicine, poi ADCS e attuatori, propulsione, payload
ORDER = ("comms", "obc", "gps", "eps", "battery", "adcs", "magnetorquer", "reaction_wheel", "star_tracker", "propulsion", "payload_optical", "payload_imager")
AXIS_SHAPES = ("cylinder", "lens_box", "baffle_box", "wheel_disc", "wheel_can", "wheel_cube", "rod", "board_lens")     # l'asse del pezzo sta lungo Z
# (tubi, obiettivi, paraluce, asse di rotazione delle ruote; le barre dei magnetorquer restano coricate: height_index/dims_spec)
# payload che riprende immagini: l'obiettivo guarda fuori dalla faccia -Z (nadir, il fondo della pila) e davanti non c'e' nessun altro
# componente (regola dell'utente, 2026-10-16: altrimenti non potrebbe scattare immagini). Il terminale ottico (laser) non e' vincolato qui:
# punta il collegamento con il suo sistema di puntamento e con la camera non potrebbe stare sullo stesso fondo di un 1U o 3U.
APERTURE_SUBSYSTEMS = ("payload_imager",)


def grid(env) -> tuple[int, int, float, float]:
    """(colonne in X, colonne in Y, larghezza X di una colonna, larghezza Y)."""
    nx, ny = max(1, int(env[0] / COLUMN_MM + 1e-9)), max(1, int(env[1] / COLUMN_MM + 1e-9))
    return nx, ny, env[0] / nx, env[1] / ny


def columns(env) -> int:
    nx, ny, _, _ = grid(env)
    return nx * ny


def full_dims(c):
    d = c.dimensions_mm
    return tuple(float(x) for x in d) if d and all(x is not None for x in d) else None


def height_index(c, sid: str, dims) -> int:
    """Quota (indice 0-2) che sta lungo Z: l'asse per tubi, obiettivi e paraluce, altrimenti la piu' piccola (schede, lastre, scatole, dischi, aste dei magnetorquer coricate)."""
    sh = c.raw.get("shape") or {}
    if sid != "magnetorquer" and sh.get("type") in AXIS_SHAPES and sh.get("axis") is not None:      # le aste dei magnetorquer stanno coricate
        return sh["axis"]
    return min(range(3), key=lambda k: (dims[k], -k))


def spec(c, sid: str, env) -> dict[str, Any] | None:
    """None se le quote non sono tutte pubblicate (altezza ignota). Altrimenti {"height", "perm", "span"}: perm[asse] = indice locale della quota su
    quell'asse, span = colonne occupate (in X, in Y). Un componente che non entra nella sezione di una colonna ma entra in quella della classe
    occupa piu' colonne affiancate (2026-10-16: l'ottica della iSIM-90, 114 x 100 mm, in un 12U con colonne di 113.15 mm); perm None se non entra
    nemmeno cosi' o l'altezza supera Z."""
    return dims_spec(full_dims(c), sid, c.raw.get("shape") or {}, env)


def dims_spec(dims, sid: str, shape: dict, env) -> dict[str, Any] | None:
    """spec() per quote date (anche la seconda scatola di un componente, es. l'elettronica di un payload)."""
    if dims is None:
        return None
    sh = shape or {}
    pref = min(range(3), key=lambda k: (dims[k], -k))
    if sid != "magnetorquer" and sh.get("type") in AXIS_SHAPES and sh.get("axis") is not None:
        pref = sh["axis"]
    strict = sid != "magnetorquer" and sh.get("type") in AXIS_SHAPES and sh.get("axis") is not None      # tubi e obiettivi: l'asse deve stare lungo Z
    # altrimenti si prova prima la quota preferita (la piu' piccola) e poi le altre in ordine crescente: un blocco alto 100 x 100 x 200 sta in piedi
    options = [pref] if strict else [pref] + sorted((k for k in range(3) if k != pref), key=lambda k: (dims[k], -k))
    _, _, cx, cy = grid(env)
    # l'orientazione che consuma meno lunghezza di colonna (altezza x colonne occupate), poi meno colonne, poi l'ordine delle opzioni: con la
    # quota piu' piccola che entra in una colonna e' la scelta di sempre; un pezzo che non ci entra si distende su piu' colonne se cosi' occupa
    # meno (es. le schede dell'elettronica di un payload, 209 x 96 x 46 mm in un 12U: 46 mm su due colonne invece di 209 mm in una)
    best = None
    for rank, h in enumerate(options):
        a, b = [k for k in range(3) if k != h]
        if dims[h] > env[2] + EPS:
            continue
        for fx, fy in ((a, b), (b, a)):
            if dims[fx] <= env[0] + EPS and dims[fy] <= env[1] + EPS:
                span = (max(1, math.ceil(dims[fx] / cx - 1e-9)), max(1, math.ceil(dims[fy] / cy - 1e-9)))
                key = (round(dims[h] * span[0] * span[1], 6), span[0] * span[1], rank)
                if best is None or key < best[0]:
                    best = (key, {"height": dims[h], "perm": (fx, fy, h), "span": span})
    if best is not None:
        return best[1]
    return {"height": dims[pref], "perm": None, "span": (1, 1)}


def arrange(seq: list[tuple], env):
    """[(chiave, altezza[, (colonne in X, in Y)[, apertura]])] nell'ordine della pila -> [(chiave, (x0, y0, colonne X, colonne Y), z_basso)]
    oppure None. Prima i pezzi con un'apertura ottica (la camera: APERTURE_SUBSYSTEMS): stanno sul fondo, contro la faccia -Z
    (nadir), senza nessun altro componente davanti all'obiettivo (2026-10-16). Poi gli altri pezzi che occupano piu' colonne (span), in fondo
    nel blocco di colonne affiancate piu' basso libero; infine gli altri si impilano dall'alto a serpentina nello spazio che resta. Senza pezzi
    larghi ne' aperture e' la serpentina di sempre."""
    nx, ny, _, _ = grid(env)
    length = env[2]
    top = [[0.0] * ny for _ in range(nx)]
    bottom = [[0.0] * ny for _ in range(nx)]
    out: dict[Any, tuple] = {}
    items = [(it[0], it[1], tuple(it[2]) if len(it) > 2 and it[2] else (1, 1)) for it in seq]
    aperture = {it[0] for it in seq if len(it) > 3 and it[3]}
    for key, h, (sx, sy) in items:          # aperture: sul fondo (z = 0) del primo blocco di colonne ancora vuoto in basso
        if key not in aperture:
            continue
        spot = next(((x0, y0) for y0 in range(ny - sy + 1) for x0 in range(nx - sx + 1)
                     if all(bottom[x][y] <= EPS for x in range(x0, x0 + sx) for y in range(y0, y0 + sy)) and h <= length + EPS), None)
        if spot is None:
            return None
        x0, y0 = spot
        for x in range(x0, x0 + sx):
            for y in range(y0, y0 + sy):
                bottom[x][y] = h
        out[key] = ((x0, y0, sx, sy), 0.0)
    for key, h, (sx, sy) in items:
        if (sx, sy) == (1, 1) or key in aperture:
            continue
        best = None
        for x0 in range(nx - sx + 1):
            for y0 in range(ny - sy + 1):
                cols = [(x, y) for x in range(x0, x0 + sx) for y in range(y0, y0 + sy)]
                z0 = max(bottom[x][y] for x, y in cols)
                if z0 + h <= length - max(top[x][y] for x, y in cols) + EPS and (best is None or z0 < best[0] - EPS):
                    best = (z0, x0, y0, cols)
        if best is None:
            return None
        z0, x0, y0, cols = best
        for x, y in cols:
            bottom[x][y] = z0 + h
        out[key] = ((x0, y0, sx, sy), z0)
    col, ncol = 0, nx * ny
    for key, h, span in items:
        if span != (1, 1) or key in aperture:
            continue
        while col < ncol and h > length - top[col % nx][col // nx] - bottom[col % nx][col // nx] + EPS:
            col += 1
        if col >= ncol:
            return None
        x, y = col % nx, col // nx
        out[key] = ((x, y, 1, 1), length - top[x][y] - h)
        top[x][y] += h
    return [(key, *out[key]) for key, _, _ in items]


def serpentine(seq: list[tuple[str, float]], length: float, ncol: int):
    """[(chiave, altezza)] nell'ordine -> [(chiave, colonna, z_basso)] oppure None se non entra in `ncol` colonne lunghe `length`."""
    col, used, out = 0, 0.0, []
    for key, h in seq:
        if h > length + EPS:
            return None
        if used + h > length + EPS:
            col, used = col + 1, 0.0
        if col >= ncol:
            return None
        out.append((key, col, length - used - h))
        used += h
    return out


def stack_order(items: list[tuple[str, Any]]) -> list[tuple[str, Any]]:
    """[(sottosistema, x)] nell'ordine della pila ORDER (piu' componenti dello stesso sottosistema, es. due radio, restano vicini); fuori pila esclusi."""
    return sorted((it for it in items if it[0] in ORDER), key=lambda it: ORDER.index(it[0]))


def stack_feasible(heights: dict[str, float | None] | list[tuple], env) -> bool:
    """I componenti con altezza nota entrano nella pila? heights: {sottosistema: altezza} oppure [(sottosistema, altezza[, span[, apertura]])]
    (span = colonne occupate, apertura = obiettivo sulla faccia -Z, vedi spec/arrange; senza il quarto valore: i sottosistemi APERTURE_SUBSYSTEMS)."""
    items = list(heights.items()) if isinstance(heights, dict) else list(heights)
    seq = [(k, it[1], it[2] if len(it) > 2 else (1, 1), it[3] if len(it) > 3 else it[0] in APERTURE_SUBSYSTEMS)
           for k, it in enumerate(stack_order(items)) if it[1] is not None]
    return arrange(seq, env) is not None

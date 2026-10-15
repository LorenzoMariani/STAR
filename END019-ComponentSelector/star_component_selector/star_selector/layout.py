"""Pila dei componenti interni lungo l'asse lungo del CubeSat (convenzione di visualizzazione dichiarata, non un dato del fornitore).

Come nelle immagini di riferimento (CubeSat con schede PC/104 impilate): i componenti interni stanno in colonne lungo Z, nell'ordine ORDER dall'alto
(antenna esterna e radio) al basso (payload). La classe fissa a priori la lunghezza Z e il numero di colonne; ogni componente ha un'altezza ricavata dalle
sue quote pubblicate (regola per forma) e un'impronta che deve entrare nella sezione di una colonna. Le colonne si riempiono a serpentina: quando il
componente successivo non entra nella lunghezza rimasta si passa alla colonna dopo. Non si modellano interfacce, cablaggi, zone di rispetto o baricentro."""
from __future__ import annotations

from typing import Any

EPS = 1e-9
COLUMN_MM = 100.0            # lato di una colonna: 1U e 3U una colonna, 6U due, 12U quattro
# dall'alto (faccia con l'antenna) al basso (payload), come nelle immagini di riferimento: radio, OBC, GPS, EPS e batteria vicine, poi ADCS e attuatori, propulsione, payload
ORDER = ("comms", "obc", "gps", "eps", "battery", "adcs", "magnetorquer", "reaction_wheel", "star_tracker", "propulsion", "payload_optical", "payload_imager")
AXIS_SHAPES = ("cylinder", "lens_box", "baffle_box")      # l'asse del pezzo sta lungo Z (tubi, obiettivi, paraluce)


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
    """None se le quote non sono tutte pubblicate (altezza ignota). Altrimenti {"height", "perm"}: perm[asse] = indice locale della quota su quell'asse,
    oppure perm None se l'impronta non entra nella sezione di una colonna o l'altezza supera Z."""
    dims = full_dims(c)
    if dims is None:
        return None
    pref = height_index(c, sid, dims)
    sh = c.raw.get("shape") or {}
    strict = sid != "magnetorquer" and sh.get("type") in AXIS_SHAPES and sh.get("axis") is not None      # tubi e obiettivi: l'asse deve stare lungo Z
    # altrimenti si prova prima la quota preferita (la piu' piccola) e poi le altre in ordine crescente: un blocco alto 100 x 100 x 200 sta in piedi
    options = [pref] if strict else [pref] + sorted((k for k in range(3) if k != pref), key=lambda k: (dims[k], -k))
    _, _, cx, cy = grid(env)
    for h in options:
        a, b = [k for k in range(3) if k != h]
        if dims[h] <= env[2] + EPS:
            for fx, fy in ((a, b), (b, a)):
                if dims[fx] <= cx + EPS and dims[fy] <= cy + EPS:
                    return {"height": dims[h], "perm": (fx, fy, h)}
    return {"height": dims[pref], "perm": None}


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


def stack_feasible(heights: dict[str, float | None], env) -> bool:
    """I componenti con altezza nota (per sottosistema) entrano nella pila a serpentina?"""
    seq = [(sid, heights[sid]) for sid in ORDER if heights.get(sid) is not None]
    return serpentine(seq, env[2], columns(env)) is not None

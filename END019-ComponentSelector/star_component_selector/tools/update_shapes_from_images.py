"""Forme semplificate piu' realistiche per la vista Placement, scelte guardando le immagini dei prodotti (STAR, 2026-10-16).

Nuovi tipi (star_selector.models.SHAPE_TYPES, disegnati dalla GUI dentro la scatola delle quote pubblicate):
  board_shield  scheda con schermo RF, connettore della pila e connettore SMA     (radio PULSAR, ISIS TRXUV/TRXVU, SatCOM, GNSS200, piNAV, P60...)
  enclosure     scatola lavorata con flangia, connettore su un lato                (EnduroSat, Satlab, AX100, TRX-U, GEMINI, MAI, OBC chiusi...)
  cells         celle cilindriche in un telaio                                     (BCT 28 V, GomSpace BPX)
  board_cells   celle su una scheda                                                (Pumpkin BM1, ISIS ICEPS2 tipo A)
  wheel_disc    disco su flangia con mozzo                                         (Astrofein RW)
  wheel_can     cilindro su piastra quadrata                                       (NewSpace NRWA, Vectronic VRW)
  wheel_cube    scatola con finestre sul rotore                                    (AAC RW222/RW400; le ruote senza immagine)
  rod           barra di magnetorquer con le estremita'                           (magnetorquer cilindrici)
  thruster      modulo con ugelli verso la faccia esterna piu' vicina              (propulsori a scatola; MICRO R3: 4 ugelli)
  adcs_box      scatola con l'apertura dello star tracker verso l'esterno          (BCT XACT)
  board_lens    camera su una scheda con l'obiettivo                               (Dragonfly Gecko, Mantis; GomSpace NanoCam)
La scheda (board) ora ha il connettore della pila, i distanziali e i chip; il tubo (cylinder) di una camera ha il paraluce dal lato dell'apertura.
Senza immagine la forma viene dalla famiglia o dal sottosistema e basis = "subsystem" (asterisco nella legenda).

uso: python tools/update_shapes_from_images.py      (idempotente)"""
import json
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent
BY_ID = {
    # comms
    **{i: "board_shield" for i in ("aac-pulsar-hstx", "aac-pulsar-stx", "aac-pulsar-utrx", "aac-pulsar-vutrx", "isis-trxuv", "isis-trxvu",
                                   "nanoavionics-satcom-uhf")},
    **{i: "enclosure" for i in ("aac-quasar-strx", "aac-trx-u", "endurosat-sband", "endurosat-sband-max", "endurosat-uhf", "endurosat-xband",
                                "endurosat-xband-sdr", "gomspace-nanocom-ax100", "gomspace-nanocom-link-s", "gomspace-nanocom-link-sx",
                                "gomspace-nanocom-link-x", "satlab-srs-3", "satlab-srs-4", "satlab-srx-8")},
    # eps
    "endurosat-cubesat-eps": "stack", "endurosat-eps-i": "enclosure", "endurosat-eps-ii": "enclosure", "gomspace-nanopower-p60": "board_shield",
    "gomspace-nanopower-p80": "stack", "isis-iceps2-type-a": "board_cells", "nanoavionics-eps-1-0": "enclosure",
    "pumpkin-linear-eps-11wh": "board_shield", "pumpkin-linear-eps-22wh": "board_shield", "spacemind-gemini-eps": "enclosure",
    # obc
    **{i: "enclosure" for i in ("aac-sirius-obc-leon3ft", "alenspace-dara-obc", "endurosat-obc", "innoflight-cfc-400-champs",
                                "nanoavionics-satbus-3c2")},
    # gps
    "hyperion-gnss200": "board_shield", "skyfox-pinav-ng": "board_shield", "newspace-ngps-01-422": "enclosure", "newspace-ngps-03-422": "enclosure",
    # battery
    "bct-battery-1p8s": "cells", "bct-battery-2p8s": "cells", "gomspace-bpx-100wh-16v": "cells", "gomspace-bpx-100wh-32v": "cells",
    "pumpkin-bm1-40wh": "board_cells", "gomspace-bp8-100wh": "enclosure",
    # adcs
    "bct-xact-15": "adcs_box", "bct-xact-50": "adcs_box", "bct-xact-100": "adcs_box", "pumpkin-mai-100": "enclosure", "pumpkin-mai-200": "enclosure",
    # payload imager
    **{i: "board_lens" for i in ("dragonfly-gecko", "dragonfly-gecko-wide", "dragonfly-mantis-hs", "dragonfly-mantis-ms", "dragonfly-mantis-rgb",
                                 "gomspace-nanocam-c1u-35mm", "gomspace-nanocam-c1u-70mm")},
}
AXIS_FIX = {"newspace-nrwa-t005": 2, "newspace-nrwa-t065": 2}       # asse del cilindro = altezza nell'immagine (era 0)
NOZZLES = {"enpulsion-micro-r3": 4}
AXIS_TYPES = ("wheel_disc", "wheel_can", "wheel_cube", "rod", "board_lens")


def wheel_type(cid: str) -> str:
    if cid.startswith("astrofein-"):
        return "wheel_disc"
    if cid.startswith(("newspace-nrwa-", "vectronic-")):
        return "wheel_can"
    return "wheel_cube"


def main() -> None:
    cat_path = PROJ / "data" / "catalog.json"
    cat = json.loads(cat_path.read_text(encoding="utf-8"))
    changed = 0
    for c in cat["components"]:
        sh = dict(c.get("shape") or {"type": "box", "axis": None})
        old = (sh.get("type"), sh.get("axis"), sh.get("nozzles"))
        cat_ = c["category"]
        new = BY_ID.get(c["id"])
        if cat_ == "reaction_wheel":
            new = wheel_type(c["id"])
        elif cat_ == "magnetorquer" and sh.get("type") == "cylinder":
            new = "rod"
        elif cat_ == "propulsion" and sh.get("type") == "box":
            new = "thruster"
        if new is None:
            continue
        sh["type"] = new
        dims = (c.get("dimensions") or {}).get("mm")
        if new in AXIS_TYPES:
            if c["id"] in AXIS_FIX:
                sh["axis"] = AXIS_FIX[c["id"]]
            elif sh.get("axis") is None and dims and all(v is not None for v in dims):
                sh["axis"] = min(range(3), key=lambda k: (dims[k], -k))      # ruote: l'asse di rotazione e' la quota piu' piccola
        else:
            sh["axis"] = sh.get("axis") if new in ("cylinder", "lens_box", "baffle_box", "coil_board") else None
        if new == "thruster" and c["id"] in NOZZLES:
            sh["nozzles"] = NOZZLES[c["id"]]
        sh["basis"] = "image" if (c.get("image") or {}).get("file") else "subsystem"
        sh["set"] = "2026-10-16"
        if (sh.get("type"), sh.get("axis"), sh.get("nozzles")) != old:
            changed += 1
        c["shape"] = sh
    cat_path.write_text(json.dumps(cat, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"forme aggiornate: {changed}")


if __name__ == "__main__":
    main()

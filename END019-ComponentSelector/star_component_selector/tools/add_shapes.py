"""Assegna a ogni componente una forma semplificata (campo `shape`) per la vista Placement.

La forma e' una semplificazione visiva disegnata DENTRO la scatola delle quote pubblicate (il controllo di ingombro usa sempre la scatola).
`basis`: "image" = tipo letto a occhio dall'immagine del prodotto (fogli di anteprima rivisti il 2026-10-15); "subsystem" = nessuna immagine
utilizzabile del prodotto (assente, o e' un render/diagramma), il tipo viene dal sottosistema e dal tipo pubblicato.
Tipi: board (scheda con blocchi), box, cylinder (asse = lato lungo o corto), lens_box (corpo + cilindro ottico), baffle_box (corpo + paraluce),
stack (schede impilate con distanziali), panel (lastra con celle), patch (lastra con patch), coil_board (scheda con due bobine), frame (struttura, non disegnata).
`axis` = indice (0,1,2) della quota pubblicata lungo cui sta l'asse; per board/stack/panel/patch la normale e' la quota piu' piccola.

uso: python tools/add_shapes.py
"""
import json
import sys
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJ))
from star_selector.models import load_catalog  # noqa: E402
from star_selector.rows import subsystem_of  # noqa: E402

RET = "2026-10-15"
LONG, SHORT = "long", "short"
# id -> (tipo, asse); basis "image" salvo gli id in NO_USABLE_IMAGE
ASSIGN = {}


def put(kind, axis, *ids):
    for i in ids:
        ASSIGN[i] = (kind, axis)


put("board", None, "aac-kryten-m3", "aac-q7s", "gomspace-nanomind-a3200", "pumpkin-csk-mb-ppma1", "pumpkin-csk-mb-ppma2", "pumpkin-csk-mb-ppma3", "pumpkin-csk-mb-ppmb1",
    "pumpkin-csk-mb-ppmd1", "pumpkin-csk-mb-ppmd2", "pumpkin-fm430")
put("box", None, "aac-sirius-obc-leon3ft", "alenspace-dara-obc", "endurosat-obc", "innoflight-cfc-400-champs", "nanoavionics-satbus-3c2")
put("board", None, "aac-starbuck-nano", "aac-starbuck-nano-plus", "gomspace-nanopower-p60", "pumpkin-linear-eps-11wh", "pumpkin-linear-eps-22wh")
put("box", None, "endurosat-cubesat-eps", "endurosat-eps-i", "endurosat-eps-ii", "gomspace-nanopower-p80", "nanoavionics-eps-1-0", "spacemind-gemini-eps")
put("stack", None, "nanoavionics-eps-2-0", "cubespace-cubeadcs-3axis-small", "cubespace-cubeadcs-ymomentum-small", "hyperion-iadcs200", "gomspace-nanoprop-cgp3")
put("board", None, "aac-optimus-30", "aac-optimus-40", "aac-optimus-80", "pumpkin-bm1-40wh")
put("box", None, "bct-battery-1p8s", "bct-battery-2p8s", "gomspace-bp8-100wh", "gomspace-bpx-100wh-16v", "gomspace-bpx-100wh-32v")
put("panel", None, "aac-photon-side-3u", "endurosat-solar-3u", "endurosat-solar-3u-deployable-double", "endurosat-solar-3u-deployable-single", "endurosat-solar-6u",
    "endurosat-solar-6u-deployable-single", "gomspace-dsp-135-mk2", "isis-solar-3u", "spacemind-sp3x", "spacemind-sp6x")
put("board", None, "aac-pulsar-hstx", "aac-pulsar-stx", "aac-pulsar-utrx", "aac-pulsar-vutrx", "isis-trxvu", "nanoavionics-satcom-uhf")
put("box", None, "aac-quasar-strx", "aac-trx-u", "endurosat-sband", "endurosat-sband-max", "endurosat-uhf", "endurosat-xband", "endurosat-xband-sdr", "gomspace-nanocom-ax100",
    "satlab-srs-3", "satlab-srs-4", "satlab-srx-8")
put("patch", None, "endurosat-s-band-commercial", "endurosat-s-band-wideband", "endurosat-uhf-antenna-iii", "endurosat-x-band-2x2", "endurosat-x-band-4x4", "endurosat-x-band-8x12",
    "endurosat-x-band-patch", "gomspace-nanocom-ant430", "iq-spacecom-x-band-patch", "isis-ants-1u3u", "isis-s-band-patch")
put("box", None, "bct-xact-15", "bct-xact-50", "bct-xact-100", "pumpkin-mai-100", "pumpkin-mai-200")
put("lens_box", LONG, "hyperion-iadcs400", "cubespace-cubestar", "rocketlab-st16rt2")
put("baffle_box", LONG, "bct-nst-full", "bct-nst-mid", "bct-nst-standard")
put("board", None, "hyperion-gnss200", "skyfox-pinav-ng", "sstl-sgr-ligo")
put("box", None, "newspace-ngps-01-422", "newspace-ngps-03-422", "aac-pm200", "busek-bgt-x5", "busek-bit-3", "cuaerospace-chips-1000", "cuaerospace-chips-180", "cuaerospace-chips-500",
    "enpulsion-nano-r3", "l3harris-mps-120-1u", "l3harris-mps-120-2u", "l3harris-mps-130-1u", "l3harris-mps-130-2u", "thrustme-npt30-i2-1-5u", "thrustme-npt30-i2-1u",
    "vacco-mips-0-5u", "vacco-mips-1u")
put("cylinder", SHORT, "l3harris-mps-135-4u")
put("cylinder", LONG, "dragonfly-caiman-ms", "dragonfly-caiman-rgb", "dragonfly-chameleon-hs", "dragonfly-chameleon-ms", "dragonfly-chameleon-rgb", "satlantis-graphium",
    "simera-monoscape200", "simera-multiscape200", "simera-triscape200")
put("lens_box", LONG, "dragonfly-gecko", "dragonfly-gecko-wide", "dragonfly-mantis-hs", "dragonfly-mantis-ms", "dragonfly-mantis-rgb", "gomspace-nanocam-c1u-35mm",
    "gomspace-nanocam-c1u-70mm", "gomspace-nanocam-c1u-8mm", "hyperion-im200", "simera-hyperscape100", "simera-multiscape100", "simera-triscape100", "simera-hyperscape50",
    "simera-multiscape50", "simera-triscape50")
put("box", None, "satlantis-isim-90", "satlantis-isim-90-swir", "tesat-cubelct", "tesat-scot20", "tesat-scot30", "tesat-scot80")
# nessuna immagine utilizzabile del prodotto (render o diagramma): tipo dal sottosistema
NO_USABLE_IMAGE = {"hyperion-st200": ("lens_box", LONG), "aac-cubecat": ("lens_box", LONG)}


def default_for(c, sid):
    if sid == "structure":
        return "frame", None
    if sid == "magnetorquer":
        return ("cylinder", LONG) if c.spec("magnetorquer_type") == "rod" else ("coil_board", LONG)
    if sid == "reaction_wheel":
        return "cylinder", SHORT
    if sid == "payload_imager":
        return "box", None          # senza immagine: l'involucro e' la rappresentazione piu' prudente
    if sid == "gps":
        return "board", None
    return "box", None


def main():
    cat_path = PROJ / "data" / "catalog.json"
    raw = json.loads(cat_path.read_text(encoding="utf-8"))
    comps = {c.id: c for c in load_catalog(cat_path)}
    n_img = n_sub = 0
    unknown = set(ASSIGN) | set(NO_USABLE_IMAGE)
    for item in raw["components"]:
        c = comps[item["id"]]
        sid = subsystem_of(c)
        has_img = bool(item.get("image"))
        if item["id"] in NO_USABLE_IMAGE:
            kind, axis = NO_USABLE_IMAGE[item["id"]]
            basis = "subsystem"
        elif item["id"] in ASSIGN and has_img:
            kind, axis = ASSIGN[item["id"]]
            basis = "image"
        else:
            kind, axis = default_for(c, sid)
            basis = "image" if sid == "structure" and has_img else "subsystem"
        unknown.discard(item["id"])
        dims = c.dimensions_mm
        idx = None
        if axis and dims and all(v is not None for v in dims):
            idx = max(range(3), key=lambda k: (dims[k], -k)) if axis == LONG else min(range(3), key=lambda k: (dims[k], k))
        item["shape"] = {"type": kind, "axis": idx, "basis": basis, "set": RET}
        n_img += basis == "image"
        n_sub += basis == "subsystem"
    assert not unknown, f"id sconosciuti: {sorted(unknown)}"
    cat_path.write_text(json.dumps(raw, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(raw['components'])} componenti: {n_img} da immagine, {n_sub} dal sottosistema")


if __name__ == "__main__":
    main()

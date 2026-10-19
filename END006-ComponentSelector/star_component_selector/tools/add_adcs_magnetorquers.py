"""Aggiunge alle unita' ADCS il campo `specs.magnetorquer_dipole_am2`: momento di dipolo per asse dei magnetorquer integrati (STAR, 2026-10-19).

END-003 scarica il momento delle ruote con i magnetorquer del progetto. Il valore viene dalle dichiarazioni dei fornitori gia' trascritte
nelle note del catalogo; dove le note nominano i magnetorquer senza il dipolo il campo resta null (END-003 usa allora la regola di
dimensionamento di END-006: il dipolo che scarica in un'orbita il momento di una ruota):

  hyperion-iadcs400                    0.5 A m2   AAC Hyperion iADCS400: "magnetorquer MTQ400 (0.5 A m2)"
  hyperion-iadcs200                    null       MTQ200 nominato senza dipolo
  bct-xact-15, bct-xact-50, bct-xact-100  null    "barre di torsione" senza dipolo
  cubespace-cubeadcs-3axis-small       null       2 CubeTorquer Small e 1 CubeCoil, valori non trascritti
  cubespace-cubeadcs-ymomentum-small   null       magnetorquer senza dipolo
  pumpkin-mai-100, pumpkin-mai-200     null       3 bobine senza dipolo

uso: python tools/add_adcs_magnetorquers.py      (idempotente; poi python -m star_selector export-schema --out schema/component_catalog.schema.json)"""
import json
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent
DIPOLES = {                                   # momento di dipolo per asse, A m2
    "hyperion-iadcs400": 0.5,
    "hyperion-iadcs200": None,
    "bct-xact-15": None,
    "bct-xact-50": None,
    "bct-xact-100": None,
    "cubespace-cubeadcs-3axis-small": None,
    "cubespace-cubeadcs-ymomentum-small": None,
    "pumpkin-mai-100": None,
    "pumpkin-mai-200": None,
}
NOTE = " Magnetorquer integrati (magnetorquer_dipole_am2, 2026-10-19): {}."


def main() -> None:
    cat_path = PROJ / "data" / "catalog.json"
    cat = json.loads(cat_path.read_text(encoding="utf-8"))
    done = 0
    for c in cat["components"]:
        if c["category"] != "adcs":
            continue
        if c["id"] not in DIPOLES:
            raise SystemExit(f"ADCS non previsto: {c['id']} (aggiungerlo a DIPOLES)")
        m = DIPOLES[c["id"]]
        c["specs"]["magnetorquer_dipole_am2"] = m
        text = "dipolo non dichiarato nelle note del fornitore" if m is None else f"{m:g} A m2 per asse"
        notes = c.get("notes") or ""
        if "magnetorquer_dipole_am2" not in notes:
            c["notes"] = notes.rstrip() + NOTE.format(text)
        done += 1
    cat_path.write_text(json.dumps(cat, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"magnetorquer_dipole_am2 scritto per {done} unita' ADCS")


if __name__ == "__main__":
    main()

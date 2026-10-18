"""Aggiunge alle unita' ADCS il campo `specs.form_factor_range_u`: le classi CubeSat per cui il fornitore dichiara l'unita' (STAR, 2026-10-16).

Il selettore sceglie l'unita' dichiarata per la classe del progetto: un'unita' fatta per un satellite piu' piccolo ha ruote con meno momento
e coppia di quanto serve (sottodimensionata). I valori vengono dalle dichiarazioni dei fornitori gia' trascritte nelle note del catalogo:

  cubespace-cubeadcs-3axis-small       [2, 3]   CubeSpace Gen-1 ADCS (gen 2023): "typical satellites 2U-3U"
  cubespace-cubeadcs-ymomentum-small   [2, 16]  stesso documento: taglie 2U-16U
  bct-xact-15                          [3, 3]   Blue Canyon ADCS 2026: "typical 3U (4 kg)"
  bct-xact-50                          [6, 6]   stesso documento: "typical 6U (14 kg)"
  bct-xact-100                         [12, 12] stesso documento: "typical 12U (25 kg)"
  hyperion-iadcs200                    [3, 3]   AAC Hyperion iADCS200 (feb 2023): ADCS integrato per CubeSat 3U
  hyperion-iadcs400                    [6, 12]  AAC Hyperion iADCS400 (feb 2023): piattaforme 6U-12U
  pumpkin-mai-100, pumpkin-mai-200     null     i datasheet Pumpkin/MAI non dichiarano la classe

Per Blue Canyon il documento indica il satellite tipico (non un intervallo): si registra quella classe.
uso: python tools/add_adcs_form_factors.py      (idempotente; poi python -m star_selector export-schema --out schema/component_catalog.schema.json)"""
import json
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent
RANGES = {
    "cubespace-cubeadcs-3axis-small": [2, 3],
    "cubespace-cubeadcs-ymomentum-small": [2, 16],
    "bct-xact-15": [3, 3],
    "bct-xact-50": [6, 6],
    "bct-xact-100": [12, 12],
    "hyperion-iadcs200": [3, 3],
    "hyperion-iadcs400": [6, 12],
    "pumpkin-mai-100": None,
    "pumpkin-mai-200": None,
}
NOTE = " Classe CubeSat dichiarata (form_factor_range_u, 2026-10-16): {}."


def main() -> None:
    cat_path = PROJ / "data" / "catalog.json"
    cat = json.loads(cat_path.read_text(encoding="utf-8"))
    done = 0
    for c in cat["components"]:
        if c["category"] != "adcs":
            continue
        if c["id"] not in RANGES:
            raise SystemExit(f"ADCS non previsto: {c['id']} (aggiungerlo a RANGES)")
        rng = RANGES[c["id"]]
        c["specs"]["form_factor_range_u"] = rng
        text = "non dichiarata dal fornitore" if rng is None else (f"{rng[0]}U" if rng[0] == rng[1] else f"{rng[0]}U-{rng[1]}U")
        notes = c.get("notes") or ""
        if "form_factor_range_u" not in notes:
            c["notes"] = notes.rstrip() + NOTE.format(text)
        done += 1
    cat_path.write_text(json.dumps(cat, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"form_factor_range_u scritto per {done} unita' ADCS")


if __name__ == "__main__":
    main()

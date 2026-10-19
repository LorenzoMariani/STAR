"""Aggiunge alle unita' ADCS i campi `specs.wheel_momentum_mnms` e `specs.wheel_max_torque_mnm`: momento e coppia massima di ciascuna
ruota di reazione integrata (una per asse) (STAR, 2026-10-19).

END-003 simula il controllo d'assetto (PD) con la saturazione delle ruote del progetto: con un'unita' integrata i dati delle ruote erano
solo nelle note. I valori vengono dalle dichiarazioni dei fornitori gia' trascritte nelle note del catalogo; quando la scheda ammette
piu' modelli di ruota si usa quello con meno momento (caso peggiore per la saturazione, come per la massa):

  bct-xact-15                          15 mNms,   5 mNm     Blue Canyon ADCS 2026: "15 mNms per asse, coppia massima 0.005 Nm"
  bct-xact-50                          50 mNms,   6 mNm     stesso documento: "50 mNms per asse, coppia massima 0.006 Nm"
  bct-xact-100                        100 mNms,   6 mNm     stesso documento: "fino a 4 ruote da 100 mNms, coppia massima 0.006 Nm"
  pumpkin-mai-100                     1.1 mNms, 0.635 mNm   Pumpkin/MAI: "3 ruote (1.1 mNms ciascuna, 0.635 mNm)"
  pumpkin-mai-200                    10.8 mNms, 0.625 mNm   Pumpkin/MAI: "ruote da 10.8 mNms (0.625 mNm)"
  hyperion-iadcs200                   1.5 mNms, 0.1 mNm     ruote RW210 (+-1.5/3.0/6.0 mNms secondo il modello): la piu' piccola; la coppia
                                                            e' quella della RW210 da 1.5 mNms del catalogo (aac-rw210-15)
  hyperion-iadcs400                    15 mNms,   2 mNm     ruote RW400: il datasheet e' incoerente (testo +-30 mNms, tabella 1.5/3.0/6.0);
                                                            si usa la RW400 piu' piccola del catalogo (aac-rw400-15) e il minimo della
                                                            coppia dichiarata (2-2.5 mNm)
  cubespace-cubeadcs-3axis-small       null                 CubeSpace Gen-1: ruote CubeWheel Small, valori non trascritti
  cubespace-cubeadcs-ymomentum-small   null                 stesso documento: una ruota, valori non trascritti

uso: python tools/add_adcs_wheels.py      (idempotente; poi python -m star_selector export-schema --out schema/component_catalog.schema.json)"""
import json
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent
WHEELS = {                                   # (momento mNms, coppia massima mNm) di ciascuna ruota
    "bct-xact-15": (15.0, 5.0),
    "bct-xact-50": (50.0, 6.0),
    "bct-xact-100": (100.0, 6.0),
    "pumpkin-mai-100": (1.1, 0.635),
    "pumpkin-mai-200": (10.8, 0.625),
    "hyperion-iadcs200": (1.5, 0.1),
    "hyperion-iadcs400": (15.0, 2.0),
    "cubespace-cubeadcs-3axis-small": (None, None),
    "cubespace-cubeadcs-ymomentum-small": (None, None),
}
NOTE = " Ruote integrate (wheel_momentum_mnms, wheel_max_torque_mnm, 2026-10-19): {}."


def main() -> None:
    cat_path = PROJ / "data" / "catalog.json"
    cat = json.loads(cat_path.read_text(encoding="utf-8"))
    done = 0
    for c in cat["components"]:
        if c["category"] != "adcs":
            continue
        if c["id"] not in WHEELS:
            raise SystemExit(f"ADCS non previsto: {c['id']} (aggiungerlo a WHEELS)")
        h, t = WHEELS[c["id"]]
        c["specs"]["wheel_momentum_mnms"] = h
        c["specs"]["wheel_max_torque_mnm"] = t
        text = "non dichiarate nelle note del fornitore" if h is None else f"{h:g} mNms e {t:g} mNm per ruota, una per asse"
        notes = c.get("notes") or ""
        if "wheel_momentum_mnms" not in notes:
            c["notes"] = notes.rstrip() + NOTE.format(text)
        done += 1
    cat_path.write_text(json.dumps(cat, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wheel_momentum_mnms / wheel_max_torque_mnm scritti per {done} unita' ADCS")


if __name__ == "__main__":
    main()

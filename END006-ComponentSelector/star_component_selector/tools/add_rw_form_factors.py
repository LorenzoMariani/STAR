"""Aggiunge alle ruote di reazione il campo `specs.form_factor_range_u`: le classi CubeSat per cui il fornitore dichiara la ruota (STAR, 2026-10-16).

Il selettore sceglie la ruota dichiarata per la classe del progetto e non usa mai una ruota dichiarata solo per CubeSat piu' piccoli (meno momento
e coppia di quanto serve). Valori dalle dichiarazioni dei fornitori gia' trascritte nelle note del catalogo; le altre ruote non dichiarano una
classe CubeSat e restano null:

  aac-rw210-15                       [1, 3]   AAC Hyperion RW210 datasheet: "per CubeSat da 1U a 3U" (la nota c'e' solo per la versione .15)
  aac-rw222-30, aac-rw222-60         [1, 3]   AAC RW222 datasheet: CubeSat 1U-3U
  aac-rw400-15, -30, -50             [6, 12]  AAC RW400 datasheet: CubeSat 6U-12U
  gomspace-nanotorque-gsw-600        [6, 12]  GomSpace NanoTorque GSW-600: nano-satelliti 6U, 8U e 12U
  newspace-nrwa-t065, -t2            null     "ruota di classe SmallSat": nessuna classe CubeSat dichiarata

uso: python tools/add_rw_form_factors.py      (idempotente; poi python -m star_selector export-schema --out schema/component_catalog.schema.json)"""
import json
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent
RANGES = {
    "aac-rw210-15": [1, 3],
    "aac-rw222-30": [1, 3],
    "aac-rw222-60": [1, 3],
    "aac-rw400-15": [6, 12],
    "aac-rw400-30": [6, 12],
    "aac-rw400-50": [6, 12],
    "gomspace-nanotorque-gsw-600": [6, 12],
}
NOTE = " Classe CubeSat dichiarata (form_factor_range_u, 2026-10-16): {}."


def main() -> None:
    cat_path = PROJ / "data" / "catalog.json"
    cat = json.loads(cat_path.read_text(encoding="utf-8"))
    done = 0
    for c in cat["components"]:
        if c["category"] != "reaction_wheel":
            continue
        rng = RANGES.get(c["id"])
        c["specs"]["form_factor_range_u"] = rng
        if rng is not None and "form_factor_range_u" not in (c.get("notes") or ""):
            c["notes"] = (c.get("notes") or "").rstrip() + NOTE.format(f"{rng[0]}U-{rng[1]}U")
        done += 1
    cat_path.write_text(json.dumps(cat, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"form_factor_range_u scritto per {done} ruote di reazione ({sum(1 for v in RANGES.values() if v)} dichiarate)")


if __name__ == "__main__":
    main()

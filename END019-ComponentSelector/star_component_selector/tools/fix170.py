import json, sys
p = sys.argv[1] + "/data/catalog.json"
d = json.load(open(p, encoding="utf-8"))
NOTE = (" min_form_factor_u = 16 NON dichiarato dal fornitore: derivato, perche' il sito parla di 'microsatelliti' senza indicare una taglia "
        "CubeSat; evita che il selettore lo scelga per un 12U o meno.")
for c in d["components"]:
    if c["id"] in ("satlantis-isim-170", "satlantis-isim-170-swir"):
        c["specs"]["min_form_factor_u"] = 16
        if NOTE not in c["notes"]:
            c["notes"] += NOTE
        print(c["id"], c["specs"]["min_form_factor_u"])
for c in d["components"]:
    if c["id"] == "aac-zaphod-12u":
        c["image"]["note"] = "Immagine della scheda satsearch: l'inquadratura sembra una struttura piu' stretta del 12U, da verificare."
open(p, "w", encoding="utf-8").write(json.dumps(d, indent=1, ensure_ascii=False))

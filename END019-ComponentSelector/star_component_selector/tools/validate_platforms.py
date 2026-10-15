"""Confronto di plausibilita' tra la selezione del catalogo e le piattaforme di riferimento (Tyvak Triumph 6U, Tyvak Renegade 12U).

Non e' una validazione con dati misurati: le piattaforme sono prodotti con valori massimi dichiarati dal fornitore (data/platforms.json).
Si confrontano solo grandezze che entrambe le fonti pubblicano: elenco dei moduli, massa del bus (massa di lancio - massa payload), potenza.
Le quantita' di moduli (2 star tracker, 3 ruote, ...) vengono dalla piattaforma, non dal selettore. Scrive audit/platform_comparison.json.
uso: python tools/validate_platforms.py
"""
import json
import re
import sys
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJ))

from star_selector.api import SelectorService  # noqa: E402
from star_selector.selector import CLASSES  # noqa: E402

SERVICE = SelectorService()
MODULE_MAP = [   # (parola chiave nel nome del modulo, sottosistema del selettore o None se il catalogo non ha la categoria)
    ("flight computer", "obc"), ("backplane", None), ("batteria", "battery"), ("mppt", "eps"), ("load controller", "eps"),
    ("sensori solari", None), ("star tracker", "star_tracker"), ("gps", "gps"), ("magnetorquer", "magnetorquer"), ("ruote", "reaction_wheel"),
    ("radio", "comms"), ("imu", None), ("watchdog", None)]
BUS = ("structure", "obc", "eps", "battery", "solar_panel", "comms", "antenna", "adcs", "magnetorquer", "reaction_wheel", "star_tracker", "gps")


def modules(platform):
    out = []
    for name in platform["modules"]:
        low = name.lower()
        sid = next((s for key, s in MODULE_MAP if key in low), "?")
        m = re.search(r"\((\d+)", name)
        out.append({"module": name, "subsystem": sid, "quantity": int(m.group(1)) if m else 1})
    return out


def main():
    plats = {p["id"]: p for p in json.loads((PROJ / "data" / "platforms.json").read_text(encoding="utf-8"))["platforms"]}
    report = {"note": "Confronto di plausibilita', non una validazione: i valori delle piattaforme sono massimi dichiarati dal fornitore.", "platforms": {}}
    for pid in ("tyvak-triumph", "tyvak-renegade"):
        p = plats[pid]
        units = p["form_factor_u"]
        res = SERVICE.select({"form_factor_u": units})
        sel = {s["id"]: s["selected"] for s in res["subsystems"]}
        cls = CLASSES[units]
        mods = modules(p)
        covered = sorted({m["subsystem"] for m in mods if m["subsystem"] not in (None, "?")})
        not_in_selector = [m["module"] for m in mods if m["subsystem"] is None]
        ours_not_on_platform = [sid for sid in sel if sid not in covered and sel[sid]]
        bus_mass = p["launch_mass_kg_max"] - p["payload_mass_kg_max"]
        ours_1x = sum((sel[s]["mass_kg"] or 0.0) for s in BUS if sel.get(s))
        qty = {}
        for m in mods:
            if m["subsystem"] not in (None, "?"):
                qty[m["subsystem"]] = max(qty.get(m["subsystem"], 1), m["quantity"]) if m["subsystem"] in ("battery", "star_tracker", "reaction_wheel", "magnetorquer") else 1
        ours_qty, qty_detail = 0.0, {}
        for s in BUS:
            k = sel.get(s)
            if not k:
                continue
            q = qty.get(s, 1)
            if s == "magnetorquer" and (k["specs"] or {}).get("axes") == 3:
                q = 1     # una scheda a 3 assi sostituisce le tre barre
            qty_detail[s] = q
            ours_qty += (k["mass_kg"] or 0.0) * q
        pay = sel.get("payload_imager")
        report["platforms"][pid] = {
            "name": p["name"], "class_u": units, "cds_mass_limit_kg": cls.mass_limit_kg, "platform_launch_mass_max_kg": p["launch_mass_kg_max"],
            "platform_exceeds_cds_limit": p["launch_mass_kg_max"] > cls.mass_limit_kg, "platform_bus_mass_kg": bus_mass, "platform_payload_max_kg": p["payload_mass_kg_max"],
            "platform_array_power_w": p["solar_array_power_w_max"],
            "selector": {"within_limits": res["within_limits"], "total_mass_kg": res["totals"]["mass_kg"], "bus_subsystems_mass_kg_one_each": ours_1x,
                         "bus_subsystems_mass_kg_platform_quantities": ours_qty, "quantities_used": qty_detail, "payload_imager": pay and {"name": pay["name"], "mass_kg": pay["mass_kg"]},
                         "declared_peak_power_w": res["totals"]["power_w_declared_peak"], "power_unknown": res["totals"]["power_unknown"],
                         "subsystems_covered": res["totals"]["n_covered"]},
            "ratios": {"one_each_over_platform_bus": ours_1x / bus_mass, "platform_quantities_over_platform_bus": ours_qty / bus_mass,
                       "selector_total_over_platform_launch_max": res["totals"]["mass_kg"] / p["launch_mass_kg_max"]},
            "module_mapping": mods, "platform_modules_without_a_catalogue_category": not_in_selector,
            "selector_subsystems_not_listed_on_platform": ours_not_on_platform,
        }
    out = PROJ / "audit" / "platform_comparison.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: {kk: v[kk] for kk in ("class_u", "platform_exceeds_cds_limit", "platform_bus_mass_kg", "selector", "ratios", "platform_modules_without_a_catalogue_category", "selector_subsystems_not_listed_on_platform")} for k, v in report["platforms"].items()}, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()

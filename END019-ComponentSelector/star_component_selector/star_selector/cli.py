from __future__ import annotations

import argparse
import json
from pathlib import Path

from .api import SelectorService, dumps
from .models import CATEGORIES, json_schema, load_catalog
from .platforms import load_platforms

DEFAULT_CATALOG = Path(__file__).resolve().parent.parent / "data" / "catalog.json"
DEFAULT_PLATFORMS = DEFAULT_CATALOG.with_name("platforms.json")
NA = "Not publicly available"


def cmd_select(a: argparse.Namespace) -> int:
    service = SelectorService(a.catalog)
    res = service.select({"form_factor_u": a.form_factor})
    if a.json:
        print(dumps(res))
        return 0 if res["within_limits"] else 1
    cs, t = res["cubesat"], res["totals"]
    print(f"{cs['class_u']}U  mass limit {cs['mass_limit_kg']:g} kg  volume limit {cs['volume_limit_m3']:.3e} m³  ({cs['standard']})")
    print(f"selected mass {t['mass_kg']:.3f} kg   volume (known sizes) {t['volume_m3']:.3e} m³   declared peak power {t['power_w_declared_peak']:.2f} W   "
          f"subsystems covered {t['n_covered']}/{t['n_subsystems']}")
    for s in res["subsystems"]:
        k = s["selected"]
        head = f"\n{s['label']:<28} {s['n_database']:>2} in database, {s['n_fit']:>2} fit"
        if not k:
            print(f"{head}\n    {s['note']}")
            continue
        print(f"{head}\n    {k['vendor']} {k['name']}   (data completeness {100 * k['completeness']:.0f}%)")
        for r in k["rows"]:
            val = NA if r["value"] is None else f"{r['value']} {r['unit']}".strip()
            print(f"      {r['label']:<24} {val}")
        if s["alternatives"]:
            print("      also fit: " + "; ".join(f"{x['vendor']} {x['name']}" for x in s["alternatives"][:5]) + (f"; +{len(s['alternatives']) - 5}" if len(s["alternatives"]) > 5 else ""))
    for m in res["messages"]:
        print(f"\n! {m}")
    if any(not c.verified for c in service.catalog):
        print("\nNOTE: the catalogue data were not rechecked by a person (verified=false).")
    return 0 if res["within_limits"] else 1


def cmd_list(a: argparse.Namespace) -> int:
    for c in load_catalog(a.catalog):
        if a.category in (None, c.category):
            mass = "   n.a." if c.mass_kg is None else f"{c.mass_kg:>6.3f}"
            print(f"{c.category:<15} {c.id:<42} {mass} kg")
    return 0


def cmd_platforms(a: argparse.Namespace) -> int:
    for p in load_platforms(a.platforms):
        def v(key, unit):
            return "n.a." if p.get(key) is None else f"{p[key]:g} {unit}"

        print(f"{p['id']:<27} {p['vendor']:<14} launch <= {v('launch_mass_kg_max', 'kg'):<8} payload <= {v('payload_mass_kg_max', 'kg'):<7} {p.get('configuration', '')}")
    return 0


def cmd_serve(a: argparse.Namespace) -> int:
    from .server import serve

    serve(a.catalog, a.port, a.open)
    return 0


def cmd_validate(a: argparse.Namespace) -> int:
    n = len(load_catalog(a.catalog))  # solleva ValueError con l'elenco degli errori
    print(f"OK: {n} valid components in {a.catalog}")
    return 0


def cmd_schema(a: argparse.Namespace) -> int:
    text = json.dumps(json_schema(), indent=2, ensure_ascii=False)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
        print(f"Schema written to {a.out}")
    else:
        print(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="star_selector", description="CubeSat component selector: one component per subsystem within the mass and volume limits of the class")
    p.add_argument("--catalog", default=str(DEFAULT_CATALOG), help="catalogue JSON file")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("select", help="select the components for a CubeSat class")
    s.add_argument("--form-factor", type=int, required=True, choices=[1, 3, 6, 12], help="CubeSat class in U")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_select)

    l = sub.add_parser("list", help="list the components")
    l.add_argument("--category", choices=CATEGORIES)
    l.set_defaults(func=cmd_list)

    sub.add_parser("validate", help="validate the catalogue").set_defaults(func=cmd_validate)

    sv = sub.add_parser("serve", help="start the GUI (local server on 127.0.0.1)")
    sv.add_argument("--port", type=int, default=8765)
    sv.add_argument("--open", action="store_true", help="open the browser")
    sv.set_defaults(func=cmd_serve)

    pl = sub.add_parser("platforms", help="list the complete reference platforms (Tyvak, Terran Orbital)")
    pl.add_argument("--platforms", default=str(DEFAULT_PLATFORMS))
    pl.set_defaults(func=cmd_platforms)

    sc = sub.add_parser("export-schema", help="export the JSON Schema")
    sc.add_argument("--out")
    sc.set_defaults(func=cmd_schema)

    a = p.parse_args(argv)
    try:
        return a.func(a)
    except ValueError as e:
        print(f"Error: {e}")
        return 2

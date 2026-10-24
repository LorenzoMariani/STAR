"""Livello di servizio con dati JSON: usato dalla GUI, dal server HTTP, dal runner dell'orchestratore STAR e da STAR stesso.

Tutto cio' che entra ed esce e' fatto di dict/list/numeri/stringhe, quindi attraversa senza adattamenti pywebview, HTTP e i file JSON dei RUN.
I messaggi sono in inglese (la GUI e STAR sono in inglese)."""
from __future__ import annotations

import base64
import io
import json
import math
import re
from pathlib import Path
from typing import Any

from .models import Component, load_catalog
from .platforms import load_platforms
from .rows import rows_for, subsystem_of
from .fit import check_fit
from .mission import design
from .selector import CDS_SOURCE, CLASSES, EXTERNAL_SUBSYSTEMS, LABELS, SUBSYSTEMS, Candidate, Selection, select

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CATALOG = ROOT / "data" / "catalog.json"
CUBESAT_MAX_MASS_KG = CLASSES[12].mass_limit_kg  # 12U, CubeSat Design Specification Rev. 14.1


# --------------------------------------------------------------------------- serializzazione


def _thumbnail_uri(path: Path, max_px: int = 360) -> str | None:
    """PNG ridotto come data URI (Pillow se disponibile, altrimenti il file originale)."""
    try:
        data = path.read_bytes()
        try:
            from PIL import Image

            im = Image.open(io.BytesIO(data)).convert("RGB")
            im.thumbnail((max_px, max_px))
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=82)
            return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
        except ImportError:
            return "data:image/png;base64," + base64.b64encode(data).decode()
    except OSError:
        return None


ACRONYMS = {"structure": ("STR", "Structure"), "obc": ("OBC", "On-board computer"), "eps": ("EPS", "Electrical power system"), "battery": ("BAT", "Battery"),
            "solar_panel": ("SOL", "Solar cells"), "comms": ("COM", "Communications"), "antenna": ("ANT", "Antenna"),
            "adcs": ("ADCS", "Attitude determination and control"), "magnetorquer": ("MTQ", "Magnetorquer"), "reaction_wheel": ("RW", "Reaction wheel"),
            "star_tracker": ("STK", "Star tracker"), "sun_sensor": ("SUN", "Sun sensor"), "gps": ("GPS", "GNSS receiver"), "gnss_antenna": ("GNA", "GNSS antenna"), "propulsion": ("PRP", "Propulsion"),
            "payload_imager": ("IMG", "Payload imager"), "payload_optical": ("OPT", "Payload optical terminal"), "heater": ("HTR", "Battery heater")}


def _pdf_page(raw: dict) -> int | None:
    """Pagina del datasheet da cui e' stata estratta la foto (se la foto viene dal datasheet stesso)."""
    img = raw.get("image") or {}
    m = re.search(r"#page=(\d+)$", str(img.get("image_url") or ""))
    same = (img.get("page_url") or "") == (raw.get("source") or {}).get("url")
    return int(m.group(1)) if m and same else None


def library_stats(catalog: list[Component], root: Path = ROOT) -> dict[str, Any]:
    """Conteggi del database per classe (sottosistema): componenti, immagini e datasheet realmente presenti come file."""
    # the search subsystems, then the battery heaters (catalogue category chosen by mission.battery_heater, not by the search)
    rows = {sid: {"id": sid, "acronym": ACRONYMS[sid][0], "name": ACRONYMS[sid][1], "n": 0, "images": 0, "datasheets": 0}
            for sid in [*(sid for sid, _, _ in SUBSYSTEMS), "heater"]}
    for c in catalog:
        r = rows[subsystem_of(c)]
        r["n"] += 1
        r["images"] += bool(c.raw.get("image") and (root / c.raw["image"]["file"]).is_file())
        r["datasheets"] += bool(c.raw.get("datasheet") and (root / c.raw["datasheet"]["file"]).is_file())
    classes = list(rows.values())
    return {"classes": classes, "total": sum(r["n"] for r in classes), "images": sum(r["images"] for r in classes), "datasheets": sum(r["datasheets"] for r in classes)}


def component_record(c: Component, root: Path = ROOT, with_image: bool = False) -> dict[str, Any]:
    """Scheda pubblica di un componente (tutto cio' che la GUI mostra, senza ricalcolare nulla)."""
    raw = c.raw
    img = raw.get("image")
    image = None
    if img:
        image = {"file": img["file"], "image_url": img["image_url"], "page_url": img.get("page_url"), "type": img.get("type")}
        if with_image:
            image["data_uri"] = _thumbnail_uri(root / img["file"])
    src = raw["source"]
    ds = raw.get("datasheet")
    datasheet = None
    if ds and (root / ds["file"]).is_file():
        datasheet = {"file": ds["file"], "document": ds.get("document"), "retrieved": ds.get("retrieved"), "bytes": ds.get("bytes"), "page": _pdf_page(raw)}
    return {
        "id": c.id, "category": c.category, "vendor": raw["vendor"], "name": raw["name"], "family": raw.get("family"),
        "mass_kg": raw.get("mass_kg"), "power_w": raw.get("power_w"), "volume_u": raw.get("volume_u"), "price": raw.get("price"),
        "status": raw.get("status"), "trl": raw.get("trl"), "flight_heritage": raw.get("flight_heritage"), "tid_krad": raw.get("tid_krad"),
        "temp_op_c": raw.get("temp_op_c"), "battery_data": raw.get("battery_data"), "notes": raw.get("notes"), "specs": raw["specs"], "dimensions": raw.get("dimensions"),
        "missing_specs": sorted(k for k, v in raw["specs"].items() if v is None) + (["mass_kg"] if raw.get("mass_kg") is None else []),
        "source": {"url": src["url"], "document": src.get("document"), "retrieved": src.get("retrieved"), "verified": bool(src.get("verified"))},
        "image": image, "datasheet": datasheet,
    }


def _candidate_record(k: Candidate, root: Path, with_image: bool, full: bool) -> dict[str, Any]:
    rec = component_record(k.comp, root, with_image=with_image) if full else {
        "id": k.comp.id, "vendor": k.comp.raw["vendor"], "name": k.comp.raw["name"], "category": k.comp.category}
    rec.update({"mass_kg": k.mass_kg, "volume_m3": k.volume_m3, "power_w_declared": k.power_w, "completeness": round(k.completeness, 3), "quantity": k.quantity,
                "external": subsystem_of(k.comp) in EXTERNAL_SUBSYSTEMS})
    if full:
        rec["rows"] = rows_for(k.comp)
    return rec


def selection_to_dict(sel: Selection, root: Path = ROOT, with_images: bool = False, library: dict[str, Any] | None = None,
                      mission: dict[str, Any] | None = None) -> dict[str, Any]:
    """mission: il blocco di mission.design() (progetto per una missione): classe cercata, motivo di ogni scheda, requisiti, sottosistemi non richiesti."""
    cls = sel.cubesat
    per = (mission or {}).get("subsystems") or {}
    return {
        "ok": True, "library": library, "fit": check_fit(sel), "external_subsystems": list(EXTERNAL_SUBSYSTEMS), "mission": mission,
        "cubesat": {"class_u": cls.units, "mass_limit_kg": cls.mass_limit_kg, "envelope_mm": list(cls.envelope_mm), "volume_limit_m3": cls.volume_limit_m3, "standard": CDS_SOURCE},
        "within_limits": sel.within_limits,
        "subsystems": [{
            "id": r.id, "subsystem": r.subsystem or r.id, "category": r.category, "label": r.label, "design": per.get(r.id),
            "n_database": r.n_database, "n_fit": r.n_fit, "n_fit_without_mass": r.n_fit_without_mass,
            "note": r.note, "selected": None if r.selected is None else _candidate_record(r.selected, root, with_images, True),
            "alternatives": [_candidate_record(k, root, False, False) for k in r.alternatives],
        } for r in sel.subsystems],
        "totals": {"mass_kg": sel.mass_kg, "mass_limit_kg": cls.mass_limit_kg, "volume_m3": sel.volume_m3, "volume_limit_m3": cls.volume_limit_m3,
                   "power_w_declared_peak": sel.power_w, "mass_unknown": sel.mass_unknown, "volume_unknown": sel.volume_unknown, "power_unknown": sel.power_unknown,
                   "n_subsystems": len(sel.subsystems), "n_covered": sum(1 for r in sel.subsystems if r.selected)},
        "breakdown": {
            "mass_kg": {r.id: r.selected.mass_kg for r in sel.subsystems if r.selected and r.selected.mass_kg},
            "volume_m3": {r.id: r.selected.volume_m3 for r in sel.subsystems if r.selected and r.selected.volume_m3},
            "power_w": {r.id: r.selected.power_w for r in sel.subsystems if r.selected and r.selected.power_w},
        },
        "messages": sel.messages, "truncated": sel.truncated,
    }


def add_battery_heater(result: dict[str, Any]) -> None:
    """The battery heater of mission.battery_heater (IF-019-006) in the totals: a separate film heater adds its mass and its power
    (key "battery_heater" of the breakdown, which STAR passes on as consumers_declared_peak_w); an integrated one adds its power only."""
    h = (result.get("mission") or {}).get("battery_heater") or {}
    if not h.get("component") or not h.get("power_w"):
        return
    totals, bd = result["totals"], result["breakdown"]
    if h.get("source") == "separate" and h.get("mass_kg"):
        totals["mass_kg"] = (totals.get("mass_kg") or 0.0) + float(h["mass_kg"])
        bd["mass_kg"]["battery_heater"] = float(h["mass_kg"])
    totals["power_w_declared_peak"] = (totals.get("power_w_declared_peak") or 0.0) + float(h["power_w"])
    bd["power_w"]["battery_heater"] = float(h["power_w"])


# --------------------------------------------------------------------------- servizio


class SelectorService:
    """Catalogo in memoria + selezione. Un'istanza tiene il catalogo caricato una volta sola."""

    def __init__(self, catalog_path: str | Path | None = None, platforms_path: str | Path | None = None):
        self.catalog_path = Path(catalog_path or DEFAULT_CATALOG)
        self.root = self.catalog_path.resolve().parent.parent
        self.catalog = load_catalog(self.catalog_path)
        self.by_id = {c.id: c for c in self.catalog}
        pp = Path(platforms_path or self.catalog_path.with_name("platforms.json"))
        self.platforms = load_platforms(pp) if pp.exists() else []

    def overview(self) -> dict[str, Any]:
        return {"classes": [{"class_u": u, "mass_limit_kg": c.mass_limit_kg, "envelope_mm": list(c.envelope_mm), "volume_limit_m3": c.volume_limit_m3} for u, c in CLASSES.items()],
                "subsystems": [{"id": sid, "label": label} for sid, _, label in SUBSYSTEMS], "n_components": len(self.catalog),
                "vendors": sorted({c.raw["vendor"] for c in self.catalog}), "standard": CDS_SOURCE, "platforms": self.platforms, "library": self.library()}

    def component(self, cid: str, with_image: bool = True) -> dict[str, Any]:
        if cid not in self.by_id:
            raise KeyError(cid)
        rec = component_record(self.by_id[cid], self.root, with_image=with_image)
        rec["rows"] = rows_for(self.by_id[cid])
        return rec

    def datasheet_path(self, relative: str) -> Path | None:
        path = (self.root / relative).resolve()
        return path if path.is_file() and (self.root / "datasheets").resolve() in path.parents and path.suffix.lower() == ".pdf" else None

    def datasheet_data(self, cid: str, max_bytes: int = 40_000_000) -> dict[str, Any]:
        """Datasheet di un componente in base64 (per STAR, che non ha un server HTTP): {"ok", "base64", "mime", "page", "document"}."""
        if cid not in self.by_id:
            raise KeyError(cid)
        rec = component_record(self.by_id[cid], self.root)
        ds = rec["datasheet"]
        path = ds and self.datasheet_path(ds["file"])
        if not path:
            return {"ok": False, "error": "Not available in the database"}
        if path.stat().st_size > max_bytes:
            return {"ok": False, "error": "File too large to display"}
        return {"ok": True, "base64": base64.b64encode(path.read_bytes()).decode(), "mime": "application/pdf", "page": ds["page"], "document": ds["document"]}

    def library(self) -> dict[str, Any]:
        return library_stats(self.catalog, self.root)

    def image_path(self, relative: str) -> Path | None:
        path = (self.root / relative).resolve()
        return path if path.is_file() and self.root.resolve() in path.parents and path.suffix.lower() in (".png", ".jpg", ".jpeg") else None

    def select(self, params: dict[str, Any], with_images: bool = False) -> dict[str, Any]:
        """params: {"form_factor_u": 1|3|6|12}. Nessun altro parametro: il selettore rispetta solo i limiti di massa e volume della classe."""
        unknown = sorted(k for k in params if k not in ("form_factor_u", "with_images", "time_budget_s"))
        if unknown:
            raise ValueError(f"unknown parameters: {', '.join(unknown)}")
        if params.get("form_factor_u") in (None, ""):
            raise ValueError("form_factor_u is required (1, 3, 6 or 12)")
        try:
            units = int(float(params["form_factor_u"]))
        except (TypeError, ValueError):
            raise ValueError(f"invalid form_factor_u: {params['form_factor_u']}") from None
        sel = select(self.catalog, units, float(params.get("time_budget_s") or 5.0))
        return selection_to_dict(sel, self.root, with_images=with_images or bool(params.get("with_images")), library=self.library())

    def design(self, params: dict[str, Any], with_images: bool = False) -> dict[str, Any]:
        """Progetto per una missione (mission.design): params {"requirements": [{"id", "text"}...], "context": {"altitude_km": [min, max],
        "altitude_source", "end016": riepilogo END-016}, "form_factor_u": classe scelta dall'utente (facoltativa)}. Solo i sottosistemi che la
        missione chiede, nella classe CubeSat piu' piccola che li porta; gli altri nel blocco mission.extras."""
        unknown = sorted(k for k in params if k not in ("requirements", "context", "form_factor_u", "with_images", "time_budget_s"))
        if unknown:
            raise ValueError(f"unknown parameters: {', '.join(unknown)}")
        forced = params.get("form_factor_u")
        forced = int(float(forced)) if forced not in (None, "") else None
        if forced is not None and forced not in CLASSES:
            raise ValueError(f"unsupported CubeSat class {forced}U (allowed: {', '.join(f'{u}U' for u in CLASSES)})")
        sel, mission = design(self.catalog, params.get("requirements") or [], params.get("context") or {}, forced, float(params.get("time_budget_s") or 2.0))
        out = selection_to_dict(sel, self.root, with_images=with_images or bool(params.get("with_images")), library=self.library(), mission=mission)
        add_battery_heater(out)
        return out


# --------------------------------------------------------------------------- orchestratore: requisiti -> parametri


def requirements_to_params(requirements: list[dict[str, Any]] | list[str] | str, defaults: dict[str, Any] | None = None) -> dict[str, Any]:
    """Estrae dalla lista dei requisiti STAR la classe del CubeSat (l'unico ingresso del selettore).

    Restituisce {"params", "evidence", "notes", "out_of_scope", "applicable"}. Non inventa nulla: se la classe non e' scritta resta assente."""
    if isinstance(requirements, str):
        texts = [requirements]
    else:
        texts = [r["text"] if isinstance(r, dict) else str(r) for r in requirements]
    blob = re.sub(r"\s+", " ", " ".join(texts))
    low = blob.lower()
    params: dict[str, Any] = dict(defaults or {})
    evidence: dict[str, str] = {}
    notes: list[str] = []
    out_of_scope: list[str] = []

    def sentence(match: re.Match) -> str:
        start = max(blob.rfind(". ", 0, match.start()), blob.rfind("; ", 0, match.start())) + 1
        end = blob.find(". ", match.end())
        return blob[start: end + 1 if end > 0 else len(blob)].strip()[:240]

    if m := re.search(r"\b(1|3|6|12)\s*-?\s*u\b(?!\w)", low) or re.search(r"\b(1|3|6|12)\s*-?\s*unit\s+cubesat", low):
        if "form_factor_u" not in params:
            params["form_factor_u"] = int(m.group(1))
            evidence["form_factor_u"] = sentence(m)
    if m := re.search(r"(?:mass|massa)[^.\d]{0,50}?(?:not exceeding|non superiore a|at most|max(?:imum)?|fino a|<=?)\s*(\d+(?:[.,]\d+)?)\s*kg", low) or \
            re.search(r"(?:not exceeding|at most|max(?:imum)?)\s*(\d+(?:[.,]\d+)?)\s*kg", low):
        mass = float(m.group(1).replace(",", "."))
        evidence["satellite_mass_kg"] = sentence(m)
        if mass > CUBESAT_MAX_MASS_KG:
            out_of_scope.append(f"satellite mass up to {mass:g} kg > {CUBESAT_MAX_MASS_KG:g} kg (12U): outside the scope of the CubeSat selector, see the reference platforms (Tyvak, Terran Orbital)")
    if "form_factor_u" not in params:
        notes.append("CubeSat class not stated in the requirements: use the class chosen by the user or propose 6U")
    return {"params": params, "evidence": evidence, "notes": notes, "out_of_scope": out_of_scope, "applicable": not out_of_scope and "form_factor_u" in params}


# --------------------------------------------------------------------------- esportazioni


def bom_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Distinta dei componenti scelti: solo valori del catalogo (vuoto = non pubblicato)."""
    rows = []
    for s in result["subsystems"]:
        k = s["selected"]
        if not k:
            continue
        price = k.get("price") or {}
        rows.append({"subsystem": s["label"], "vendor": k["vendor"], "name": k["name"], "id": k["id"], "mass_kg": k["mass_kg"], "volume_m3": k["volume_m3"],
                     "power_w_declared_peak": k["power_w_declared"], "price": price.get("amount"), "currency": price.get("currency"),
                     "data_completeness": k["completeness"], "datasheet": (k.get("source") or {}).get("url"), "datasheet_file": (k.get("datasheet") or {}).get("file"), "image_source": (k.get("image") or {}).get("image_url")})
    return rows


def power_handoff(result: dict[str, Any]) -> dict[str, Any]:
    """Potenze dichiarate dai fornitori dei componenti scelti (per END-004 Power Budget). Nessun consumo e' stato stimato: i componenti senza dato sono elencati."""
    return {"source": "END-006 Component Selector", "kind": "declared maximum power per subsystem, from vendor documents only (no estimates)",
            "subsystems_declared_peak_power_W": result["breakdown"]["power_w"], "sum_declared_peak_W": result["totals"]["power_w_declared_peak"],
            "not_publicly_available": result["totals"]["power_unknown"]}


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1, default=lambda o: None if isinstance(o, float) and math.isnan(o) else str(o))

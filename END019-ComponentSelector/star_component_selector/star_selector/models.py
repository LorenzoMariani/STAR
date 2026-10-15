"""Schema del catalogo componenti e validazione (solo libreria standard).

Ogni componente ha campi comuni (massa, costo, TRL, fonte...) piu' un blocco
`specs` il cui contenuto dipende dalla categoria. SPEC_FIELDS e' l'unica
definizione: la validazione e lo JSON Schema esportato derivano da qui.

Dati reali: i datasheet pubblici lasciano molti valori non dichiarati. In
`specs` ogni chiave deve comparire, ma `null` significa "non dichiarato dal
fornitore" (tranne per i campi marcati obbligatori).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# `payload` resta sempre l'ultima (la ricerca la tratta a parte); star_tracker, propulsion, antenna e gps sono opzionali
CATEGORIES = ("structure", "obc", "eps", "battery", "solar_panel", "comms", "antenna", "adcs", "magnetorquer", "reaction_wheel", "star_tracker", "gps", "propulsion", "payload")

# Tipi dei campi di `specs`:
#   num, int, str, strs (lista di stringhe), nums (lista di numeri),
#   range ([min, max]), ranges (lista di [min, max]), faces (faccia -> n. pannelli)
# Terzo elemento: True se il valore non puo' essere null.
DIMENSION_BASES = ("declared", "standard", "derived")
SPEC_FIELDS: dict[str, dict[str, tuple[str, str, bool]]] = {
    "structure": {
        "form_factor_u": ("num", "Taglia in U (1, 3, 6...)", True),
        "max_total_mass_kg": ("num", "Massa massima del satellite (CubeSat Design Spec. o dispenser)", True),
        "internal_volume_u": ("num", "Volume interno utilizzabile (U)", False),
        "panel_faces": ("faces", "Facce per pannelli body-mounted, es. {'3U': 4}", False),
    },
    "obc": {
        "data_interfaces": ("strs", "Interfacce dati, es. ['I2C','SPI','CAN']", False),
        "supply_voltage_ranges_v": ("ranges", "Tensioni di alimentazione accettate [[min,max],...]", False),
    },
    "eps": {
        "compatible_form_factors_u": ("nums", "Taglie di struttura supportate", False),
        "pv_channels": ("int", "Ingressi per pannelli solari", False),
        "pv_voltage_v": ("range", "Tensione ammessa in ingresso dal PV [min, max]", False),
        "pv_power_w_max": ("num", "Potenza PV massima totale in ingresso", False),
        "battery_voltage_v": ("range", "Tensione batteria esterna ammessa [min, max]", False),
        "battery_families": ("strs", "Famiglie di batterie dichiarate compatibili (campo 'family')", False),
        "integrated_battery_wh": ("num", "Energia della batteria integrata (null = nessuna)", False),
        "integrated_battery_voltage_v": ("num", "Tensione della batteria integrata", False),
        "output_voltage_ranges_v": ("ranges", "Uscite regolate [[min,max],...]; [v,v] per tensione fissa", False),
        "output_power_w_max": ("num", "Potenza massima in uscita", False),
        "data_interfaces": ("strs", "Interfacce di telemetria/comando", False),
        "efficiency": ("num", "Rendimento di conversione 0-1", False),
    },
    "battery": {
        "voltage_range_v": ("range", "Tensione [scarica minima, carica massima]", True),
        "capacity_wh": ("num", "Energia nominale", True),
        "max_discharge_a": ("num", "Corrente massima di scarica", False),
        "max_dod": ("num", "DoD massimo raccomandato 0-1", False),
        "cycle_life": ("int", "Cicli garantiti al DoD massimo", False),
    },
    "solar_panel": {
        "face": ("str", "Faccia su cui si monta, es. '3U'", True),
        "peak_power_w": ("num", "Potenza massima in LEO dichiarata dal fornitore", True),
        "voltage_options_v": ("nums", "Tensioni di uscita disponibili (al punto di massima potenza)", False),
        "open_circuit_voltage_v": ("num", "Tensione a vuoto massima: non deve superare il massimo ingresso PV dell'EPS", False),
        "degradation_per_year": ("num", "Degrado annuo, es. 0.02", False),
    },
    "comms": {
        "band": ("str", "Banda, es. 'UHF', 'S', 'X'", True),
        "has_receiver": ("bool", "True se riceve (uplink di comando), False se e' solo trasmettitore", False),
        "data_rate_kbps_max": ("num", "Velocita' massima in downlink", True),
        "power_w_idle": ("num", "Potenza DC in ricezione/idle", False),
        "power_w_tx": ("num", "Potenza DC in trasmissione", False),
        "data_interfaces": ("strs", "Interfacce dati verso OBC", False),
        "supply_voltage_ranges_v": ("ranges", "Tensioni di alimentazione accettate [[min,max],...]", False),
    },
    "adcs": {
        "pointing_accuracy_deg": ("num", "Accuratezza di puntamento", False),
        "data_interfaces": ("strs", "Interfacce dati verso OBC", False),
        "supply_voltage_ranges_v": ("ranges", "Tensioni di alimentazione accettate [[min,max],...]", False),
    },
    # Star tracker (opzionale): accuratezza di conoscenza dell'assetto. I fornitori usano basi statistiche diverse
    # (1-sigma, 3-sigma, RMS): il valore e' riportato com'e' e la base e' dichiarata in `accuracy_basis`.
    "star_tracker": {
        "accuracy_cross_arcsec": ("num", "Accuratezza attorno agli assi trasversali alla boresight (pitch/yaw) [arcsec]", True),
        "accuracy_roll_arcsec": ("num", "Accuratezza attorno alla boresight (roll) [arcsec]", False),
        "accuracy_basis": ("str", "Base statistica dei valori di accuratezza: '1-sigma', '3-sigma' o 'RMS'", True),
        "update_rate_hz": ("num", "Frequenza di aggiornamento dell'assetto [Hz]", False),
        "fov_deg": ("nums", "Campo di vista pieno [gradi] (una o due dimensioni)", False),
        "data_interfaces": ("strs", "Interfacce dati verso l'OBC", False),
        "supply_voltage_ranges_v": ("ranges", "Tensioni di alimentazione accettate [[min,max],...]", False),
    },
    # Magnetorquer: attuatore magnetico (barra, bobina o scheda a tre assi). `magnetic_moment_am2` e' il momento di dipolo dichiarato per asse (il piu' basso se
    # gli assi differiscono: i valori per asse sono nelle note).
    "magnetorquer": {
        "magnetorquer_type": ("str", "rod (barra), board (scheda a tre assi) o coil (bobina)", True),
        "axes": ("int", "Assi coperti dall'unita'", False),
        "magnetic_moment_am2": ("num", "Momento di dipolo per asse [A m2]", False),
        "power_w_max": ("num", "Potenza elettrica massima dichiarata [W]", False),
        "supply_voltage_ranges_v": ("ranges", "Tensioni di alimentazione accettate [[min,max],...]", False),
        "data_interfaces": ("strs", "Interfacce di comando", False),
    },
    # Ruota di reazione. Momento e coppia sono quelli dichiarati dal fornitore (a quale regime e' scritto nelle note).
    "reaction_wheel": {
        "momentum_mnms": ("num", "Momento angolare immagazzinato [mN m s]", False),
        "max_torque_mnm": ("num", "Coppia massima [mN m]", False),
        "max_speed_rpm": ("num", "Velocita' massima [giri/min]", False),
        "power_w_nominal": ("num", "Potenza in regime nominale dichiarata [W]", False),
        "power_w_peak": ("num", "Potenza di picco dichiarata [W]", False),
        "supply_voltage_ranges_v": ("ranges", "Tensioni di alimentazione accettate [[min,max],...]", False),
        "data_interfaces": ("strs", "Interfacce di comando e dati", False),
    },
    # Propulsione (opzionale). `mass_kg` e' la massa del sistema CARICO di propellente come consegnato (wet); `dry_mass_kg` e `propellant_mass_kg`
    # sono indicativi. Il delta-v si calcola dall'impulso totale e dall'impulso specifico (equazione del razzo); senza Isp si usa impulso/massa
    # di lancio, che e' una stima per difetto. Se il fornitore dichiara un intervallo di Isp o di spinta si riporta il valore dichiarato piu'
    # prudente (minimo) e l'altro estremo e' nelle note.
    "propulsion": {
        "propulsion_type": ("str", "cold_gas, warm_gas, green_monoprop, hydrazine_monoprop, bipropellant, feep, gridded_ion, electrospray", True),
        "propellant": ("str", "Propellente", False),
        "thrust_mn_min": ("num", "Spinta minima dichiarata [mN]", False),
        "thrust_mn_max": ("num", "Spinta massima o nominale dichiarata [mN]", False),
        "isp_s": ("num", "Impulso specifico [s]; se e' dichiarato un intervallo, il minimo", False),
        "total_impulse_ns": ("num", "Impulso totale del sistema [N s]", True),
        "propellant_mass_kg": ("num", "Massa del propellente [kg]", False),
        "dry_mass_kg": ("num", "Massa a secco (senza propellente) [kg]", False),
        "power_w_firing": ("num", "Potenza elettrica durante la spinta [W]", False),
        "power_w_standby": ("num", "Potenza elettrica in attesa [W]", False),
        "min_form_factor_u": ("num", "Taglia minima di satellite indicata dal fornitore", False),
        "data_interfaces": ("strs", "Interfacce di comando e telemetria", False),
        "supply_voltage_ranges_v": ("ranges", "Tensioni di alimentazione accettate [[min,max],...]", False),
    },
    # Antenna di comunicazione (opzionale): deve coprire la banda della radio. Il guadagno e' quello di picco dichiarato (o il minimo
    # garantito se il fornitore dichiara solo quello); i diagrammi reali dipendono dalla geometria del satellite.
    "antenna": {
        "bands": ("strs", "Bande coperte, es. ['UHF'], ['VHF','UHF'], ['S'], ['X']", True),
        "frequency_ranges_mhz": ("ranges", "Intervalli di frequenza [[min,max],...] in MHz", False),
        "antenna_type": ("str", "wire (monopolo, dipolo o turnstile), patch o patch_array", True),
        "gain_dbi": ("num", "Guadagno dichiarato [dBi]", False),
        "beamwidth_deg": ("num", "Larghezza di fascio a meta' potenza [gradi]", False),
        "polarization": ("str", "RHCP, LHCP, RHCP/LHCP, linear", False),
        "rf_power_w_max": ("num", "Potenza RF massima ammessa [W]", False),
        "deployable": ("bool", "True se si dispiega in orbita", False),
        "data_interfaces": ("strs", "Interfacce di comando/telemetria del dispiegamento", False),
        "supply_voltage_ranges_v": ("ranges", "Tensioni di alimentazione accettate [[min,max],...]", False),
    },
    # Ricevitore GNSS (opzionale): accuratezza di posizione dichiarata con la sua base statistica.
    "gps": {
        "constellations": ("strs", "Costellazioni: GPS, Galileo, GLONASS, BeiDou", False),
        "accuracy_position_m": ("num", "Accuratezza di posizione [m]", False),
        "accuracy_basis": ("str", "Base statistica dell'accuratezza: '1-sigma', '2-sigma', '3-sigma' o 'RMS'", False),
        "accuracy_velocity_m_s": ("num", "Accuratezza di velocita' [m/s]", False),
        "ttff_cold_s": ("num", "Tempo al primo fix a freddo [s]", False),
        "update_rate_hz": ("num", "Frequenza di aggiornamento [Hz]", False),
        "channels": ("int", "Canali del ricevitore", False),
        "antenna_included": ("bool", "True se l'antenna GNSS e' fornita con il ricevitore", False),
        "data_interfaces": ("strs", "Interfacce dati verso l'OBC", False),
        "supply_voltage_ranges_v": ("ranges", "Tensioni di alimentazione accettate [[min,max],...]", False),
    },
    # Payload: camere e telescopi di osservazione (`payload_type` = "imager") oppure terminali di comunicazione ottica
    # ("optical_terminal"). La potenza media in funzione e' `power_w` (campo comune); GSD e swath sono dichiarati a una quota di
    # riferimento e scalano linearmente con la quota.
    "payload": {
        "payload_type": ("str", "'imager' (camera/telescopio) oppure 'optical_terminal' (terminale di comunicazione ottica)", True),
        "link_type": ("str", "Terminali ottici: 'space_to_ground', 'inter_satellite' o 'both'", False),
        "link_data_rate_mbps": ("num", "Terminali ottici: velocita' massima del collegamento [Mbps]", False),
        "uplink_data_rate_kbps": ("num", "Terminali ottici: canale di comando verso il satellite [kbps]", False),
        "max_range_km": ("num", "Terminali ottici: distanza massima del collegamento [km]", False),
        "wavelength_nm": ("num", "Terminali ottici: lunghezza d'onda [nm]", False),
        "host_pointing_deg": ("num", "Terminali ottici: puntamento richiesto alla piattaforma (3-sigma) [gradi]", False),
        "spectral_bands": ("strs", "Bande disponibili: PAN, RGB, MONO, VNIR, MS, HS, SWIR, TIR, VIDEO (solo imager)", False),
        "reference_altitude_km": ("num", "Quota a cui sono dichiarati GSD e swath", False),
        "gsd_m_at_ref": ("num", "GSD al nadir alla quota di riferimento [m]", False),
        "swath_km_at_ref": ("num", "Swath alla quota di riferimento [km]", False),
        "focal_length_mm": ("num", "Lunghezza focale", False),
        "aperture_mm": ("num", "Apertura (diametro)", False),
        "pixel_pitch_um": ("num", "Passo pixel", False),
        "across_track_pixels": ("int", "Pixel across-track", False),
        "min_form_factor_u": ("num", "Taglia minima di satellite indicata dal fornitore", False),
        "data_interfaces": ("strs", "Interfacce di comando e dati verso l'OBC", False),
        "supply_voltage_ranges_v": ("ranges", "Tensioni di alimentazione accettate [[min,max],...]", False),
        "storage_gb": ("num", "Memoria di massa integrata", False),
    },
}

# Campi comuni: nome -> (tipo, obbligatorio, descrizione)
COMMON_FIELDS: dict[str, tuple[str, bool, str]] = {
    "id": ("str", True, "Identificativo univoco"),
    "category": ("str", True, f"Una tra: {', '.join(CATEGORIES)}"),
    "vendor": ("str", True, "Produttore"),
    "name": ("str", True, "Nome commerciale"),
    "family": ("str", False, "Famiglia di prodotto, usata per le compatibilita' dichiarate"),
    "mass_kg": ("num", False, "Massa del singolo pezzo; null se il fornitore non la dichiara (il componente non e' selezionabile senza --mass-override)"),
    "power_w": ("num", False, "Potenza media assorbita (consumatori); per comms vedi specs"),
    "volume_u": ("num", False, "Volume occupato in U (0 se montato sul corpo)"),
    "price": ("obj", False, "Prezzo di listino pubblicato: {amount, currency, as_of}; null se non pubblicato o 'su richiesta'"),
    "status": ("str", False, "Disponibilita' dichiarata dal fornitore: 'nla' = non piu' disponibile; null = non indicato"),
    "trl": ("int", False, "Technology Readiness Level 1-9"),
    "flight_heritage": ("int", False, "Numero di missioni in orbita (solo se dichiarato)"),
    "tid_krad": ("num", False, "Tolleranza alla dose totale, krad(Si)"),
    "temp_op_c": ("range", False, "Temperatura operativa [min, max] in gradi C"),
    "notes": ("str", False, "Valori non modellati, discrepanze tra fonti, campi derivati"),
    "dimensions": ("obj", False, "Ingombro esterno {mm: [a, b, c], basis, note}: mm nell'ordine della fonte (per le schede: ingombro in pianta poi altezza), "
                                 "un valore null se non dichiarato; basis = declared (numeri del fornitore), standard (formato normato, es. PC/104, con altezza dichiarata "
                                 "o passo del modulo) o derived (da taglia nominale, es. 1U); assente se non pubblicato"),
    "image": ("obj", False, "Immagine del prodotto: {file, image_url, page_url, type, retrieved, note}; assente se non trovata"),
    "datasheet": ("obj", False, "Copia locale del documento della fonte (datasheet o brochure PDF): {file, document, source_url, retrieved, bytes}; assente se la fonte non e' un PDF scaricabile"),
    "source": ("obj", True, "Provenienza dei dati: url, document, retrieved, verified"),
    "specs": ("obj", True, "Specifiche dipendenti dalla categoria"),
}

_JSON_TYPES = {
    "num": {"type": "number"},
    "int": {"type": "integer"},
    "str": {"type": "string"},
    "bool": {"type": "boolean"},
    "strs": {"type": "array", "items": {"type": "string"}},
    "nums": {"type": "array", "items": {"type": "number"}},
    "range": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
    "ranges": {"type": "array", "items": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2}},
    "faces": {"type": "object", "additionalProperties": {"type": "integer", "minimum": 0}},
    "obj": {"type": "object"},
}


def _is_num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _is_range(v: Any) -> bool:
    return isinstance(v, list) and len(v) == 2 and all(_is_num(x) for x in v) and v[0] <= v[1]


def _check(kind: str, v: Any) -> bool:
    if kind == "num":
        return _is_num(v)
    if kind == "int":
        return isinstance(v, int) and not isinstance(v, bool)
    if kind == "str":
        return isinstance(v, str)
    if kind == "bool":
        return isinstance(v, bool)
    if kind == "strs":
        return isinstance(v, list) and all(isinstance(x, str) for x in v)
    if kind == "nums":
        return isinstance(v, list) and all(_is_num(x) for x in v)
    if kind == "range":
        return _is_range(v)
    if kind == "ranges":
        return isinstance(v, list) and all(_is_range(x) for x in v)
    if kind == "faces":
        return isinstance(v, dict) and all(isinstance(k, str) and isinstance(n, int) for k, n in v.items())
    if kind == "obj":
        return isinstance(v, dict)
    return False


def validate_component(d: dict) -> list[str]:
    """Restituisce la lista di errori (vuota se il componente e' valido)."""
    cid = d.get("id", "<senza id>")
    errs: list[str] = []
    for name, (kind, required, _) in COMMON_FIELDS.items():
        if d.get(name) is None:
            if required:
                errs.append(f"{cid}: campo obbligatorio mancante '{name}'")
        elif not _check(kind, d[name]):
            errs.append(f"{cid}: '{name}' non e' di tipo {kind}")
    cat = d.get("category")
    if cat not in CATEGORIES:
        return errs + [f"{cid}: categoria sconosciuta '{cat}'"]
    specs = d.get("specs")
    if isinstance(specs, dict):
        for name, (kind, _, required) in SPEC_FIELDS[cat].items():
            if name not in specs:
                errs.append(f"{cid}: specs.{name} mancante (usa null se non dichiarato)")
            elif specs[name] is None:
                if required:
                    errs.append(f"{cid}: specs.{name} non puo' essere null")
            elif not _check(kind, specs[name]):
                errs.append(f"{cid}: specs.{name} non e' di tipo {kind}")
        errs += [f"{cid}: specs.{k} non previsto per {cat}" for k in specs if k not in SPEC_FIELDS[cat]]
    if _is_num(d.get("mass_kg")) and d["mass_kg"] <= 0:
        errs.append(f"{cid}: mass_kg deve essere > 0")
    img = d.get("image")
    if isinstance(img, dict):
        errs += [f"{cid}: image.{k} mancante" for k in ("file", "image_url", "retrieved") if not img.get(k)]
    ds = d.get("datasheet")
    if isinstance(ds, dict):
        errs += [f"{cid}: datasheet.{k} mancante" for k in ("file", "retrieved") if not ds.get(k)]
    price = d.get("price")
    if isinstance(price, dict):
        if not (_is_num(price.get("amount")) and price["amount"] > 0):
            errs.append(f"{cid}: price.amount deve essere un numero > 0")
        if not (isinstance(price.get("currency"), str) and len(price["currency"]) == 3):
            errs.append(f"{cid}: price.currency deve essere un codice di 3 lettere (es. EUR)")
    dim = d.get("dimensions")
    if isinstance(dim, dict):
        mm = dim.get("mm")
        if not (isinstance(mm, list) and len(mm) == 3 and all(x is None or (_is_num(x) and x > 0) for x in mm) and any(x is not None for x in mm)):
            errs.append(f"{cid}: dimensions.mm deve essere una lista di 3 valori (numeri > 0 oppure null, almeno uno non null)")
        if dim.get("basis") not in DIMENSION_BASES:
            errs.append(f"{cid}: dimensions.basis deve essere una tra {', '.join(DIMENSION_BASES)}")
    src = d.get("source")
    if isinstance(src, dict):
        errs += [f"{cid}: source.{k} mancante" for k in ("url", "document", "retrieved", "verified") if k not in src]
    return errs


@dataclass(frozen=True)
class Component:
    raw: dict

    @property
    def id(self) -> str:
        return self.raw["id"]

    @property
    def category(self) -> str:
        return self.raw["category"]

    @property
    def mass_kg(self) -> float | None:
        m = self.raw.get("mass_kg")
        return None if m is None else float(m)

    @property
    def price(self) -> tuple[float, str] | None:
        p = self.raw.get("price")
        return None if not p else (float(p["amount"]), p["currency"])

    @property
    def dimensions_mm(self) -> list[float | None] | None:
        d = self.raw.get("dimensions")
        return None if not d else list(d["mm"])

    @property
    def verified(self) -> bool:
        return bool(self.raw["source"].get("verified"))

    def spec(self, key: str) -> Any:
        return self.raw["specs"][key]

    def get(self, key: str, default: Any = None) -> Any:
        v = self.raw.get(key)
        return default if v is None else v

    def label(self) -> str:
        return f"{self.raw['vendor']} {self.raw['name']}"


def load_catalog(path: str | Path) -> list[Component]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    items = data["components"] if isinstance(data, dict) else data
    errs = [e for d in items for e in validate_component(d)]
    ids = [d.get("id") for d in items]
    errs += [f"id duplicato: {i}" for i in {i for i in ids if ids.count(i) > 1}]
    if errs:
        raise ValueError("Catalogo non valido:\n  " + "\n  ".join(errs))
    return [Component(d) for d in items]


def _nullable(schema: dict, required: bool) -> dict:
    return schema if required else {"anyOf": [schema, {"type": "null"}]}


def json_schema() -> dict:
    """JSON Schema (draft 2020-12) del catalogo, utilizzabile da qualunque stack."""
    props = {n: dict(_JSON_TYPES[k], description=desc) for n, (k, _, desc) in COMMON_FIELDS.items()}
    props["category"] = {"enum": list(CATEGORIES)}
    required = [n for n, (_, req, _) in COMMON_FIELDS.items() if req]
    by_category = [
        {
            "if": {"properties": {"category": {"const": cat}}, "required": ["category"]},
            "then": {
                "properties": {
                    "specs": {
                        "type": "object",
                        "properties": {
                            n: _nullable(dict(_JSON_TYPES[k], description=d), req) for n, (k, d, req) in fields.items()
                        },
                        "required": list(fields),
                        "additionalProperties": False,
                    }
                }
            },
        }
        for cat, fields in SPEC_FIELDS.items()
    ]
    component = {"type": "object", "properties": props, "required": required, "allOf": by_category}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "STAR satellite component catalog",
        "type": "object",
        "properties": {"components": {"type": "array", "items": component}},
        "required": ["components"],
    }

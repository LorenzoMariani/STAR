"""Dati fondamentali di un componente, come li mostra la scheda del sottosistema.

Ogni riga e' un valore che sta nel catalogo (con la sua fonte); `value = None` significa "non pubblicato dal fornitore" e la GUI scrive
"Not publicly available". Nulla e' stimato o ipotizzato. Il volume e' il prodotto delle tre quote dichiarate (un calcolo, non un'ipotesi)."""
from __future__ import annotations

from typing import Any, Callable

from .models import Component

Row = dict[str, Any]   # {"key", "label", "unit", "value" (testo o None), "core" (conta per la completezza)}


def _num(v: float | None) -> str | None:
    return None if v is None else f"{v:.6g}"


def _rng(r: list | None, unit: str = "") -> str | None:
    if not r:
        return None
    return "; ".join((f"{a:g}" if a == b else f"{a:g}–{b:g}") for a, b in r)


def _list(v: list | None) -> str | None:
    return ", ".join(str(x) for x in v) if v else None


_SUP = str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹")


def sci(v: float, digits: int = 3) -> str:
    """7.706e-03 -> 7.706×10⁻³"""
    mant, exp = f"{v:.{digits}e}".split("e")
    return f"{mant}×10{str(int(exp)).translate(_SUP)}"


def volume_m3(c: Component) -> float | None:
    d = c.dimensions_mm
    if not d or any(x is None for x in d):
        return None
    return (d[0] * d[1] * d[2] + sum(b[0] * b[1] * b[2] for b in c.extra_boxes_mm)) * 1e-9     # con le altre scatole del prodotto


def size_text(c: Component) -> str | None:
    d = c.dimensions_mm
    if not d or any(x is None for x in d):
        return None
    return " + ".join(" × ".join(f"{x:g}" for x in box) for box in [d, *c.extra_boxes_mm])      # con le altre scatole del prodotto


def declared_power_w(c: Component) -> float | None:
    """Potenza elettrica massima dichiarata dal fornitore (null se non pubblicata). Nessuna ipotesi."""
    s = c.raw["specs"]
    if c.category == "comms":
        vals = [s.get("power_w_tx"), s.get("power_w_idle")]
    elif c.category == "propulsion":
        vals = [s.get("power_w_firing")]
    elif c.category == "magnetorquer":
        vals = [s.get("power_w_max")]
    elif c.category == "reaction_wheel":
        vals = [s.get("power_w_peak"), s.get("power_w_nominal")]
    else:
        vals = [c.raw.get("power_w")]
    vals = [v for v in vals if v is not None]
    return max(vals) if vals else None


def _acc(v, basis, unit) -> str | None:
    return None if v is None else f"{v:g} {unit}" + (f" ({basis})" if basis else "")


def _thrust(s) -> str | None:
    lo, hi = s.get("thrust_mn_min"), s.get("thrust_mn_max")
    if lo is None and hi is None:
        return None
    if lo is None or hi is None or lo == hi:
        return f"{(hi if lo is None else lo):g}"
    return f"{lo:g}–{hi:g}"


def _gsd(s) -> str | None:
    g, a = s.get("gsd_m_at_ref"), s.get("reference_altitude_km")
    if g is None:
        return None
    return f"{g:g}" + (f" at {a:g} km" if a is not None else " (altitude not published)")


# category (o sottosistema) -> [(chiave, etichetta, unita', estrattore)]
_SPEC_ROWS: dict[str, list[tuple[str, str, str, Callable[[Component], str | None]]]] = {
    "structure": [("form_factor_u", "Class", "U", lambda c: _num(c.spec("form_factor_u")))],
    "obc": [("data_interfaces", "Interfaces", "", lambda c: _list(c.spec("data_interfaces"))),
            ("supply", "Supply voltage", "V", lambda c: _rng(c.spec("supply_voltage_ranges_v"))),
            ("power", "Power", "W", lambda c: _num(c.raw.get("power_w")))],
    "eps": [("pv_channels", "Solar inputs", "", lambda c: _num(c.spec("pv_channels"))),
            ("output_power_w_max", "Max output", "W", lambda c: _num(c.spec("output_power_w_max"))),
            ("integrated_battery_wh", "Integrated battery", "Wh", lambda c: _num(c.spec("integrated_battery_wh"))),
            ("data_interfaces", "Interfaces", "", lambda c: _list(c.spec("data_interfaces")))],
    "battery": [("capacity_wh", "Capacity", "Wh", lambda c: _num(c.spec("capacity_wh"))),
                ("voltage", "Voltage", "V", lambda c: _rng([c.spec("voltage_range_v")]) if c.spec("voltage_range_v") else None),
                ("max_discharge_a", "Max discharge", "A", lambda c: _num(c.spec("max_discharge_a"))),
                ("cycle_life", "Cycle life", "cycles", lambda c: _num(c.spec("cycle_life")))],
    "solar_panel": [("peak_power_w", "Peak power", "W", lambda c: _num(c.spec("peak_power_w"))),
                    ("voltage_options_v", "Output voltage", "V", lambda c: _list(c.spec("voltage_options_v"))),
                    ("degradation", "Degradation", "%/year", lambda c: None if c.spec("degradation_per_year") is None else f"{100 * c.spec('degradation_per_year'):g}")],
    "comms": [("band", "Band", "", lambda c: c.spec("band")),
              ("data_rate", "Data rate", "kbps", lambda c: _num(c.spec("data_rate_kbps_max"))),
              ("power_w_tx", "Power, transmit", "W", lambda c: _num(c.spec("power_w_tx"))),
              ("power_w_idle", "Power, receive/idle", "W", lambda c: _num(c.spec("power_w_idle"))),
              ("data_interfaces", "Interfaces", "", lambda c: _list(c.spec("data_interfaces")))],
    "antenna": [("bands", "Bands", "", lambda c: _list(c.spec("bands"))),
                ("gain_dbi", "Gain", "dBi", lambda c: _num(c.spec("gain_dbi"))),
                ("antenna_type", "Type", "", lambda c: c.spec("antenna_type")),
                ("polarization", "Polarization", "", lambda c: c.spec("polarization"))],
    "adcs": [("pointing", "Pointing accuracy", "deg", lambda c: _num(c.spec("pointing_accuracy_deg"))),
             ("power", "Power", "W", lambda c: _num(c.raw.get("power_w"))),
             ("data_interfaces", "Interfaces", "", lambda c: _list(c.spec("data_interfaces")))],
    "magnetorquer": [("magnetorquer_type", "Type", "", lambda c: c.spec("magnetorquer_type")),
                     ("magnetic_moment_am2", "Magnetic moment", "A·m²", lambda c: _num(c.spec("magnetic_moment_am2"))),
                     ("axes", "Axes", "", lambda c: _num(c.spec("axes"))),
                     ("power_w_max", "Power, max", "W", lambda c: _num(c.spec("power_w_max")))],
    "reaction_wheel": [("momentum_mnms", "Momentum", "mN·m·s", lambda c: _num(c.spec("momentum_mnms"))),
                       ("max_torque_mnm", "Max torque", "mN·m", lambda c: _num(c.spec("max_torque_mnm"))),
                       ("max_speed_rpm", "Max speed", "rpm", lambda c: _num(c.spec("max_speed_rpm"))),
                       ("power", "Power, peak or nominal", "W", lambda c: _num(declared_power_w(c)))],
    "star_tracker": [("accuracy", "Accuracy", "", lambda c: _acc(c.spec("accuracy_cross_arcsec"), c.spec("accuracy_basis"), "arcsec")),
                     ("update_rate_hz", "Update rate", "Hz", lambda c: _num(c.spec("update_rate_hz"))),
                     ("fov_deg", "Field of view", "deg", lambda c: _list(c.spec("fov_deg"))),
                     ("power", "Power", "W", lambda c: _num(c.raw.get("power_w")))],
    "sun_sensor": [("sensor_type", "Type", "", lambda c: c.spec("sensor_type")),
                   ("accuracy", "Accuracy", "", lambda c: _acc(c.spec("accuracy_deg"), c.spec("accuracy_basis"), "deg")),
                   ("fov_deg", "Field of view", "deg", lambda c: _list(c.spec("fov_deg"))),
                   ("update_rate_hz", "Update rate", "Hz", lambda c: _num(c.spec("update_rate_hz"))),
                   ("power", "Power", "W", lambda c: _num(c.raw.get("power_w")))],
    "gps": [("constellations", "Constellations", "", lambda c: _list(c.spec("constellations"))),
            ("accuracy", "Position accuracy", "", lambda c: _acc(c.spec("accuracy_position_m"), c.spec("accuracy_basis"), "m")),
            ("update_rate_hz", "Update rate", "Hz", lambda c: _num(c.spec("update_rate_hz"))),
            ("power", "Power", "W", lambda c: _num(c.raw.get("power_w")))],
    "gnss_antenna": [("bands", "Signals", "", lambda c: _list(c.spec("bands"))),
                     ("total_gain_dbi", "Active gain", "dBi", lambda c: _num(c.spec("total_gain_dbi"))),
                     ("lna_gain_db", "LNA gain", "dB", lambda c: _num(c.spec("lna_gain_db"))),
                     ("noise_figure_db", "Noise figure", "dB", lambda c: _num(c.spec("noise_figure_db"))),
                     ("power", "Power", "W", lambda c: _num(c.raw.get("power_w")))],
    "propulsion": [("propulsion_type", "Type", "", lambda c: c.spec("propulsion_type")),
                   ("total_impulse_ns", "Total impulse", "N·s", lambda c: _num(c.spec("total_impulse_ns"))),
                   ("isp_s", "Specific impulse", "s", lambda c: _num(c.spec("isp_s"))),
                   ("thrust", "Thrust", "mN", lambda c: _thrust(c.raw["specs"])),
                   ("power_w_firing", "Power, firing", "W", lambda c: _num(c.spec("power_w_firing")))],
    "heater": [("heater_type", "Type", "", lambda c: c.spec("heater_type")),
               ("resistance_ohm", "Resistance", "ohm", lambda c: _num(c.spec("resistance_ohm"))),
               ("rated_power_w", "Typical power (at the rated voltage)", "W", lambda c: _num(c.spec("rated_power_w"))),
               ("rated_voltage_v", "Rated voltage", "V", lambda c: _num(c.spec("rated_voltage_v")))],
    "payload_imager": [("gsd", "GSD", "m", lambda c: _gsd(c.raw["specs"])),
                       ("aperture_mm", "Aperture", "mm", lambda c: _num(c.spec("aperture_mm"))),
                       ("spectral_bands", "Spectral bands", "", lambda c: _list(c.spec("spectral_bands"))),
                       ("power", "Power", "W", lambda c: _num(c.raw.get("power_w")))],
    "payload_optical": [("link_data_rate_mbps", "Link rate", "Mbps", lambda c: _num(c.spec("link_data_rate_mbps"))),
                        ("max_range_km", "Range", "km", lambda c: _num(c.spec("max_range_km"))),
                        ("link_type", "Link type", "", lambda c: c.spec("link_type")),
                        ("power", "Power", "W", lambda c: _num(c.raw.get("power_w")))],
}


def subsystem_of(c: Component) -> str:
    if c.category == "payload":
        return "payload_optical" if c.spec("payload_type") == "optical_terminal" else "payload_imager"
    return c.category


def rows_for(c: Component) -> list[Row]:
    """Righe della scheda: massa, dimensioni, volume, i dati chiave del sottosistema, poi eredita', TRL, TID, prezzo (queste ultime non contano per la completezza)."""
    raw = c.raw
    out: list[Row] = [
        {"key": "mass_kg", "label": "Mass", "unit": "kg", "value": _num(c.mass_kg), "core": True},
        {"key": "size", "label": "Size", "unit": "mm", "value": size_text(c), "core": True},
    ]
    vol = volume_m3(c)
    out.append({"key": "volume_m3", "label": "Volume (from size)", "unit": "m³", "value": None if vol is None else sci(vol), "core": False})
    for key, label, unit, fn in _SPEC_ROWS.get(subsystem_of(c), []):
        out.append({"key": key, "label": label, "unit": unit, "value": fn(c), "core": True})
    price = c.price
    out += [
        {"key": "flight_heritage", "label": "Flight heritage", "unit": "missions", "value": _num(raw.get("flight_heritage")), "core": False},
        {"key": "trl", "label": "TRL", "unit": "", "value": _num(raw.get("trl")), "core": False},
        {"key": "tid_krad", "label": "Radiation (TID)", "unit": "krad", "value": _num(raw.get("tid_krad")), "core": False},
        {"key": "price", "label": "List price", "unit": "", "value": None if price is None else f"{price[0]:,.0f} {price[1]}", "core": False},
    ]
    return out


def completeness(c: Component) -> float:
    """Frazione dei dati fondamentali (massa, dimensioni e dati chiave del sottosistema) pubblicati dal fornitore."""
    core = [r for r in rows_for(c) if r["core"]]
    return sum(1 for r in core if r["value"] is not None) / len(core)

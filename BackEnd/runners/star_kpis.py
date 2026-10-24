"""STAR common KPI format: one kpis.json per workflow node (phase E, 2026-10-22).

Every module writes ``modules_output/<END-xxx>/kpis.json`` at the end of its run (END-006: ``kpis_initial.json`` for the
initial design and ``kpis.json`` for the final one, the same convention as its other products). Compliance, the
traceability matrix and the results page read only these files.

Layout (``schema_version`` 1)::

    {"schema_version": 1, "module_id": "END-004", "node": "END-004", "phase": "", "run_id": "...", "generated_at": "...",
     # END-006: "node": "END-006/initial" | "END-006/final", "phase": "initial" | "final"
     "kpis": [{"id": "END-004.worst_dod_pct", "native_id": null, "name": "...", "value": 1.2464, "unit": "%",
               "category": "mission_compliance", "context": {"case": "worst", "satellite": "SAT-01"},
               "source": {"product": "power_design_cases", "field": "worst_dod_pct"},
               "assessment": null}]}

- ``id`` is the global id ``<module>.<key>``, stable across runs; ``native_id`` keeps the module's own number
  (END-001/003/010 ``KPI-nn``), never used to refer to a KPI from another module.
- ``unit`` is one of ``UNITS``; values are converted to it. A bound or an infinite value is kept as text
  (``"> 200"``, ``"inf"``), as compliance reads it.
- ``context`` says where the value comes from (design case, satellite, scope); ``source`` names the registry product
  (phase B ids) and the field.
- ``assessment`` is the module's own verdict, or null::

      {"meets": true|false|null, "operator": "<=", "threshold": 30, "unit": "%",
       "threshold_source": "requirement|component|module_default|auto", "requirement_ids": ["REQ-017"], "note": ""}

  Only ``requirement`` and ``component`` thresholds can change a requirement status; ``module_default`` and ``auto``
  ones are informative. A requirement that delegates its limit to the component ("within its operational limit")
  uses the threshold of the KPI as it is (``kpi_limit`` in requirement_kpi_rules.yaml), with its source shown.

``CATALOGUE`` lists every global id: name, unit, category and the product / field it comes from. A key written with
``{n}`` (or ``{slot}`` / ``{what}``) is a family: ``END-016.disposal_dv_{n}y_m_s`` is ``END-016.disposal_dv_5y_m_s``
for the 5-year rule. ``validate`` refuses an id that is not in the catalogue, so a new KPI is added here first.
"""
from __future__ import annotations

import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

UNITS = ("h", "min", "s", "km", "m", "m2", "deg", "deg/s", "kg", "%", "Wh", "W", "C", "m/s", "m/s/year", "years", "mag",
         "Nm", "Nms", "Nms/day", "Am2", "U", "bool", "-")
# the spellings the modules write today, and what they mean in UNITS
UNIT_ALIASES = {"": "-", "none": "-", "count": "-", "unity units": "-", "hours": "h", "hour": "h", "hr": "h", "minutes": "min",
                "seconds": "s", "sec": "s", "degrees": "deg", "°": "deg", "degc": "C", "°c": "C", "deg c": "C", "celsius": "C",
                "year": "years", "yr": "years", "percent": "%", "% of capacity": "%", "% of wheel torque": "%",
                "% of dipole": "%", "m^2": "m2", "m²": "m2", "boolean": "bool"}

CATEGORIES = ("run_validity", "mission_compliance", "design", "performance", "environment", "evidence")
THRESHOLD_SOURCES = ("requirement", "component", "module_default", "auto")
OPERATORS = ("<=", ">=", "==", "in", "<", ">")

KPI_ID = re.compile(r"^(END-\d{3})\.([A-Za-z0-9_]+)$")


def _c(name: str, unit: str, category: str, product: str, field: str, native: str | None = None) -> dict[str, Any]:
    return {"name": name, "unit": unit, "category": category, "product": product, "field": field, "native": native}


# --------------------------------------------------------------------------- catalogue of the global KPI ids
# native = the name the module writes in its own KPI list (END-001/003/010 match by name, their KPI-nn numbers move).
CATALOGUE: dict[str, dict[str, Any]] = {
    # END-001 constellation optimizer: coverage_summary.json kpis[] (KPI-01..16) and the downstream exports
    "END-001.converged": _c("Optimiser converged", "bool", "run_validity", "coverage_summary", "kpis[Converged]", "Converged"),
    "END-001.feasible_solution": _c("Feasible solution found", "bool", "run_validity", "coverage_summary", "kpis[Feasible Solution Found]", "Feasible Solution Found"),
    "END-001.max_revisit_h": _c("Maximum revisit time", "h", "mission_compliance", "coverage_summary", "kpis[Maximum Revisit Time]", "Maximum Revisit Time"),
    "END-001.p90_revisit_h": _c("90th percentile revisit time", "h", "mission_compliance", "coverage_summary", "kpis[P90 Revisit Time]", "P90 Revisit Time"),
    "END-001.mean_revisit_h": _c("Mean revisit time", "h", "mission_compliance", "coverage_summary", "kpis[Mean Revisit Time]", "Mean Revisit Time"),
    "END-001.max_latency_h": _c("Maximum data latency", "h", "mission_compliance", "coverage_summary", "kpis[Maximum Latency]", "Maximum Latency"),
    "END-001.gs_access_h": _c("Average ground-station access time", "h", "performance", "coverage_summary", "kpis[Average Ground Station Access Time]", "Average Ground Station Access Time"),
    "END-001.aoi_covered_pct": _c("Area of interest covered", "%", "mission_compliance", "coverage_summary", "kpis[Percent AOI Covered]", "Percent AOI Covered"),
    "END-001.generations_run": _c("GA generations run", "-", "run_validity", "coverage_summary", "kpis[Generations Run]", "Generations Run"),
    "END-001.population_size": _c("GA population size", "-", "run_validity", "coverage_summary", "kpis[Population Size]", "Population Size"),
    "END-001.ga_still_improving": _c("GA still improving at the last generation", "bool", "run_validity", "coverage_summary", "kpis[GA Still Improving]", "GA Still Improving"),
    "END-001.pareto_front_size": _c("Final Pareto front size", "-", "run_validity", "coverage_summary", "kpis[Final Pareto Front Size]", "Final Pareto Front Size"),
    "END-001.n_satellites": _c("Number of satellites", "-", "design", "coverage_summary", "kpis[Number of Satellites]", "Number of Satellites"),
    "END-001.n_planes": _c("Number of orbital planes", "-", "design", "coverage_summary", "kpis[Number of Planes]", "Number of Planes"),
    "END-001.altitude_km": _c("Altitude", "km", "design", "coverage_summary", "kpis[Altitude]", "Altitude"),
    "END-001.inclination_deg": _c("Inclination", "deg", "design", "coverage_summary", "kpis[Inclination]", "Inclination"),
    "END-001.orbit_type": _c("Orbit family (SSORGT = Sun-synchronous RGT, RGT = inclined RGT)", "-", "design", "coverage_summary", "orbit_type"),
    "END-001.orbit_type_requested": _c("Orbit family requested (Auto = chosen by END-001)", "-", "design", "coverage_summary", "orbit_type_requested"),
    "END-001.fitness_engine": _c("Fitness engine used", "-", "run_validity", "coverage_summary", "fitness_engine_used"),
    "END-001.mission_life_years": _c("Mission life used for the life envelope", "years", "design", "eclipse_summary", "mission_life_years"),
    "END-001.eclipse_max_life_min": _c("Longest eclipse over the mission life", "min", "environment", "eclipse_summary", "life_envelope.eclipse_max_min"),
    "END-001.eclipse_min_life_min": _c("Shortest eclipse over the mission life", "min", "environment", "eclipse_summary", "life_envelope.eclipse_min_min"),
    "END-001.abs_beta_max_life_deg": _c("Largest |beta| over the mission life", "deg", "environment", "eclipse_summary", "life_envelope.abs_beta_max_deg"),
    "END-001.orbits_per_day": _c("Orbits per day (constellation mean)", "-", "performance", "operations_summary", "constellation_mean.orbits_per_day"),
    "END-001.imaging_s_per_day": _c("Imaging time per day (constellation mean)", "s", "performance", "operations_summary", "constellation_mean.imaging_s_per_day"),
    "END-001.imaging_orbits_per_day": _c("Orbits with imaging per day (constellation mean)", "-", "performance", "operations_summary", "constellation_mean.imaging_orbits_per_day"),
    "END-001.contact_s_per_day": _c("Ground-station contact time per day (constellation mean)", "s", "performance", "operations_summary", "constellation_mean.contact_s_per_day"),
    "END-001.contact_orbits_per_day": _c("Orbits with a contact per day (constellation mean)", "-", "performance", "operations_summary", "constellation_mean.contact_orbits_per_day"),
    "END-001.n_ground_stations": _c("Ground stations used", "-", "design", "ground_stations", "len(ground_stations)"),

    # END-003 attitude propagation: attitude_summary.json kpis[] (KPI-01..33)
    "END-003.imaging_pass_found": _c("Daylight imaging pass found", "bool", "run_validity", "attitude_summary", "kpis[Ground Station Pass Found]", "Ground Station Pass Found"),
    "END-003.imaging_peak_elevation_deg": _c("Imaging pass elevation (threshold check)", "deg", "run_validity", "attitude_summary", "kpis[Elevation Threshold Met]", "Elevation Threshold Met"),
    "END-003.sun_constraint_ok": _c("Sun constraint satisfied on the imaging pass", "bool", "run_validity", "attitude_summary", "kpis[Sun Constraint Satisfied]", "Sun Constraint Satisfied"),
    "END-003.quaternion_norm_drift": _c("Max quaternion norm drift", "-", "run_validity", "attitude_summary", "kpis[Max Quaternion Norm Drift]", "Max Quaternion Norm Drift"),
    "END-003.peak_elevation_deg": _c("Peak elevation of the imaging pass", "deg", "performance", "attitude_summary", "kpis[Peak Elevation]", "Peak Elevation"),
    "END-003.imaging_pass_duration_min": _c("Imaging pass duration", "min", "performance", "attitude_summary", "kpis[Pass Duration]", "Pass Duration"),
    "END-003.mean_nadir_offset_deg": _c("Mean nadir offset during the pass", "deg", "performance", "attitude_summary", "kpis[Mean Nadir Offset During Pass]", "Mean Nadir Offset During Pass"),
    "END-003.max_nadir_offset_deg": _c("Max nadir offset during the pass", "deg", "performance", "attitude_summary", "kpis[Max Nadir Offset During Pass]", "Max Nadir Offset During Pass"),
    "END-003.mean_target_offset_deg": _c("Mean target offset during the pass", "deg", "performance", "attitude_summary", "kpis[Mean Target Offset During Pass]", "Mean Target Offset During Pass"),
    "END-003.max_target_offset_deg": _c("Max target offset during the pass", "deg", "performance", "attitude_summary", "kpis[Max Target Offset During Pass]", "Max Target Offset During Pass"),
    "END-003.mean_gg_torque_Nm": _c("Mean gravity-gradient torque", "Nm", "environment", "attitude_summary", "kpis[Mean Gravity-Gradient Torque]", "Mean Gravity-Gradient Torque"),
    "END-003.mean_srp_torque_Nm": _c("Mean solar radiation pressure torque", "Nm", "environment", "attitude_summary", "kpis[Mean SRP Torque]", "Mean SRP Torque"),
    "END-003.mean_drag_torque_Nm": _c("Mean drag torque", "Nm", "environment", "attitude_summary", "kpis[Mean Drag Torque]", "Mean Drag Torque"),
    "END-003.eclipse_fraction_pct": _c("Eclipse fraction of the window", "%", "environment", "attitude_summary", "kpis[Eclipse Fraction]", "Eclipse Fraction"),
    "END-003.peak_momentum_Nms": _c("Peak angular momentum magnitude", "Nms", "performance", "attitude_summary", "kpis[Peak Angular Momentum Magnitude]", "Peak Angular Momentum Magnitude"),
    "END-003.momentum_growth_Nms_day": _c("Angular momentum net growth rate", "Nms/day", "performance", "attitude_summary", "kpis[Angular Momentum Net Growth Rate]", "Angular Momentum Net Growth Rate"),
    "END-003.satellites_screened": _c("Constellation satellites screened for the passes", "-", "run_validity", "attitude_summary", "kpis[Constellation Satellites Screened]", "Constellation Satellites Screened"),
    "END-003.imaging_satellite_index": _c("Satellite of the imaging pass", "-", "performance", "attitude_summary", "kpis[Imaging Pass Satellite Index]", "Imaging Pass Satellite Index"),
    "END-003.night_pass_found": _c("Night light-curve pass found", "bool", "run_validity", "attitude_summary", "kpis[Night Light-Curve Pass Found]", "Night Light-Curve Pass Found"),
    "END-003.mean_body_rate_deg_s": _c("Mean body rate during the imaging pass", "deg/s", "performance", "attitude_summary", "kpis[Mean Body Rate During Imaging Pass]", "Mean Body Rate During Imaging Pass"),
    "END-003.max_body_rate_deg_s": _c("Max body rate during the imaging pass", "deg/s", "performance", "attitude_summary", "kpis[Max Body Rate During Imaging Pass]", "Max Body Rate During Imaging Pass"),
    "END-003.closed_loop_control": _c("Closed-loop attitude control", "bool", "run_validity", "attitude_summary", "kpis[Closed-Loop Attitude Control]", "Closed-Loop Attitude Control"),
    "END-003.mean_pointing_error_deg": _c("Mean pointing error during the imaging pass", "deg", "performance", "attitude_summary", "kpis[Mean Pointing Error During Imaging Pass]", "Mean Pointing Error During Imaging Pass"),
    "END-003.max_pointing_error_deg": _c("Max pointing error during the imaging pass", "deg", "mission_compliance", "attitude_summary", "kpis[Max Pointing Error During Imaging Pass]", "Max Pointing Error During Imaging Pass"),
    "END-003.rms_pointing_error_deg": _c("RMS pointing error (closed-loop windows)", "deg", "performance", "attitude_summary", "kpis[RMS Pointing Error (closed-loop windows)]", "RMS Pointing Error (closed-loop windows)"),
    "END-003.peak_wheel_momentum_pct": _c("Peak wheel momentum (% of capacity)", "%", "design", "attitude_summary", "kpis[Peak Wheel Momentum]", "Peak Wheel Momentum"),
    "END-003.peak_control_torque_pct": _c("Peak control torque (% of wheel torque)", "%", "design", "attitude_summary", "kpis[Peak Control Torque]", "Peak Control Torque"),
    "END-003.wheel_limits_time_pct": _c("Time with wheel limits active", "%", "design", "attitude_summary", "kpis[Time With Wheel Limits Active]", "Time With Wheel Limits Active"),
    "END-003.worst_gg_torque_Nm": _c("Worst-case gravity-gradient torque", "Nm", "environment", "attitude_summary", "kpis[Worst-Case Gravity-Gradient Torque]", "Worst-Case Gravity-Gradient Torque"),
    "END-003.worst_srp_torque_Nm": _c("Worst-case solar radiation pressure torque", "Nm", "environment", "attitude_summary", "kpis[Worst-Case SRP Torque]", "Worst-Case SRP Torque"),
    "END-003.worst_drag_torque_Nm": _c("Worst-case drag torque", "Nm", "environment", "attitude_summary", "kpis[Worst-Case Drag Torque]", "Worst-Case Drag Torque"),
    "END-003.peak_mtq_dipole_pct": _c("Peak magnetorquer dipole (% of dipole)", "%", "design", "attitude_summary", "kpis[Peak Magnetorquer Dipole]", "Peak Magnetorquer Dipole"),
    "END-003.end_wheel_momentum_pct": _c("Wheel momentum at the end of the window (% of capacity)", "%", "design", "attitude_summary", "kpis[Wheel Momentum at the End of the Window]", "Wheel Momentum at the End of the Window"),
    # IF-003-006 (phase F): absolute values for the END-006 wheel sizing; derived from the % KPIs and the wheels / magnetorquers
    # END-003 used (attitude_summary.attitude_control) when the module does not write them
    "END-003.peak_wheel_momentum_Nms": _c("Peak wheel momentum", "Nms", "design", "attitude_summary", "peak_wheel_momentum_pct x attitude_control.wheel_momentum_Nms"),
    "END-003.peak_control_torque_Nm": _c("Peak control torque", "Nm", "design", "attitude_summary", "peak_control_torque_pct x attitude_control.wheel_torque_Nm"),
    "END-003.peak_mtq_dipole_Am2": _c("Peak magnetorquer dipole", "Am2", "design", "attitude_summary", "peak_mtq_dipole_pct x attitude_control.magnetorquer_dipole_Am2"),
    "END-003.attitude_mode": _c("Attitude mode", "-", "design", "attitude_summary", "attitude_mode"),

    # END-004 power budget: power_budget_summary.json and power_design_cases.json (phase D)
    "END-004.daily_balance_Wh": _c("Daily energy balance (eclipse of the run)", "Wh", "mission_compliance", "power_budget_summary", "analysis.daily_balance_Wh"),
    "END-004.worst_daily_balance_Wh": _c("Daily energy balance (worst case: longest eclipse over the mission life)", "Wh", "mission_compliance", "power_design_cases", "battery_worst_case.daily_balance_Wh"),
    "END-004.worst_dod_pct": _c("Max depth of discharge per orbit (worst case: longest eclipse over the mission life)", "%", "mission_compliance", "power_design_cases", "worst_dod_pct"),
    "END-004.nominal_dod_pct": _c("Max depth of discharge per orbit (eclipse of the run)", "%", "performance", "power_design_cases", "nominal.max_dod_pct"),
    "END-004.worst_eclipse_min": _c("Eclipse of the battery worst case", "min", "environment", "power_design_cases", "battery_worst_case.eclipse_min"),
    "END-004.nominal_eclipse_min": _c("Eclipse of the run (selected satellite)", "min", "environment", "power_design_cases", "orbit.eclipse_min"),
    "END-004.orbit_period_min": _c("Orbital period", "min", "environment", "power_design_cases", "orbit.period_min"),
    "END-004.generation_per_orbit_Wh": _c("Generation per orbit (mean of the day)", "Wh", "performance", "power_budget_summary", "mode_summaries[].power_generated_per_orbit_Wh (weighted by orbits_per_day)"),
    "END-004.peak_power_W": _c("Peak power demand (flown modes)", "W", "performance", "power_budget_summary", "max(mode_summaries[].peak_power_W)"),
    "END-004.battery_capacity_Wh": _c("Battery capacity used", "Wh", "design", "power_design_cases", "battery_capacity_Wh"),
    "END-004.design_margin_pct": _c("Power design margin", "%", "design", "power_budget_summary", "analysis.margin_fraction x 100"),
    "END-004.dissipation_hot_W": _c("Internal dissipation, hot case", "W", "performance", "power_design_cases", "dissipation_W.hot"),
    "END-004.dissipation_cold_W": _c("Internal dissipation, cold case", "W", "performance", "power_design_cases", "dissipation_W.cold"),
    "END-004.heater_energy_per_orbit_Wh": _c("Battery heater energy per orbit in the worst case (END-019 cold-case mean x period)", "Wh", "performance", "power_design_cases", "battery_heater.energy_per_orbit_Wh"),
    "END-004.dissipation_nominal_W": _c("Internal dissipation, nominal (mean of the day)", "W", "performance", "power_design_cases", "dissipation_W.nominal"),

    # END-006 component selector. Final node: component_selector_results / spacecraft_definition_final (kpis.json);
    # initial node: the *_initial products and spacecraft_definition (kpis_initial.json), same ids.
    "END-006.class_u": _c("CubeSat class", "U", "design", "spacecraft_definition_final", "class_u"),
    "END-006.stated_class_u": _c("CubeSat class stated in the requirements (reported only)", "U", "design", "component_selector_results", "result.mission.stated_class.class_u"),
    "END-006.design_signature": _c("Design signature (hash of the slot -> component choice; CEF loop criterion)", "-", "design", "component_selector_results", "result.subsystems[].selected.id"),
    "END-006.wheel_momentum_ratio": _c("Wheel momentum capacity / END-003 need (IF-003-006)", "-", "design", "component_selector_results", "result.mission.wheel_sizing.momentum_ratio"),
    "END-006.wheel_torque_ratio": _c("Wheel torque capacity / END-003 need (IF-003-006)", "-", "design", "component_selector_results", "result.mission.wheel_sizing.torque_ratio"),
    "END-006.battery_heater_W": _c("Battery heater power of the design (IF-019-006, at the lowest battery voltage)", "W", "design", "component_selector_results", "result.mission.battery_heater.power_w"),
    "END-006.check_battery_temperature": _c("Battery within its limits: cold case held by the heater, hot max <= upper limit (IF-019-006)", "bool", "evidence", "component_selector_results", "result.mission.battery_heater.temperature_check.met"),
    "END-006.requests_total": _c("Design requests made to the final design (END-019 heater, END-003 wheels, END-004 battery, END-016 propulsion)", "-", "design", "design_requests", "len(requests)"),
    "END-006.requests_open": _c("Design requests no catalogued component satisfies (response not_satisfiable)", "-", "design", "design_requests", "count(requests[].response == not_satisfiable)"),
    "END-006.mass_kg": _c("Satellite mass", "kg", "design", "component_selector_results", "result.totals.mass_kg"),
    "END-006.mass_limit_kg": _c("Mass limit of the class / requirement", "kg", "design", "component_selector_results", "result.totals.mass_limit_kg"),
    "END-006.volume_used_pct": _c("Volume used (% of the class envelope)", "%", "design", "component_selector_results", "result.totals.volume_m3 / volume_limit_m3 x 100"),
    "END-006.dv_capacity_m_s": _c("Delta-v capacity of the propulsion", "m/s", "design", "component_selector_results", "result.mission.dv.given_m_s"),
    "END-006.dv_need_m_s": _c("Delta-v the mission needs (END-016 disposal)", "m/s", "design", "component_selector_results", "result.mission.dv.dv_m_s"),
    "END-006.battery_capacity_Wh": _c("Battery capacity", "Wh", "design", "spacecraft_definition_final", "battery_wh"),
    "END-006.battery_need_Wh": _c("Battery capacity the mission needs (END-004 eclipse energy / DoD)", "Wh", "design", "component_selector_results", "result.mission.battery.need_wh"),
    "END-006.pointing_accuracy_deg": _c("Pointing accuracy declared by the ADCS vendor", "deg", "design", "spacecraft_definition_final", "attitude_control.pointing_accuracy_deg"),
    "END-006.solar_peak_power_W": _c("Solar panels peak power", "W", "design", "spacecraft_definition_final", "solar_panels.total_peak_w"),
    "END-006.declared_peak_power_W": _c("Declared peak power of the components", "W", "design", "component_selector_results", "result.totals.power_w_declared_peak"),
    "END-006.drag_area_m2": _c("Mean projected drag area", "m2", "design", "spacecraft_definition_final", "area_mean_projected_m2"),
    "END-006.drag_coefficient": _c("Drag coefficient", "-", "design", "spacecraft_definition_final", "cd"),
    "END-006.has_propulsion": _c("Propulsion selected", "bool", "design", "component_selector_results", "result.subsystems[propulsion].selected"),
    "END-006.subsystems_covered_pct": _c("Subsystems with a selected component", "%", "run_validity", "component_selector_results", "result.totals.n_covered / n_subsystems x 100"),
    "END-006.components_from_catalogue": _c("Components selected from the vendor-datasheet catalogue", "bool", "evidence", "component_selector_results", "result.ok and n_covered == n_subsystems (END-006 selects only catalogued components)"),
    "END-006.unmet_requirements": _c("Requirements no catalogued component meets", "-", "mission_compliance", "component_selector_results", "len(result.mission.unmet)"),
    # one boolean per END-006 requirement check: slot = the subsystem slot (or 'design'), what = the words of the
    # check before its first number or operator ("swath >= 30 km at 628 km" -> check_payload_imager_swath);
    # the check's requirement goes to assessment.requirement_ids with threshold_source 'requirement'
    "END-006.check_{slot}_{what}": _c("END-006 requirement check", "bool", "evidence", "component_selector_results", "result.mission.requirements[]"),

    # END-007 synthetic data generation
    "END-007.imaging_pass_simulated": _c("END-003 imaging pass simulated", "bool", "run_validity", "simulated_pass", "imaging_pass"),
    "END-007.images_produced": _c("Synthetic images produced", "-", "evidence", "synthetic_images", "count of output_synthetic_data_generation/*.png"),

    # END-010 reflectance determination: reflectance_summary.json kpis[] (KPI-01..16)
    "END-010.simulation_completed": _c("Unity simulation completed", "bool", "run_validity", "reflectance_summary", "kpis[Unity Simulation Completed]", "Unity Simulation Completed"),
    "END-010.flux_samples": _c("Flux samples generated", "-", "run_validity", "reflectance_summary", "kpis[Flux Samples Generated]", "Flux Samples Generated"),
    "END-010.frames_rendered": _c("Frames rendered", "-", "run_validity", "reflectance_summary", "kpis[Frames Rendered]", "Frames Rendered"),
    "END-010.invalid_flux_samples": _c("Invalid flux samples", "-", "run_validity", "reflectance_summary", "kpis[Invalid Flux Samples]", "Invalid Flux Samples"),
    "END-010.pass_duration_s": _c("Night pass duration", "s", "performance", "reflectance_summary", "kpis[Pass Duration]", "Pass Duration"),
    "END-010.max_elevation_deg": _c("Max elevation from the observatory", "deg", "performance", "reflectance_summary", "kpis[Max Elevation]", "Max Elevation"),
    "END-010.visible_fraction_pct": _c("Visible fraction of the pass", "%", "performance", "reflectance_summary", "kpis[Visible Fraction]", "Visible Fraction"),
    "END-010.mean_range_km": _c("Mean object-station range", "km", "performance", "reflectance_summary", "kpis[Mean Object-Station Range]", "Mean Object-Station Range"),
    "END-010.min_range_km": _c("Min object-station range", "km", "performance", "reflectance_summary", "kpis[Min Object-Station Range]", "Min Object-Station Range"),
    "END-010.mean_phase_angle_deg": _c("Mean phase angle", "deg", "performance", "reflectance_summary", "kpis[Mean Phase Angle]", "Mean Phase Angle"),
    "END-010.mean_flux": _c("Mean instrumental flux (Unity units)", "-", "performance", "reflectance_summary", "kpis[Mean Instrumental Flux]", "Mean Instrumental Flux"),
    "END-010.peak_flux": _c("Peak instrumental flux (Unity units)", "-", "performance", "reflectance_summary", "kpis[Peak Instrumental Flux]", "Peak Instrumental Flux"),
    "END-010.lc_amplitude_mag": _c("Light-curve amplitude", "mag", "performance", "reflectance_summary", "kpis[Light Curve Amplitude]", "Light Curve Amplitude"),
    "END-010.lc_rms_mag": _c("Light-curve RMS variability", "mag", "performance", "reflectance_summary", "kpis[Light Curve RMS Variability]", "Light Curve RMS Variability"),
    "END-010.peak_magnitude": _c("Peak apparent visual magnitude (fainter = larger)", "mag", "mission_compliance", "reflectance_summary", "kpis[Peak Apparent Visual Magnitude (Est.)]", "Peak Apparent Visual Magnitude (Est.)"),
    "END-010.limiting_magnitude": _c("Site limiting visual magnitude", "mag", "environment", "reflectance_summary", "kpis[Site Limiting Visual Magnitude]", "Site Limiting Visual Magnitude"),
    "END-010.observatory": _c("Observatory", "-", "design", "reflectance_summary", "observatory"),

    # END-016 space safety: space_safety_summary.json kpis{} and config{}
    "END-016.n_pairs": _c("Satellite pairs screened", "-", "run_validity", "space_safety_summary", "kpis.n_pairs"),
    "END-016.min_separation_km": _c("Minimum separation between satellites", "km", "mission_compliance", "space_safety_summary", "kpis.min_separation_km"),
    "END-016.screening_km": _c("Close-approach screening distance", "km", "design", "space_safety_summary", "config.screening_km"),
    "END-016.n_events_below_screening": _c("Close approaches below the screening distance", "-", "mission_compliance", "space_safety_summary", "kpis.n_events_below_screening"),
    "END-016.n_events_below_1km": _c("Close approaches below 1 km", "-", "mission_compliance", "space_safety_summary", "kpis.n_events_below_1km"),
    "END-016.events_per_day": _c("Close approaches per day", "-", "performance", "space_safety_summary", "kpis.events_per_day"),
    "END-016.max_pc": _c("Max probability of collision", "-", "mission_compliance", "space_safety_summary", "kpis.max_pc"),
    "END-016.n_events_above_pc_threshold": _c("Close approaches above the Pc threshold", "-", "mission_compliance", "space_safety_summary", "kpis.n_events_above_pc_threshold"),
    "END-016.passive_lifetime_years": _c("Passive orbital lifetime (mean solar activity)", "years", "mission_compliance", "space_safety_summary", "kpis.passive_lifetime_years_mean_activity"),
    "END-016.passive_lifetime_min_years": _c("Passive orbital lifetime, shortest satellite", "years", "performance", "space_safety_summary", "kpis.passive_lifetime_years_min"),
    "END-016.passive_lifetime_max_years": _c("Passive orbital lifetime, longest satellite", "years", "performance", "space_safety_summary", "kpis.passive_lifetime_years_max"),
    "END-016.complies_{n}y_rule": _c("Passive re-entry within the {n}-year rule", "bool", "mission_compliance", "space_safety_summary", "kpis.complies_{n}y_rule_mean_activity"),
    "END-016.disposal_dv_{n}y_m_s": _c("Disposal delta-v for the {n}-year rule", "m/s", "mission_compliance", "space_safety_summary", "kpis.disposal_dv_m_s_{n}y_rule_mean_activity"),
    "END-016.drag_makeup_dv_m_s_per_year": _c("Drag make-up delta-v per year", "m/s/year", "performance", "space_safety_summary", "kpis.drag_makeup_dv_m_s_per_year_mean_activity"),
    "END-016.orbit_maintenance_needed": _c("Orbit maintenance needed within the mission life", "bool", "mission_compliance", "space_safety_summary", "kpis.orbit_maintenance_needed"),
    "END-016.mass_used_kg": _c("Spacecraft mass used for the decay", "kg", "design", "space_safety_summary", "config.mass_kg"),
    "END-016.drag_area_used_m2": _c("Drag area used for the decay", "m2", "design", "space_safety_summary", "config.drag_area_m2"),

    # END-019 components thermal analysis: thermal_summary_SAT-*.json (window + hot / cold design cases), worst over
    # the satellites; context = {"satellite", "case": "window|hot|cold"} of the worst value
    "END-019.battery_max_C": _c("Battery max temperature (window and hot case)", "C", "mission_compliance", "thermal_summary", "max(nodes.BAT.max_C, design_cases.hot.nodes.BAT.max_C)"),
    "END-019.battery_min_C": _c("Battery min temperature (window and cold case; with the heater of the design when it has one)", "C", "mission_compliance", "thermal_summary", "min(nodes.BAT.min_C, design_cases.cold.nodes.BAT.min_C); heater_cases.worst.battery_min_with_heater_C with a heater"),
    "END-019.battery_min_no_heater_C": _c("Battery min temperature without heater (window and cold case)", "C", "performance", "thermal_summary", "min(nodes.BAT.min_C, design_cases.cold.nodes.BAT.min_C)"),
    "END-019.heater_needed_peak_W": _c("Battery heater power needed, peak (cold case, ideal thermostat at the setpoint)", "W", "design", "heater_cases", "worst.needed_peak_W"),
    "END-019.heater_needed_mean_W_cold": _c("Battery heater power needed, orbit mean (cold case, ideal thermostat)", "W", "design", "heater_cases", "worst.needed_mean_W_cold"),
    "END-019.heater_duty_cold_pct": _c("Battery heater duty in the cold case", "%", "performance", "heater_cases", "worst.duty_cold_pct"),
    "END-019.heater_in_design_W": _c("Battery heater power of the design END-019 used", "W", "design", "heater_cases", "heater_in_design.power_W"),
    "END-019.central_body_max_C": _c("Central body max temperature (window and hot case)", "C", "mission_compliance", "thermal_summary", "max(nodes.CTR.max_C, design_cases.hot.nodes.CTR.max_C)"),
    "END-019.central_body_min_C": _c("Central body min temperature (window and cold case)", "C", "performance", "thermal_summary", "min(nodes.CTR.min_C, design_cases.cold.nodes.CTR.min_C)"),
    "END-019.solar_panel_max_C": _c("Solar panel max temperature (window)", "C", "performance", "thermal_summary", "solar_panels.max_C"),
    "END-019.solar_panel_min_C": _c("Solar panel min temperature (window)", "C", "performance", "thermal_summary", "solar_panels.min_C"),
    "END-019.face_max_C": _c("Face max temperature (window and design cases)", "C", "performance", "thermal_summary", "max over nodes pX..mZ max_C"),
    "END-019.face_min_C": _c("Face min temperature (window and design cases)", "C", "performance", "thermal_summary", "min over nodes pX..mZ min_C"),
    "END-019.sar_max_C": _c("SAR payload max temperature", "C", "mission_compliance", "thermal_summary", "nodes.SAR.max_C"),
    "END-019.battery_limit_min_C": _c("Battery operating minimum used", "C", "design", "thermal_run_info", "config.bat_min_C (provenance.bat_min_C)"),
    "END-019.battery_charge_start_C": _c("Battery temperature at the start of the sunlit part, cold case (charge starts)", "C", "mission_compliance", "heater_cases", "worst.battery_charge_start_C"),
    "END-019.battery_charge_limit_min_C": _c("Battery charge lower limit used", "C", "design", "thermal_run_info", "config.bat_charge_min_C (provenance.bat_charge_min_C)"),
    "END-019.battery_limit_max_C": _c("Battery operating maximum used", "C", "design", "thermal_run_info", "config.bat_max_C (provenance.bat_max_C)"),
    "END-019.limits_violated": _c("A thermal limit is exceeded on at least one satellite", "bool", "mission_compliance", "thermal_summary", "any(violations)"),
    "END-019.hot_case_beta_deg": _c("Beta angle of the hot case", "deg", "environment", "thermal_summary", "design_cases.hot.beta_deg"),
    "END-019.cold_case_eclipse_min": _c("Eclipse of the cold case", "min", "environment", "thermal_summary", "design_cases.cold.eclipse_min"),
    "END-019.n_satellites": _c("Satellites analysed", "-", "run_validity", "thermal_summary", "count of thermal_summary_SAT-*.json"),
    # END-008 battery health monitoring: battery_health_summary.json (battery_monitoring.exe summary, run once after the loop)
    "END-008.soh_end_of_mission": _c("Battery state of health at the end of the mission (median)", "%", "mission_compliance", "battery_health_summary", "soh_end_of_mission"),
    "END-008.soh_p05": _c("Battery state of health at the end of the mission (5th percentile)", "%", "mission_compliance", "battery_health_summary", "soh_p05"),
    "END-008.eol_reached": _c("Battery end of life reached within the mission", "bool", "mission_compliance", "battery_health_summary", "eol_reached"),
    "END-008.soc_min_mission": _c("Lowest battery state of charge of the mission", "%", "performance", "battery_health_summary", "soc_min_mission"),
    "END-008.orbits_below_soc_min": _c("Orbits with the state of charge below its minimum", "-", "performance", "battery_health_summary", "orbits_below_soc_min"),
    "END-008.law_domain_outside_fraction": _c("Orbits outside the domain of the degradation law", "%", "run_validity", "battery_health_summary", "law_domain_outside_fraction"),
}

# END-006 initial node: the products of the initial design carry these names
END006_INITIAL_PRODUCTS = {"component_selector_results": "component_selector_results_initial",
                           "spacecraft_definition_final": "spacecraft_definition"}

_FAMILY_FIELDS = {"n": r"(?P<n>\d+)", "slot": r"(?P<slot>[a-z0-9_]+?)", "what": r"(?P<what>[a-z0-9_]+)"}


def _family_re(key: str) -> re.Pattern:
    pattern, pos = "", 0
    for m in re.finditer(r"\{(\w+)\}", key):
        pattern += re.escape(key[pos:m.start()]) + _FAMILY_FIELDS[m.group(1)]
        pos = m.end()
    return re.compile("^" + pattern + re.escape(key[pos:]) + "$")


_FAMILIES = [(k, _family_re(k)) for k in CATALOGUE if "{" in k]


def catalogue_entry(kpi_id: str) -> dict[str, Any] | None:
    """The catalogue entry of a global id, with a family's {n} filled in (None when the id is unknown)."""
    if kpi_id in CATALOGUE:
        return dict(CATALOGUE[kpi_id])
    for key, rx in _FAMILIES:
        m = rx.match(kpi_id)
        if m:
            fill = m.groupdict()
            e = dict(CATALOGUE[key])
            e.update({f: str(e[f]).format(**{k: fill.get(k, "{" + k + "}") for k in _FAMILY_FIELDS}) for f in ("name", "field")})
            return e
    return None


def check_key(slot: Any, what: Any) -> str:
    """Key of an END-006 requirement check: 'check_<slot>_<words before the first number or operator>'."""
    words = re.split(r"\s*(?:[<>=]=?|\d)", str(what or "").lower(), maxsplit=1)[0]
    w = re.sub(r"[^a-z0-9]+", "_", words).strip("_")[:40].rstrip("_") or "check"
    s = re.sub(r"[^a-z0-9]+", "_", str(slot or "design").lower()).strip("_") or "design"
    return f"check_{s}_{w}"


# --------------------------------------------------------------------------- builders
def norm_unit(unit: Any) -> str:
    u = str(unit if unit is not None else "").strip()
    if u in UNITS:
        return u
    return UNIT_ALIASES.get(u.lower(), u)


def _value(v: Any) -> Any:
    """JSON-safe value: numbers as float/int, inf as text, NaN as null, numpy scalars unwrapped."""
    if v is None or isinstance(v, (bool, str)):
        return v
    if isinstance(v, int):
        return v
    if type(v).__name__ == "bool_":
        return bool(v)
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if math.isnan(f):
        return None
    if math.isinf(f):
        return "inf" if f > 0 else "-inf"
    if hasattr(v, "dtype") and float(f).is_integer() and "int" in str(getattr(v, "dtype", "")):
        return int(f)
    return f


def assessment(meets: bool | None, operator: str, threshold: Any, unit: str, threshold_source: str,
               requirement_ids: list[str] | tuple[str, ...] = (), note: str = "") -> dict[str, Any]:
    """A module's verdict on one of its KPIs (see the module docstring for when it counts)."""
    return {"meets": None if meets is None else bool(meets), "operator": operator, "threshold": _value(threshold) if not isinstance(threshold, (list, tuple)) else [_value(t) for t in threshold],
            "unit": norm_unit(unit), "threshold_source": threshold_source, "requirement_ids": [str(r) for r in requirement_ids or []],
            "note": str(note or "")}


def kpi(kpi_id: str, value: Any, *, name: str | None = None, unit: str | None = None, category: str | None = None,
        native_id: str | None = None, context: dict[str, Any] | None = None, source: dict[str, Any] | None = None,
        assessment: dict[str, Any] | None = None) -> dict[str, Any]:
    """One KPI entry; name, unit, category and source default to the catalogue."""
    e = catalogue_entry(kpi_id) or {}
    return {"id": kpi_id, "native_id": native_id, "name": name or e.get("name") or kpi_id.split(".", 1)[-1],
            "value": _value(value), "unit": norm_unit(unit if unit is not None else e.get("unit", "-")),
            "category": category or e.get("category") or "performance", "context": dict(context or {}),
            "source": dict(source or ({"product": e.get("product"), "field": e.get("field")} if e else {})),
            "assessment": assessment}


def document(module_id: str, kpis: list[dict[str, Any]], node: str | None = None, phase: str = "", run_id: str = "",
             generated_at: str | None = None) -> dict[str, Any]:
    # node ids of star_workflow_graph: "END-004", "END-006/initial", "END-006/final"
    return {"schema_version": SCHEMA_VERSION, "module_id": module_id, "node": node or (f"{module_id}/{phase}" if phase else module_id),
            "phase": phase or "", "run_id": run_id or "", "generated_at": generated_at or datetime.now().isoformat(timespec="seconds"),
            "kpis": list(kpis)}


# --------------------------------------------------------------------------- validation, files
def validate(doc: dict[str, Any]) -> list[str]:
    """Problems of a kpis.json document (empty list = valid)."""
    errs: list[str] = []
    if not isinstance(doc, dict):
        return ["the document is not an object"]
    if doc.get("schema_version") != SCHEMA_VERSION:
        errs.append(f"schema_version {doc.get('schema_version')!r} != {SCHEMA_VERSION}")
    mid = str(doc.get("module_id") or "")
    if not re.match(r"^END-\d{3}$", mid):
        errs.append(f"module_id {mid!r} is not END-xxx")
    if doc.get("phase") not in ("", "initial", "final", None):
        errs.append(f"phase {doc.get('phase')!r} is not '', 'initial' or 'final'")
    items = doc.get("kpis")
    if not isinstance(items, list):
        return errs + ["kpis is not a list"]
    seen: set[str] = set()
    for i, k in enumerate(items):
        where = f"kpis[{i}]"
        if not isinstance(k, dict):
            errs.append(f"{where} is not an object")
            continue
        kid = str(k.get("id") or "")
        m = KPI_ID.match(kid)
        if not m:
            errs.append(f"{where}: id {kid!r} is not <END-xxx>.<key>")
        elif m.group(1) != mid:
            errs.append(f"{where}: id {kid!r} does not belong to {mid}")
        elif catalogue_entry(kid) is None:
            errs.append(f"{where}: id {kid!r} is not in star_kpis.CATALOGUE")
        if kid in seen:
            errs.append(f"{where}: duplicate id {kid!r}")
        seen.add(kid)
        if k.get("unit") not in UNITS:
            errs.append(f"{where} ({kid}): unit {k.get('unit')!r} not in UNITS")
        if k.get("category") not in CATEGORIES:
            errs.append(f"{where} ({kid}): category {k.get('category')!r} not in CATEGORIES")
        v = k.get("value")
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            errs.append(f"{where} ({kid}): value {v!r} must be written as text or null")
        elif v is not None and not isinstance(v, (bool, int, float, str)):
            errs.append(f"{where} ({kid}): value of type {type(v).__name__}")
        for f in ("context", "source"):
            if not isinstance(k.get(f), dict):
                errs.append(f"{where} ({kid}): {f} is not an object")
        a = k.get("assessment")
        if a is not None:
            if not isinstance(a, dict):
                errs.append(f"{where} ({kid}): assessment is not an object")
                continue
            if a.get("meets") not in (True, False, None):
                errs.append(f"{where} ({kid}): assessment.meets {a.get('meets')!r}")
            if a.get("operator") not in OPERATORS:
                errs.append(f"{where} ({kid}): assessment.operator {a.get('operator')!r} not in OPERATORS")
            if a.get("threshold_source") not in THRESHOLD_SOURCES:
                errs.append(f"{where} ({kid}): assessment.threshold_source {a.get('threshold_source')!r} not in THRESHOLD_SOURCES")
            if a.get("unit") not in UNITS:
                errs.append(f"{where} ({kid}): assessment.unit {a.get('unit')!r} not in UNITS")
            if not isinstance(a.get("requirement_ids", []), list):
                errs.append(f"{where} ({kid}): assessment.requirement_ids is not a list")
    return errs


def file_name(phase: str = "") -> str:
    return "kpis_initial.json" if phase == "initial" else "kpis.json"


def write(module_root: str | Path, doc: dict[str, Any], phase: str | None = None) -> Path:
    """Validate and write <module_root>/kpis.json (kpis_initial.json for END-006's initial node)."""
    phase = doc.get("phase", "") if phase is None else phase
    errs = validate(doc)
    if errs:
        raise ValueError("invalid kpis.json: " + "; ".join(errs[:10]))
    path = Path(module_root) / file_name(phase)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=1, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    return path


def load_doc(path: str | Path) -> dict[str, Any] | None:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None


def load_run(run_path: str | Path, phase: str = "final") -> dict[str, dict[str, Any]]:
    """{kpi_id: entry} of every kpis.json of a run. END-006: the final node (its initial one when the final did not
    run); phase='initial' reads the initial node instead. Each entry gets 'module_id', 'node' and '_file'."""
    out: dict[str, dict[str, Any]] = {}
    root = Path(run_path) / "modules_output"
    for mdir in sorted(p for p in root.glob("END-*") if p.is_dir()):
        names = ["kpis_initial.json"] if phase == "initial" else ["kpis.json", "kpis_initial.json"]
        for name in names:
            doc = load_doc(mdir / name)
            if doc:
                for k in doc.get("kpis") or []:
                    if isinstance(k, dict) and k.get("id"):
                        out[k["id"]] = {**k, "module_id": doc.get("module_id"), "node": doc.get("node"), "_file": str(mdir / name)}
                break
    return out

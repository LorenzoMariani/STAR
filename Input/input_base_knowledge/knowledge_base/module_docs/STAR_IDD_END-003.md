# STAR Interface Definition Notes — END-003 Attitude Propagation

> Updated 2026-10-21 to the STAR version of the module (star_attitude_propagation_star.m). The formal IDD is STAR/IDD/STAR_IDD_END-003.docx; the module README is END003-AttitudePropagation/README.md.

## Functional role

END-003 computes the attitude of the satellite during the passes END-001 chose: the daylight imaging pass over the area of interest (for END-007, END-019, END-004) and the first night pass visible from the observatory (for END-010). The orbit is not propagated by END-003: it comes from the END-001 ephemerides (Hermite interpolation, sub-metre), so the satellites are exactly the ones END-001 designed.

Attitude modes on a 1 s grid: nadir (+Z to nadir, +X along track; body rate = orbital rate about the orbit normal plus the turn of the orbital plane), follow_site (+Z to the target while it is above the elevation threshold, slews limited) and dynamics (Euler equations with the disturbance torques, free motion). In nadir and follow_site the guidance attitude is the reference of a PD controller with one reaction wheel per body axis, with the wheel torque and momentum limits of the END-006 design, the attitude knowledge error of its star tracker or ADCS unit, and momentum dumping with the magnetorquers (tilted IGRF-13 dipole field). The exported attitude is the controlled one, with its pointing error. Disturbance torques: gravity gradient, solar radiation pressure (with Earth shadow) and drag, and their worst case over all attitudes.

## When the planner should select this module

Select END-003 when the request mentions attitude, nadir or target pointing, pointing accuracy or pointing error, quaternions, line of sight, viewing or observation geometry, target tracking, reaction wheels, magnetorquers, momentum, disturbance torques, eclipses, or when a downstream module needs the attitude of a pass: END-007 (synthetic images), END-010 (light curve), END-019 (thermal) and END-004 (power: eclipse and panel illumination). END-003 needs END-001 earlier in the same workflow (ephemerides and pass_selection.json).

## Input interface

The runner (BackEnd/runners/end003_runner.py) writes modules_output/END-003/end003_runtime_input.json from Input/input_attitude_propagator.json:

- END-001 products of the run: satellite_NN_ephemeris.csv, pass_selection.json and the ground stations of end001_runtime_input.json (the runner stops with a message when they are missing);
- satellite from the END-006 initial design: mass, inertia (uniform box), mean projected area, Cd, Cr, centre of pressure at 20% of each side of the envelope (CubeSat Design Specification centre-of-gravity tolerance), reaction wheels (momentum, maximum torque), star tracker accuracy (converted to 1 sigma) or ADCS pointing accuracy, magnetorquer dipole (otherwise sized to dump a full wheel in one orbit);
- optional STAR inputs: attitude_mode (nadir, follow_site, dynamics), initial_attitude_state, environmental_flags (gg, srp, drag), simulation_duration_hours, spacecraft_physical_properties.

Every decision and its origin is in star_runtime.end003_inputs.

## Output interface

In modules_output/END-003/output_attitude_propagation/:

- output_attitude_propagation.csv — imaging pass every 10 s: timestamp_utc, ECI position [km], quaternion ECI->body (the conjugate, for Unreal / END-007), nadir offset;
- output_attitude_propagation_lightcurve_ECI.csv — the night pass for END-010 (body->ECI);
- selected_passes.json and selected_pass_summary.csv — the two passes (satellite, start, end, peak, elevation, site or observer, Sun);
- pass_candidates.csv; AEM_END003_<satellite>_<pass>_<date>.xml — CCSDS AEM of each pass (1 s, J2000).

In modules_output/END-003/results_attitude_propagator/: output_attitude_propagation_ECI.csv (imaging pass, body->ECI), output_attitude_propagation_Unity.csv, attitude_summary.json (KPI-01 to KPI-33: pass found, thresholds, quaternion drift, peak elevation, duration, nadir and target offsets, mean GG / SRP / drag torques, eclipse fraction KPI-14, angular momentum, body rates, closed-loop control, pointing error, wheel momentum and torque, time at the wheel limits, magnetorquer dipole; face illumination for END-004), figures and attitude_propagation_plots_data.js for the END003 results tab.

## Relationship with other modules

- END-001 gives orbits, passes and ground stations; END-006 gives mass, inertia, areas and ADCS components.
- END-004 uses the orbit of the selected satellite, the eclipse fraction and the face illumination.
- END-007 uses output_attitude_propagation.csv (ECI->body) and selected_passes.json.
- END-010 uses the light-curve pass CSV and its observer.
- END-019 uses selected_pass_summary.csv and the body->ECI attitude of the pass.
- STAR compliance and the END003 results tab read attitude_summary.json.

## Known limits

The satellite is a uniform box: SRP and drag torques use a conservative lever arm, not the real geometry. The closed loop runs at 1 s only over the passes (plus 300 s); elsewhere only the wheel momentum is followed. The dynamics mode is free motion without control. A run takes about one minute.

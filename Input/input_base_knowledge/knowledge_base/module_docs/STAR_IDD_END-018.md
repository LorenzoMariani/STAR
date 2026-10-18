# STAR Interface Definition Notes — END-018 Components Thermal Analysis

## Functional role

END-018 computes the thermal behaviour of a CubeSat (1U, 3U, 6U or 12U) along the orbit and the imaging passes produced by the upstream STAR modules: the temperature over time of the six faces (+X/-X, +Y/-Y, +Z/-Z), of the deployable solar panels and of the internal nodes (central body, battery and, when the payload is a SAR, the SAR payload), and the operational limits that are exceeded (for example the battery above 25 degC). It is a lumped-parameter model: a few thermal nodes exchange heat with each other, with the orbital environment (solar flux, albedo, Earth infrared, eclipses) and with deep space. Its parameters were calibrated on temperatures measured in orbit by a 3U CubeSat (WildtrackCube / SIMBA). The analysis lasts as long as the propagation it receives and starts from the periodic thermal regime of the orbit.

MATLAB sources in `END018-ComponentsThermalAnalysis/src` (MATLAB base only; entry `star_thermal_main`, run by the STAR runner with `matlab -batch`): it reads a configuration file and the STAR products, and writes its results files. The satellite follows its real orbit phase (RAAN, inclination, true anomaly, Sun at the epoch; radius and J2 rates as END-001), so eclipses are aligned with the END-003 passes. `blackbox_build/star_thermal.exe` is the compiled version as delivered (before the 2026-10-15 fixes, see the module README).

## When the planner should select this module

Select END-018 when the mission is a CubeSat (the request or the requirements name a CubeSat or a 1U, 3U, 6U or 12U class) and the request asks for its thermal behaviour, its temperatures, thermal control or thermal limits (battery, payload, solar panels). END-018 needs END-001 Constellation Optimizer (orbits) and END-003 Attitude Propagation (imaging passes, position and attitude) earlier in the same workflow. Do not select it for satellites above 24 kg: the module would report that the mission is out of scope.

## Input interface

The Python runner `runners.end018_runner.run_end018` reads the module input JSON written by the orchestrator and builds `input_termico.json`:

- `form_factor` (1U / 3U / 6U / 12U): the value approved in the missing-information step, else the class written in the requirements (for example "6U CubeSat"), else the first guess 3U when the mission is a CubeSat;
- `panels` (body / deployable / both): from the requirements ("deployable solar panels", "body-mounted solar panels"), else the model default;
- `n_internal_nodes`: 3 (central body, battery, SAR) when the payload is a SAR, else 2 (central body and battery: the model's third node is a SAR payload);
- `sar_power_W`, `sar_source` (passes / duty), `sar_duty`: for a SAR payload; the SAR is switched on during the END-003 imaging passes unless the user chooses a duty cycle; a SAR power not stated in the requirements is left to the model default.

Values the mission does not state are not invented: the model's own defaults are used and listed in the notes. Every value records where it came from (`thermal_run_info.json`).

Upstream files, copied by the runner into one folder for the model: `modules_output/END-001/output_constellation_optimizer/satellite_XX.json` (every satellite is analysed) and `modules_output/END-003/output_attitude_propagation/selected_pass_summary.csv` and the pass attitude `modules_output/END-003/results_attitude_propagator/output_attitude_propagation_ECI.csv` (quaternion body to ECI; if it is missing, `output_attitude_propagation.csv`, the Unreal file with the conjugate quaternion, is read conjugated).

## Output interface

- `modules_output/END-018/output_components_thermal_analysis/output_thermal_SAT-XX.csv` — per satellite: `timestamp_utc`, one `T_<node>` column per face, panel and internal node [degC], `sar_on` (0/1), `eclipse` (0/1);
- `thermal_summary_SAT-XX.json` — per satellite: configuration used, orbit, minimum / maximum / mean of every node, solar panels block, peaks (SAR over the orbit and in the imaging pass with the real attitude, battery, central body), `limits` (battery 25, central body 60, SAR 85 degC) and `violations` (limit flags);
- `thermal_constellation_output.csv` — one row per satellite (form factor, beta angle, number of passes, maximum SAR / battery / central / panel temperatures, battery limit flag);
- `modules_output/END-018/results_components_thermal_analysis/thermal_run_info.json` — configuration passed to the model, provenance of every value, domain notes and status, read by the STAR FrontEnd results tab (END018 Thermal Analysis).

Status: `completed`; `skipped` when the mission is out of scope (no CubeSat, or a satellite above 24 kg); `failed` when END-001 / END-003 products are missing or the model cannot run (MATLAB not found; with the black box, a missing MATLAB Runtime R2026a: the message says so).

## Relationship with other modules

- END-001 provides the orbits, END-003 the imaging passes and the attitude.
- END-006 Satellite Design Component Selector chooses the CubeSat class and components; END-018 takes the class from the requirements or from the user.
- END-004 Power Budget and END-018 share the battery and payload duty assumptions only through the requirements.

## Known limits

- CubeSats only (1U-12U); calibrated on a 3U; preliminary fidelity.
- The internal payload node is a SAR payload; other payloads are not modelled as a separate node.
- Integration test case (author's report): SAT-01 of the STAR example, 3U, deployable panels, 3 nodes, SAR 200 W with 30% duty: maximum SAR about 217 degC, central body 172 degC, battery 103 degC, solar panels 192 degC (+-3 degC), battery limit flag active. Reproduced exactly by star_thermal.exe (the delivered version): 216.5 / 172.3 / 103.2 / 192.2 degC; the corrected sources (periodic start, real orbit phase) give 217.8 / 173.1 / 103.3 / 193.3 degC, within the +-3 degC of the report.

1. ## **Satellite of the run (2026-10-17)**

The CubeSat class is the one of the END-006 initial design (spacecraft_definition.json), shared by all the modules of the
workflow; a class written in the requirements is only reported when it differs.

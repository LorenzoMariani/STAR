# STAR Interface Definition Notes — END-001 Constellation Optimizer

> Updated 2026-10-21 to the STAR version of the module. The formal IDD is STAR/IDD/STAR_IDD_END-001.docx; the module README is END001-ConstellationOptimizer/README.md (END-001 is a git submodule of STAR).

## Functional role

END-001 designs the Earth-observation constellation of the mission. Given the area of interest, the ground stations, the sensor (SAR, push-broom, framing or conical optical) and the weights of the objectives, a multi-objective genetic algorithm (NSGA-II) searches the constellation that best balances maximum, 90th-percentile and mean revisit time, maximum latency to a ground station, average ground-station access, area coverage, robustness and cost (number of satellites and planes, collision proxy, launch). Orbit families: Sun-synchronous repeat ground track (SSORGT), Walker delta with a repeat ground track (RGT), Hybrid, or Auto (both families optimised, the better one kept, also compared at equal number of satellites).

Each candidate is evaluated by a simulator (circular orbits with secular J2, sensor footprints, station visibility on WGS84, Sun constraint for optical sensors) or by a machine-learning surrogate trained on it, which turns hours of optimisation into minutes. The surrogate is valid for an area of interest inside Italy, one ground station in Italy, an optical RECT or push-broom sensor with the Sun constraint and 3-10 planes; outside this domain END-001 falls back to the simulator by itself and says why. The best designs of the surrogate are re-simulated and the best simulated one is exported.

END-001 is the first module of the STAR chain. After choosing the constellation it also selects the passes for the downstream modules (the daylight imaging pass over the area of interest and the first night pass visible from the observatory) and counts the daily operations (acquisitions over the area, ground-station contacts in sunlight and eclipse).

## When the planner should select this module

Select END-001 when the request asks for a constellation, a number of satellites or orbital planes, orbits, altitude or inclination, revisit time, coverage of an area, acquisition frequency, latency, ground-station access or observation windows. Select it also when a downstream module needs orbits: END-003 (attitude), END-004 (power), END-010 (light curve), END-016 (space safety) and END-019 (thermal) all start from the END-001 products of the same run. The area of interest must be inside Italy (STAR domain): a request for an area outside Italy stops STAR.

## Input interface

The runner (BackEnd/runners/end001_runner.py, input built by end001_star_inputs.py) starts from the template Input/input_constellation_optimizer.json and writes modules_output/END-001/end001_runtime_input.json. Priority: STAR input > requirement text > template; every decision and its origin is in star_runtime.end001_inputs.

- Fixed in STAR: surrogate fitness engine, PropagationDays "auto" (one repeat cycle for SSO, a whole lighting-drift cycle for inclined orbits), 10 s step, Sun constraint from the sensor type.
- From the mission (document or user, not registry defaults): area of interest (named area, polygon, point or known place), constellation type, optical FOV, SAR field of regard, start date, evaluation mode, observatory of the night pass.
- Rules read from the requirements: "at most / at least N satellites", "N orbital planes", altitude or altitude range, inclination, Sun-synchronous or Walker delta, push-broom / frame camera / SAR, swath, start epoch. No orbit family stated: Orbit_Type Auto; no revisit stated: "auto" revisit thresholds.
- Satellite: mass, drag area (mean projected area) and Cd from the END-006 initial design (spacecraft_definition.json), unless STAR inputs give them.
- GA size from the run mode: test 20 x 5 x 1 (population x generations x restarts); full levels 1-5 from 60 x 40 x 1 to 200 x 150 x 6.

## Output interface

In modules_output/END-001/output_constellation_optimizer/:

- constellation_optimizer_output.csv — one row per satellite: index, JSON file, start, hours, perigee and apogee altitude [m], inclination, RAAN, argument of perigee, true anomaly [deg];
- satellite_NN.json — the same orbit elements per satellite (sim_start_date, sim_hours, orbit);
- satellite_NN_ephemeris.csv — ECI position [km], velocity [km/s] and nadir body->ECI quaternion every 10 s for 48 h (IAU-82 GMST frame, as END-003 and END-007);
- pass_selection.json — imaging pass (satellite, site, start, end, peak elevation, Sun), light-curve pass (satellite, observer, night conditions) and all imaging candidates;
- operations_summary.json — per satellite and constellation mean: orbits per day, imaging seconds and orbits per day, contact seconds and orbits per day, sunlit and eclipse contact time per contact orbit (an upper bound of the operations).

In modules_output/END-001/results_constellation_optimizer/: coverage_summary.json (KPI-01 to KPI-16: run validity, maximum / P90 / mean revisit, maximum latency, average ground-station access, percent of AOI covered, search quality, number of satellites and planes, altitude, inclination; thresholds and meets_requirement; fitness engine used, orbit family choice), the figures 01-11 and constellation_plots_data.js for the END001 results tab.

## Relationship with other modules

- END-006 (initial design) gives mass, drag area and Cd.
- END-003 uses the ephemerides, pass_selection.json and the ground stations: it computes the attitude on the passes END-001 chose.
- END-004 uses operations_summary.json (duty cycles and orbits per mode) and, through END-003, the orbit period.
- END-006 (final design) uses the orbit altitudes (GSD and swath of the imager).
- END-010 receives the night pass through END-003; END-007 receives orbit and attitude through END-003.
- END-016 uses satellite_NN.json, the ephemerides and the mass, drag area and Cd of end001_runtime_input.json.
- END-019 uses satellite_NN.json.
- STAR compliance and the END001 results tab read coverage_summary.json.

## Known limits

Circular orbits with secular J2 only. The surrogate domain is Italy with one station; elsewhere the simulator is used and runs are much slower (a level-3 run over the whole of Italy takes about 2 hours with the per-site surrogate; test mode about 1 minute). With the Sun constraint the maximum revisit cannot drop below the night length. Weights.EndOfLife and SensorSettings.Optic_Steerable have no effect.

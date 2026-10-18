# STAR Interface Definition Notes — END-016 Collision Avoidance

## Functional role

Inside STAR, END-016 checks the space safety of the constellation designed by END-001:

1. **Close approaches between the satellites of the constellation.** For every pair of satellites over the END-001 ephemeris window (48 h, 10 s): the time of closest approach (TCA, refined between the samples by cubic Hermite interpolation of positions and velocities), the miss distance and its radial, in-track and cross-track components, the relative speed, the sub-satellite point, and the collision probability Pc (Chan method; validated against NASA CARA Pc2D_Foster to 2e-5) with a declared position uncertainty of each satellite, its circumscribing-square upper bound, and Pc_max, the largest Pc any uncertainty could give (it does not depend on the declared uncertainty). Satellites in different Sun-synchronous planes cross near the poles: the phasing and the altitudes decide how close they come.
2. **Orbital lifetime and post-mission disposal.** For every orbit shell: decay under drag with the NRLMSISE-00 atmosphere (averaged over the orbit and local time) for low, mean and high solar activity (F10.7 70, 140, 220), with the mass, drag area and drag coefficient END-001 used; compliance with the FCC 5-year and IADC 25-year rules; delta-v of the perigee-lowering burn that brings the lifetime within each rule; drag make-up delta-v per year that holds the operational altitude; orbits that decay before the end of the mission.

The module's operational tools (collision probability from a CDM and TLE histories downloaded from space-track.org, main.m) are not used inside STAR.

## When the planner should select this module

Select END-016 when the request asks about collisions or close approaches between satellites, safe separation, space debris mitigation, post-mission disposal, re-entry, deorbiting or orbital lifetime. END-016 needs END-001 Constellation Optimizer (orbits and ephemerides) earlier in the same workflow.

## Input interface

From END-001 (copied by the runner into one folder): `modules_output/END-001/output_constellation_optimizer/satellite_NN.json` and `satellite_NN_ephemeris.csv` (written by END-001 since 2026-10-15), and mass, drag area and drag coefficient from `modules_output/END-001/end001_runtime_input.json`.

From the requirements: mission lifetime ("The mission lifetime shall be three years"), disposal deadlines ("re-enter within N years").

Optional, editable in the input-resolution step: `position_sigma_rtn_m` (1-sigma position uncertainty of each satellite, radial / in-track / cross-track; default 50 / 200 / 50 m, a declared assumption for owner/operator GNSS ephemerides predicted about one day ahead), `hard_body_radius_m` (default twice the radius of a disc with the drag area), `screening_km` (10 km), `disposal_rules_years` (5 and 25), `mission_lifetime_years`.

Run mode: test = mean solar activity only; full = low, mean and high.

## Output interface

- `modules_output/END-016/output_collision_avoidance/space_safety_summary.json` — configuration, KPIs (minimum separation and pair, close approaches below the screening distance and below 1 km, highest Pc and Pc_max, passive lifetime at mean activity and range, compliance and disposal delta-v per rule, drag make-up delta-v, orbit maintenance needed), close approaches, pair matrix, distance history of the closest pair, lifetime and decay curve per shell and solar activity;
- `intra_close_approaches.csv` — close approaches below the screening distance;
- `intra_pair_min_distance.csv` — minimum distance of every pair [km];
- `disposal_lifetime.csv` — per shell and solar activity: passive lifetime, drag make-up delta-v, disposal delta-v, perigee and compliance per rule;
- `modules_output/END-016/results_collision_avoidance/collision_run_info.json` — configuration passed to the model, provenance of every value, notes and status, read by the STAR FrontEnd results tab (END016 Collision Avoidance).

Status: `completed`; `failed` when the END-001 products (or its ephemerides) are missing or MATLAB cannot run.

## Relationship with other modules

- END-001 provides the orbits, the ephemerides and the spacecraft mass and drag; its own collision objective `J_collav` is a geometric proxy of the crossings inside the constellation, END-016 measures them.
- The disposal and drag make-up delta-v are inputs for the propulsion choice (END-006) and the mission budgets.

## Known limits

- Only the satellites of the designed constellation: catalogued objects and debris are not included.
- Pc depends on the declared position uncertainty; Pc_max bounds it for any uncertainty.
- Circular orbits, drag only, constant solar activity per level (the real decay crosses solar cycles; low and high activity bound it); lifetimes beyond 200 years are reported as "> 200 years".
- Test case (v6 proposal, 6U CubeSats, 3 planes x 2 satellites at 642 km): minimum separation 2052.8 km, no close approach below 10 km; passive lifetime 35.2 years at mean activity (10.1 years high, > 200 years low): the 5-year rule needs 58 m/s (perigee lowered to 429 km), the 25-year rule 12.3 m/s.

# STAR Interface Definition Notes — END-004 Power Budget

> Updated 2026-10-21. The formal IDD is STAR/IDD/STAR_IDD_END-004.docx; the module README is END004-PowerBudget/README.md.

## Functional role

END-004 is the STAR module for the preliminary electrical power-system feasibility. It computes the energy balance of the satellite for four operating modes (idle, TX UHF, TX S-band, payload): consumption of every subsystem in sunlight and eclipse from its power and duty cycles, a margin (10%), generation per orbit, energy saved or missing, peak power, battery depth of discharge per orbit, idle orbits needed to recharge a deficit, and the daily balance over the orbits of each mode. It reproduces the logic of the reference Excel power-budget workbook of STAR. In STAR the loads come from the components of the END-006 design, the duty cycles from the operations END-001 computed, and the generation from the illumination of the panels in the END-003 attitude.

## When the planner should select this module

Select END-004 when a mission request or reviewed requirement mentions any of the following:

- power budget, EPS feasibility, energy balance;
- battery capacity or battery depth of discharge;
- solar array or solar panel generation;
- duty cycle, payload operating mode, transmission mode;
- daily power margin;
- operational feasibility constrained by power availability.

END-004 should be placed after END-003 Attitude Propagation (orbit, eclipse and panel illumination) and therefore after END-001 (orbits and operations). When END-006 is in the workflow its initial design gives the loads, the battery and the panels.

## Input interface

The runner (BackEnd/runners/end004_runner.py) builds modules_output/END-004/end004_runtime_input.json from END004-PowerBudget/Input/input_power_budget.json and the products of the same run (approved STAR inputs win):

- orbit: period from the END-001 orbit of the satellite END-003 selected (selected_passes.json), eclipse from the END-003 shadow fraction (KPI-14 of attitude_summary.json); otherwise the template values;
- loads: from the END-006 initial design (spacecraft_definition.json): template entries of the subsystems the satellite has, with the vendor-declared powers (peak power for the transmitters); entries of subsystems it does not have are dropped;
- battery: capacity of the END-006 battery or of the battery integrated in the EPS;
- duty cycles and orbits per mode: from END-001 operations_summary.json — payload on while the area is in the footprint, transmitters on during the ground-station contacts (sunlit and eclipse parts), receivers, computers, ADCS and GNSS always on; payload orbits = orbits with acquisitions, contact orbits = orbits with a contact and no acquisition, idle = the rest;
- generation: END-006 peak power per panel x sum of the mean cosines of the panel faces in the END-003 attitude x sunlit minutes; during sunlit transmissions the illumination with the satellite pointing the ground station; beginning of life;
- optional STAR inputs: battery_capacity_Wh, power_generated_per_orbit_Wh, daily_mode_allocation.

## Output interface

- modules_output/END-004/output_power_budget/power_budget_summary.json — orbit, per-mode summaries (consumption, generation, saved energy, peak power, DoD, recharge orbits, orbits per day, daily balance) and analysis (daily balance, maximum DoD, generation per orbit);
- power_budget_summary.csv, power_budget_subsystems.csv (per mode and subsystem), power_budget_sheet1.csv, power_budget_foglio1.csv, power_budget_tables.xlsx (workbook layout), power_budget_status.json;
- modules_output/END-004/results_power_budget/power_budget_tables.js and the figures 01_power_balance.png (generated and consumed energy per mode), 02_mode_consumption.png (sunlight and eclipse consumption per mode), 03_orbital_dod.png (depth of discharge per mode).

## Calculation logic

For each subsystem and mode: duty minutes in sunlight = duty_sun x sunlight_min and in eclipse = duty_eclipse x eclipse_min; energy = power_W x minutes / 60. For each mode: consumption without and with margin, generated energy, saved or missing energy, peak power, DoD = eclipse energy / capacity when the generation covers the sunlit load, otherwise (consumption with margin - generation) / capacity, and idle orbits to recharge a deficit. Daily balance = sum over the modes of saved energy x orbits per day.

## Relationship with other modules

- END-001 gives the operations (operations_summary.json); END-003 gives orbit, eclipse and face illumination; END-006 gives loads, battery and panels.
- END-006 (final design) uses power_budget_summary.json: the energy the battery must give in an orbit sizes the battery.
- STAR compliance reads the daily balance, the maximum depth of discharge and the generation per orbit; END004 results tabs.

## Known limits

Orbit-average balance per mode, no state-of-charge simulation over time; generation at beginning of life without temperature, wiring or ageing losses; the END-001 duty cycles are an upper bound of the operations; four fixed operating modes.

# STAR Interface Definition Notes — END-004 Power Budget

## Functional role

END-004 Power Budget is the STAR module responsible for preliminary electrical power-system feasibility. It computes an energy balance for spacecraft operational modes using subsystem power consumption, sun/eclipse duty cycles, solar-generation assumptions, battery capacity and mission mode allocation. The module replaces the previous END-004 Attitude Visualization placeholder.

## When the planner should select this module

Select END-004 when a mission request or reviewed requirement mentions any of the following:

- power budget;
- EPS feasibility;
- energy balance;
- battery capacity or battery depth of discharge;
- solar array generation;
- duty cycle;
- payload operating mode;
- transmission mode;
- daily power margin;
- operational feasibility constrained by power availability.

END-004 should generally be placed after END-003 Attitude Propagation, because END-004 consumes orbit and timing information from the attitude-propagation output. If END-003 is not already in the workflow, the planner should include END-001 and END-003 upstream when a mission-level power assessment requires an orbit solution.

## Input interface

The Python runner generates `end004_runtime_input.json` from `input_power_budget.json`. The input JSON includes:

- `paths.attitudeCsv`: file path to `modules_output/END-003/output_attitude_propagation/output_attitude_propagation.csv`;
- `paths.attitudeConfigJson`: optional path to `modules_output/END-003/end003_runtime_input.json`;
- `orbit`: default orbit timing values, including `daily_orbits`, `period_min`, `sunlight_min`, and `eclipse_min`;
- `generation`: solar-generation assumptions, including `power_generated_per_orbit_Wh` or optionally `solar_power_W`;
- `battery`: battery capacity in Wh;
- `operations.mode_orbits_per_day`: allocation of daily orbits to idle, TX UHF, TX S-band and payload modes;
- `subsystems`: subsystem power values and sun/eclipse duty cycles for each operational mode.

The runner overwrites only the runtime paths to upstream END-003 products. It does not overwrite the native power-budget configuration unless the user changes the template.

## Output interface

END-004 writes STAR products in the standard module layout:

- `modules_output/END-004/output_power_budget/power_budget_summary.csv`;
- `modules_output/END-004/output_power_budget/power_budget_subsystems.csv`;
- `modules_output/END-004/output_power_budget/power_budget_sheet1.csv`;
- `modules_output/END-004/output_power_budget/power_budget_foglio1.csv`;
- `modules_output/END-004/output_power_budget/power_budget_tables.xlsx`, when MATLAB XLSX writing is available;
- `modules_output/END-004/output_power_budget/power_budget_summary.json`;
- `modules_output/END-004/results_power_budget/power_budget_tables.js`;
- `modules_output/END-004/results_power_budget/01_power_balance.png`;
- `modules_output/END-004/results_power_budget/02_mode_consumption.png`;
- `modules_output/END-004/results_power_budget/03_orbital_dod.png`.

## Calculation logic

For each subsystem and mode, the module computes:

- duty duration in sunlight: `duty_sun * sunlight_min`;
- duty duration in eclipse: `duty_eclipse * eclipse_min`;
- energy consumed in sunlight: `power_W * duty_sun_min / 60`;
- energy consumed in eclipse: `power_W * duty_eclipse_min / 60`.

For each operational mode, it computes:

- total per-orbit consumption without margin;
- total per-orbit consumption with margin;
- generated energy per orbit;
- saved or missing energy per orbit;
- peak power;
- orbital battery depth of discharge;
- number of idle or TX S-band orbits required to recover a deficit;
- daily energy balance using the mode allocation.

## Relationship with other modules

- END-001 can provide the orbit solution used upstream by END-003.
- END-003 provides the attitude/orbit propagation CSV consumed by END-004.
- END-004 can be used before downstream reporting or mission-feasibility discussion.

# STAR Interface Definition Notes — END-019 Satellite Design Component Selector

## Functional role

END-019 selects, for a CubeSat class (1U, 3U, 6U or 12U), at least one component per subsystem that can be accommodated in that CubeSat. It only enforces the mass and volume limits of the CubeSat Design Specification (CDS) Rev. 14.1 (mass 1U 2 kg, 3U 6 kg, 6U 12 kg, 12U 24 kg; volume limit = volume of the CDS envelope, in m3: 1.135e-3, 3.405e-3, 8.283e-3, 1.874e-2) and prefers the components whose key data are most completely published. The catalogue (179 real products from public vendor documents: EnduroSat, ISISpace, AAC Clyde Space, CubeSpace, GomSpace, Pumpkin, NanoAvionics, Blue Canyon, Satlab, NPC Spacemind, Hyperion, Alén Space, Innoflight, Dragonfly Aerospace, Simera Sense, Satlantis, Rocket Lab, Enpulsion, ThrustMe, Busek, VACCO, L3Harris and others) holds only sourced values: a value the vendor does not publish is `null` and is shown as "Not publicly available"; nothing is estimated, assumed or defaulted.

Subsystems (one card each): structure, on-board computer, EPS, battery, solar cells, communications radio, antenna, ADCS, magnetorquer, reaction wheel, star tracker, GNSS receiver, propulsion, payload imager, payload optical terminal. For the small classes not all subsystems fit together (a 1U cannot carry propulsion, optical terminal and camera together): the module reports it, and each card shows the best component that fits on its own. If no component of a subsystem fits the class the card says "No component meets the CubeSat XU standard".

## When the planner should select this module

Select END-019 when a mission request or reviewed requirement mentions a CubeSat or small-satellite platform, a CubeSat form factor (1U, 3U, 6U, 12U), the selection of components or subsystems, a bill of materials, or whether components fit in a CubeSat. Do not select it when the requirements state a satellite mass above 24 kg (the largest CubeSat is 12U): the module then reports that the mission is out of scope and suggests reference platforms (Tyvak Triumph, Renegade, Nebula; Terran Orbital Voyager, Excelsior, Ambassador, Enterprise, SmallSat GEO). END-019 needs no upstream module.

## Input interface

The single input is the CubeSat class `form_factor_u` (1, 3, 6 or 12). The Python runner `runners.end019_runner.run_end019` reads the module input JSON written by the orchestrator and builds it in this order of priority: (1) the value resolved and approved in the missing-information step (`resolved_inputs`); (2) the class written in the requirements text (for example "6U CubeSat"), saved with its supporting sentence in `component_selector_requirements_mapping.json`; (3) `Input/input_component_selector.json`; (4) 6U as first guess, flagged in the notes. No mission, power, pointing, orbit or performance parameter is used.

## Output interface

- `modules_output/END-019/output_component_selector/component_selector_results.json` — class, one entry per subsystem (chosen component with its key data and sources, alternatives that also fit, counts "in database" and "fit"), totals (mass, volume in m3, declared peak power), database statistics (`library`: components, images and datasheets per class) and messages;
- `component_selector_bom.csv` — bill of materials of the chosen components (blank = not publicly available);
- `component_selector_requirements_mapping.json` — the class extracted from the requirements;
- `component_selector_power_handoff.json` — maximum powers declared by the vendors of the chosen components (not estimates), with the subsystems whose power is not publicly available; usable by END-004 Power Budget only as vendor-declared data;
- `modules_output/END-019/results_component_selector/component_selector_data.js` and `component_selector_report.html` — payload and self-contained report for the results tab (view only; the datasheets are shown when the selector runs inside STAR or on the local server).

Status: `completed` when the selection ran (subsystems without a fitting component are listed), `skipped` when the mission is out of scope (satellite above 24 kg).

## Selection logic

- Candidates of a subsystem: published mass not above the class limit; published dimensions that fit the CDS envelope in any orientation (solar panels without dimensions use the declared face); a structure must be of the class. Components without a published mass are used only when no candidate with a known mass exists.
- Choice: the candidate with the most complete published key data (mass, dimensions and the key rows of the subsystem), then the lightest. If the choice exceeds the mass or volume limit of the class, an exact search finds the most complete combination that fits; if none exists the best single component per subsystem is shown and the totals are flagged.
- Volume of a component: product of its three published dimensions (m3). Power: sum of the maximum powers declared by the vendors; unknown values are listed.
- Every number shown comes from the catalogue and carries its source document. The GUI is read-only; for each component it shows the image and the datasheet (local PDF) side by side, and writes "Not available in the database" when either is missing.

## Relationship with other modules

- END-004 Power Budget can read the vendor-declared powers from `component_selector_power_handoff.json`.
- END-019 does not replace END-010 Reflectance Determination or END-007 Synthetic Data Generation: it selects hardware that those modules may later simulate.

## Known limits

Only mass and volume are checked: no electrical, interface, frequency-band or thermal compatibility, no power balance, no mission performance (GSD, pointing, delta-v, gain) and no placement of the components inside the satellite. The sum of the component volumes is a necessary, not a sufficient, condition. All data are `verified: false` until checked by a person. 81 of the 179 components have no local datasheet (their source is a web page or an unreachable PDF) and 24 have no image.

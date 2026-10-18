# STAR - current field of use

Which calls for proposals STAR can process today (frontend v4, October 2026).
STAR federates 18 END modules, 8 of which run (see the README, "The 18 END").
The domain is configured in `Input/input_base_knowledge/config/star_domain.json`
and checked by `BackEnd/runners/star_domain.py` when the workflow is planned and
again when the module inputs are approved: outside it STAR stops and gives the
reason instead of running the modules on default values.

## Calls STAR can process

A call is in the STAR domain when it asks for all of the following.

| aspect | STAR domain | why |
|---|---|---|
| mission | Earth observation (imaging, revisit, monitoring) | the modules and their requirement rules are built for EO |
| satellite | CubeSat 1U, 3U, 6U or 12U, at most 24 kg | END-006 designs the satellite every module uses, from a catalogue of 1U-12U CubeSat components (CubeSat Design Specification) |
| area of interest | Italy: the whole country, a region, a city, a site or coordinates (30 km tolerance on the coastline) | the END-001 surrogate is trained on the Italian area |
| orbit | low Earth orbit, 400-1200 km: Sun-synchronous repeat ground track or inclined repeat ground track (Walker delta) | END-001 orbit table and surrogate training range |
| payload | optical (push-broom or rectangular field of view) | END-001 surrogate, END-006 imagers and END-007 images are optical |
| ground segment | Italian ground stations (6 communication stations) and optical telescopes (8 confirmed), named in the call or chosen by STAR | `Input/input_base_knowledge/config/italian_ground_stations.json` |
| language and format | English or Italian, `.txt` or `.docx`, optional requirements JSON | shared text rules in `BackEnd/runners/star_text_rules.py` |

Requirements STAR reads and checks: maximum, mean and P90 revisit (the call value
is the threshold, twice the value the "bad" end of the scale), latency, access to
the ground stations, coverage, altitude, number of satellites and planes,
inclination, satellite mass and class, GSD and swath, pointing accuracy, bands,
delta-v, disposal deadline, battery depth of discharge.

Example of a call in the domain: `Input/input_base_knowledge/sample_inputs/Mission_Proposal_v7.txt`
(ASI PATRIMONIO-CUBE, a CubeSat optical constellation monitoring Italian
cultural heritage monuments). v7 (2026-10-18) leaves the orbit type and the
number of satellites and of planes to the design: END-001 optimises a
Sun-synchronous and a Walker delta constellation and keeps the better one;
v6 asked for Sun-synchronous orbits and at most 12 satellites.

## What STAR produces for such a call

| END | result |
|---|---|
| END-001 Constellation Optimizer | constellation (orbits, planes, satellites), coverage, revisit, latency, ground-station access, the daylight imaging pass and the night pass over the telescope used by the other modules |
| END-006 Satellite Design Component Selector | the CubeSat from real components: initial design (step 0, used by every module) and final design with their results; requirements met or not met |
| END-003 Attitude Propagation | attitude over the selected passes, attitude ephemeris (AEM) |
| END-004 Power Budget | power and energy balance with the real duty cycles of the passes |
| END-007 Synthetic Data Generation | synthetic optical images of the imaging pass (Unreal), scenario generation included |
| END-010 Reflectance Determination | brightness and light curve of the satellite seen from an Italian telescope |
| END-016 Collision Avoidance | close approaches inside the constellation, orbital lifetime, post-mission disposal |
| END-018 Components Thermal Analysis | temperatures of the CubeSat components over the orbit |

END-001 and END-006 are always in the workflow; the others when the call asks
for their results. The results page shows every module and a "Requirements &
KPIs" tab with each requirement met, not met, partially verified or not
verifiable. A run takes about 3 minutes in Test mode; Full mode has an accuracy
level from 1 to 5 (see the README, "Run modes and smoke test").

## Calls STAR does not process (it stops and gives the reason)

- Area of interest outside Italy, or global coverage (another country, Europe,
  the Mediterranean basin, polar regions, worldwide).
- Orbits outside low Earth orbit (GEO, MEO, HEO, Molniya, lunar, interplanetary,
  Lagrange points) or altitudes outside 400-1200 km.
- Satellites that are not CubeSats (micro- or mini-satellites), a mass above
  24 kg, or classes other than 1U, 3U, 6U, 12U.

## Calls STAR covers only in part

- **SAR missions**: END-001 designs the orbits with its simulation (slower than
  the surrogate); there is no SAR payload in the END-006 catalogue and END-007
  generates optical images only.
- **Areas or constellations the END-001 surrogate does not cover** (a region or
  a city instead of the whole of Italy, several or unusual ground stations,
  sizes outside the surrogate training ranges): STAR uses the END-001
  simulation, valid but slower.
- **Custom 3D scenes** for END-007 (local terrain, 3D objects, events) only
  with the terrain, texture and 3D data provided by the user: STAR never
  invents them.
- **Analyses of the 10 END that are only in the catalogue** (orbit
  determination, CMG and battery health monitoring, solar arrays, multi-fidelity
  analysis, degradation of materials, planetary surfaces, robotic manipulators,
  flexible components, clock anomalies): STAR does not run them.

## Known limits

- The subsystems and requirements are read with declared keyword rules (English
  and Italian); a requirement written in an unusual way may be missed. The user
  reviews the extracted requirements and the workflow before the run.
- The LLM planner may propose END-007 (long Unreal run) when the call mentions
  images; the user can remove it from the workflow.
- Values a vendor does not publish are not estimated: a requirement that needs
  them is "not verifiable".

To widen the domain when a module is extended, edit `star_domain.json` (area,
altitudes, CubeSat classes), `italian_ground_stations.json` and
`italy_places.json`.

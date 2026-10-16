# STAR

AI-based Concurrent Engineering Facility for Earth-observation mission design:
a Python / pywebview orchestrator (`FrontEnd/`, `BackEnd/`) that plans a mission
from its requirements and runs the simulation modules `END0XX-*` (MATLAB,
Python, Unity / Unreal). This repository holds only what running STAR needs.

- `FrontEnd/` - `star_frontend_v3.py` (entry point, with END-018 and END-019) or
  `star_frontend_v2.py` (without them), and the `web/` assets; each version
  writes its own `web/star_*_v2.html` / `_v3.html` pages.
- `BackEnd/` - `ai/` (LLM providers), `modules/`, `runners/` (one runner per
  module; they find STAR's root from their own location).
- `Input/` - `input_base_knowledge/` (module registry, AI config, knowledge
  base, sample mission requests) and the modules' native input templates.
- `END001-ConstellationOptimizer/` - git submodule
  (github.com/LorenzoMariani/matlabConstellationOptimizer), see its `USAGE.md`.
- `END018-ComponentsThermalAnalysis/` - CubeSat thermal model, MATLAB sources
  in `src/` (see its `README.md`; runner `BackEnd/runners/end018_runner.py`,
  results tab in frontend v3).
- `END016-CollisionAvoidance/` - space safety of the END-001 constellation
  inside STAR (close approaches between its satellites with collision
  probability, orbital lifetime and post-mission disposal; MATLAB
  `lib/star_collision_main.m`, runner `BackEnd/runners/end016_runner.py`,
  results tab in frontend v3). Its operational CDM / space-track tools are not
  used by STAR.
- `END003`, `END004`, `END010` - the other modules.
- `END019-ComponentSelector/star_component_selector/` - CubeSat component
  selector (Python standard library only; runner `BackEnd/runners/end019_runner.py`,
  results tab in frontend v3). Since 2026-10-15 it designs the CubeSat for the
  mission: only the subsystems the requirements ask for (propulsion only for
  manoeuvres or the END-016 disposal delta-v), the smallest class that carries
  them, the mission requirements checked with the published data ("Does not
  satisfy REQ-xxx" when no component of the database meets one), the other
  subsystems listed apart. Its vendor datasheets (PDF) are not in the
  repository: without them the selector works and its drawer shows
  "Not available in the database".
- `requirements.txt` - Python packages.

Clone with the submodule:

```
git clone --recursive https://github.com/LorenzoMariani/STAR.git
```

(or `git submodule update --init` in an existing clone).

## Run modes and smoke test

FrontEnd v3 has two **Test / Full** buttons next to the theme switch (default
`test`; `STAR_RUN_MODE` sets the default at start-up; locked while a workflow
runs). With Full, an **accuracy bar** (levels 1-5: Low, Medium, High, Extra
high, Max; default 3 = the module templates, `STAR_RUN_LEVEL`) sets how long
END-001 searches, and the header shows the estimated time of the planned
workflow (of END-001 alone before planning; per-module breakdown in the
tooltip). The mode and level go into every module input file (`run_mode`,
`run_level`) and each runner maps them onto its module:

| module | test (default) | full |
|---|---|---|
| END-001 | surrogate GA 20 x 5, top 1 re-simulated, no parallel pool (~1 min) | by level, see below |
| END-016 | mean solar activity | low, mean and high solar activity |
| END-003, END-004, END-010, END-018, END-019 | complete settings (each takes 1-60 s, mostly MATLAB / Unity start-up) | same |
| END-007 (Unreal) | always complete | always complete |

END-001 by level (surrogate GA population x generations x restarts, best
designs re-simulated; simulation GA outside the surrogate domain), wall time
measured with up to 60 satellites and 400-1200 km:

| level | surrogate GA | simulation GA | END-001 time | weighted score (lower = better) |
|---|---|---|---|---|
| test | 20 x 5 x 1, top 1, no pool | 8 x 1 | 52 s | 0.4616 |
| 1 Low | 60 x 40 x 1, top 10 | 24 x 2 | 94 s | 0.4316 |
| 2 Medium | 80 x 60 x 2, top 20 | 36 x 3 | 168 s | 0.4316 |
| 3 High (template) | 100 x 100 x 3, top 30 | 50 x 3 | 325 s | 0.4319 |
| 4 Extra high | 150 x 120 x 4, top 50 | 64 x 4 | 472 s | 0.4317 |
| 5 Max | 200 x 150 x 6, top 80 | 80 x 6 | 651 s | 0.4316 |

On that case every full level finds the same configuration (3 planes x 2
satellites at 1200 km): the higher levels only lower the chance of missing
the best design on harder search spaces.

The estimate adds the module times measured on the STAR workstation (8 MATLAB
workers); the scenario changes them (END-001 outside the surrogate domain
runs the simulation GA). On the v6 proposal the test GA of END-001 already
finds the configuration of the full run (3 planes x 2 satellites, 642 vs 647
km, weighted score within 0.4%); on larger search spaces (up to 60
satellites, 400-1200 km) it does not, and level 1 is enough to match level 3.
The `demo` mode (same settings as test) was removed on 2026-10-15; old input
files that carry it run as test.

`FrontEnd/star_smoke_test.py` runs the whole pipeline headless through the
same StarApi as the window (new run, reviewed requirements, rule-based
planning, approvals, execution) and prints the status and time of each
module; by default the v6 sample proposal with its stored requirements, mode
`test`, without END-007 (about 3 minutes):

```
python FrontEnd/star_smoke_test.py
python FrontEnd/star_smoke_test.py --mode full --level 1 --with-end007
```

## Not in this repository

| What | Why | To run |
|---|---|---|
| `Output/` | run outputs | created by every run |
| `END007-SyntheticDataGeneration/` | own repository, 16 GB | copy it next to the other modules |
| `STAR-ORCHESTRATOR/OllamaModels/` | local LLM models, 4.4 GB | copy them, or pull the models with Ollama |
| `END010-ReflectanceDetermination/lib/data/DE440.mat` (94 MB) | JPL DE440 ephemeris | copy it into `lib/data/` |
| `END010-ReflectanceDetermination/lib/BuildCubeSat/` (99 MB) | Unity build of the CubeSat light curve | build it from `END010-ReflectanceDetermination/unity_project` (`README_STAR.md`), or copy it into `lib/` |
| `END010-ReflectanceDetermination/lib/BuildAqua/` (97 MB) | previous Unity build (Aqua), used only if `BuildCubeSat` is missing | copy the build into `lib/` |
| `Input/cubesat_3d_models/` except `cds_nasa_style_1U_2U_3U_6U_12U/` (CDS boxes, NASA and Pumpkin models) | only the NASA-style CDS models are used | - |
| `END016-CollisionAvoidance/lib/loginSpaceTrack.m` | space-track.org credentials | keep your own copy locally |
| `Documentation/`, presentations and documents (`*.pptx`, `*.pdf`, `*.docx`, ...; the sample mission requests in `Input/` stay), `DEMO_WorkshopASI.pptx`, `folder_tree.py`, `struttura_cartelle.txt`, `.claude/`, `.vscode/` | not needed to run STAR | - |
| documentation and example results of the CARA tools in `END016-CollisionAvoidance/CARA_Analysis_Tools/` | not needed to run STAR | - |
| `_old_versions/`, `_old*/` folders, `END019-ComponentSelector.zip` | superseded / not integrated | - |

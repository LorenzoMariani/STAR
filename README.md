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
- `END003`, `END004`, `END010`, `END016` - the other modules.
- `END019-ComponentSelector/star_component_selector/` - CubeSat component
  selector (Python standard library only; runner `BackEnd/runners/end019_runner.py`,
  results tab in frontend v3). Its vendor datasheets (PDF) are not in the
  repository: without them the selector works and its drawer shows
  "Not available in the database".
- `requirements.txt` - Python packages.

Clone with the submodule:

```
git clone --recursive https://github.com/LorenzoMariani/STAR.git
```

(or `git submodule update --init` in an existing clone).

## Run modes and smoke test

The execution toolbar of FrontEnd v3 has a **Run mode** selector (default
`demo`; `STAR_RUN_MODE` sets the default at start-up). The mode goes into every
module input file (`run_mode`) and each runner maps it onto its module:

| module | demo (default) | test | full |
|---|---|---|---|
| END-001 | surrogate GA 60 x 40, top 10 re-simulated (~1.5 min; same design as full on the cases tried) | 20 x 5, top 1, no parallel pool (~50 s) | template sizes (5-8 min) |
| END-003, END-004, END-010, END-018, END-019 | complete settings (each takes 1-60 s, mostly MATLAB / Unity start-up) | same | same |
| END-007 (Unreal) | always complete | always complete | always complete |

`FrontEnd/star_smoke_test.py` runs the whole pipeline headless through the
same StarApi as the window (new run, reviewed requirements, rule-based
planning, approvals, execution) and prints the status and time of each
module; by default the v6 sample proposal with its stored requirements, mode
`test`, without END-007 (about 3 minutes):

```
python FrontEnd/star_smoke_test.py
python FrontEnd/star_smoke_test.py --mode demo --with-end007
```

## Not in this repository

| What | Why | To run |
|---|---|---|
| `Output/` | run outputs | created by every run |
| `END007-SyntheticDataGeneration/` | own repository, 16 GB | copy it next to the other modules |
| `STAR-ORCHESTRATOR/OllamaModels/` | local LLM models, 4.4 GB | copy them, or pull the models with Ollama |
| `END010-ReflectanceDetermination/lib/data/DE440.mat` (94 MB) | JPL DE440 ephemeris | copy it into `lib/data/` |
| `END010-ReflectanceDetermination/lib/BuildAqua/` (97 MB) | Unity build | copy the build into `lib/` |
| `END016-CollisionAvoidance/lib/loginSpaceTrack.m` | space-track.org credentials | keep your own copy locally |
| `Documentation/`, presentations and documents (`*.pptx`, `*.pdf`, `*.docx`, ...; the sample mission requests in `Input/` stay), `DEMO_WorkshopASI.pptx`, `folder_tree.py`, `struttura_cartelle.txt`, `.claude/`, `.vscode/` | not needed to run STAR | - |
| documentation and example results of the CARA tools in `END016-CollisionAvoidance/CARA_Analysis_Tools/` | not needed to run STAR | - |
| `_old_versions/`, `_old*/` folders, `END019-ComponentSelector.zip` | superseded / not integrated | - |

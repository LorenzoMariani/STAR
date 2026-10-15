# STAR

AI-based Concurrent Engineering Facility for Earth-observation mission design:
a Python / pywebview orchestrator (`FrontEnd/`, `BackEnd/`) that plans a mission
from its requirements and runs the simulation modules `END0XX-*` (MATLAB,
Python, Unity / Unreal).

- `FrontEnd/` - `star_frontend_v2.py` (entry point) and the `web/` assets.
- `BackEnd/` - `ai/` (LLM providers), `modules/`, `runners/` (one runner per
  module; they find STAR's root from their own location).
- `Input/` - `input_base_knowledge/` (module registry, AI config, knowledge
  base, sample mission requests) and the modules' native input templates.
- `END001-ConstellationOptimizer/` - git submodule
  (github.com/LorenzoMariani/matlabConstellationOptimizer), see its `USAGE.md`.
- `END003`, `END004`, `END010`, `END016`, `END018` - the other modules.
- `Documentation/` - architecture, ICD / IDD, ECSS references, presentations.

Clone with the submodule:

```
git clone --recursive https://github.com/LorenzoMariani/STAR.git
```

(or `git submodule update --init` in an existing clone).

## Not in this repository

| What | Why | To run |
|---|---|---|
| `Output/` | run outputs | created by every run |
| `END007-SyntheticDataGeneration/` | own repository, 16 GB | copy it next to the other modules |
| `_old_versions/`, `_old*/` folders | superseded versions | - |
| `STAR-ORCHESTRATOR/OllamaModels/` | local LLM models, 4.4 GB | copy them, or pull the models with Ollama |
| `END010-ReflectanceDetermination/lib/data/DE440.mat` (94 MB) | JPL DE440 ephemeris | copy it into `lib/data/` |
| `END010-ReflectanceDetermination/lib/BuildAqua/` (97 MB) | Unity build | copy the build into `lib/` |
| `END016-CollisionAvoidance/lib/loginSpaceTrack.m` | space-track.org credentials | keep your own copy locally |
| `END019-ComponentSelector.zip`, `Documentation/.../STAR_Presentazione_Spoke2.pptx`, `video_ terra.mp4` | over 50 MB | - |

# STAR — notes for Claude sessions

STAR (Space mission Twin for Architecture Representation) federates 19 END modules: END-018 is ABEP (catalogue only), the components thermal analysis is END-019. Read `README.md` for the module table.

## Working rules
- Chat with the user in Italian; code, comments, commit messages and docs in English.
- Plan + time estimate before big changes; preview UI changes; **commit and push only when the user asks**.
- Do not create or update documentation, Word or PDF files unless asked.
- The user deletes data (Output runs); never delete them yourself.
- Token budget: work directly, no multi-agent fan-out unless the user asks. When a step needs another model or effort, finish the current operations, stop and tell the user which model/effort to pick.
- The architecture plan (phases A–F, 2026-10-21..23) is complete: single dependency source in the registry, statuses/provenance, eclipse and power single source, common KPIs, CEF loop. Accepted result: the CEF loop ends `not_converged` on CEF-BATTERY (no catalogued heater keeps the battery warm in the cold case).
- END-019 is a black box: never modify existing files in `END019-ComponentsThermalAnalysis`; additions go in separate files under `BackEnd/runners/matlab/`.

## Layout
- `FrontEnd/star_frontend_v5.py` — app and orchestrator (`StarApi`); results page `FrontEnd/web/star_results_frontend_v5.html` and execution page are GENERATED from `web/star_results_shell_template_v5.html`, `web/modules/*.html` and the Python patches: regenerate them after editing.
- `BackEnd/runners/end0XX_runner.py` — one runner per module; shared helpers `star_runner_io.py` (runners read inputs with `upstream_product()`); text rules `star_text_rules.py`.
- Shared STAR logic in `BackEnd/runners/`: `star_workflow_graph.py` (order, closure, product checks from the registry), `star_status.py` + `star_provenance.py` (statuses, `star_provenance.json`), `star_kpis.py` + `star_kpi_adapters.py` (one `kpis.json` per node, global ids `<module>.<key>`), `star_compliance.py` (generic, rules in `config/requirement_kpi_rules.yaml`), `star_traceability.py`, `star_cef.py` (CEF loop, criteria in `config/cef_loop.yaml`).
- `Input/input_base_knowledge/registry/*.yaml` — module registry; its `produces`/`consumes` are the ONLY source of dependencies (a new module or product is declared there). `config/` — rule and loop configuration; `knowledge_base/module_docs/*.md` — planner notes.
- `END001-ConstellationOptimizer` is a git submodule (private repo, MATLAB, code in `lib/`).
- Modules: END003 attitude, END004 power, END006 component selector (runs first as initial design and last as final design), END007 Unreal (excluded from tests), END010 reflectance, END016 space safety, END019 thermal.

## Commands
- Tests: `C:/Users/s5oss/anaconda3/python.exe run_all_tests.py` (all suites but SMOKE, ~4 min; `--list`, or suite ids such as STAR, CEF, END-006, HEATER).
- Smoke test (whole pipeline with the CEF loop, ~8 min): `C:/Users/s5oss/anaconda3/envs/star/python.exe run_all_tests.py SMOKE` — needs the `star` env (pywebview).
- END-006 tests need base anaconda (PIL); the app and python-docx need the `star` env.
- MATLAB R2025b (`matlab -batch`); do not name scratch scripts `run.m`.
- GitHub CLI: `C:/Program Files/GitHub CLI/gh.exe` (CI = workflow "tests").

## Git
- Stage explicit paths; end commit messages with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` (or the model in use).
- Push from a new terminal tab: END-001 submodule first (`git -C END001-ConstellationOptimizer push origin HEAD:main`), then STAR (`git push origin HEAD:main`); GitHub login is the user's (Git Credential Manager).
- Work from another PC arrives as branches: fetch, merge into main, run the tests, then push.
- One branch per task; delete it (local and remote) once merged into main.
- Datasheet PDFs (`END006-ComponentSelector/star_component_selector/datasheets/`, `Datasheet_CubeSat_1U-12U/`) are never committed.

## Security
- Never read, print or commit `END016-CollisionAvoidance/lib/loginSpaceTrack.m` (credentials).
- Never use or repeat tokens (e.g. the Unity repo remote); never enter credentials.
- Do not modify the Unity package; only its inputs.

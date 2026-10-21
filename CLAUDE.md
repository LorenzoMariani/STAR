# STAR — notes for Claude sessions

STAR (Space mission Twin for Architecture Representation) federates 19 END modules: END-018 is ABEP (catalogue only), the components thermal analysis is END-019. Read `README.md` for the module table.

## Working rules
- Chat with the user in Italian; code, comments, commit messages and docs in English.
- Plan + time estimate before big changes; preview UI changes; **commit and push only when the user asks**.
- Do not create or update documentation, Word or PDF files unless asked.
- The user deletes data (Output runs); never delete them yourself.
- Token budget: work directly, no multi-agent fan-out unless the user asks. When a step needs another model or effort, finish the current operations, stop and tell the user which model/effort to pick.
- Architecture plan in progress (phases A–F, decided 2026-10-21): CEF loop, single dependency source in the registry, statuses/provenance, eclipse and power single source, common KPIs. Ask the user for the current phase before starting.

## Layout
- `FrontEnd/star_frontend_v5.py` — app and orchestrator (`StarApi`); results page `FrontEnd/web/star_results_frontend_v5.html` and execution page are GENERATED from `web/star_results_shell_template_v5.html`, `web/modules/*.html` and the Python patches: regenerate them after editing.
- `BackEnd/runners/end0XX_runner.py` — one runner per module; shared helpers `star_runner_io.py`; compliance `star_compliance.py`; text rules `star_text_rules.py`.
- `Input/input_base_knowledge/registry/*.yaml` — module registry; `knowledge_base/module_docs/*.md` — planner notes.
- `END001-ConstellationOptimizer` is a git submodule (private repo, MATLAB, code in `lib/`).
- Modules: END003 attitude, END004 power, END006 component selector (runs first as initial design and last as final design), END007 Unreal (excluded from tests), END010 reflectance, END016 space safety, END019 thermal.

## Commands
- Tests: `C:/Users/s5oss/anaconda3/python.exe run_all_tests.py` (all suites but SMOKE; `--list`, or suite ids).
- Smoke test (whole pipeline, ~4 min): `C:/Users/s5oss/anaconda3/envs/star/python.exe run_all_tests.py SMOKE` — needs the `star` env (pywebview).
- END-006 tests need base anaconda (PIL); the app and python-docx need the `star` env.
- MATLAB R2025b (`matlab -batch`); do not name scratch scripts `run.m`.
- GitHub CLI: `C:/Program Files/GitHub CLI/gh.exe` (CI = workflow "tests").

## Git
- Stage explicit paths; end commit messages with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` (or the model in use).
- Push from a new terminal tab: END-001 submodule first (`git -C END001-ConstellationOptimizer push origin HEAD:main`), then STAR (`git push origin HEAD:main`); GitHub login is the user's (Git Credential Manager).
- Work from another PC arrives as branches: fetch, merge into main, run the tests, then push.

## Security
- Never read, print or commit `END016-CollisionAvoidance/lib/loginSpaceTrack.m` (credentials).
- Never use or repeat tokens (e.g. the Unity repo remote); never enter credentials.
- Do not modify the Unity package; only its inputs.

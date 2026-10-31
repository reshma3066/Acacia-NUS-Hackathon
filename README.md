# Acacia-NUS-Hackathon
# Acacia-NUS-Hackathon

# SAF Planner v2.0
Four owners: Shaza data/validation, Reshma MILP/baseline, Sarah UI/integration, Syakir Claude/service.
Reference implementations supplied. Setup and contract tests run locally without an API key or paid Claude calls.

## Windows PowerShell
```
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```
If activation fails call .venv\Scripts\python.exe directly.
## macOS / Linux
```
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```
Python 3.11+. The contract tests do not need `.env`. For optional live Claude features, copy `.env.example` to `.env` only if `.env` does not already exist, then configure credentials locally. Keep `CLAUDE_MODEL=claude-opus-5-5`. Never commit `.env` or API keys. Live API calls are outside this starter setup.
## Run from repository root
```
python scripts/prepare_data.py
python -m pytest tests/test_contract_fixtures.py -q
python scripts/check_full_scenarios.py
python scripts/render_network.py
python -m streamlit run app.py
```
Expected tests: 6 passed. Mock annual cost USD 48,258,300. Fixture demand is synthetic 100 t, full base 1,200,000 t.
Raw organiser data is included; commit it in the bootstrap commit. New four-airport CSV is authoritative. No external public dataset is used.
Results in docs are actually computed solver evidence. They are replays until rerun; inspect status and mip_gap.
The API parser uses official Messages API: https://platform.claude.com/docs/en/api/sdks/python . This is a code documentation reference, not an external dataset.

## First valid submission
Start 13:20 Singapore time. Interface check 13:40. Integrated target 14:05. First valid submission target 14:20. It must include actual Claude interaction, candidate MILP, baseline, validated result and a usable UI; a mock-only UI does not qualify. Verify organiser submission checklist and store receipt + commit SHA. Improvements until 15:10 freeze; final resubmit by16:00 only if allowed; hard close16:15.

## Git
The shared starter is proposed on `setup/saf-v2-starter`; Sarah owns review and integration into `main`. Keep the existing branches:

| Owner | Branch |
| --- | --- |
| Shaza | `shaza` |
| Reshma | `reshma-optimizer` |
| Sarah | `sarah-dashboard` |
| Syakir | `feat/syakir-agent-service` |

After Sarah merges the starter PR, commit your work on your own branch (or stash it with `git stash push -u`) before synchronizing. Run from the repository root, replacing `<your-existing-branch>` with the branch above:

```sh
git fetch origin
git switch <your-existing-branch>
git merge origin/main
git push -u origin HEAD
```

If you stashed work, restore it with `git stash pop` after the merge. If there are conflicts, stop and resolve them with the affected file owner before committing or pushing; `git merge --abort` cancels an in-progress merge. Do not reset branches or force-push. Contracts require Shaza + affected owner. Sarah integrates data -> solver -> service -> UI.

Syakir's current branch keeps his implementation under `syakir_agent_service/saf/` and uses schema `1.0`. This starter uses root `saf/` and schema `2.0`; the app imports root `saf/`. Merging main preserves both paths. Syakir and Shaza should reconcile the schema and integrate his implementation into the shared modules with Sarah; this setup does not move or replace it.

## Baseline and scenarios
80 small depots at sources, all8 large refineries, own source->depot links; other stage links complete. Baseline solves flows only. Supply6800kt. Base requires6000kt; BPN+20%6300kt; all+15%6900kt infeasible. Eight large intakes8696kt. Individual source <150kt. Six large refineries are the minimum capacity count for either feasible scenario.
Capacity is intake only. Cost = CapEx/20 + fixed OpEx + variable OpEx + transport. TRK final leg barge and excluded from truck trips.

See docs/CHANGELOG.md, assumptions_notes.md and evaluation.md. All five guides repeat identical shared contracts.

## Team
- Reshma
- Sarah
- Shaza
- Syakir
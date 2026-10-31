# SAF Planner - demo script (Sarah drives, three speakers talk)

Target: under 3 minutes. Sarah drives the UI and starts/stops the backup recording; no spoken slot.

## Before going on stage

1. `python -m pytest tests/test_contract_fixtures.py -q` -> `6 passed`.
2. `python -m streamlit run app.py`, browser zoom ~90%, sidebar open.
3. Check the API key with one small live request (e.g. "Increase BPN demand by 20%"). If it fails, plan to use **Cached replay** for steps 2-3 and say so out loud.
4. Start the backup screen recording.

## Run of show

| # | Sidebar action | What the screen must show | Speaker line (cue) |
|---|---|---|---|
| 1 | Mode **Live solve**, scenario **Base**, no request, **Solve** (~15 s + baseline) | Status `feasible`, Validation `PASS`, gap ~0.98%. MILP ~$946.6m vs same-scenario baseline ~$1,113.9m (~15% lower). Map: dashed TRK barge, no TRK truck trips. | "Supply planner's question: where to build, how big, and what it costs per year." |
| 2 | Scenario **Base**, request `Increase BPN demand by 20%`, **Solve** | New scenario id (`full-base-v2.0-xxxxxxxx`), sidebar BPN 360 kt. MILP ~$982.2m vs its own baseline ~$1,150.4m. Sidebar shows the Claude request. | "Claude only turns words into a bounded demand patch; the solver computes, the validator checks." |
| 3 | Scenario **All airports +15%**, no request, **Solve** | `INFEASIBLE` banner: 1,380 kt asked vs 1,360 kt max, 20 kt short. **No** cost cards, map or flows. | "When there is no plan, it says so and why; it never shows a cheap-looking empty network." |
| 4 | Scenario **Base**, **Solve** | Back to a valid base plan. Point at the facility table and the CSV coordinate download. | "Every site has coordinates and utilisation; planners can export and check it." |

Base vs BPN+20% is the cost of serving more demand, **not** optimisation savings. Savings are only MILP vs its own same-scenario baseline.

## If something breaks

- **Claude/API error:** screen shows "No scenario changed"; that is the honest failure state. Switch to **Cached replay -> BPN +20%** and say it is a recorded run (the provenance line says `cached`).
- **Solver slow / `NO_SOLUTION`:** say "not proof of infeasibility", switch to **Cached replay**.
- **App down:** play the backup recording.

## After

Stop the recording, save it next to the submission receipt and the commit SHA (`git rev-parse HEAD`).

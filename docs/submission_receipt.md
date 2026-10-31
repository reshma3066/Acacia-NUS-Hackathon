# Submission receipt

## First valid submission

| Field | Value |
|---|---|
| Commit SHA | `804a3e3ceac18a385cd32316d021d641ccc3152f` |
| Branch | `sarah-dashboard` |
| Submitted at (local time) | _fill in_ |
| Organiser receipt / confirmation id | _fill in_ |
| Submitted by | Sarah |

## End-to-end smoke on that SHA (clean `git archive` export, 2026-10-31)

| Check | Result |
|---|---|
| `python -m pytest tests/test_contract_fixtures.py -q` | 6 passed |
| `python scripts/check_full_scenarios.py` (~23 s) | Base: MILP feasible, valid, $946,631,692/yr, gap 0.970%; baseline optimal, valid, $1,113,867,184/yr |
| | BPN +20%: MILP feasible, valid, $982,173,384/yr, gap 0.845%; baseline optimal, valid, $1,150,419,177/yr |
| | All +15%: MILP and baseline both `infeasible`, valid=false, empty costs |
| App, Live solve, Base | PASS, $946.63m vs same-scenario baseline $1,113.87m |
| App, Live solve, infeasible right after Base | INFEASIBLE banner (1,380 vs 1,360 kt, 20 kt short); no cost cards, map or flows from the previous run |
| App, Cached replay, all three scenarios | Labelled `cached`; numbers match the recorded runs |
| App, Claude request with no API key | "No scenario changed"; no plan shown |
| Live Claude `parse_request("Increase BPN demand by 20%")` | `ready` patch: BPN 300,000 -> 360,000 t/yr, others unchanged |
| Live Claude -> solver -> validator -> baseline | scenario `full-base-v2.0-3030a577`, feasible, valid, $982,173,384/yr, gap 0.845%; same-scenario baseline optimal, $1,150,419,177/yr |
| Live Claude, unsupported request "Change refinery yield to 0.5" | Refused, no plan: "Changing refinery yield is not supported. Only airport demand changes..." |
| App in browser, live Claude request | _fill in after manual check_ |

MIP-gap runs differ slightly between solves (time/gap-limited HiGHS); every result is checked by the independent validator.

## Later resubmissions

| Time | SHA | Change |
|---|---|---|
| | | |

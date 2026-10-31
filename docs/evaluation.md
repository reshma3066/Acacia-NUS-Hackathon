# Measured solver evaluation

Measured on 31 October 2026, 14:28:11 to 14:28:17 Singapore time. Run ID: `20261031T142811+0800-be728b03`.

Source commit: `52c1b3e4729666c45c439062a14b61a61157b4bb`. The working tree was clean when the run started. Environment: Python 3.14.7, NumPy 2.5.4, SciPy 1.18.1, Windows-11-10.0.26200-SP0.

All figures below come from this local run. Solver settings remain 30 seconds and a 0.01 relative-gap target from the shared configs. No Claude API calls were made.

## Results

| Scenario | Method | Status | Annual cost (USD) | Runtime (s) | Relative gap | Independent validation |
| --- | --- | --- | ---: | ---: | ---: | --- |
| Base | baseline | optimal | 1,113,867,184.07 | 0.024795 | 0.000000% | Passed |
| Base | milp | feasible | 946,681,061.43 | 5.196913 | 0.850070% | Passed |
| BPN +20% | baseline | optimal | 1,150,419,177.46 | 0.023257 | 0.000000% | Passed |
| BPN +20% | milp | feasible | 986,705,744.91 | 0.447913 | 0.949715% | Passed |
| All airports +15% | baseline | infeasible | Unavailable | 0.015245 | null | No feasible solution to validate |
| All airports +15% | milp | infeasible | Unavailable | 0.006881 | null | No feasible solution to validate |

Both MILP incumbents have positive gaps and are reported as `feasible`. Baseline optimality applies only to continuous flows within the fixed layout. The all-airports +15% case has empty costs, facilities, flows and deliveries, with a null gap; its `valid=false` is expected.

## Matching baseline comparisons

| Scenario | Baseline annual cost (USD) | MILP annual cost (USD) | Saving (USD/year) | Saving (%) |
| --- | ---: | ---: | ---: | ---: |
| Base | 1,113,867,184.07 | 946,681,061.43 | 167,186,122.64 | 15.0095% |
| BPN +20% | 1,150,419,177.46 | 986,705,744.91 | 163,713,432.56 | 14.2308% |

Each comparison uses identical demand, yields, costs, distances and capacity definitions. The baseline fixes all 80 small depots and all eight large refineries, restricts each source to its own depot, and optimises continuous flows. Its feasible set is contained in the candidate MILP. Comparing BPN +20% against the base baseline would be invalid.

The measured MILP costs are above the starter's recorded incumbents. Both runs meet the agreed 1% gap target; different termination paths can produce different feasible solutions. Hardware and solver versions also differ from the starter, so these timings do not establish a controlled speedup.

## Four annual cost terms

| Scenario / method | Annualised CapEx (USD) | Fixed OpEx (USD) | Variable OpEx (USD) | Transport (USD) |
| --- | ---: | ---: | ---: | ---: |
| Base / baseline | 315,000,000.00 | 315,000,000.00 | 360,000,000.00 | 123,867,184.07 |
| Base / milp | 234,112,500.00 | 234,112,500.00 | 354,399,030.00 | 124,057,031.43 |
| BPN +20% / baseline | 315,000,000.00 | 315,000,000.00 | 378,000,000.00 | 142,419,177.46 |
| BPN +20% / milp | 234,675,000.00 | 234,675,000.00 | 371,700,000.00 | 145,655,744.91 |

Annual total = CapEx / 20 + fixed OpEx + variable OpEx + transport. Upfront CapEx and the aggregate `opex_usd_per_year` remain available in the Result JSON; neither is added again to this breakdown. Capacity and variable OpEx use input biomass tonnes. Refinery-airport transport uses SAF tonnes. Distances already contain the organiser's 1.3 multiplier.

## Selected facilities and flow checks

| Scenario / method | Small depots | Large depots | Small refineries | Large refineries |
| --- | ---: | ---: | ---: | ---: |
| Base / baseline | 80 | 0 | 0 | 8 |
| Base / milp | 3 | 19 | 0 | 6 |
| BPN +20% / baseline | 80 | 0 | 0 | 8 |
| BPN +20% / milp | 0 | 23 | 0 | 6 |

PNK, PKN and TRK each receive 300,000 t SAF/year in both feasible cases. BPN receives 300,000 t in base and 360,000 t after the demand increase. Every selected facility has a coordinate export joined by candidate ID outside the shared Result schema. TRK final legs are barge; its edges are absent from truck-trip equivalents. Other trip equivalents use the supplied 3/9, 18/30 and 16/32 tonne payloads.

## Capacity and infeasibility proof

| Scenario | SAF demand (t/year) | Required biomass (t/year) | Available biomass (t/year) | Supply test |
| --- | ---: | ---: | ---: | --- |
| Base | 1,200,000 | 6,000,000 | 6,800,000 | Sufficient |
| BPN +20% | 1,260,000 | 6,300,000 | 6,800,000 | Sufficient |
| All airports +15% | 1,380,000 | 6,900,000 | 6,800,000 | Infeasible |

The 80 sources supply 6,800,000 t/year, so refinery yield 0.20 and depot yield 1 limit SAF to 1,360,000 t/year. The +15% case needs 1,380,000 t SAF. Both methods return proven `infeasible` before invoking HiGHS.

Every source is below a small depot's 150,000 t/year intake. The eight fixed large refineries provide 8,696,000 t/year intake. The base and BPN scenarios need at least six refinery candidates because each can accept at most 1,087,000 t/year. Integer count cuts enforce that valid lower bound while preserving the original feasible layouts.

## Verification and reproducibility

- `python -m pytest tests/test_contract_fixtures.py -q`: **6 passed in 0.42s**.
- `python scripts/check_full_scenarios.py --checks-only`: **30 named checks passed**; the same checks also passed before the full run.
- `python scripts/check_full_scenarios.py`: all six full-data runs completed; four feasible Results passed the unchanged independent validator, and both expected failures passed the supply proof and empty-result checks.
- Regression checks cover fixture costs, mass balance, modes and trips, fixed layouts, input immutability, malformed inputs, disconnected networks, finite values, backend termination statuses, positive gaps and invalid incumbents.
- The optimizer validates bounds, size integrality and flow constraints before assembling output, then calls the independent validator. It distinguishes `error`, `no_solution` and `infeasible`; positive gaps never produce an exact optimum claim.
- Full-run evidence includes strict JSON, matching scenario IDs, fixed-baseline rule checks, coordinates, source hashes and runtime metadata. Source hashes and returned validation were independently rechecked without rerunning the solver.

Run from an activated repository virtual environment (or use `.venv\Scripts\python.exe` directly on Windows):

```sh
python -m pytest tests/test_contract_fixtures.py -q
python scripts/check_full_scenarios.py --checks-only
python scripts/check_full_scenarios.py
```

The final command regenerates solver evidence in `docs/`. Use `--output-dir <temporary-directory>` to preserve the committed run during experiments. The runner has no import-time solver execution. Model runtime includes preflight, model construction, solve and output validation; baseline runtime also includes copying and filtering its layout. Evidence rendering and file writes are outside those runtimes.

Evidence: [run summary](run_results.json), [run metadata and input hashes](solver_run_metadata.json), [base baseline](assumptions_full_baseline.json), [base MILP](assumptions_full_milp.json), [BPN baseline](assumptions_full_bpn20_baseline.json), [BPN MILP](assumptions_full_bpn20_milp.json), [infeasible baseline](assumptions_full_infeasible_baseline.json), [infeasible MILP](assumptions_full_infeasible_milp.json). Saved solver outputs are replays when loaded later. This run's package versions are in `solver_run_metadata.json`; `environment.json` is the unchanged starter record.

## Inputs, scope and handoff

The attached updated organiser workbook and airport CSV were SHA-256 identical to `data/raw/challenge3_parameters.xlsx` and `data/raw/challenge3_airports_4.csv`. All organiser values match the shared configs. No data, config, schema, shared signature, validator, UI or Claude/service file was changed.

The existing size-choice MILP and four-term objective are retained. This work adds error/status handling, validated incumbents, valid facility-count cuts, a continuous fixed-layout baseline, regression checks and fresh evidence. All source/config hashes and the source commit are recorded for Sarah's integration.

Limits: the model optimises only 80 source-derived depot candidates and eight refinery candidates. Land eligibility is assumed; it does not prove an optimum over all Kalimantan. Great-circle x1.3 distances and the entire TRK barge link are proxies without actual roads, port routing or transfer costs. Annual continuous flows and truck equivalents do not represent dispatch plans. No upstream procurement, inventory, carbon benefits or emissions savings are modelled.

No solver blockers remain for the agreed scenarios. UI integration and live Claude behaviour are outside these solver measurements. Keep cached evidence labelled and compare only matching scenarios.

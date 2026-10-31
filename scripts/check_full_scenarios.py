"""Check solver contracts and record full-data evidence without API calls.

Run from any directory. ``--checks-only`` skips full solves and writes no files;
``--output-dir`` keeps experimental evidence separate from the committed docs.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
from importlib.metadata import version
import json
import math
from pathlib import Path
import platform
import subprocess
import sys
from unittest.mock import patch
import uuid

import numpy as np

P = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(P))

from saf import optimizer
from saf.baseline import run_baseline
from saf.data import load_bundle
from saf.validation import validate_solution


def require(condition, message):
    """Keep checks active even when Python is invoked with -O."""
    if not condition:
        raise AssertionError(message)


def check_failure(result, status, scenario):
    require(result['status'] == status, f"Expected {status}: {result}")
    require(result['scenario_id'] == scenario['scenario_id'], 'Stale scenario ID')
    require(result['mip_gap'] is None, 'Failure must have a null gap')
    for field in ('facilities', 'flows', 'deliveries_t_per_year', 'costs'):
        require(not result[field], f'Failure contains stale {field}')
    require(math.isfinite(result['runtime_s']) and result['runtime_s'] >= 0,
            'Invalid measured runtime')
    json.dumps(result, allow_nan=False)


def check_valid(bundle, scenario, result):
    validation = validate_solution(bundle, scenario, result)
    require(validation['valid'], f"Independent validation failed: {validation['errors']}")
    json.dumps(result, allow_nan=False)
    return validation


def run_regression_checks():
    """Exercise real fixture solves and controlled backend failure paths."""
    bundle = json.loads((P / 'mocks/bundle.json').read_text(encoding='utf-8'))
    scenario = json.loads((P / 'mocks/scenario.json').read_text(encoding='utf-8'))
    original_bundle, original_scenario = deepcopy(bundle), deepcopy(scenario)
    passed = []
    captured = {}
    backend = optimizer.milp

    def capture(*args, **kwargs):
        result = backend(*args, **kwargs)
        captured['result'] = deepcopy(result)
        captured['integrality'] = np.asarray(kwargs['integrality']).copy()
        return result

    with patch.object(optimizer, 'milp', side_effect=capture):
        result = optimizer.solve_scenario(bundle, scenario)
    check_valid(bundle, scenario, result)
    require(math.isclose(result['costs']['total_usd_per_year'], 48_258_300,
                         rel_tol=0, abs_tol=0.01), 'Fixture cost changed')
    require(any(e['to_id'] == 'TRK' and e['mode'] == 'barge'
                for e in result['flows']), 'TRK barge flow missing')
    require(all(t['to_id'] != 'TRK' for t in result['truck_trips']),
            'TRK incorrectly included in truck trips')
    passed.append('fixture_cost_balances_modes_and_trip_equivalents')

    baseline = run_baseline(bundle, scenario)
    check_valid(bundle, scenario, baseline)
    require({(f['candidate_id'], f['size']) for f in baseline['facilities']}
            == {('D1', 'small'), ('R1', 'large')}, 'Incorrect fixed fixture layout')
    require(all(e['from_id'] == 'S1' and e['to_id'] == 'D1'
                for e in baseline['flows'] if e['stage'] == 'source_depot'),
            'Baseline used another source\'s depot')
    passed.append('baseline_fixed_layout_and_own_depot')
    require(bundle == original_bundle and scenario == original_scenario,
            'Solver or baseline mutated caller inputs')
    passed.append('inputs_remain_unchanged')

    fixed_cases = [
        ('invalid_fixed_size', [{'candidate_id': 'D1', 'size': 'medium'}], 'error'),
        ('duplicate_fixed_id', [{'candidate_id': 'D1', 'size': 'small'},
                                {'candidate_id': 'D1', 'size': 'large'}], 'error'),
        ('unknown_fixed_id', [{'candidate_id': 'UNKNOWN', 'size': 'small'}], 'error'),
        ('empty_fixed_layout', [], 'infeasible'),
        ('unlisted_refinery_is_closed', [{'candidate_id': 'D1', 'size': 'small'}],
         'infeasible'),
    ]
    for name, fixed, status in fixed_cases:
        fixed_before = deepcopy(fixed)
        check_failure(optimizer.solve_scenario(bundle, scenario, fixed), status, scenario)
        require(fixed == fixed_before, f'{name} mutated fixed_facilities')
        passed.append(name)

    over_demand = deepcopy(scenario)
    over_demand['scenario_id'] += '-over-demand'
    over_demand['demand_t_per_year']['BPN'] += 1
    check_failure(optimizer.solve_scenario(bundle, over_demand), 'infeasible', over_demand)
    passed.append('supply_proof_and_fresh_failure_scenario')

    disconnected = deepcopy(bundle)
    disconnected['distances'] = [e for e in disconnected['distances']
                                 if e['to_id'] != 'BPN']
    check_failure(optimizer.solve_scenario(disconnected, scenario), 'infeasible', scenario)
    passed.append('disconnected_airport_is_infeasible')

    malformed = deepcopy(bundle)
    malformed['distances'][0]['from_id'] = 'UNKNOWN_SOURCE'
    check_failure(optimizer.solve_scenario(malformed, scenario), 'error', scenario)
    passed.append('malformed_topology_is_error')

    duplicate = deepcopy(bundle)
    duplicate['distances'].append(deepcopy(duplicate['distances'][0]))
    check_failure(optimizer.solve_scenario(duplicate, scenario), 'error', scenario)
    passed.append('duplicate_edge_is_error')

    bad_cost = deepcopy(bundle)
    bad_cost['facility_options']['depot']['small']['capex_usd'] = float('inf')
    check_failure(optimizer.solve_scenario(bad_cost, scenario), 'error', scenario)
    passed.append('nonfinite_cost_is_error')

    bad_demand = deepcopy(scenario)
    bad_demand['demand_t_per_year']['BPN'] = float('nan')
    check_failure(optimizer.solve_scenario(bundle, bad_demand), 'error', bad_demand)
    passed.append('nonfinite_demand_is_error')

    bad_demand_shape = deepcopy(scenario)
    bad_demand_shape['demand_t_per_year'] = list(scenario['demand_t_per_year'])
    check_failure(optimizer.solve_scenario(bundle, bad_demand_shape), 'error', bad_demand_shape)
    passed.append('malformed_demand_container_is_error')

    for field, value in [('annualisation_years', 0),
                         ('solver_time_limit_s', float('nan'))]:
        invalid = deepcopy(scenario)
        invalid[field] = value
        check_failure(optimizer.solve_scenario(bundle, invalid), 'error', invalid)
        passed.append(f'invalid_{field}_is_error')

    missing_depot = deepcopy(bundle)
    missing_depot['candidates'] = [r for r in missing_depot['candidates']
                                    if r['candidate_id'] != 'D1']
    check_failure(run_baseline(missing_depot, scenario), 'error', scenario)
    passed.append('baseline_missing_own_depot_is_error')

    duplicate_site = deepcopy(bundle)
    duplicate_site['candidates'].append(deepcopy(duplicate_site['candidates'][0]))
    check_failure(run_baseline(duplicate_site, scenario), 'error', scenario)
    passed.append('baseline_duplicate_site_is_error')

    for status, expected in [(1, 'no_solution'), (2, 'infeasible'),
                             (3, 'error'), (4, 'error')]:
        stopped = deepcopy(captured['result'])
        stopped.update(status=status, x=None, mip_gap=None,
                       message=f'Simulated backend status {status}')
        with patch.object(optimizer, 'milp', return_value=stopped):
            check_failure(optimizer.solve_scenario(bundle, scenario), expected, scenario)
        passed.append(f'backend_status_{status}_without_incumbent')

    for status, gap in [(1, 0.01), (0, 1e-12)]:
        incumbent = deepcopy(captured['result'])
        incumbent.update(status=status, mip_gap=gap, message='Simulated valid incumbent')
        with patch.object(optimizer, 'milp', return_value=incumbent):
            feasible = optimizer.solve_scenario(bundle, scenario)
        check_valid(bundle, scenario, feasible)
        require(feasible['status'] == 'feasible' and feasible['mip_gap'] == gap,
                'Positive gap incorrectly reported as an exact optimum')
        passed.append(f'positive_gap_{gap:g}_remains_feasible')

    invalid_gap = deepcopy(captured['result'])
    invalid_gap.mip_gap = float('nan')
    with patch.object(optimizer, 'milp', return_value=invalid_gap):
        check_failure(optimizer.solve_scenario(bundle, scenario), 'error', scenario)
    passed.append('nonfinite_gap_is_error')

    binary_index = int(np.flatnonzero(captured['integrality'])[0])
    continuous_index = int(np.flatnonzero(
        (captured['integrality'] == 0) & (captured['result'].x > 0))[0])
    for name, index, value in [
        ('nonfinite_incumbent', continuous_index, float('nan')),
        ('infeasible_incumbent', continuous_index,
         float(captured['result'].x[continuous_index]) + 1),
        ('fractional_binary_incumbent', binary_index, 0.5),
    ]:
        invalid = deepcopy(captured['result'])
        invalid.x[index] = value
        with patch.object(optimizer, 'milp', return_value=invalid):
            check_failure(optimizer.solve_scenario(bundle, scenario), 'error', scenario)
        passed.append(name)

    with patch.object(optimizer, 'milp', side_effect=RuntimeError('Simulated backend failure')):
        check_failure(optimizer.solve_scenario(bundle, scenario), 'error', scenario)
    passed.append('backend_exception_is_error')
    require(bundle == original_bundle and scenario == original_scenario,
            'A failure path mutated caller inputs')
    return passed


def source_hashes():
    files = [P / 'saf' / name for name in
             ('optimizer.py', 'baseline.py', 'data.py', 'validation.py', 'contracts.py')]
    files.extend([Path(__file__).resolve(), P / 'requirements.txt',
                  P / 'tests/test_contract_fixtures.py'])
    for folder in ('config', 'data/raw', 'data/processed', 'mocks'):
        files.extend(path for path in (P / folder).iterdir() if path.is_file())
    return {path.relative_to(P).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(set(files))}


def scenario_proof(bundle, scenario):
    supply = sum(s['supply_t_per_year'] for s in bundle['sources'])
    demand = sum(scenario['demand_t_per_year'].values())
    depots = [r for r in bundle['candidates'] if r['kind'] == 'depot']
    refineries = [r for r in bundle['candidates'] if r['kind'] == 'refinery']
    depot_capacity = bundle['facility_options']['depot']['small']['capacity_t_per_year']
    refinery_capacity = bundle['facility_options']['refinery']['large']['capacity_t_per_year']
    refinery_intake = demand / scenario['refinery_yield']
    source_intake = refinery_intake / scenario['depot_yield']
    maximum_saf = supply * scenario['depot_yield'] * scenario['refinery_yield']
    return dict(
        source_count=len(bundle['sources']), depot_candidates=len(depots),
        refinery_candidates=len(refineries), supply_t_per_year=supply,
        demand_t_per_year=demand, maximum_saf_from_supply_t_per_year=maximum_saf,
        required_source_biomass_t_per_year=source_intake,
        required_refinery_intake_t_per_year=refinery_intake,
        demand_exceeds_supply_limit=demand > maximum_saf + 1e-6,
        baseline_depot_intake_capacity_t_per_year=len(depots) * depot_capacity,
        each_source_fits_small_depot=all(s['supply_t_per_year'] <= depot_capacity
                                       for s in bundle['sources']),
        baseline_refinery_intake_capacity_t_per_year=len(refineries) * refinery_capacity,
        minimum_refineries_at_large_capacity=math.ceil(refinery_intake / refinery_capacity),
    )


def check_baseline_rules(bundle, result):
    expected = {(r['candidate_id'], 'small' if r['kind'] == 'depot' else 'large')
                for r in bundle['candidates']}
    own_links = all(e['to_id'] == 'D_' + e['from_id']
                    for e in result['flows'] if e['stage'] == 'source_depot')
    layout = {(f['candidate_id'], f['size']) for f in result['facilities']} == expected
    require(own_links and layout, 'Full baseline violates the fixed source-depot layout')
    return dict(all_small_depots_and_large_refineries_open=layout,
                source_depot_links_are_own_source_only=own_links)


def write_json(path, content):
    path.write_text(json.dumps(content, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def run_full_scenarios(output_dir, checks):
    started = datetime.now(timezone(timedelta(hours=8), 'Asia/Singapore'))
    run_id = started.strftime('%Y%m%dT%H%M%S%z') + '-' + uuid.uuid4().hex[:8]
    metadata = dict(
        run_id=run_id, started_at=started.isoformat(), timezone='Asia/Singapore',
        python=platform.python_version(), platform=platform.platform(),
        packages={name: version(name) for name in ('numpy', 'scipy')},
        source_sha256=source_hashes(), regression_checks=checks,
        regression_pass_count=len(checks), comparisons=[], scenario_proofs={},
        note='Measured local solver runs. No Claude/API calls. Saved results are replays when loaded later.',
    )
    for key, arguments in [('code_commit', ['rev-parse', 'HEAD']),
                           ('working_tree_dirty', ['status', '--porcelain'])]:
        try:
            value = subprocess.run(['git', *arguments], cwd=P, check=True,
                                   capture_output=True, text=True).stdout.strip()
            metadata[key] = bool(value) if key == 'working_tree_dirty' else value
        except (OSError, subprocess.CalledProcessError):
            metadata[key] = None
    rows, evidence = [], []
    for name in ('assumptions_full', 'assumptions_full_bpn20', 'assumptions_full_infeasible'):
        bundle, scenario = load_bundle(str(P / 'data/processed'),
                                       str(P / 'config' / f'{name}.json'))
        before = deepcopy(bundle), deepcopy(scenario)
        proof = scenario_proof(bundle, scenario)
        require(proof['source_count'] == 80 and proof['depot_candidates'] == 80
                and proof['refinery_candidates'] == 8,
                'Full data no longer matches the agreed 80-source/eight-refinery baseline')
        metadata['scenario_proofs'][scenario['scenario_id']] = proof
        coordinates = {r['candidate_id']: r for r in bundle['candidates']}
        pair = {}
        for method, solve in (('baseline', run_baseline), ('milp', optimizer.solve_scenario)):
            result = solve(bundle, scenario)
            validation = validate_solution(bundle, scenario, result)
            rules = None
            if name == 'assumptions_full_infeasible':
                require(proof['demand_exceeds_supply_limit'], 'Missing infeasibility proof')
                check_failure(result, 'infeasible', scenario)
                require(not validation['valid'], 'Infeasible result unexpectedly validates')
            else:
                require(validation['valid'],
                        f"{name}/{method}: independent validation failed: {validation['errors']}")
                if method == 'baseline':
                    rules = check_baseline_rules(bundle, result)
            require(bundle == before[0] and scenario == before[1], 'Full solve mutated inputs')
            json.dumps(result, allow_nan=False)
            summary = dict(
                scenario=scenario['scenario_id'], method=method, status=result['status'],
                runtime_s=result['runtime_s'], mip_gap=result['mip_gap'],
                valid=validation['valid'], costs=result['costs'],
                facilities=len(result['facilities']),
            )
            rows.append(summary)
            pair[method] = summary
            evidence.append((f'{name}_{method}.json', dict(
                scenario=scenario, result=result, validation=validation, run_id=run_id,
                baseline_rule_checks=rules, demand_capacity_proof=proof,
                facility_coordinates=[dict(candidate_id=f['candidate_id'],
                                           latitude=coordinates[f['candidate_id']]['latitude'],
                                           longitude=coordinates[f['candidate_id']]['longitude'])
                                      for f in result['facilities']],
            )))
            print(json.dumps(summary, allow_nan=False), flush=True)
        if all(pair[method]['valid'] for method in pair):
            baseline_cost = pair['baseline']['costs']['total_usd_per_year']
            milp_cost = pair['milp']['costs']['total_usd_per_year']
            saving = baseline_cost - milp_cost
            metadata['comparisons'].append(dict(
                scenario=scenario['scenario_id'], baseline_usd_per_year=baseline_cost,
                milp_usd_per_year=milp_cost, saving_usd_per_year=saving,
                saving_percent=100 * saving / baseline_cost,
                note='Same-scenario fixed baseline comparison; positive MIP gap is not an exact optimum.',
            ))

    metadata['completed_at'] = datetime.now(
        timezone(timedelta(hours=8), 'Asia/Singapore')).isoformat()
    # Validate serialization before replacing any existing evidence files.
    for _, content in evidence:
        json.dumps(content, allow_nan=False)
    json.dumps(rows, allow_nan=False)
    json.dumps(metadata, allow_nan=False)
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, content in evidence:
        write_json(output_dir / name, content)
    write_json(output_dir / 'run_results.json', rows)
    write_json(output_dir / 'solver_run_metadata.json', metadata)
    print(json.dumps(dict(run_id=run_id, output_dir=str(output_dir),
                          comparisons=metadata['comparisons']), allow_nan=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checks-only', action='store_true',
                        help='Run quick solver regressions without full solves or evidence writes.')
    parser.add_argument('--output-dir', type=Path, default=P / 'docs',
                        help='Evidence directory; defaults to repository docs/.')
    args = parser.parse_args()
    checks = run_regression_checks()
    print(json.dumps(dict(regression_pass_count=len(checks), regression_checks=checks)), flush=True)
    if not args.checks_only:
        run_full_scenarios(args.output_dir.resolve(), checks)


if __name__ == '__main__':
    main()

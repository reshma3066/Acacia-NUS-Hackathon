"""Fixed-layout comparison using the same costs, capacities and solver as MILP."""
from copy import deepcopy
import time

from .contracts import Bundle, Scenario, Result
from .optimizer import _check_inputs, _failure, solve_scenario

def run_baseline(bundle: Bundle, scenario: Scenario) -> Result:
    """Open each source's small depot and every large refinery; solve flows only.

    Full data has 80 depots and eight refineries. The synthetic one-source
    fixture uses its agreed S1 -> D1 naming exception. Inputs remain read-only.
    """
    started = time.perf_counter()
    try:
        # Validate before filtering so malformed cross-source links cannot vanish.
        _check_inputs(bundle, scenario, None)
        depots = {r['candidate_id'] for r in bundle['candidates'] if r['kind'] == 'depot'}
        own_depot = {}
        for source in bundle['sources']:
            sid = source['source_id']
            candidates = {'D_' + sid} & depots
            if sid == 'S1' and 'D1' in depots:
                candidates.add('D1')
            if len(candidates) != 1:
                raise ValueError(f'Baseline requires exactly one own depot for {sid}')
            own_depot[sid] = candidates.pop()
        if set(own_depot.values()) != depots:
            raise ValueError('Baseline depot candidates must match source-owned depots')
        b = deepcopy(bundle)
        b['distances'] = [e for e in b['distances']
                          if e['stage'] != 'source_depot'
                          or e['to_id'] == own_depot[e['from_id']]]
        fixed = [dict(candidate_id=r['candidate_id'],
                      size='small' if r['kind'] == 'depot' else 'large')
                 for r in b['candidates']]
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        return _failure(scenario, started, 'error', f'Invalid baseline inputs: {exc}')
    result = solve_scenario(b, scenario, fixed)
    # Include copy/filter/validation overhead in the measured baseline runtime.
    result['runtime_s'] = time.perf_counter() - started
    return result

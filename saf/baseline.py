from copy import deepcopy
from .contracts import Bundle,Scenario,Result
from .optimizer import solve_scenario

def run_baseline(bundle: Bundle, scenario: Scenario) -> Result:
    b=deepcopy(bundle)
    # One depot at each source, all eight refinery candidates. Flows only.
    b['distances']=[e for e in b['distances'] if e['stage']!='source_depot' or e['to_id']=='D_'+e['from_id'] or (e['from_id']=='S1' and e['to_id']=='D1')]
    fixed=[dict(candidate_id=r['candidate_id'],size='small' if r['kind']=='depot' else 'large') for r in b['candidates']]
    return solve_scenario(b,scenario,fixed)

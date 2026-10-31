import math,uuid
from copy import deepcopy
from .contracts import Bundle,Scenario,Result,Validation,Patch
from .agent import parse_request,explain_result
from .optimizer import solve_scenario
from .validation import validate_solution

def apply_patch(scenario: Scenario, patch: Patch) -> Scenario:
    if patch['status']!='ready' or not isinstance(patch['changes'],list) or not patch['changes']:raise ValueError('Patch is not ready')
    c=deepcopy(scenario);seen=set()
    for change in patch['changes']:
        if set(change)!={'airport_id','new_demand_t_per_year'}:raise ValueError('Only demand changes allowed')
        a=change['airport_id'];v=change['new_demand_t_per_year']
        if a not in c['demand_t_per_year'] or a in seen or isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<0:raise ValueError('Invalid airport or demand')
        c['demand_t_per_year'][a]=v;seen.add(a)
    c['scenario_id']=scenario['scenario_id']+'-'+uuid.uuid4().hex[:8]
    return c

def run_scenario(bundle: Bundle, scenario: Scenario,
                 request: str | None = None) -> dict:
    c=deepcopy(scenario)
    if request:
        try:
            p=parse_request(request,c)
            if p['status']!='ready':return dict(scenario=c,result=None,validation=None,explanation='',clarification=p['question'] or 'Only airport demand changes are supported.')
            c=apply_patch(c,p)
        except Exception as e:
            return dict(scenario=c,result=None,validation=None,explanation='Claude request failed: '+type(e).__name__,clarification='No scenario changed. Check API setup or enter demand explicitly.')
    r=solve_scenario(bundle,c);v=validate_solution(bundle,c,r)
    return dict(scenario=c,result=r,validation=v,explanation=explain_result(c,r,v),clarification=None)

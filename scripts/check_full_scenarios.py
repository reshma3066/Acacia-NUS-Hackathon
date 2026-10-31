"""Run from repository root. No API calls. Writes reproducible solver evidence."""
import sys,json
from pathlib import Path
P=Path(__file__).resolve().parents[1];sys.path.insert(0,str(P))
from saf.data import load_bundle
from saf.optimizer import solve_scenario
from saf.baseline import run_baseline
from saf.validation import validate_solution
rows=[]
for name in ['assumptions_full','assumptions_full_bpn20','assumptions_full_infeasible']:
 b,c=load_bundle(str(P/'data/processed'),str(P/'config'/f'{name}.json'))
 for kind,fn in [('baseline',run_baseline),('milp',solve_scenario)]:
  r=fn(b,c);v=validate_solution(b,c,r)
  if name!='assumptions_full_infeasible':assert v['valid'],v['errors']
  else:assert r['status']=='infeasible'
  (P/'docs'/f'{name}_{kind}.json').write_text(json.dumps(dict(scenario=c,result=r,validation=v),indent=2))
  summary=dict(scenario=c['scenario_id'],method=kind,status=r['status'],runtime_s=r['runtime_s'],mip_gap=r['mip_gap'],valid=v['valid'],costs=r['costs'],facilities=len(r['facilities']))
  rows.append(summary);print(json.dumps(summary),flush=True)
(P/'docs/run_results.json').write_text(json.dumps(rows,indent=2))

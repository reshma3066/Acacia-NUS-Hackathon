import json,inspect,copy
from pathlib import Path
import pytest
from saf import data,optimizer,baseline,validation,service,agent
from app import render_dashboard
P=Path(__file__).resolve().parents[1]
def j(n):return json.loads((P/n).read_text())
def test_fixture():
 b,c,r=j('mocks/bundle.json'),j('mocks/scenario.json'),j('mocks/result.json')
 assert validation.validate_solution(b,c,r)['valid']
 assert r['costs']['total_usd_per_year']==48258300
 assert sum(c['demand_t_per_year'].values())==100
 assert r['facilities'][1]['input_t_per_year']==500
 assert all(t['to_id']!='TRK' for t in r['truck_trips'])
def test_reject_bad_result():
 b,c,r=j('mocks/bundle.json'),j('mocks/scenario.json'),j('mocks/result.json')
 r['costs']['total_usd_per_year']+=1000
 assert not validation.validate_solution(b,c,r)['valid']
 r=j('mocks/result.json');r['flows'][-1]['mode']='truck'
 assert not validation.validate_solution(b,c,r)['valid']
def test_signatures():
 expected=[(data.load_bundle,['data_dir','config_path']), (data.build_distances,['bundle','scenario']), (validation.validate_solution,['bundle','scenario','result']), (optimizer.solve_scenario,['bundle','scenario','fixed_facilities']), (baseline.run_baseline,['bundle','scenario']), (agent.parse_request,['text','scenario']), (agent.explain_result,['scenario','result','validation']), (service.apply_patch,['scenario','patch']), (service.run_scenario,['bundle','scenario','request']), (render_dashboard,['response','baseline'])]
 for fn,names in expected:assert list(inspect.signature(fn).parameters)==names
 assert inspect.signature(optimizer.solve_scenario).parameters['fixed_facilities'].default is None
 assert inspect.signature(service.run_scenario).parameters['request'].default is None
def test_service_and_patch():
 assert set(j('mocks/service_response.json'))=={'scenario','result','validation','explanation','clarification'}
 c=j('mocks/scenario.json');n=service.apply_patch(c,j('mocks/patch.json'))
 assert n['demand_t_per_year']['BPN']==30 and c['demand_t_per_year']['BPN']==25
 with pytest.raises(ValueError):service.apply_patch(c,dict(status='ready',changes=[dict(airport_id='XXX',new_demand_t_per_year=1)]))
def test_full_capacity():
 b,c=data.load_bundle(str(P/'data/processed'),str(P/'config/assumptions_full.json'))
 assert sum(s['supply_t_per_year'] for s in b['sources'])==6800000
 assert max(s['supply_t_per_year'] for s in b['sources'])<150000
 assert len({s['candidate_id'] for s in b['candidates'] if s['kind']=='refinery'})==8
 for name,feed in [('assumptions_full',6000000),('assumptions_full_bpn20',6300000)]:
  c=j('config/'+name+'.json');assert sum(c['demand_t_per_year'].values())/.2==feed
  assert feed/8<1087000
 c=j('config/assumptions_full_infeasible.json');assert optimizer.solve_scenario(b,c)['status']=='infeasible'
def test_tiny_solver():
 b,c=j('mocks/bundle.json'),j('mocks/scenario.json');r=optimizer.solve_scenario(b,c)
 assert validation.validate_solution(b,c,r)['valid']
 assert r['costs']['total_usd_per_year']==pytest.approx(48258300)

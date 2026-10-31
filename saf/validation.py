"""Independent recomputation from returned flows, not solver variables."""
import math
from .contracts import Bundle,Scenario,Result,Validation

def validate_solution(bundle: Bundle, scenario: Scenario,
                      result: Result) -> Validation:
    checks=[]
    def check(n,ok,detail=''):checks.append(dict(name=n,passed=bool(ok),detail=detail))
    def close(a,b):return math.isfinite(float(a)) and abs(a-b)<=max(.01,abs(b)*1e-7)
    check('status',result.get('status') in ['optimal','feasible'],'Only a solution with flows is valid.')
    check('scenario',result.get('scenario_id')==scenario['scenario_id'])
    if not checks[0]['passed']:return dict(valid=False,checks=checks,errors=['No feasible solution to validate'])
    try:
        sources={x['source_id']:x for x in bundle['sources']};candidates={x['candidate_id']:x for x in bundle['candidates']};dist={(x['from_id'],x['to_id'],x['stage']):x['distance_km'] for x in bundle['distances']};opened={x['candidate_id']:x for x in result['facilities']};inc={};out={};transport=0.;seen=set()
        check('unique_facilities',len(opened)==len(result['facilities']))
        for e in result['flows']:
            a,b,stage,t=e['from_id'],e['to_id'],e['stage'],e['tonnes_per_year'];key=(a,b,stage)
            check('edge '+str(key),key in dist and key not in seen and math.isfinite(t) and t>=0)
            seen.add(key);inc[b]=inc.get(b,0)+t;out[a]=out.get(a,0)+t
            check('mode '+str(key),e.get('mode')==('barge' if stage=='refinery_airport' and b=='TRK' else 'truck'))
            transport+=t*dist[key]*scenario['transport_usd_per_t_km'][stage]
        for sid,s in sources.items():check('supply '+sid,out.get(sid,0)<=s['supply_t_per_year']+.01)
        capex=fix=var=0.
        for cid,r in candidates.items():
            if cid not in opened:check('closed '+cid,inc.get(cid,0)<.01 and out.get(cid,0)<.01);continue
            f=opened[cid];o=bundle['facility_options'][r['kind']][f['size']];t=inc.get(cid,0);y=scenario['depot_yield'] if r['kind']=='depot' else scenario['refinery_yield']
            check('kind '+cid,f['kind']==r['kind']);check('capacity '+cid,t<=o['capacity_t_per_year']+.01);check('balance '+cid,close(out.get(cid,0),t*y));check('reported intake '+cid,close(f['input_t_per_year'],t));check('reported output '+cid,close(f['output_t_per_year'],t*y))
            capex+=o['capex_usd'];fix+=o['fixed_opex_usd_per_year'];var+=t*o['variable_opex_usd_per_tonne_in']
        check('known facilities',set(opened)<=set(candidates))
        for a,d in scenario['demand_t_per_year'].items():
            check('demand '+a,close(inc.get(a,0),d));check('reported delivery '+a,close(result['deliveries_t_per_year'][a],inc.get(a,0)))
        expected=dict(capex_usd=capex,annualised_capex_usd_per_year=capex/scenario['annualisation_years'],fixed_opex_usd_per_year=fix,variable_opex_usd_per_year=var,opex_usd_per_year=fix+var,transport_usd_per_year=transport,total_usd_per_year=capex/scenario['annualisation_years']+fix+var+transport)
        for k,v in expected.items():check('cost '+k,close(result['costs'][k],v))
        if 'truck_trips' in result:
            truck_edges={(e['from_id'],e['to_id'],e['stage']):e for e in result['flows'] if e['mode']=='truck'}
            trips=result['truck_trips'];check('truck coverage',len(trips)==len(truck_edges) and {(t['from_id'],t['to_id'],t['stage']) for t in trips}==set(truck_edges))
            for t in trips:
                key=(t['from_id'],t['to_id'],t['stage']);e=truck_edges[key];a,b={'source_depot':(3,9),'depot_refinery':(18,30),'refinery_airport':(16,32)}[e['stage']]
                check('truck payload '+str(key),close(t['small_trip_equivalents_per_year'],e['tonnes_per_year']/a) and close(t['large_trip_equivalents_per_year'],e['tonnes_per_year']/b))
    except (KeyError,TypeError,ValueError,OverflowError) as e:check('schema',False,str(e))
    return dict(valid=all(c['passed'] for c in checks),checks=checks,errors=[c['name']+': '+c['detail'] for c in checks if not c['passed']])

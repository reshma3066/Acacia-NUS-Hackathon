"""Reference candidate-site MILP. Reshma owns refinement and evaluation.
Internal units kt/year and million USD/year; external contracts tonnes/USD.
"""
import math
import time
from numbers import Real
import numpy as np
from scipy.optimize import milp,Bounds,LinearConstraint
from scipy.sparse import coo_matrix
from .contracts import Bundle,Scenario,Result
from .validation import validate_solution


def _number(value, name, *, positive=False):
    if (isinstance(value, bool) or not isinstance(value, Real)
            or not math.isfinite(value) or value < 0
            or (positive and value == 0)):
        raise ValueError(f'{name} must be a finite {"positive" if positive else "nonnegative"} number')


def _check_inputs(bundle, scenario, fixed_facilities):
    """Reject malformed inputs before they can masquerade as infeasibility."""
    if not isinstance(bundle, dict) or not isinstance(scenario, dict):
        raise ValueError('Bundle and Scenario must be dictionaries')
    if scenario['schema_version'] != '2.0':
        raise ValueError('Expected Scenario schema_version 2.0')
    if not isinstance(scenario['scenario_id'], str) or not scenario['scenario_id']:
        raise ValueError('scenario_id must be a nonempty string')
    _number(scenario['period_years'], 'period_years', positive=True)
    _number(scenario['discount_rate'], 'discount_rate')
    if (scenario['period_years'] != 1 or scenario['discount_rate'] != 0
            or scenario['use_all_supply'] is not False):
        raise ValueError('The v2 model requires one year, no discounting and optional supply use')
    for name in ['depot_yield', 'refinery_yield', 'annualisation_years']:
        _number(scenario[name], name, positive=True)
    if scenario['depot_yield'] > 1 or scenario['refinery_yield'] > 1:
        raise ValueError('Mass yields cannot exceed one')
    for name in ['solver_time_limit_s', 'solver_rel_gap']:
        _number(scenario[name], name)

    def index(rows, key):
        ids = [row[key] for row in rows]
        if any(not isinstance(cid, str) or not cid for cid in ids):
            raise ValueError(f'Invalid {key}')
        if len(set(ids)) != len(ids):
            raise ValueError(f'Duplicate {key}')
        return {row[key]: row for row in rows}

    sources = index(bundle['sources'], 'source_id')
    sites = index(bundle['candidates'], 'candidate_id')
    airports = index(bundle['airports'], 'airport_id')
    if not sources or not sites or not airports:
        raise ValueError('Sources, candidates and airports must be nonempty')
    if set(sources) & set(sites) or set(sources) & set(airports) or set(sites) & set(airports):
        raise ValueError('Source, candidate and airport IDs must be distinct')
    if not isinstance(scenario['demand_t_per_year'], dict):
        raise ValueError('demand_t_per_year must be a dictionary')
    if set(scenario['demand_t_per_year']) != set(airports):
        raise ValueError('Demand must specify every known airport exactly once')
    for cid, row in sources.items():
        _number(row['supply_t_per_year'], f'supply {cid}')
    for cid, demand in scenario['demand_t_per_year'].items():
        _number(demand, f'demand {cid}')
    for row in sites.values():
        if row['kind'] not in ('depot', 'refinery'):
            raise ValueError('Unknown candidate kind')
    for kind in ('depot', 'refinery'):
        for size in ('small', 'large'):
            option = bundle['facility_options'][kind][size]
            _number(option['capacity_t_per_year'], f'{kind}.{size} capacity', positive=True)
            for name in ('capex_usd', 'fixed_opex_usd_per_year', 'variable_opex_usd_per_tonne_in'):
                _number(option[name], f'{kind}.{size} {name}')
    depots = {cid for cid, row in sites.items() if row['kind'] == 'depot'}
    refineries = set(sites) - depots
    allowed = {'source_depot': (set(sources), depots),
               'depot_refinery': (depots, refineries),
               'refinery_airport': (refineries, set(airports))}
    for stage in allowed:
        _number(scenario['transport_usd_per_t_km'][stage], f'transport rate {stage}')
    seen = set()
    for edge in bundle['distances']:
        key = (edge['from_id'], edge['to_id'], edge['stage'])
        if key in seen or edge['stage'] not in allowed:
            raise ValueError('Duplicate edge or unknown transport stage')
        left, right = allowed[edge['stage']]
        if edge['from_id'] not in left or edge['to_id'] not in right:
            raise ValueError(f'Invalid stage endpoints: {key}')
        _number(edge['distance_km'], f'distance {key}')
        seen.add(key)
    if fixed_facilities is not None:
        if not isinstance(fixed_facilities, list):
            raise ValueError('fixed_facilities must be a list or None')
        fixed = index(fixed_facilities, 'candidate_id')
        if set(fixed) - set(sites):
            raise ValueError('Unknown fixed_facilities ID')
        if any(row['size'] not in ('small', 'large') for row in fixed.values()):
            raise ValueError('Invalid fixed_facilities size')


def _failure(scenario, started, status, message):
    scenario_id = scenario.get('scenario_id', 'invalid-scenario') if isinstance(scenario, dict) else 'invalid-scenario'
    if not isinstance(scenario_id, str):
        scenario_id = 'invalid-scenario'
    return dict(schema_version='2.0', scenario_id=scenario_id, provenance='solver',
                status=status, runtime_s=time.perf_counter()-started, mip_gap=None,
                message=message, facilities=[], flows=[], deliveries_t_per_year={}, costs={})

def solve_scenario(bundle: Bundle, scenario: Scenario,
                   fixed_facilities: list[dict] | None = None) -> Result:
    """Solve the existing size-choice MILP; never return unchecked incumbents.

    A fixed list is a complete layout: every unlisted candidate stays closed.
    Neither the Bundle nor Scenario is modified.
    """
    started = time.perf_counter()
    try:
        _check_inputs(bundle, scenario, fixed_facilities)
        return _solve_model(bundle, scenario, fixed_facilities, started)
    except (KeyError, TypeError, ValueError, OverflowError, ArithmeticError) as exc:
        return _failure(scenario, started, 'error', f'Invalid model input or result: {exc}')


def _solve_model(bundle, scenario, fixed_facilities, started):
    empty=_failure(scenario, started, 'no_solution', '')
    def fail(status,message):
        return _failure(scenario, started, status, message)
    supply=sum(s['supply_t_per_year'] for s in bundle['sources'])
    demand=sum(scenario['demand_t_per_year'].values())
    _number(supply, 'total supply'); _number(demand, 'total demand')
    available=supply*scenario['depot_yield']*scenario['refinery_yield']
    if demand>available+1e-6:
        return fail('infeasible',f'Demand {demand:,.3f} t/year exceeds feedstock-based SAF limit {available:,.3f} t/year; no feasible flows.')
    edges=bundle['distances']; sites=bundle['candidates']; opts=bundle['facility_options']; nf=len(edges)
    choices=[(r,s) for r in sites for s in ['small','large']]; nc=len(choices); nv=nf+2*nc
    cost=np.zeros(nv);integrality=np.zeros(nv);lo=np.zeros(nv);hi=np.full(nv,np.inf)
    for k,e in enumerate(edges):cost[k]=e['distance_km']*scenario['transport_usd_per_t_km'][e['stage']]/1000
    fixed=None if fixed_facilities is None else {f['candidate_id']:f['size'] for f in fixed_facilities}
    for j,(r,s) in enumerate(choices):
        o=opts[r['kind']][s];q=nf+j;y=nf+nc+j
        cost[q]=o['variable_opex_usd_per_tonne_in']/1000
        cost[y]=(o['capex_usd']/scenario['annualisation_years']+o['fixed_opex_usd_per_year'])/1e6
        # A fixed baseline is a continuous flow problem, with opening costs retained.
        integrality[y]=int(fixed is None);hi[y]=1
        if fixed is not None:lo[y]=hi[y]=int(fixed.get(r['candidate_id'])==s)
    rows=[];cols=[];values=[];lower=[];upper=[]
    def add(terms,l=-np.inf,u=np.inf):
        idx=len(lower)
        for col,val in terms.items():rows.append(idx);cols.append(col);values.append(val)
        lower.append(l);upper.append(u)
    incoming={};outgoing={}
    for k,e in enumerate(edges):incoming.setdefault(e['to_id'],[]).append(k);outgoing.setdefault(e['from_id'],[]).append(k)
    for s in bundle['sources']:add({k:1 for k in outgoing.get(s['source_id'],[])},u=s['supply_t_per_year']/1000)
    for r in sites:
        cid=r['candidate_id'];js=[j for j,(rr,ss) in enumerate(choices) if rr['candidate_id']==cid]
        add({nf+nc+j:1 for j in js},u=1)
        terms={k:1 for k in incoming.get(cid,[])};terms.update({nf+j:-1 for j in js});add(terms,0,0)
        terms={k:1 for k in outgoing.get(cid,[])};yield_=scenario['depot_yield'] if r['kind']=='depot' else scenario['refinery_yield'];terms.update({nf+j:-yield_ for j in js});add(terms,0,0)
        for j in js:
            o=opts[r['kind']][choices[j][1]];add({nf+j:1,nf+nc+j:-o['capacity_t_per_year']/1000},u=0)
    for a,d in scenario['demand_t_per_year'].items():add({k:1 for k in incoming.get(a,[])},d/1000,d/1000)
    # Valid count cuts strengthen the relaxation without excluding any integer layout.
    # Both full feasible cases need at least six of the eight refinery candidates.
    for kind,required in [('refinery', demand/scenario['refinery_yield']),
                          ('depot', demand/scenario['refinery_yield']/scenario['depot_yield'])]:
        js=[j for j,(r,s) in enumerate(choices) if r['kind']==kind]
        capacity=max(opts[kind][s]['capacity_t_per_year'] for s in ('small','large'))
        add({nf+nc+j:1 for j in js},l=max(0,math.ceil(required/capacity-1e-9)))
    A=coo_matrix((values,(rows,cols)),shape=(len(lower),nv)).tocsc()
    try:sol=milp(cost,integrality=integrality,bounds=Bounds(lo,hi),constraints=LinearConstraint(A,lower,upper),options={'time_limit':scenario['solver_time_limit_s'],'mip_rel_gap':scenario['solver_rel_gap']})
    except Exception as e:return fail('error',str(e))
    if sol.status==2:return fail('infeasible',str(sol.message))
    if sol.status not in (0,1):return fail('error',str(sol.message))
    if sol.x is None:
        return fail('no_solution' if sol.status==1 else 'error',str(sol.message))
    x=np.asarray(sol.x,dtype=float)
    if x.shape!=(nv,) or not np.all(np.isfinite(x)):
        return fail('error','Solver returned a malformed or nonfinite incumbent.')
    tolerance=1e-6  # kt = 0.001 tonnes; the independent output validator runs too.
    binary=x[nf+nc:]
    activity=A@x
    if (np.any(x<lo-tolerance) or np.any(x>hi+tolerance)
            or np.any(np.abs(binary-np.rint(binary))>tolerance)
            or np.any(activity<np.asarray(lower)-tolerance)
            or np.any(activity>np.asarray(upper)+tolerance)):
        return fail('error','Solver incumbent violates bounds, size choices or flow constraints.')
    gap=getattr(sol,'mip_gap',None)
    if gap is not None and (not math.isfinite(gap) or gap<0):
        return fail('error','Solver returned an invalid relative gap.')
    # HiGHS may omit MIP statistics for a continuous fixed-layout optimum.
    if fixed is not None and sol.status==0 and gap is None:gap=0.
    flows=[];fac=[];capex=fix=var=transport=0.
    for k,e in enumerate(edges):
        t=max(0,float(x[k])*1000)
        if t<1e-6:continue
        flows.append({z:e[z] for z in ['from_id','to_id','stage']}|dict(tonnes_per_year=t,mode='barge' if e['stage']=='refinery_airport' and e['to_id']=='TRK' else 'truck'))
        transport+=t*e['distance_km']*scenario['transport_usd_per_t_km'][e['stage']]
    for j,(r,s) in enumerate(choices):
        if x[nf+nc+j]<.5:continue
        o=opts[r['kind']][s];t=max(0,float(x[nf+j])*1000);yy=scenario['depot_yield'] if r['kind']=='depot' else scenario['refinery_yield']
        fac.append(dict(candidate_id=r['candidate_id'],kind=r['kind'],size=s,input_t_per_year=t,output_t_per_year=t*yy))
        capex+=o['capex_usd'];fix+=o['fixed_opex_usd_per_year'];var+=t*o['variable_opex_usd_per_tonne_in']
    costs=dict(capex_usd=capex,annualised_capex_usd_per_year=capex/scenario['annualisation_years'],fixed_opex_usd_per_year=fix,variable_opex_usd_per_year=var,opex_usd_per_year=fix+var,transport_usd_per_year=transport,total_usd_per_year=capex/scenario['annualisation_years']+fix+var+transport)
    trips=[]
    for e in flows:
        if e['mode']=='barge':continue
        a,b={'source_depot':(3,9),'depot_refinery':(18,30),'refinery_airport':(16,32)}[e['stage']]
        trips.append({k:e[k] for k in ['from_id','to_id','stage']}|dict(small_trip_equivalents_per_year=e['tonnes_per_year']/a,large_trip_equivalents_per_year=e['tonnes_per_year']/b))
    result=empty|dict(status='optimal' if sol.status==0 and gap==0 else 'feasible',mip_gap=None if gap is None else float(gap),message=str(sol.message)+' Candidate-set result; inspect mip_gap.',facilities=fac,flows=flows,deliveries_t_per_year={a:sum(e['tonnes_per_year'] for e in flows if e['to_id']==a) for a in scenario['demand_t_per_year']},costs=costs,truck_trips=trips)
    validation=validate_solution(bundle,scenario,result)
    if not validation['valid']:
        return fail('error','Incumbent failed independent validation: '+'; '.join(validation['errors']))
    result['runtime_s']=time.perf_counter()-started
    return result

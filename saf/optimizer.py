"""Reference candidate-site MILP. Reshma owns refinement and evaluation.
Internal units kt/year and million USD/year; external contracts tonnes/USD.
"""
import time
import numpy as np
from scipy.optimize import milp,Bounds,LinearConstraint
from scipy.sparse import coo_matrix
from .contracts import Bundle,Scenario,Result

def solve_scenario(bundle: Bundle, scenario: Scenario,
                   fixed_facilities: list[dict] | None = None) -> Result:
    started=time.perf_counter()
    empty=dict(schema_version='2.0',scenario_id=scenario['scenario_id'],provenance='solver',status='no_solution',runtime_s=0.,mip_gap=None,message='',facilities=[],flows=[],deliveries_t_per_year={},costs={})
    def fail(status,message):
        return empty|dict(status=status,message=message,runtime_s=time.perf_counter()-started)
    supply=sum(s['supply_t_per_year'] for s in bundle['sources'])
    if sum(scenario['demand_t_per_year'].values())>supply*scenario['refinery_yield']+1e-6:
        return fail('infeasible','Demand exceeds feedstock-based SAF limit; no feasible flows.')
    edges=bundle['distances']; sites=bundle['candidates']; opts=bundle['facility_options']; nf=len(edges)
    choices=[(r,s) for r in sites for s in ['small','large']]; nc=len(choices); nv=nf+2*nc
    cost=np.zeros(nv);integrality=np.zeros(nv);lo=np.zeros(nv);hi=np.full(nv,np.inf)
    for k,e in enumerate(edges):cost[k]=e['distance_km']*scenario['transport_usd_per_t_km'][e['stage']]/1000
    fixed=None if fixed_facilities is None else {f['candidate_id']:f['size'] for f in fixed_facilities}
    if fixed is not None and (len(fixed)!=len(fixed_facilities) or set(fixed)-{r['candidate_id'] for r in sites}):return fail('error','Invalid fixed_facilities IDs')
    for j,(r,s) in enumerate(choices):
        o=opts[r['kind']][s];q=nf+j;y=nf+nc+j
        cost[q]=o['variable_opex_usd_per_tonne_in']/1000
        cost[y]=(o['capex_usd']/scenario['annualisation_years']+o['fixed_opex_usd_per_year'])/1e6
        integrality[y]=1;hi[y]=1
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
    A=coo_matrix((values,(rows,cols)),shape=(len(lower),nv)).tocsc()
    try:sol=milp(cost,integrality=integrality,bounds=Bounds(lo,hi),constraints=LinearConstraint(A,lower,upper),options={'time_limit':scenario['solver_time_limit_s'],'mip_rel_gap':scenario['solver_rel_gap']})
    except Exception as e:return fail('error',str(e))
    if sol.x is None:return fail('infeasible' if sol.status==2 else 'no_solution',str(sol.message))
    x=sol.x; flows=[];fac=[];capex=fix=var=transport=0.
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
    gap=getattr(sol,'mip_gap',None)
    return empty|dict(status='optimal' if sol.status==0 and (gap is None or gap<1e-8) else 'feasible',runtime_s=time.perf_counter()-started,mip_gap=None if gap is None else float(gap),message=str(sol.message)+' Candidate-set result; inspect mip_gap.',facilities=fac,flows=flows,deliveries_t_per_year={a:sum(e['tonnes_per_year'] for e in flows if e['to_id']==a) for a in scenario['demand_t_per_year']},costs=costs,truck_trips=trips)

"""SAF Planner dashboard (Sarah). Renders a Service response and its same-scenario baseline.

The dashboard never computes or invents plan values: every number shown comes from the
solver Result, the validator, the scenario or the input bundle.
"""
import json,math
from pathlib import Path
from saf.contracts import Result

ROOT=Path(__file__).resolve().parent
OK_STATUSES=('optimal','feasible')
COMPONENTS=[('annualised_capex_usd_per_year','Annualised CapEx'),('fixed_opex_usd_per_year','Fixed OpEx'),
            ('variable_opex_usd_per_year','Variable OpEx'),('transport_usd_per_year','Transport')]
FAILURES={
    'infeasible':('error','No feasible plan exists for this scenario under the fixed supply and yield. Old flows and costs are hidden.'),
    'no_solution':('warning','The solver stopped before finding any plan. This is NOT proof of infeasibility: retry, or use a labelled cached result.'),
    'error':('error','The solver reported an error. There is no plan to show.'),
}

def _finite(v):
    return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)

def _usd(v):return f'${v:,.0f}'
def _usd_m(v):return f'${v/1e6:,.2f}m'

def cost_problems(costs:dict)->list[str]:
    """Missing/non-finite cost keys and reconciliation errors (opex = fixed+variable; total = annualised CapEx + opex + transport)."""
    keys=['capex_usd','opex_usd_per_year','total_usd_per_year']+[k for k,_ in COMPONENTS]
    missing=[k for k in keys if not _finite(costs.get(k))]
    if missing:return ['missing or non-finite: '+', '.join(missing)]
    problems=[]
    def close(a,b):return abs(a-b)<=max(1.0,1e-6*abs(b))
    if not close(costs['fixed_opex_usd_per_year']+costs['variable_opex_usd_per_year'],costs['opex_usd_per_year']):
        problems.append('fixed + variable OpEx does not equal opex_usd_per_year')
    if not close(costs['annualised_capex_usd_per_year']+costs['opex_usd_per_year']+costs['transport_usd_per_year'],costs['total_usd_per_year']):
        problems.append('annualised CapEx + OpEx + transport does not equal total_usd_per_year')
    return problems

def is_usable(result:Result|None,validation:dict|None)->bool:
    return bool(result) and result.get('status') in OK_STATUSES and bool(validation) and validation.get('valid') is True

def matching_baseline(scenario_id:str,baseline:Result|None)->tuple[Result|None,str]:
    """Return the baseline only if it is a usable result for the same scenario, else a reason it is not shown."""
    if baseline is None:return None,'No baseline supplied for this scenario.'
    if baseline.get('scenario_id')!=scenario_id:
        return None,f"Baseline is for '{baseline.get('scenario_id')}', not '{scenario_id}'; comparison hidden."
    if baseline.get('status') not in OK_STATUSES:return None,f"Baseline status is {baseline.get('status')}; comparison hidden."
    if cost_problems(baseline.get('costs') or {}):return None,'Baseline costs do not reconcile; comparison hidden.'
    return baseline,''

def load_bundle_for(scenario:dict)->dict:
    """Coordinates come from the bundle matching the scenario: mock fixture or full processed data."""
    if scenario.get('assumptions_status')=='SYNTHETIC_INTERFACE_FIXTURE':
        return json.loads((ROOT/'mocks/bundle.json').read_text())
    from saf.data import load_bundle
    bundle,_=load_bundle(str(ROOT/'data/processed'),str(ROOT/'config/assumptions_full.json'))
    return bundle

def _scenario_panel(st,scenario:dict)->None:
    st.sidebar.subheader('Scenario in view')
    st.sidebar.code(scenario['scenario_id'],language=None)
    demand=scenario['demand_t_per_year']
    st.sidebar.table([{'Airport':a,'SAF demand (kt/yr)':f'{v/1000:,.1f}'} for a,v in demand.items()])
    total=sum(demand.values())
    st.sidebar.caption(f"Total SAF {total/1000:,.1f} kt/yr -> needs {total/scenario['refinery_yield']/1000:,.1f} kt biomass/yr "
                       f"at yield {scenario['refinery_yield']:.2f}.")

def _failure_screen(st,response:dict,bundle_supply_t:float|None)->None:
    r,v=response['result'],response['validation']
    status=r.get('status')
    if status in FAILURES:
        level,text=FAILURES[status]
        getattr(st,level)(f'**{status.upper()}** - {text}')
    else:
        st.error('**VALIDATION FAILED** - the solver returned a plan but the independent validator rejected it. Do not use these results.')
        if v:
            st.write('Failed checks:')
            st.dataframe([c for c in v['checks'] if not c['passed']],use_container_width=True)
            for e in v.get('errors',[]):st.write('-',e)
    if status=='infeasible' and bundle_supply_t is not None:
        sc=response['scenario'];need=sum(sc['demand_t_per_year'].values());cap=bundle_supply_t*sc['refinery_yield']
        st.info(f"Requested SAF {need/1000:,.1f} kt/yr. Maximum from all {bundle_supply_t/1000:,.0f} kt biomass "
                f"at yield {sc['refinery_yield']:.2f} is {cap/1000:,.1f} kt/yr"
                +(f' (shortfall {(need-cap)/1000:,.1f} kt SAF).' if need>cap else '.'))
    st.caption('Solver message: '+(r.get('message') or '-'))
    st.caption('Use the sidebar to return to the base scenario.')

def _cost_section(st,r:Result,base:Result|None,base_reason:str)->None:
    c=r['costs']
    rows=[{'Component (USD/yr)':label,**({'Fixed baseline':_usd(base['costs'][k])} if base else {}),'Candidate-site MILP':_usd(c[k])} for k,label in COMPONENTS]
    rows.append({'Component (USD/yr)':'Total',**({'Fixed baseline':_usd(base['costs']['total_usd_per_year'])} if base else {}),
                 'Candidate-site MILP':_usd(c['total_usd_per_year'])})
    st.subheader('Annual cost breakdown')
    st.table(rows)
    st.caption(f"Upfront CapEx (not added to the annual total): MILP {_usd(c['capex_usd'])}"
               +(f"; baseline {_usd(base['costs']['capex_usd'])}" if base else '')
               +'. Total = annualised CapEx (CapEx/20) + fixed OpEx + variable OpEx + transport.')
    if not base:st.caption(base_reason)

def render_dashboard(response: dict, baseline: Result | None) -> None:
    import streamlit as st
    st.title('SAF Planner | Kalimantan')
    st.caption('Candidate-site planning. All costs USD/year. Organiser parameters v2.0.')
    scenario,r,v=response['scenario'],response['result'],response['validation']
    _scenario_panel(st,scenario)

    if response.get('clarification'):st.warning(response['clarification'])
    if r is None:
        st.info('No plan was solved for this request; the scenario is unchanged.')
        if response.get('explanation'):st.caption(response['explanation'])
        return

    usable=is_usable(r,v)
    problems=cost_problems(r.get('costs') or {}) if usable else []
    gap='-' if r.get('mip_gap') is None else f"{r['mip_gap']:.3%}"
    cols=st.columns(4)
    cols[0].metric('Scenario',scenario['scenario_id'])
    cols[1].metric('Solver status',r['status'])
    cols[2].metric('Validation','PASS' if usable and not problems else 'FAIL')
    cols[3].metric('MIP gap / runtime',f"{gap} / {r.get('runtime_s',0):.2f}s")
    st.caption(f"Provenance: **{r['provenance']}**"+(' (synthetic interface fixture, not a computed optimum)' if r['provenance']=='mock' else '')
               +(' (recorded solver run replayed from disk)' if r['provenance']=='cached' else ''))

    if not usable:
        supply=None
        try:supply=sum(s['supply_t_per_year'] for s in load_bundle_for(scenario)['sources'])
        except Exception:pass
        _failure_screen(st,response,supply)
        return
    if problems:
        st.error('Costs do not reconcile, so no cost figures are shown: '+'; '.join(problems))
        return

    if response.get('explanation'):st.success(response['explanation'])
    base,base_reason=matching_baseline(scenario['scenario_id'],baseline)
    total=r['costs']['total_usd_per_year']
    m=st.columns(3)
    m[0].metric('MILP annual cost',_usd_m(total))
    if base:
        bt=base['costs']['total_usd_per_year']
        m[1].metric('Same-scenario baseline',_usd_m(bt))
        m[2].metric('Annual difference vs baseline',_usd_m(bt-total),f'{(bt-total)/bt:.2%} lower' if bt>total else f'{(total-bt)/bt:.2%} higher',
                    delta_color='normal' if bt>=total else 'inverse')
    else:
        m[1].metric('Same-scenario baseline','not available')
        m[2].metric('Annual difference vs baseline','-')
    _cost_section(st,r,base,base_reason)

    with st.expander(f"Evidence: {sum(c['passed'] for c in v['checks'])}/{len(v['checks'])} validator checks passed"):
        st.write(r.get('message',''))
        st.dataframe(v['checks'],use_container_width=True)
        st.caption('Candidate-site MILP: optimal over the finite candidate set, not a global land-location optimum.')

    from scripts.render_network import make_figure
    import matplotlib.pyplot as plt
    bundle=load_bundle_for(scenario)
    fig=make_figure(bundle,r)
    fig.axes[0].set_title('Computed candidate-site network | '+scenario['scenario_id'],loc='left')
    st.pyplot(fig)
    plt.close(fig)
    coords={c['candidate_id']:c for c in bundle['candidates']}
    facilities=[f|{k:coords[f['candidate_id']][k] for k in ['latitude','longitude']} for f in r['facilities']]
    st.dataframe(facilities);st.dataframe(r['flows'])
    st.download_button('Download facilities with coordinates',json.dumps(facilities,indent=2),'facilities.json')
    st.caption('TRK last leg: barge, no truck trips. Truck sizes affect trips, not tonne-km costs.')
    st.download_button('Download result JSON',json.dumps(response,indent=2),'result.json')

if __name__=='__main__':
    import streamlit as st
    from saf.data import load_bundle
    from saf.service import run_scenario
    from saf.baseline import run_baseline
    choice=st.sidebar.selectbox('Scenario',['assumptions_full','assumptions_full_bpn20','assumptions_full_infeasible'])
    request=st.sidebar.text_input('Ask Claude for a demand change')
    if st.sidebar.button('Solve'):
        st.session_state.pop('last',None)
        b,c=load_bundle('data/processed','config/'+choice+'.json')
        with st.spinner('Solving and validating'):
            response=run_scenario(b,c,request or None)
            baseline=run_baseline(b,response['scenario']) if is_usable(response['result'],response['validation']) else None
            st.session_state['last']=(response,baseline)
    if 'last' in st.session_state:render_dashboard(*st.session_state['last'])

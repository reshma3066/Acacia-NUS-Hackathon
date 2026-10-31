"""SAF Planner dashboard (Sarah). Renders a Service response and its same-scenario baseline.

The dashboard never computes or invents plan values: every number shown comes from the
solver Result, the validator, the scenario or the input bundle.
"""
import json,math,html,time
from pathlib import Path
from saf.contracts import Result

ROOT=Path(__file__).resolve().parent
OK_STATUSES=('optimal','feasible')
COMPONENTS=[('annualised_capex_usd_per_year','Annualised CapEx'),('fixed_opex_usd_per_year','Fixed OpEx'),
            ('variable_opex_usd_per_year','Variable OpEx'),('transport_usd_per_year','Transport')]
COMPONENT_COLORS=['#17363f','#0f7c7c','#6fb7b0','#e2a030']
FAILURES={
    'infeasible':('bad','No feasible plan for this scenario','No plan can meet this demand under the fixed supply and yield. Old flows and costs are hidden.'),
    'no_solution':('warn','No solution found within the time limit','The solver stopped before finding any plan. This is NOT proof of infeasibility: retry, or use a labelled cached result.'),
    'error':('bad','Solver error','The solver reported an error. There is no plan to show.'),
}
# Map palette (RGBA). Kept close to scripts/render_network.py so the PNG exports and the live map agree.
STAGE_RGBA={'source_depot':[134,168,121,150],'depot_refinery':[220,154,60,180],'refinery_airport':[52,120,169,200]}
BARGE_RGBA=[123,94,167,220]
BIOMASS,DEPOT,REFINERY,AIRPORT=[135,175,121],[226,160,48],[183,67,57],[35,100,154]
STAGE_LABEL={'source_depot':'Biomass → depot','depot_refinery':'Depot → refinery','refinery_airport':'SAF → airport'}

CSS="""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html,body,.stApp,.stApp p,.stApp label,.stApp input,.stApp textarea,.stApp h1,.stApp h2,.stApp h3,.stApp h4,.stApp li,
.stApp [data-baseweb="select"] div,.stApp [data-baseweb="tab"] p{font-family:'Inter',system-ui,-apple-system,'Segoe UI',sans-serif;}
[data-testid="stHeader"]{background:transparent;height:0;}
[data-testid="stMainBlockContainer"],.block-container{padding-top:1.2rem;padding-bottom:3rem;max-width:1400px;}
[data-testid="stSidebar"]{border-right:1px solid #dfe8eb;}
[data-testid="stSidebar"] [data-testid="stSidebarUserContent"]{padding-top:1rem;}
.stTabs [data-baseweb="tab-list"]{gap:4px;border-bottom:1px solid #dfe8eb;}
.stTabs [data-baseweb="tab"]{height:42px;padding:0 18px;border-radius:8px 8px 0 0;font-weight:600;color:#5a6f78;}
.stTabs [aria-selected="true"]{color:#0f7c7c;background:#ffffff;}
[data-testid="stExpander"] details{background:#fff;border:1px solid #dfe8eb;border-radius:12px;}
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]){border-radius:14px;}
div[data-testid="stDownloadButton"] button{border-radius:8px;}

.topbar{display:flex;align-items:center;gap:18px;background:#17363f;color:#fff;border-radius:14px;padding:14px 22px;margin-bottom:14px;
        box-shadow:0 6px 20px rgba(23,54,63,.18);flex-wrap:wrap;}
.brand{display:flex;align-items:center;gap:10px;font-weight:800;font-size:1.15rem;letter-spacing:-.01em;}
.logo{display:grid;place-items:center;width:32px;height:32px;border-radius:9px;background:linear-gradient(135deg,#19a3a3,#0f7c7c);font-size:1rem;}
.crumb{font-size:.72rem;letter-spacing:.08em;color:#a9c4cb;text-transform:uppercase;margin-left:auto;}
.topbar .sid{font-family:ui-monospace,Consolas,monospace;font-size:.78rem;background:rgba(255,255,255,.1);padding:4px 10px;border-radius:6px;color:#dcecef;}

.strip{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 14px;}
.pill{display:inline-flex;align-items:center;gap:6px;font-size:.78rem;font-weight:600;padding:5px 11px;border-radius:999px;
      background:#fff;border:1px solid #dfe8eb;color:#36505a;white-space:nowrap;}
.pill .dot{width:7px;height:7px;border-radius:50%;background:currentColor;}
.pill.good{color:#0b6b4f;background:#e5f5ee;border-color:#c4e8d8;}
.pill.warn{color:#8a5a00;background:#fff4dc;border-color:#f3dfae;}
.pill.bad{color:#a2341f;background:#fdebe6;border-color:#f6cfc4;}
.pill.info{color:#1f5f8b;background:#e6f0f8;border-color:#c9ddee;}
.pill .k{color:#7b8f97;font-weight:500;}

.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:14px;margin-bottom:16px;}
.kpi{background:#fff;border:1px solid #dfe8eb;border-radius:14px;padding:16px 18px;box-shadow:0 1px 2px rgba(23,54,63,.04);}
.kpi-label{font-size:.78rem;font-weight:600;color:#5a6f78;text-transform:uppercase;letter-spacing:.05em;}
.kpi-value{font-size:1.75rem;font-weight:800;color:#17323b;letter-spacing:-.02em;margin-top:4px;line-height:1.15;}
.kpi-sub{font-size:.8rem;color:#6b7f87;margin-top:6px;}
.kpi.accent{background:linear-gradient(135deg,#0f7c7c,#17363f);border:none;}
.kpi.accent .kpi-label,.kpi.accent .kpi-sub{color:#bfe0e0;}
.kpi.accent .kpi-value{color:#fff;}
.delta-good{color:#0b6b4f;font-weight:700;}
.delta-bad{color:#a2341f;font-weight:700;}
.kpi.accent .delta-good{color:#8fe3bd;}.kpi.accent .delta-bad{color:#ffb4a2;}

.card{background:#fff;border:1px solid #dfe8eb;border-radius:14px;padding:16px 18px;margin-bottom:14px;}
.card h4{margin:0 0 4px;font-size:.95rem;font-weight:700;color:#17323b;}
.card .muted{font-size:.8rem;color:#6b7f87;}
.eyebrow{font-size:.7rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#0f7c7c;margin:12px 0 2px;}

.bar-row{margin:10px 0;}
.bar-head{display:flex;justify-content:space-between;font-size:.82rem;color:#36505a;}
.bar-head b{color:#17323b;}
.bar{height:8px;background:#e8eff1;border-radius:99px;overflow:hidden;margin-top:5px;}
.bar > span{display:block;height:100%;border-radius:99px;background:linear-gradient(90deg,#19a3a3,#0f7c7c);}
.bar.over > span{background:#c0502f;}

.legend{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:.78rem;color:#36505a;margin-top:6px;}
.legend span{display:inline-flex;align-items:center;gap:6px;}
.sw{width:11px;height:11px;border-radius:50%;display:inline-block;}
.sw.sq{border-radius:2px;}
.sw.line{width:18px;height:3px;border-radius:2px;}
.sw.dash{width:18px;height:0;border-top:3px dashed;background:none!important;}

.tbl{width:100%;border-collapse:collapse;font-size:.85rem;}
.tbl th{text-align:left;font-size:.72rem;text-transform:uppercase;letter-spacing:.05em;color:#6b7f87;background:#eef4f5;padding:9px 12px;font-weight:600;}
.tbl th:first-child{border-radius:8px 0 0 8px;}.tbl th:last-child{border-radius:0 8px 8px 0;}
.tbl td{padding:10px 12px;border-bottom:1px solid #edf2f3;color:#17323b;}
.tbl td.num,.tbl th.num{text-align:right;font-variant-numeric:tabular-nums;}
.tbl tr.total td{font-weight:800;border-bottom:none;border-top:2px solid #17363f;}

.banner{border-radius:14px;padding:20px 24px;margin-bottom:16px;}
.banner.bad{background:#fdebe6;border:1px solid #f6cfc4;color:#7d2a17;}
.banner.warn{background:#fff4dc;border:1px solid #f3dfae;color:#6b4600;}
.banner h3{margin:0 0 6px;font-size:1.1rem;font-weight:800;letter-spacing:.01em;text-transform:uppercase;}
.banner p{margin:4px 0;font-size:.92rem;}
.note{background:#fff8ea;border:1px solid #f3dfae;border-radius:12px;padding:12px 14px;font-size:.82rem;color:#6b4600;}
.note b{display:block;font-size:.7rem;letter-spacing:.08em;text-transform:uppercase;margin-bottom:3px;}

.steps{display:flex;flex-direction:column;gap:2px;}
.step{display:flex;gap:12px;align-items:flex-start;padding:9px 0;border-bottom:1px solid #edf2f3;}
.step:last-child{border-bottom:none;}
.step .ic{flex:none;width:24px;height:24px;border-radius:50%;display:grid;place-items:center;font-size:.75rem;font-weight:800;}
.step .ic.ok{background:#e5f5ee;color:#0b6b4f;}.step .ic.no{background:#fdebe6;color:#a2341f;}.step .ic.skip{background:#eef2f3;color:#7b8f97;}
.step .t{font-weight:600;font-size:.88rem;color:#17323b;}.step .d{font-size:.8rem;color:#6b7f87;}
.chat-you{background:#eef4f5;border-radius:12px;padding:12px 14px;margin-bottom:10px;}
.chat-you small,.chat-ai small{font-size:.68rem;font-weight:700;letter-spacing:.08em;color:#6b7f87;}
.chat-ai{background:#f4fbfa;border:1px solid #d3ebe8;border-radius:12px;padding:12px 14px;}

.assume{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:2px 18px;}
.assume div{padding:6px 0;}
.assume .v{font-size:.86rem;color:#17323b;}
.check-ok{color:#0b6b4f;font-weight:700;}.check-no{color:#a2341f;font-weight:700;}

.side-demand{display:grid;grid-template-columns:1fr auto;gap:6px 10px;font-size:.85rem;margin:6px 0 4px;}
.side-demand .code{font-weight:700;color:#17323b;}
.side-demand .v{text-align:right;font-variant-numeric:tabular-nums;color:#36505a;}
.side-foot{font-size:.76rem;color:#6b7f87;line-height:1.45;}

.empty{background:#fff;border:1px solid #dfe8eb;border-radius:16px;padding:34px 36px;}
.empty h2{margin:0 0 6px;font-size:1.5rem;font-weight:800;color:#17323b;letter-spacing:-.02em;}
.howto{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px;margin-top:22px;}
.howto div{background:#f6f9fa;border-radius:12px;padding:14px 16px;font-size:.85rem;color:#36505a;}
.howto b{display:block;color:#0f7c7c;font-size:.75rem;letter-spacing:.06em;text-transform:uppercase;margin-bottom:4px;}
</style>
"""

def _finite(v):
    return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)

def _usd(v):return f'${v:,.0f}'
def _usd_m(v):return f'${v/1e6:,.2f}m'
def _usd_short(v):return f'${v/1e9:,.2f}bn' if abs(v)>=1e9 else _usd_m(v)
def _kt(v):return f'{v/1000:,.1f} kt'
def _signed(v,fmt)->str:return ('+' if v>0 else '−' if v<0 else '')+fmt(abs(v))
def _e(s)->str:return html.escape(str(s))

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

# ---------- small HTML building blocks ----------

def _pill(text:str,tone:str='',key:str='')->str:
    return f'<span class="pill {tone}"><span class="dot"></span>'+(f'<span class="k">{_e(key)}</span>' if key else '')+f'{_e(text)}</span>'

def _kpi(label:str,value:str,sub:str='',tone:str='')->str:
    return f'<div class="kpi {tone}"><div class="kpi-label">{_e(label)}</div><div class="kpi-value">{_e(value)}</div><div class="kpi-sub">{sub}</div></div>'

def _table(head:list[str],rows:list[list],num_from:int=1,total_last:bool=False)->str:
    th=''.join(f'<th class="{"num" if i>=num_from else ""}">{_e(h)}</th>' for i,h in enumerate(head))
    body=''
    for j,row in enumerate(rows):
        cls=' class="total"' if total_last and j==len(rows)-1 else ''
        body+=f'<tr{cls}>'+''.join(f'<td class="{"num" if i>=num_from else ""}">{c}</td>' for i,c in enumerate(row))+'</tr>'
    return f'<table class="tbl"><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>'

def _bar(label:str,value:float,cap:float,right:str)->str:
    pct=0 if not cap else 100*value/cap
    return (f'<div class="bar-row"><div class="bar-head"><span><b>{_e(label)}</b></span><span>{right}</span></div>'
            f'<div class="bar{" over" if pct>100.5 else ""}"><span style="width:{min(pct,100):.1f}%"></span></div></div>')

def _topbar(st,scenario_id:str|None=None)->None:
    sid=f'<span class="sid">{_e(scenario_id)}</span>' if scenario_id else ''
    st.html(f'<div class="topbar"><div class="brand"><span class="logo">✈</span>SAF Planner</div>{sid}'
            '<div class="crumb">Kalimantan · Planning workspace</div></div>')

# ---------- sidebar ----------

def _scenario_panel(st,scenario:dict)->None:
    demand=scenario['demand_t_per_year'];total=sum(demand.values())
    rows=''.join(f'<span class="code">{_e(a)}</span><span class="v">{_kt(v)}</span>' for a,v in demand.items())
    st.sidebar.html('<div class="eyebrow">Scenario in view</div>'
                    f'<div class="side-demand">{rows}<span class="code" style="border-top:1px solid #dfe8eb;padding-top:6px">Total SAF</span>'
                    f'<span class="v" style="border-top:1px solid #dfe8eb;padding-top:6px"><b>{_kt(total)}</b></span></div>'
                    f'<div class="side-foot">Needs {_kt(total/scenario["refinery_yield"])} biomass/yr at refinery yield '
                    f'{scenario["refinery_yield"]:.0%}.</div>')

# ---------- failure screen ----------

def _failure_screen(st,response:dict,bundle_supply_t:float|None)->None:
    r,v,sc=response['result'],response['validation'],response['scenario']
    status=r.get('status')
    if status in FAILURES:
        tone,title,text=FAILURES[status]
    else:
        tone,title,text='bad','Validation failed','The solver returned a plan but the independent validator rejected it. Do not use these results.'
    need=sum(sc['demand_t_per_year'].values())
    lines=f'<p>{_e(text)}</p>'
    if status=='infeasible' and bundle_supply_t is not None:
        cap=bundle_supply_t*sc['refinery_yield']
        lines+=(f'<p>Requested SAF is <b>{_kt(need)}/yr</b>; all {_kt(bundle_supply_t)} of biomass at yield '
                f'{sc["refinery_yield"]:.0%} can produce at most <b>{_kt(cap)}/yr</b>'
                +(f' — a shortfall of <b>{_kt(need-cap)}</b> SAF.' if need>cap else '.')+'</p>')
    st.html(f'<div class="banner {tone}"><h3>{_e(title)}</h3>{lines}</div>')

    left,right=st.columns([1.15,1],gap='medium')
    with left:
        rows=[['Requested SAF',f'{_kt(need)}/yr']]
        if bundle_supply_t is not None:
            rows=[['Available biomass',f'{_kt(bundle_supply_t)}/yr'],
                  ['Depot / refinery yield',f'{sc["depot_yield"]:.0%} / {sc["refinery_yield"]:.0%}'],
                  ['Maximum SAF output',f'{_kt(bundle_supply_t*sc["refinery_yield"])}/yr']]+rows
        rows.append(['Solver status',_e(status)])
        st.html('<div class="card"><h4>Evidence behind the outcome</h4><div class="muted" style="margin-bottom:10px">'
                'Inputs and solver status only; no plan values are shown.</div>'+_table(['Check','Value'],rows)+'</div>')
    with right:
        if status=='infeasible':
            steps=('This scenario exceeds the available feedstock after conversion. Adding refinery capacity alone '
                   'would not resolve the shortage. Reduce demand, or supply evidence for more available biomass.')
        elif status=='no_solution':
            steps='Retry with a longer time limit, or switch to Cached replay to show a recorded and labelled run.'
        else:
            steps='Return to the base scenario from the sidebar, or switch to Cached replay.'
        st.html(f'<div class="card"><h4>Helpful next steps</h4><p class="muted" style="font-size:.88rem;line-height:1.55">{_e(steps)}</p>'
                f'<div class="muted">Solver message: {_e(r.get("message") or "-")}</div></div>')
    if v and status not in FAILURES:
        failed=[c for c in v['checks'] if not c['passed']]
        with st.expander(f'Failed validator checks ({len(failed)})',expanded=True):
            st.dataframe(failed,width='stretch',hide_index=True)
            for e in v.get('errors',[]):st.write('-',e)

# ---------- main dashboard ----------

def render_dashboard(response: dict, baseline: Result | None) -> None:
    import streamlit as st
    scenario,r,v=response['scenario'],response['result'],response['validation']
    _topbar(st,scenario['scenario_id'])
    _scenario_panel(st,scenario)

    if response.get('clarification'):
        st.warning(f"**Claude needs clarification:** {response['clarification']}",icon='💬')
    if r is None:
        st.info('No plan was solved for this request; the scenario is unchanged.',icon='ℹ️')
        if response.get('explanation'):st.caption(response['explanation'].replace('$','\\$'))
        return

    usable=is_usable(r,v)
    problems=cost_problems(r.get('costs') or {}) if usable else []
    gap='—' if r.get('mip_gap') is None else f"{r['mip_gap']:.2%}"
    prov=r['provenance']
    status_tone='good' if r['status'] in OK_STATUSES else ('warn' if r['status']=='no_solution' else 'bad')
    prov_text={'mock':'mock · synthetic fixture','cached':'cached · recorded run replay','solver':'live solver'}.get(prov,prov)
    checks=v['checks'] if v else []
    st.html('<div class="strip">'+_pill(r['status'],status_tone,'Solver ')
            +_pill('PASS' if usable and not problems else 'FAIL','good' if usable and not problems else 'bad','Validation ')
            +(_pill(f"{sum(c['passed'] for c in checks)}/{len(checks)} checks",'info') if checks and r['status'] in OK_STATUSES else '')
            +_pill(gap,'','MIP gap ')+_pill(f"{r.get('runtime_s',0):.2f}s",'','Runtime ')
            +_pill(prov_text,'warn' if prov in ('mock','cached') else 'info','Source ')+'</div>')

    if not usable:
        supply=None
        try:supply=sum(s['supply_t_per_year'] for s in load_bundle_for(scenario)['sources'])
        except Exception:pass
        _failure_screen(st,response,supply)
        return
    if problems:
        st.error('Costs do not reconcile, so no cost figures are shown: '+'; '.join(problems))
        return

    base,base_reason=matching_baseline(scenario['scenario_id'],baseline)
    bundle=load_bundle_for(scenario)
    c=r['costs'];total=c['total_usd_per_year']
    demand=scenario['demand_t_per_year'];delivered=r.get('deliveries_t_per_year') or {}
    refs=[f for f in r['facilities'] if f['kind']=='refinery'];depots=[f for f in r['facilities'] if f['kind']=='depot']
    met=sum(1 for a,d in demand.items() if delivered.get(a,0)>=d-1e-6)

    if base:
        bt=base['costs']['total_usd_per_year'];diff=bt-total
        delta=(f'<span class="delta-good">▼ {abs(diff)/bt:.1%} lower</span> than fixed-layout baseline ({_usd_m(bt)})' if diff>=0
               else f'<span class="delta-bad">▲ {abs(diff)/bt:.1%} higher</span> than fixed-layout baseline ({_usd_m(bt)})')
        save_kpi=_kpi('Saving vs baseline',_usd_m(diff) if diff>=0 else _signed(diff,_usd_m),'Same scenario, same assumptions')
    else:
        delta='Baseline not evaluated';save_kpi=_kpi('Saving vs baseline','Not evaluated',_e(base_reason))
    st.html('<div class="kpis">'
            +_kpi('Annual cost (optimised)',_usd_m(total),delta,'accent')
            +save_kpi
            +_kpi('Demand fulfilled',f'{_kt(sum(delivered.values()))}',f'{met} of {len(demand)} airport requirements met · target {_kt(sum(demand.values()))}')
            +_kpi('Selected facilities',f'{len(refs)+len(depots)} sites',
                  f'{len(refs)} refineries · {len(depots)} depots · CapEx {_usd_short(c["capex_usd"])}')+'</div>')

    tabs=st.tabs(['🗺️  Network','💰  Costs','🔁  Scenarios','🧾  Evidence'])
    with tabs[0]:_network_section(st,response,bundle)
    with tabs[1]:_cost_section(st,r,base,base_reason)
    with tabs[2]:_scenario_section(st,response,base)
    with tabs[3]:_evidence_section(st,response)

def _cost_section(st,r:Result,base:Result|None,base_reason:str)->None:
    import altair as alt,pandas as pd
    c=r['costs']
    plans=[('Optimised (MILP)',c)]+([('Fixed-layout baseline',base['costs'])] if base else [])
    df=pd.DataFrame([{'Plan':p,'Component':label,'USD m/yr':cc[k]/1e6,'order':i} for p,cc in plans for i,(k,label) in enumerate(COMPONENTS)])
    chart=(alt.Chart(df).mark_bar(cornerRadius=3)
           .encode(y=alt.Y('Plan:N',title=None,sort=[p for p,_ in plans],axis=alt.Axis(labelFontSize=12,labelFontWeight='bold',labelLimit=200)),
                   x=alt.X('sum(USD m/yr):Q',title='USD million per year',axis=alt.Axis(grid=True,gridColor='#edf2f3')),
                   color=alt.Color('Component:N',scale=alt.Scale(domain=[l for _,l in COMPONENTS],range=COMPONENT_COLORS),
                                   legend=alt.Legend(orient='top',title=None,labelFontSize=12)),
                   order=alt.Order('order:Q'),
                   tooltip=['Plan','Component',alt.Tooltip('USD m/yr:Q',format=',.2f')])
           .properties(height=alt.Step(52)).configure_view(stroke=None).configure_scale(bandPaddingInner=.3))
    with st.container(border=True):
        st.markdown('**Annual cost composition**')
        st.altair_chart(chart,width='stretch')

    head=['Component (USD/yr)']+(['Fixed baseline'] if base else [])+['Optimised (MILP)']+(['Difference'] if base else [])
    def diff(k):
        d=c[k]-base['costs'][k]
        return f'<span class="{"delta-good" if d<0 else "delta-bad" if d>0 else ""}">{_signed(d,_usd)}</span>'
    rows=[[label]+([_usd(base['costs'][k])] if base else [])+[_usd(c[k])]+([diff(k)] if base else []) for k,label in COMPONENTS]
    rows.append(['Total']+([_usd(base['costs']['total_usd_per_year'])] if base else [])+[_usd(c['total_usd_per_year'])]
                +([diff('total_usd_per_year')] if base else []))
    left,right=st.columns([1.6,1],gap='medium')
    with left:
        st.html('<div class="card"><h4>Breakdown</h4><div class="muted" style="margin-bottom:10px">Total = annualised CapEx (CapEx / '
                '20 years) + fixed OpEx + variable OpEx + transport.</div>'+_table(head,rows,total_last=True)+'</div>')
    with right:
        capex=f'<div class="eyebrow">Upfront CapEx</div><div class="kpi-value" style="font-size:1.4rem">{_usd(c["capex_usd"])}</div>'
        if base:capex+=f'<div class="muted">Baseline {_usd(base["costs"]["capex_usd"])}</div>'
        st.html(f'<div class="card">{capex}<div class="muted" style="margin-top:8px">Not added to the annual total; '
                'it enters only through the annualised line.</div></div>'
                +('<div class="note"><b>How to read this</b>Savings compare the optimised layout with a fixed-layout plan at the '
                  'same demand and assumptions. Differences between scenarios are demand effects, not optimisation savings.</div>' if base
                  else f'<div class="note"><b>Baseline not evaluated</b>{_e(base_reason)} No savings percentage is shown.</div>'))

def _scenario_section(st,response:dict,base:Result|None)->None:
    last=st.session_state.get('last') or {}
    sc,r=response['scenario'],response['result']
    request=last.get('request');start=last.get('start_demand') or {}
    left,right=st.columns([1.25,1],gap='medium')
    with left:
        chat=''
        if request:chat+=f'<div class="chat-you"><small>YOU</small><div>{_e(request)}</div></div>'
        steps=[('ok' if request else 'skip','Interpret request',
                'Claude turned the request into a bounded demand patch' if request else 'No natural-language request in this run'),
               ('ok','Run optimisation',f'Candidate-site MILP · {r["status"]} in {r.get("runtime_s",0):.2f}s'),
               ('ok','Validate output',f'{sum(c["passed"] for c in response["validation"]["checks"])} independent checks passed'),
               ('ok' if base else 'skip','Same-scenario baseline','Fixed-layout plan solved for comparison' if base else 'Not evaluated'),
               ('ok' if response.get('explanation') else 'skip','Explain the result','Quoting only validated model outputs')]
        steps_html=''.join(f'<div class="step"><div class="ic {s}">{"✓" if s=="ok" else "–"}</div><div><div class="t">{i+1}. {t}</div>'
                           f'<div class="d">{_e(d)}</div></div></div>' for i,(s,t,d) in enumerate(steps))
        expl=response.get('explanation')
        st.html('<div class="card"><h4>Scenario assistant</h4><div class="muted" style="margin-bottom:12px">'
                'Claude only edits airport demand. The solver computes every number; the validator checks it.</div>'
                +chat+f'<div class="eyebrow" style="margin-top:4px">Tool flow</div><div class="steps">{steps_html}</div>'
                +(f'<div class="chat-ai" style="margin-top:12px"><small>CLAUDE / RESULT</small><div style="font-size:.9rem;margin-top:4px">{_e(expl)}</div></div>' if expl else '')
                +'</div>')
    with right:
        rows=[]
        for a,v in sc['demand_t_per_year'].items():
            b=start.get(a,v);d=v-b
            rows.append([f'<b>{_e(a)}</b>',_kt(b),_kt(v),f'<span class="{"delta-bad" if d>0 else "delta-good" if d<0 else ""}">{_signed(d,_kt) if d else "—"}</span>'])
        sb,sa=sum(start.values()) if start else sum(sc['demand_t_per_year'].values()),sum(sc['demand_t_per_year'].values())
        rows.append(['Total',_kt(sb),_kt(sa),_signed(sa-sb,_kt) if sa!=sb else '—'])
        st.html('<div class="card"><h4>Demand change</h4><div class="muted" style="margin-bottom:10px">Starting scenario vs. the scenario that was solved.</div>'
                +_table(['Airport','Before','After','Change'],rows,total_last=True)+'</div>')
        _previous_run_card(st,r)
    _history_table(st)

def _previous_run_card(st,r:Result)->None:
    """Before/after against the previous usable run in this session. A demand-change effect, never 'savings'."""
    hist=[h for h in st.session_state.get('history',[]) if h['usable']]
    if len(hist)<2 or hist[-1]['scenario_id']!=r['scenario_id']:
        st.html('<div class="card"><h4>Compare with previous run</h4><div class="muted">Solve another scenario to see a before / after comparison here.</div></div>')
        return
    prev,cur=hist[-2],hist[-1]
    d=cur['total']-prev['total']
    rows=[['Annual cost',_usd_m(prev['total']),_usd_m(cur['total'])],
          ['SAF delivered',_kt(prev['delivered']),_kt(cur['delivered'])],
          ['Refineries / depots',f"{prev['refineries']} / {prev['depots']}",f"{cur['refineries']} / {cur['depots']}"]]
    st.html(f'<div class="card"><h4>Compare with previous run</h4><div class="muted" style="margin-bottom:10px">'
            f'{_e(prev["label"])} → {_e(cur["label"])}</div>'+_table(['Metric','Previous','This run'],rows)
            +f'<div class="note" style="margin-top:12px"><b>Interpretation</b>Annual cost changed by {_signed(d,_usd_m)}. '
            'This is the effect of the scenario change, not savings from a better facility layout.</div></div>')

def _history_table(st)->None:
    hist=st.session_state.get('history',[])
    if not hist:return
    with st.expander(f'Run history ({len(hist)} this session)'):
        st.dataframe([{'Time':h['time'],'Scenario':h['label'],'Mode':h['mode'],'Status':h['status'],
                       'Valid':'✓' if h['usable'] else '✗','Annual cost':_usd_m(h['total']) if h['total'] is not None else '—'}
                      for h in reversed(hist)],width='stretch',hide_index=True)

def _evidence_section(st,response:dict)->None:
    sc,r,v=response['scenario'],response['result'],response['validation']
    left,right=st.columns([1,1.5],gap='medium')
    with left:
        t=sc['transport_usd_per_t_km']
        items=[('Assumption set',sc['assumptions_status'].replace('_',' ').lower()),
               ('Conversion',f"Depot {sc['depot_yield']:.0%} · refinery {sc['refinery_yield']:.0%}"),
               ('Cost horizon',f"{sc['annualisation_years']}-year straight line · {sc['discount_rate']:.0%} discount"),
               ('Distances',f"{sc['distance_method']} × {sc['distance_multiplier']}"),
               ('Transport (USD/t·km)',' · '.join(f'{STAGE_LABEL.get(k,k).split(" → ")[1]} {v}' for k,v in t.items())),
               ('Use all supply','Yes' if sc['use_all_supply'] else 'No — unused biomass allowed'),
               ('Solver limits',f"{sc['solver_time_limit_s']}s · rel. gap {sc['solver_rel_gap']:.0%}"),
               ('Result provenance',r['provenance'])]
        st.html('<div class="card"><h4>Assumptions & provenance</h4><div class="assume">'
                +''.join(f'<div><div class="eyebrow">{_e(k)}</div><div class="v">{_e(val)}</div></div>' for k,val in items)
                +'</div></div>')
    with right:
        groups={}
        for c in v['checks']:groups.setdefault(c['name'].split(' ')[0].replace('_',' '),[]).append(c['passed'])
        rows=[[f'<span class="{"check-ok" if all(g) else "check-no"}">{"✓" if all(g) else "✗"}</span> {_e(name)}',
               f'{sum(g)} / {len(g)}'] for name,g in groups.items()]
        st.html(f'<div class="card"><h4>Checks before displaying a valid plan</h4><div class="muted" style="margin-bottom:10px">'
                f'{sum(c["passed"] for c in v["checks"])}/{len(v["checks"])} independent validator checks passed, grouped by type.</div>'
                +_table(['Check type','Passed'],rows)+'</div>')
        with st.expander(f'All {len(v["checks"])} individual checks'):
            st.dataframe(v['checks'],width='stretch',hide_index=True)
    st.html(f'<div class="card"><h4>Solver message</h4><div class="muted">{_e(r.get("message",""))}</div>'
            '<div class="muted" style="margin-top:6px">Candidate-site MILP: optimal over the finite candidate set, not a global land-location optimum.</div></div>')

def facility_rows(bundle:dict,result:Result)->list[dict]:
    """Selected facilities joined to candidate coordinates by candidate_id, with intake capacity and utilisation."""
    coords={c['candidate_id']:c for c in bundle['candidates']}
    rows=[]
    for f in sorted(result['facilities'],key=lambda f:(f['kind']!='refinery',f['candidate_id'])):
        c=coords[f['candidate_id']];cap=bundle['facility_options'][f['kind']][f['size']]['capacity_t_per_year']
        rows.append(dict(candidate_id=f['candidate_id'],kind=f['kind'],size=f['size'],latitude=c['latitude'],longitude=c['longitude'],
                         intake_t_per_year=round(f['input_t_per_year'],1),output_t_per_year=round(f['output_t_per_year'],1),
                         intake_capacity_t_per_year=cap,utilisation_pct=round(100*f['input_t_per_year']/cap,1)))
    return rows

def _csv(rows:list[dict])->str:
    import csv,io
    buf=io.StringIO()
    if rows:
        w=csv.DictWriter(buf,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    return buf.getvalue()

def _short_id(cid:str)->str:
    return cid.replace('R_KAL_SUP_','R').replace('D_KAL_SUP_','D')

def network_deck(bundle:dict,r:Result):
    """Interactive pydeck map of sources, selected facilities, airports and solver flows. Straight lines, not routes."""
    import pydeck as pdk
    names={}
    pts={}
    for kind,key in [('sources','source_id'),('candidates','candidate_id'),('airports','airport_id')]:
        for row in bundle[kind]:pts[row[key]]=[row['longitude'],row['latitude']];names[row[key]]=row.get('name') or row.get('district') or row[key]
    flows=r['flows'];biggest=max([e['tonnes_per_year'] for e in flows],default=1) or 1
    lines=[dict(src=pts[e['from_id']],dst=pts[e['to_id']],width=round(1+7*e['tonnes_per_year']/biggest),
                color=BARGE_RGBA if e.get('mode')=='barge' else STAGE_RGBA[e['stage']],
                title=f"{_short_id(e['from_id'])} → {_short_id(e['to_id'])}",
                detail=f"{STAGE_LABEL[e['stage']]} · {e.get('mode','truck')} · {e['tonnes_per_year']/1000:,.1f} kt/yr") for e in flows
           if e['from_id'] in pts and e['to_id'] in pts]
    used={e['from_id'] for e in flows if e['stage']=='source_depot'}
    sources=[dict(pos=pts[s['source_id']],r=math.sqrt(s['supply_t_per_year'])*45,
                  color=BIOMASS+[200 if s['source_id'] in used else 60],title=f"{s['source_id']} · {names[s['source_id']]}",
                  detail=f"Biomass source · {s['supply_t_per_year']/1000:,.1f} kt/yr"+(' · used' if s['source_id'] in used else ' · unused'))
             for s in bundle['sources']]
    fac=[dict(pos=pts[f['candidate_id']],color=(REFINERY if f['kind']=='refinery' else DEPOT)+[255],
              px=(13 if f['size']=='large' else 10) if f['kind']=='refinery' else (7 if f['size']=='large' else 5),
              title=f"{_short_id(f['candidate_id'])} · {f['size']} {f['kind']}",
              detail=f"In {f['input_t_per_year']/1000:,.1f} kt/yr · out {f['output_t_per_year']/1000:,.1f} kt/yr")
         for f in sorted(r['facilities'],key=lambda f:f['kind']=='refinery')]
    delivered=r.get('deliveries_t_per_year') or {}
    airports=[dict(pos=pts[a['airport_id']],label=a['airport_id'],title=f"{a['airport_id']} · {a['name']}",
                   detail=f"Airport · receives {delivered.get(a['airport_id'],0)/1000:,.1f} kt SAF/yr") for a in bundle['airports']]
    lons=[p[0] for p in pts.values()];lats=[p[1] for p in pts.values()]
    span=max(max(lons)-min(lons),max(lats)-min(lats),0.5)
    view=pdk.ViewState(longitude=(min(lons)+max(lons))/2,latitude=(min(lats)+max(lats))/2,
                       zoom=max(3.0,min(9.0,math.log2(360/span)-0.4)),pitch=0)
    layers=[
        pdk.Layer('ScatterplotLayer',sources,get_position='pos',get_radius='r',get_fill_color='color',radius_min_pixels=2,pickable=True),
        # One layer per pixel width: min/max pixel clamps are honoured where per-feature pixel widths are not.
        *[pdk.Layer('LineLayer',[l for l in lines if l['width']==w],get_source_position='src',get_target_position='dst',
                    get_color='color',get_width=1,width_min_pixels=w,width_max_pixels=w,pickable=True,auto_highlight=True)
          for w in sorted({l['width'] for l in lines})],
        *[pdk.Layer('ScatterplotLayer',[f for f in fac if f['px']==px],get_position='pos',get_radius=1,radius_min_pixels=px,
                    radius_max_pixels=px,get_fill_color='color',stroked=True,get_line_color=[38,60,70],line_width_min_pixels=1.5,
                    pickable=True,auto_highlight=True) for px in sorted({f['px'] for f in fac})],
        pdk.Layer('ScatterplotLayer',airports,get_position='pos',get_radius=1,radius_min_pixels=11,radius_max_pixels=11,
                  get_fill_color=AIRPORT+[255],stroked=True,get_line_color=[255,255,255],line_width_min_pixels=2.5,
                  pickable=True,auto_highlight=True),
        pdk.Layer('TextLayer',airports,get_position='pos',get_text='label',get_size=14,get_color=[255,255,255],
                  get_pixel_offset=[0,24],font_weight=800,background=True,get_background_color=AIRPORT+[240],background_padding=[6,3]),
    ]
    return pdk.Deck(layers=layers,initial_view_state=view,map_provider='carto',map_style='light',
                    tooltip={'html':'<b>{title}</b><br/><span style="opacity:.8">{detail}</span>',
                             'style':{'backgroundColor':'#17363f','color':'#fff','fontSize':'12px','borderRadius':'8px','padding':'8px 10px'}})

def _network_section(st,response:dict,bundle:dict)->None:
    r,sc,sid=response['result'],response['scenario'],response['scenario']['scenario_id']
    facilities=facility_rows(bundle,r)
    left,right=st.columns([2.6,1],gap='medium')
    with left:
        with st.container(border=True):
            st.markdown('**Material-flow network** &nbsp;<span style="color:#6b7f87;font-size:.82rem">Hover any site or link for details</span>',
                        unsafe_allow_html=True)
            try:
                st.pydeck_chart(network_deck(bundle,r),height=520)
            except Exception:
                # Fall back to the static renderer if pydeck or the basemap is unavailable.
                from scripts.render_network import make_figure
                import matplotlib.pyplot as plt
                fig=make_figure(bundle,r,'Computed candidate-site network | '+sid);st.pyplot(fig);plt.close(fig)
            st.html('<div class="legend">'
                    f'<span><i class="sw" style="background:rgb{tuple(BIOMASS)}"></i>Biomass source (size = supply)</span>'
                    f'<span><i class="sw sq" style="background:rgb{tuple(DEPOT)}"></i>Depot</span>'
                    f'<span><i class="sw" style="background:rgb{tuple(REFINERY)}"></i>Refinery</span>'
                    f'<span><i class="sw" style="background:rgb{tuple(AIRPORT)}"></i>Airport</span>'
                    +''.join(f'<span><i class="sw line" style="background:rgb{tuple(STAGE_RGBA[k][:3])}"></i>{STAGE_LABEL[k]}</span>' for k in STAGE_RGBA)
                    +f'<span><i class="sw line" style="background:rgb{tuple(BARGE_RGBA[:3])}"></i>SAF → TRK (barge)</span></div>'
                    '<div class="muted" style="font-size:.74rem;color:#7b8f97;margin-top:6px">Line width = annual tonnes. '
                    'Straight lines are distance proxies, not surveyed routes. Co-located zero-distance links are not visible.</div>')
    with right:
        demand=sc['demand_t_per_year'];delivered=r.get('deliveries_t_per_year') or {}
        bars=''.join(_bar(a,delivered.get(a,0),d,f'{_kt(delivered.get(a,0))} / {_kt(d)}') for a,d in demand.items())
        supply=sum(s['supply_t_per_year'] for s in bundle['sources'])
        used=sum(e['tonnes_per_year'] for e in r['flows'] if e['stage']=='source_depot')
        st.html(f'<div class="card"><h4>Airport deliveries</h4><div class="muted">SAF delivered vs. demand, per year</div>{bars}</div>'
                f'<div class="card"><h4>Feedstock</h4>{_bar("Biomass used",used,supply,f"{_kt(used)} / {_kt(supply)}")}'
                f'<div class="muted">{sum(1 for s in bundle["sources"] if any(e["from_id"]==s["source_id"] for e in r["flows"]))} '
                f'of {len(bundle["sources"])} sources supply the network.</div></div>')
        barge=[e for e in r['flows'] if e['mode']=='barge']
        trk_trucks=[t for t in r.get('truck_trips') or [] if t['to_id']=='TRK']
        st.html(f'<div class="card"><h4>TRK last leg</h4><div class="muted">{len(barge)} barge link(s) carrying '
                f'{_kt(sum(e["tonnes_per_year"] for e in barge))} SAF/yr. '
                +('No truck trips to TRK.' if not trk_trucks else f'<b style="color:#a2341f">Warning: {len(trk_trucks)} truck-trip record(s) to TRK.</b>')
                +'</div></div>')

    refs=[f for f in facilities if f['kind']=='refinery'];depots=[f for f in facilities if f['kind']=='depot']
    with st.container(border=True):
        head,dl=st.columns([3,2],vertical_alignment='center')
        head.markdown(f'**Selected facilities** &nbsp;<span style="color:#6b7f87;font-size:.82rem">{len(refs)} refineries · {len(depots)} depots</span>',
                      unsafe_allow_html=True)
        with dl:
            b=st.columns(3)
            b[0].download_button('CSV',_csv(facilities),f'facilities_{sid}.csv','text/csv',icon=':material/download:',width='stretch')
            b[1].download_button('JSON',json.dumps(facilities,indent=2),f'facilities_{sid}.json','application/json',icon=':material/data_object:',width='stretch')
            b[2].download_button('Full run',json.dumps(response,indent=2),f'response_{sid}.json','application/json',icon=':material/archive:',width='stretch')
        st.dataframe(facilities,width='stretch',hide_index=True,column_config={
            'candidate_id':st.column_config.TextColumn('Site'),'kind':st.column_config.TextColumn('Type'),'size':st.column_config.TextColumn('Size'),
            'latitude':st.column_config.NumberColumn('Lat',format='%.4f'),'longitude':st.column_config.NumberColumn('Lon',format='%.4f'),
            'intake_t_per_year':st.column_config.NumberColumn('Intake (t/yr)',format='localized'),
            'output_t_per_year':st.column_config.NumberColumn('Output (t/yr)',format='localized'),
            'intake_capacity_t_per_year':st.column_config.NumberColumn('Capacity (t/yr)',format='localized'),
            'utilisation_pct':st.column_config.ProgressColumn('Utilisation',min_value=0,max_value=100,format='%.1f%%')})

    with st.expander(f"Material flows ({len(r['flows'])} links)"):
        st.dataframe(r['flows'],width='stretch',hide_index=True,column_config={
            'tonnes_per_year':st.column_config.NumberColumn('Tonnes / yr',format='localized')})
        st.download_button('Flows (CSV)',_csv(r['flows']),f'flows_{sid}.csv','text/csv',icon=':material/download:')
    with st.expander('Truck-trip equivalents (operational context)'):
        st.caption('Trips = tonnes / payload, not rounded dispatch counts. Both truck sizes share the same tonne-km cost, '
                   'so truck size changes trips, not cost. Barge trips are not estimated.')
        st.dataframe(r.get('truck_trips') or [],width='stretch',hide_index=True)

SCENARIOS={'assumptions_full':'Base: 300 kt SAF at each airport',
           'assumptions_full_bpn20':'BPN +20%: BPN 360 kt, others 300 kt',
           'assumptions_full_infeasible':'All airports +15%: 345 kt each (infeasible)'}

def solve_live(config:str,request:str|None)->tuple[dict,Result|None]:
    """Claude patch (optional) -> MILP -> independent validation -> same-scenario baseline."""
    from saf.data import load_bundle
    from saf.service import run_scenario
    from saf.baseline import run_baseline
    b,c=load_bundle(str(ROOT/'data/processed'),str(ROOT/'config'/(config+'.json')))
    response=run_scenario(b,c,request)
    baseline=run_baseline(b,response['scenario']) if is_usable(response['result'],response['validation']) else None
    return response,baseline

def load_cached(config:str)->tuple[dict,Result|None]:
    """Replay a recorded solver run from docs/, relabelled provenance=cached so it is never mistaken for a live solve."""
    def read(kind):
        d=json.loads((ROOT/'docs'/f'{config}_{kind}.json').read_text())
        if d['result']:d['result']=d['result']|{'provenance':'cached'}
        return d
    milp,base=read('milp'),read('baseline')
    response=dict(scenario=milp['scenario'],result=milp['result'],validation=milp['validation'],
                  explanation=f'CACHED REPLAY of a recorded solver run (docs/{config}_milp.json). No live solve or Claude call was made.',
                  clarification=None)
    return response,base['result'] if is_usable(base['result'],base['validation']) else None

def _history_entry(view:tuple,label:str,mode:str)->dict:
    """Summary of a run for the session history. Only copies values already in the response."""
    response,_=view;r,v=response['result'],response['validation']
    usable=is_usable(r,v) and not cost_problems(r.get('costs') or {})
    return dict(time=time.strftime('%H:%M:%S'),label=label,mode=mode,scenario_id=response['scenario']['scenario_id'],
                status=(r or {}).get('status','no plan'),usable=usable,
                total=r['costs']['total_usd_per_year'] if usable else None,
                delivered=sum((r.get('deliveries_t_per_year') or {}).values()) if usable else None,
                refineries=sum(f['kind']=='refinery' for f in r['facilities']) if usable else None,
                depots=sum(f['kind']=='depot' for f in r['facilities']) if usable else None)

def _empty_state(st,config:str)->None:
    _topbar(st)
    sc=json.loads((ROOT/'config'/(config+'.json')).read_text())
    demand=sc['demand_t_per_year']
    rows=[[f'<b>{_e(a)}</b>',_kt(v)] for a,v in demand.items()]+[['Total',_kt(sum(demand.values()))]]
    left,right=st.columns([1.5,1],gap='medium')
    with left:
        st.html('<div class="empty"><div class="eyebrow">Supply-chain planning</div>'
                '<h2>Where to build, how big, and what it costs per year</h2>'
                '<div class="muted" style="font-size:.95rem;line-height:1.55">Plan a sustainable aviation fuel network across '
                'Kalimantan: biomass sources → depots → refineries → four airports. Pick a scenario in the sidebar and press '
                '<b>Run optimisation</b>.</div><div class="howto">'
                '<div><b>1 · Choose</b>Start from a demand scenario, then optionally change one airport&#8217;s demand.</div>'
                '<div><b>2 · Solve</b>A candidate-site MILP picks facilities and flows; a validator checks every number.</div>'
                '<div><b>3 · Inspect</b>Explore the map, costs vs. baseline, and the evidence behind the plan.</div>'
                '</div></div>')
    with right:
        st.html(f'<div class="card"><h4>Selected scenario</h4><div class="muted" style="margin-bottom:10px">{_e(SCENARIOS[config])}</div>'
                +_table(['Airport','SAF demand / yr'],rows,total_last=True)
                +f'<div class="muted" style="margin-top:10px">Refinery yield {sc["refinery_yield"]:.0%} · '
                f'{sc["annualisation_years"]}-year annualisation</div></div>')

def main()->None:
    import streamlit as st
    st.set_page_config(page_title='SAF Planner | Kalimantan',page_icon='✈️',layout='wide',initial_sidebar_state='expanded')
    st.html(CSS)
    with st.sidebar:
        st.html('<div style="font-weight:800;font-size:1.05rem;color:#17323b">Plan a scenario</div>'
                '<div class="side-foot" style="margin-bottom:6px">Configure inputs, then run the optimiser.</div>')
        mode=st.segmented_control('Mode',['Live solve','Cached replay'],default='Live solve',width='stretch',
                                  help='Cached replay shows recorded solver runs, labelled as cached. Use it if the network or API fails.') or 'Live solve'
        config=st.selectbox('Starting scenario',list(SCENARIOS),format_func=SCENARIOS.get)
        request=None
        if mode=='Live solve':
            AIRPORTS={'PNK':'Supadio (Pontianak)','PKN':'Iskandar (Pangkalan Bun)',
                      'BPN':'Sepinggan (Balikpapan)','TRK':'Juwata (Tarakan)'}
            airport=st.selectbox('Airport to change',list(AIRPORTS),format_func=lambda k:f'{k} – {AIRPORTS[k]}')
            pct=st.number_input('Demand change (%)',min_value=-100.0,max_value=200.0,value=0.0,step=5.0,
                                help='0 = no change (plain solve, no Claude call)')
            request=None if pct==0 else f"{'Increase' if pct>0 else 'Decrease'} {airport} demand by {abs(pct):g}%"
            st.html(f'<div class="side-foot" style="margin-bottom:4px">Request sent to Claude: <b>{_e(request or "none")}</b></div>')
        go=st.button('Run optimisation' if mode=='Live solve' else 'Load recorded run',type='primary',width='stretch',
                     icon=':material/play_arrow:' if mode=='Live solve' else ':material/history:')
        st.html('<div class="side-foot">Claude only turns the request into a bounded demand patch. The solver computes every number; '
                'an independent validator checks it before anything is shown.</div>')
    if go:
        # Clear first so a failure can never leave the previous success on screen.
        st.session_state.pop('last',None)
        try:
            with st.spinner('Solving, validating and running the matching baseline…' if mode=='Live solve' else 'Loading recorded run…'):
                view=solve_live(config,request) if mode=='Live solve' else load_cached(config)
            start=json.loads((ROOT/'config'/(config+'.json')).read_text())['demand_t_per_year']
            st.session_state['last']=dict(view=view,mode=mode,request=request,start_demand=start)
            label=SCENARIOS[config].split(':')[0]+(f' + “{request}”' if request else '')
            st.session_state.setdefault('history',[]).append(_history_entry(view,label,mode))
        except Exception as e:
            st.error(f'Run failed ({type(e).__name__}: {e}). Nothing is shown from earlier runs. Retry, or switch to Cached replay.',icon='⚠️')
    last=st.session_state.get('last')
    if not last:
        _empty_state(st,config)
        return
    st.sidebar.divider()
    st.sidebar.html(f'<div class="side-foot">Showing <b>{_e(last["mode"])}</b>'
                    +(f' · Claude request: “{_e(last["request"])}”' if last['request'] else ' · no Claude request')+'</div>')
    render_dashboard(*last['view'])

if __name__=='__main__':
    main()

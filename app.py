"""Working minimal UI. Sarah owns styling, map improvements and integration."""
from saf.contracts import Result

def render_dashboard(response: dict, baseline: Result | None) -> None:
    import streamlit as st
    st.title('SAF Planner | Kalimantan')
    st.caption('Candidate-site planning. All costs USD/year. Organiser parameters v2.0.')
    if response['clarification']:st.warning(response['clarification'])
    st.write(response['explanation'])
    r=response['result']
    if r is None:return
    st.write('Status:',r['status'],'Provenance:',r['provenance'],'MIP gap:',r['mip_gap'])
    if r['status'] not in ['optimal','feasible'] or not response['validation']['valid']:
        st.error(r['message']);return
    st.metric('MILP annual cost',f"${r['costs']['total_usd_per_year']:,.0f}")
    if baseline and baseline['status'] in ['optimal','feasible']:
        st.metric('Same-scenario baseline',f"${baseline['costs']['total_usd_per_year']:,.0f}")
        st.write('Difference USD/year:',baseline['costs']['total_usd_per_year']-r['costs']['total_usd_per_year'])
    from pathlib import Path
    from saf.data import load_bundle
    from scripts.render_network import make_figure
    root=Path(__file__).resolve().parent
    if r['provenance']=='mock':
        bundle=__import__('json').loads((root/'mocks/bundle.json').read_text())
    else:
        bundle,_=load_bundle(str(root/'data/processed'),str(root/'config/assumptions_full.json'))
    fig=make_figure(bundle,r)
    fig.axes[0].set_title('Computed candidate-site network | '+response['scenario']['scenario_id'],loc='left')
    st.pyplot(fig)
    import matplotlib.pyplot as plt
    plt.close(fig)
    coords={c['candidate_id']:c for c in bundle['candidates']}
    facilities=[f|{k:coords[f['candidate_id']][k] for k in ['latitude','longitude']} for f in r['facilities']]
    st.json(r['costs']);st.dataframe(facilities);st.dataframe(r['flows'])
    st.download_button('Download facilities with coordinates',__import__('json').dumps(facilities,indent=2),'facilities.json')
    st.caption('TRK last leg: barge, no truck trips. Truck sizes affect trips, not tonne-km costs.')
    st.download_button('Download result JSON',__import__('json').dumps(response,indent=2),'result.json')

if __name__=='__main__':
    import streamlit as st
    from saf.data import load_bundle
    from saf.service import run_scenario
    from saf.baseline import run_baseline
    choice=st.sidebar.selectbox('Scenario',['assumptions_full','assumptions_full_bpn20','assumptions_full_infeasible'])
    request=st.sidebar.text_input('Ask Claude for a demand change')
    if st.sidebar.button('Solve'):
        b,c=load_bundle('data/processed','config/'+choice+'.json')
        with st.spinner('Solving and validating'):
            response=run_scenario(b,c,request or None)
            baseline=run_baseline(b,response['scenario']) if response['result'] and response['validation']['valid'] else None
            st.session_state['last']=(response,baseline)
    if 'last' in st.session_state:render_dashboard(*st.session_state['last'])

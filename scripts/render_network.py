"""Sarah owns map styling. No external basemap or external data.

Green circles: biomass sources (size = supply; faded if unused). Orange squares: selected depots.
Red triangles: selected refineries. Blue stars: airports. Line width = annual tonnes on that link.
Dashed blue: barge (TRK last leg). Straight lines are distance proxies, not surveyed routes.

Usage: python scripts/render_network.py [assumptions_full|assumptions_full_bpn20]
"""
import sys,json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
P=Path(__file__).resolve().parents[1]
BG='#f5f8fa'
STAGE_COLOR={'source_depot':'#86a879','depot_refinery':'#dc9a3c','refinery_airport':'#3478a9'}
BIOMASS,DEPOT,REFINERY,AIRPORT='#87af79','#e2a030','#b74339','#23649a'

def coordinates(bundle):
    """id -> (longitude, latitude) for sources, candidates and airports."""
    out={}
    for kind,key in [('sources','source_id'),('candidates','candidate_id'),('airports','airport_id')]:
        for row in bundle[kind]:out[row[key]]=(row['longitude'],row['latitude'])
    return out

def short_id(cid):
    return cid.replace('R_KAL_SUP_','R').replace('D_KAL_SUP_','D')

def make_figure(bundle,result,title='Computed candidate-site MILP network'):
    fig,ax=plt.subplots(figsize=(10.8,6.7),layout='constrained')
    fig.patch.set_facecolor(BG);ax.set_facecolor(BG)
    xy=coordinates(bundle)
    flows=result['flows']
    biggest=max([e['tonnes_per_year'] for e in flows],default=1) or 1

    # Flows first so markers sit on top. Width scales with tonnes relative to the largest link.
    for e in sorted(flows,key=lambda e:e['tonnes_per_year']):
        (x0,y0),(x1,y1)=xy[e['from_id']],xy[e['to_id']]
        barge=e.get('mode')=='barge'
        ax.plot([x0,x1],[y0,y1],color=STAGE_COLOR[e['stage']],alpha=.75 if barge else .5,
                lw=.4+4*e['tonnes_per_year']/biggest,ls=(0,(5,3)) if barge else '-',zorder=2)

    used={e['from_id'] for e in flows if e['stage']=='source_depot'}
    for s in bundle['sources']:
        ax.scatter(*xy[s['source_id']],s=max(s['supply_t_per_year']/2000,12),color=BIOMASS,
                   alpha=.75 if s['source_id'] in used else .25,edgecolor='none',zorder=3)

    for f in sorted(result['facilities'],key=lambda f:f['kind']):
        ref=f['kind']=='refinery';large=f['size']=='large'
        ax.scatter(*xy[f['candidate_id']],marker='^' if ref else 's',color=REFINERY if ref else DEPOT,
                   s=(200 if large else 120) if ref else (55 if large else 30),edgecolor='#263c46',lw=.8,zorder=5 if ref else 4)
        if ref:ax.annotate(short_id(f['candidate_id']),xy[f['candidate_id']],xytext=(6,7),textcoords='offset points',fontsize=8,zorder=8)

    for a in bundle['airports']:
        ax.scatter(*xy[a['airport_id']],s=230,marker='*',color=AIRPORT,edgecolor='white',lw=.6,zorder=7)
        ax.annotate(a['airport_id'],xy[a['airport_id']],xytext=(9,-3),textcoords='offset points',fontsize=10,fontweight='bold',zorder=8)

    handles=[Line2D([],[],ls='',marker='o',color=BIOMASS,ms=8,label='Biomass source'),
             Line2D([],[],ls='',marker='s',color=DEPOT,mec='#263c46',ms=7,label='Selected depot'),
             Line2D([],[],ls='',marker='^',color=REFINERY,mec='#263c46',ms=9,label='Selected refinery'),
             Line2D([],[],ls='',marker='*',color=AIRPORT,ms=12,label='Airport'),
             Line2D([],[],color=STAGE_COLOR['source_depot'],lw=2,label='Biomass -> depot (truck)'),
             Line2D([],[],color=STAGE_COLOR['depot_refinery'],lw=2,label='Depot -> refinery (truck)'),
             Line2D([],[],color=STAGE_COLOR['refinery_airport'],lw=2,label='SAF -> airport (truck)'),
             Line2D([],[],color=STAGE_COLOR['refinery_airport'],lw=2,ls=(0,(5,3)),label='SAF -> TRK (barge)')]
    ax.legend(handles=handles,loc='lower left',fontsize=8,ncol=2,framealpha=.9)
    ax.set_xlabel('Longitude');ax.set_ylabel('Latitude');ax.set_aspect('equal',adjustable='datalim');ax.grid(alpha=.15)
    ax.set_title(title,loc='left',fontsize=14)
    ax.text(1,-.08,'Line width = annual tonnes. Straight lines are distance proxies, not routes.',transform=ax.transAxes,ha='right',fontsize=7,color='#5a6b75')
    return fig

if __name__=='__main__':
    sys.path.insert(0,str(P));from saf.data import load_bundle
    name=sys.argv[1] if len(sys.argv)>1 else 'assumptions_full'
    b,_=load_bundle(str(P/'data/processed'),str(P/'config'/(name+'.json')))
    r=json.loads((P/'docs'/(name+'_milp.json')).read_text())['result']
    out=P/'docs'/('network_base.png' if name=='assumptions_full' else 'network_'+name.removeprefix('assumptions_full_')+'.png')
    make_figure(b,r,'Computed candidate-site MILP network | '+r['scenario_id']).savefig(out,dpi=180)
    print('wrote',out)

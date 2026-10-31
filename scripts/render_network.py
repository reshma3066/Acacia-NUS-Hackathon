"""Sarah owns map styling. No external basemap or external data."""
import sys,json,csv
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
P=Path(__file__).resolve().parents[1]
def make_figure(bundle,result):
 fig,ax=plt.subplots(figsize=(10.8,6.7),layout='constrained');fig.patch.set_facecolor('#f5f8fa');ax.set_facecolor('#f5f8fa')
 coords={r.get('source_id',r.get('candidate_id',r.get('airport_id'))):(r['longitude'],r['latitude']) for kind in ['sources','candidates','airports'] for r in bundle[kind]}
 for e in sorted(result['flows'],key=lambda e:e['stage']):
  a,b=coords[e['from_id']],coords[e['to_id']];color={'source_depot':'#86a879','depot_refinery':'#dc9a3c','refinery_airport':'#3478a9'}[e['stage']]
  ax.plot([a[0],b[0]],[a[1],b[1]],color=color,alpha=.48,lw=.4+3.5*e['tonnes_per_year']/600000,ls='--' if e.get('mode')=='barge' else '-')
 for s in bundle['sources']:ax.scatter(*coords[s['source_id']],s=s['supply_t_per_year']/2000,color='#87af79',alpha=.65,zorder=3)
 for f in result['facilities']:
  ref=f['kind']=='refinery';ax.scatter(*coords[f['candidate_id']],s=160 if ref else 35,marker='^' if ref else 's',color='#b74339' if ref else '#e2a030',edgecolor='#263c46',zorder=5)
  if ref:ax.annotate(f['candidate_id'].replace('R_KAL_SUP_','R'),coords[f['candidate_id']],xytext=(5,7),textcoords='offset points',fontsize=8)
 for a in bundle['airports']:
  ax.scatter(*coords[a['airport_id']],s=170,marker='*',color='#23649a',zorder=7);ax.annotate(a['airport_id'],coords[a['airport_id']],xytext=(8,0),textcoords='offset points',fontsize=10)
 for marker,col,label in [('o','#87af79','Biomass'),('s','#e2a030','Selected depot'),('^','#b74339','Selected refinery'),('*','#23649a','Airport')]:ax.scatter([],[],s=65,marker=marker,color=col,label=label)
 ax.plot([],[],ls='--',color='#3478a9',label='TRK barge')
 ax.legend(loc='lower left',fontsize=8,ncol=3);ax.set_xlabel('Longitude');ax.set_ylabel('Latitude');ax.grid(alpha=.15);ax.set_title('Computed candidate-site MILP network | Base demand',loc='left',fontsize=14)
 return fig
if __name__=='__main__':
 sys.path.insert(0,str(P));from saf.data import load_bundle
 b,c=load_bundle(str(P/'data/processed'),str(P/'config/assumptions_full.json'));r=json.loads((P/'docs/assumptions_full_milp.json').read_text())['result'];fig=make_figure(b,r);fig.savefig(P/'docs/network_base.png',dpi=180)

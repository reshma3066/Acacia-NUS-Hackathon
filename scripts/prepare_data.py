"""Rebuild inputs solely from committed organiser data; no external data used."""
import csv,json,sys,math
from pathlib import Path
P=Path(__file__).resolve().parents[1];sys.path.insert(0,str(P))
from saf.data import build_distances

def save(name,rows):
 with (P/'data/processed'/name).open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
sources=[]
for r in csv.DictReader((P/'data/raw/biomass.csv').open()):sources.append(dict(source_id=r['location_id'],province=r['province'],district=r['district'],latitude=float(r['latitude']),longitude=float(r['longitude']),supply_t_per_year=float(r['production_tonnes'])))
airports=[]
for r in csv.DictReader((P/'data/raw/challenge3_airports_4.csv').open()):airports.append(dict(airport_id=r['iata'],name=r['name'],latitude=float(r['latitude']),longitude=float(r['longitude'])))
candidates=[dict(candidate_id='D_'+s['source_id'],kind='depot',latitude=s['latitude'],longitude=s['longitude']) for s in sources]
def hav(s,a):
 x,y,u,v=map(math.radians,[s['latitude'],s['longitude'],a['latitude'],a['longitude']]);h=math.sin((u-x)/2)**2+math.cos(x)*math.cos(u)*math.sin((v-y)/2)**2
 return 2*6371.0088*math.asin(min(1,math.sqrt(h)))
chosen=set()
for aid in ['PNK','PKN','BPN','TRK']:
 a=next(a for a in airports if a['airport_id']==aid)
 for _ in range(2):
  s=min((s for s in sources if s['source_id'] not in chosen),key=lambda s:(hav(s,a),s['source_id']))
  chosen.add(s['source_id']);candidates.append(dict(candidate_id='R_'+s['source_id'],kind='refinery',latitude=s['latitude'],longitude=s['longitude']))
b=dict(sources=sources,airports=airports,candidates=candidates)
c=json.loads((P/'config/assumptions_full.json').read_text());d=build_distances(b,c)
for name,rows in [('sources.csv',sources),('airports.csv',airports),('candidates.csv',candidates),('distances.csv',d)]:save(name,rows)
assert len(chosen)==8
print('Prepared 80 sources, 80 depot candidates, 8 refinery candidates, 4 airports.')

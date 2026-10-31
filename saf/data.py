import csv,json,math
from pathlib import Path
from .contracts import Bundle,Scenario

def load_bundle(data_dir: str, config_path: str) -> tuple[Bundle, Scenario]:
    p=Path(data_dir); c=json.loads(Path(config_path).read_text())
    b={}
    for name in ['sources','airports','candidates','distances']:
        b[name]=list(csv.DictReader((p/(name+'.csv')).open()))
        for r in b[name]:
            for k in ['latitude','longitude','supply_t_per_year','distance_km']:
                if k in r:r[k]=float(r[k])
    b['facility_options']=json.loads((Path(config_path).parent/'facilities.json').read_text())
    if c['distance_method']!='fixture_effective_km':b['distances']=build_distances(b,c)
    return b,c

def build_distances(bundle: Bundle, scenario: Scenario) -> list[dict]:
    def hav(a,b):
        x,y,u,v=map(math.radians,[a['latitude'],a['longitude'],b['latitude'],b['longitude']])
        h=math.sin((u-x)/2)**2+math.cos(x)*math.cos(u)*math.sin((v-y)/2)**2
        return 6371.0088*2*math.asin(min(1,math.sqrt(h)))*scenario['distance_multiplier']
    d=[x for x in bundle['candidates'] if x['kind']=='depot'];r=[x for x in bundle['candidates'] if x['kind']=='refinery']
    rows=[]
    for left,right,stage,lk,rk in [(bundle['sources'],d,'source_depot','source_id','candidate_id'),(d,r,'depot_refinery','candidate_id','candidate_id'),(r,bundle['airports'],'refinery_airport','candidate_id','airport_id')]:
        for a in left:
            for b in right:rows.append(dict(from_id=a[lk],to_id=b[rk],stage=stage,distance_km=hav(a,b)))
    return rows

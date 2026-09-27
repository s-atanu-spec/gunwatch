"""Daily CDC refresh with schema validation and a last-known-good fallback."""
import json,datetime as dt
from collections import defaultdict
from locations import STATES
URL='https://www.cdc.gov/nchs/pressroom/sosmap/firearm_mortality/firearm_mortality_dfe.json'

def parse(raw):
 data=json.loads(raw);groups=defaultdict(dict)
 for r in data['data']:
  year=int(r['YEAR']);state='DC' if r['STATE']=='District of Columbia' else r['STATE']
  if state not in STATES or not 2014<=year<dt.datetime.now(dt.timezone.utc).year:continue
  deaths=int(str(r['DEATHS']).replace(',',''));rate=float(r['RATE'])
  if deaths<0 or not 0<=rate<1000:raise ValueError('Invalid mortality value')
  if state in groups[year]:raise ValueError('Duplicate state/year')
  groups[year][state]={'year':year,'state':state,'deaths':deaths,'rate':rate}
 rows=[r for year,states in groups.items() if set(states)==set(STATES) for r in states.values()]
 if not rows:raise ValueError('No complete annual data')
 return rows

def refresh_history(db,now,fetch,config):
 guard=db.execute("SELECT expires FROM cache WHERE key='history:check'").fetchone()
 if guard and guard[0]>now:return
 db.execute("INSERT OR REPLACE INTO cache VALUES('history:check','null',?)",(now+86400,));db.commit()
 try:
  status,_,raw=fetch(URL,config['user_agent'],2000000)
  if status!=200:return
  rows=parse(raw);old=db.execute("SELECT payload FROM cache WHERE key='history:data'").fetchone()
  if old:
   combined={(r['year'],r['state']):r for r in json.loads(old[0])['rows']}
   combined.update({(r['year'],r['state']):r for r in rows});rows=list(combined.values())
  payload={'rows':rows,'checked_at':now,'source':URL,'latest_year':max(r['year'] for r in rows)}
  db.execute("INSERT OR REPLACE INTO cache VALUES('history:data',?,?)",(json.dumps(payload),now+31536000));db.commit()
 except (ValueError,KeyError,TypeError,OSError):return

def published_history(db,fallback):
 base=json.loads(fallback.read_text());hit=db.execute("SELECT payload FROM cache WHERE key='history:data'").fetchone()
 if hit:
  fresh=json.loads(hit[0]);combined={(r['year'],r['state']):r for r in base['rows']};combined.update({(r['year'],r['state']):r for r in fresh['rows']});base.update(fresh,rows=list(combined.values()))
 return base

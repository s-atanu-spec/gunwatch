"""Evidence-based US place matching. Coordinates never come from a language model."""
import json,re,gzip
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
STATES=json.loads((ROOT/'reference/states.json').read_text())
PLACES=json.loads(gzip.decompress((ROOT/'reference/places.json.gz').read_bytes()))
COUNTIES=json.loads((ROOT/'reference/counties.json').read_text())
CENTERS={p['state']:p for p in json.loads((ROOT/'reference/state.json').read_text())}
MAP_REFERENCES=json.loads((ROOT/'reference/map-reference-points.json').read_text())
INDEX=defaultdict(list)
for state,items in PLACES.items():
 for p in items:INDEX[p['name'].casefold()].append({**p,'state':state,'level':'city'})
for p in COUNTIES:INDEX[p['name'].casefold()].append({**p,'level':'county'})
STREET_SUFFIX=r'(?:Street|St\.?|Avenue|Ave\.?|Road|Rd\.?|Boulevard|Blvd\.?|Drive|Dr\.?|Lane|Ln\.?|Court|Ct\.?|Way|Parkway|Pkwy\.?|Highway|Hwy\.?)'
STREET=r'(?:[A-Z0-9][\w.\x27-]*\s+){1,5}'+STREET_SUFFIX
ADDRESS_RE=re.compile(r'\b(\d{1,6})\s+(?:(block(?: of)?)\s+)?('+STREET+r')\b')
STREET_ONLY=re.compile(r'\b(?i:on|near|at|along)\s+('+STREET+r')\b')
def normalize_street(s):
 s=re.sub(r'[^a-z0-9 ]','',s.casefold()); s=' '.join(s.split())
 for long,short in [('street','st'),('avenue','ave'),('road','rd'),('boulevard','blvd'),('drive','dr'),('lane','ln'),('court','ct'),('parkway','pkwy'),('highway','hwy'),('north','n'),('south','s'),('east','e'),('west','w')]:s=re.sub(r'\b'+long+r'\b',short,s)
 return s

def locate(text):
 text=text[:3000]
 loc={'state':None,'city':None,'county':None,'area':None,'street':None,'address':None,'lat':None,'lon':None,'precision':'unlocated','pin_color':None,'basis':'No defensible US location found','match_key':None}
 # Find complete proper-name spans. Trailing punctuation is not part of a place.
 tokens=list(re.finditer(r"[A-Z][\w'-]*",text))
 candidates=[]
 for i,t in enumerate(tokens):
  for j in range(i,min(i+5,len(tokens))):
   end=tokens[j].end();name=text[t.start():end]
   if not re.fullmatch(r"[A-Z][\w'-]*(?:\s+[A-Z][\w'-]*)*",name):break
   hits=INDEX.get(name.casefold(),[])
   if hits:candidates.append((t.start(),end,name,hits))
 # Prefer full names, never North (SC) inside North Philadelphia or Cape May city inside its county.
 candidates=[c for c in candidates if not any(d[0]<=c[0] and d[1]>=c[1] and (d[0],d[1])!=(c[0],c[1]) for d in candidates)]
 candidates=[c for c in candidates if c[2] not in ('North','South','East','West','Lamb') and not re.match(r'\s+(?:'+STREET_SUFFIX+r'|County|Speedway|Sports Grounds?|Bridge)\b',text[c[1]:])]
 explicit=[]
 for start,end,name,hits in candidates:
  for p in hits:
   state=p['state'];pattern=r'^\s*,\s*(?:'+re.escape(STATES[state])+'|'+state+r')\b'
   if re.search(pattern,text[end:]):explicit.append((name,p))
 chosen=[]
 if explicit:
  chosen=[p for name,p in explicit]
 else:
  states=set()
  for code,name in STATES.items():
   if re.search(r'\b(?:in|near|across)\s+'+re.escape(name)+r'\b',text,re.I) and code not in ('GA','WA','NY'):states.add(code)
   if re.search(r',\s*'+code+r'\b',text):states.add(code)
   if code in ('GA','WA','NY') and re.search(r'\b'+name+r' state\b',text,re.I):states.add(code)
  if len(states)>1:loc['basis']='Multiple states mentioned; review required';return loc
  state=next(iter(states),None)
  ambiguous=[]
  for start,end,name,hits in candidates:
   valid=[p for p in hits if not state or p['state']==state]
   before=text[max(0,start-55):start];after=text[end:end+55]
   context=bool(re.search(r'\b(?:in|near|outside|across|of|at)\s+(?:(?:downtown|north|south|east|west|northeast|northwest|southeast|southwest)\s+)?$',before,re.I) or re.match(r"(?:['’]s)?\s+(?:police|shooting|gunfire)\b",after,re.I) or (start==0 and re.match(r'\s*:',after)))
   if name=='Treasure Island' and re.search(r'\bBay Bridge\b',text):context=False
   if context:
    if len(valid)==1:chosen+=valid
    elif valid:ambiguous+=valid
  # Do not resolve a short unique name while an independent ambiguous scene is also present.
  if ambiguous:
   loc['candidates']=[{'name':p['name'],'state':p['state'],'level':p['level']} for p in ambiguous][:30]
   loc['basis']='Place named in source, but several US matches; state or local context needed'
   if not chosen and len({p['state'] for p in ambiguous})==1:
    state=ambiguous[0]['state']
  if state:loc.update(state=state,lat=CENTERS[state]['lat'],lon=CENTERS[state]['lon'],precision='state',pin_color='yellow',basis='State center; approximate location')
 unique={(p['state'],p['name'],p['lat'],p['lon']):p for p in chosen}
 if len(unique)>1:
  # City and containing county cannot be verified as belonging together without geography evidence.
  names={(p['state'],p['name']) for p in unique.values()}
  if len(names)==1:
   state=next(iter(unique.values()))['state'];loc.update(state=state,lat=CENTERS[state]['lat'],lon=CENTERS[state]['lon'],precision='state',pin_color='yellow',basis='Repeated place name in this state; approximate state center')
  else:loc.update(lat=None,lon=None,state=None,precision='unlocated',pin_color=None,basis='Multiple locations mentioned; review required')
  return loc
 if len(unique)==1:
  p=next(iter(unique.values()));loc.update(state=p['state'],lat=p['lat'],lon=p['lon'],precision=p['level'],pin_color='yellow',basis=f"Census {p['level']} center; approximate location")
  loc[p['level']]=p['name']
  if p['level']=='city':
   loc['area']=p['name']
   override=MAP_REFERENCES.get(p['state']+'|'+p['name'])
   if override:loc.update(lat=override['lat'],lon=override['lon'],basis=override['basis'],coordinate_source=override['source'])
 if loc['state']:
  matches=list(ADDRESS_RE.finditer(text))
  streets=[]
  for m in matches:
   number,block,name=m.groups();street=' '.join(name.split());address=((number+' ') if number else '')+street
   streets.append((address,number,block,street))
  if not streets:
   for m in STREET_ONLY.finditer(text):streets.append((m.group(1),None,None,m.group(1)))
  streets=list(dict.fromkeys(streets))
  # Avoid presenting a selection between multiple streets as an exact scene.
  if len(streets)==1:
   address,number,block,street=streets[0];loc.update(street=street,address=address if number and not block else None)
   context=loc['city'] or loc['county']
   if context:loc['match_key']='|'.join([loc['state'],context.casefold(),normalize_street(address), 'block' if block else 'address' if number else 'street'])
   loc['basis']+='; source street: '+(('block of ' if block else '')+address)
  elif len(streets)>1:
   loc['basis']+='; multiple streets mentioned, exact scene unresolved'
  area=re.search(r'\b(?:in|near)\s+(?:the\s+)?([A-Z][\w-]*(?:\s+[A-Z][\w-]*){0,3})\s+(?:neighborhood|neighbourhood|area|district)\b',text)
  if area:loc['area']=area.group(1);loc['basis']+='; area: '+area.group(1)
 return loc

def census_match(loc,fetch):
 """One validated address match. Census coordinates are address-range interpolation."""
 if not(loc['address'] and loc['city'] and loc['state']):return loc
 from urllib.parse import urlencode
 url='https://geocoding.geo.census.gov/geocoder/locations/address?'+urlencode({'street':loc['address'],'city':loc['city'],'state':loc['state'],'benchmark':'Public_AR_Current','format':'json'})
 result=fetch(url);matches=result.get('result',{}).get('addressMatches',[])
 if len(matches)!=1:return loc
 m=matches[0];a=m.get('addressComponents',{});coords=m.get('coordinates',{})
 if a.get('state')!=loc['state'] or a.get('city','').casefold()!=loc['city'].casefold():return loc
 if normalize_street(m.get('matchedAddress','').split(',')[0])!=normalize_street(loc['address']):return loc
 lon,lat=coords.get('x'),coords.get('y')
 if not isinstance(lat,(int,float)) or not isinstance(lon,(int,float)) or not(-180<=lon<=180 and -90<=lat<=90):return loc
 return {**loc,'lat':lat,'lon':lon,'precision':'address','pin_color':'red','basis':'US Census address match, interpolated along address range; not an independently verified incident coordinate','geocoded_address':m.get('matchedAddress')}

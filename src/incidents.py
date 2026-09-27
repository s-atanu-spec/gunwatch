"""Conservative source-supported incident extraction and non-transitive deduplication."""
import datetime as dt,hashlib,re
from zoneinfo import ZoneInfo
from locations import locate
NUMBERS={x:i for i,x in enumerate(['zero','one','two','three','four','five','six','seven','eight','nine','ten','eleven','twelve'])};NUMBERS.update({'a':1,'an':1,'no':0})
N=r'(?:\d{1,3}|zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|a|an|no)'
NEGATIVE=re.compile(r'\b(movie shoot|film shoot|photo shoot|shooting star|shooting guard|shooting range|shooter game|active shooter drill|vaccine shot)\b',re.I)
GUN=re.compile(r'\b(shooting|shootings|gunfire|gunshots?|shots fired|shootout|(?:man|woman|person|people|teen|child) shot)\b',re.I)
FOLLOW=re.compile(r'\b(sentenced|sentencing|trial|convicted|conviction|anniversary|years? ago)\b',re.I)
OUTCOME=re.compile(r'\b(killed|dead|injured|wounded|hospitalized|shots fired|gunfire|gunshots?|fatal)\b',re.I)

def number(s):return int(s) if s.isdigit() else NUMBERS[s.lower()]
def classify(title,text):
 if NEGATIVE.search(title):return 'excluded'
 if FOLLOW.search(title):return 'follow_up'
 if GUN.search(title) and (OUTCOME.search(text) or re.search(r'\bpolice\b',title,re.I)):return 'likely'
 return 'review'

def casualties(text):
 result={};evidence=[]
 for field,words in [('killed','killed|dead|fatally shot'),('injured','injured|wounded|hospitalized'),('shot','shot')]:
  found=[]
  for m in re.finditer(r'\b('+N+r')\s+(?:(?:people|persons?|men|women|children|teens?|officers?|victims?|man|woman|child)\s+)?(?:(?:were|was|are|is|reported)\s+)?(?:'+words+r')\b',text,re.I):found.append(number(m.group(1)));evidence.append(m.group(0))
  for m in re.finditer(r'\b(?:'+words+r')\s+('+N+r')\s+(?:people|persons?|men|women|children|teens?|victims?)\b',text,re.I):found.append(number(m.group(1)));evidence.append(m.group(0))
  if field=='injured' and re.search(r'\bno (?:one was injured|injuries(?: were reported)?)\b',text,re.I):found.append(0);evidence.append('No injuries reported')
  result[field]=found[0] if found and len(set(found))==1 else None
  if len(set(found))>1:evidence.append(field+': conflicting numbers in source; not resolved automatically')
 return result,evidence

def event_time(text,published):
 """Incident dates require an event sentence. Publication time is never an incident time."""
 # Source text is bounded to lead paragraphs; avoid unrelated prior incidents further down articles.
 sentences=re.split(r'(?<=[!?])\s+|(?<!\b[aApP])\.\s+(?=[A-Z])',text[:3000])
 relevant=[s for s in sentences if GUN.search(s) or re.search(r'\b(?:officers|police)\s+(?:responded|arrived|were called)|\bhappened\b|\boccurred\b',s,re.I)]
 dates=[];clocks=[];evidence=[]
 pub=dt.datetime.fromtimestamp(published,ZoneInfo('America/New_York')) if published else None
 for s in relevant:
  date=None;m=re.search(r'\b(20\d{2}-\d{2}-\d{2})\b',s)
  if m:
   try:date=dt.date.fromisoformat(m.group(1))
   except ValueError:pass
  if not date:
   m=re.search(r'\b(January|February|March|April|May|June|July|August|September|October|November|December|Jan\.?|Feb\.?|Mar\.?|Apr\.?|Jun\.?|Jul\.?|Aug\.?|Sep\.?|Sept\.?|Oct\.?|Nov\.?|Dec\.?)\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(20\d{2}))?\b',s,re.I)
   if m and (m.group(3) or pub):
    months=['jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec']
    try:
     date=dt.date(int(m.group(3)) if m.group(3) else pub.year,months.index(m.group(1).lower()[:3])+1,int(m.group(2)))
     if not m.group(3) and date>pub.date()+dt.timedelta(days=1):date=date.replace(year=date.year-1)
    except ValueError:pass
  if not date and pub:
   m=re.search(r'\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b',s,re.I)
   if m:
    weekday=['monday','tuesday','wednesday','thursday','friday','saturday','sunday'].index(m.group(1).lower());delta=(pub.weekday()-weekday)%7;date=pub.date()-dt.timedelta(days=delta)
   elif re.search(r'\byesterday\b',s,re.I):date=pub.date()-dt.timedelta(days=1)
   elif re.search(r'\btoday\b',s,re.I):date=pub.date()
  if date:dates.append(date.isoformat());evidence.append('Incident date in source event sentence: '+s.strip()[:240])
  for m in re.finditer(r'\b(?:at|around|about|after|before)\s+(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\.?',s,re.I):
   hour=int(m.group(1));minute=int(m.group(2) or 0)
   if 1<=hour<=12 and minute<60:clocks.append((hour%12+(12 if m.group(3).lower()=='p' else 0))*60+minute);evidence.append('Source local time: '+m.group(0))
 return {'date':dates[0] if dates and len(set(dates))==1 else None,'minute':clocks[0] if clocks and len(set(clocks))==1 else None,'date_basis':'source event sentence; relative dates anchored to publication in America/New_York','evidence':evidence}

def extract(report):
 text=report['title']+'. '+report.get('text','')[:3000]
 counts,evidence=casualties(text);when=event_time(text,report.get('published_at'));loc=locate(text)
 return {'relevance':classify(report['title'],text),'casualties':counts,'when':when,'location':loc,'evidence':evidence+when['evidence']}

def eligible(f):
 return not any('conflicting numbers' in e for e in f['evidence']) and f['relevance']=='likely' and bool(f['location'].get('match_key')) and bool(f['when']['date']) and f['when']['minute'] is not None and any(v is not None for v in f['casualties'].values())

def duplicate(a,b):
 if not(eligible(a) and eligible(b)):return False
 return a['location']['match_key']==b['location']['match_key'] and a['when']['date']==b['when']['date'] and abs(a['when']['minute']-b['when']['minute'])<=30 and a['casualties']==b['casualties']

def group_reports(reports,overrides=None):
 groups=[];pending=[]
 # Original first-seen ordering gives an existing group a stable anchor and ID.
 for r in sorted(reports,key=lambda r:(r['first_seen_at'],r['id'])):
  f=r['facts']
  if not eligible(f):pending.append(r);continue
  # Every member must match, preventing a chain of half-hour windows from merging distinct events.
  candidates=[g for g in groups if all(duplicate(f,x['facts']) for x in g['reports'])]
  if len(candidates)==1:candidates[0]['reports'].append(r)
  elif len(candidates)>1:pending.append({**r,'review_reason':'Matches several groups; not assigned automatically'})
  else:groups.append({'id':'case-'+r['id'][:20],'reports':[r]})
 # Explicit reviewed membership lists support correction without deleting source reports.
 byid={r['id']:r for r in reports}
 for o in overrides or []:
  ids=o.get('report_ids',[])
  if not ids or not o.get('reason') or any(i not in byid for i in ids):continue
  chosen=[byid[i] for i in ids]
  if not o.get('date') or not o.get('state'):continue
  groups=[{**g,'reports':[r for r in g['reports'] if r['id'] not in ids]} for g in groups];groups=[g for g in groups if g['reports']];pending=[r for r in pending if r['id'] not in ids]
  groups.append({'id':o['id'],'reports':chosen,'reviewed':o})
 cases=[]
 for g in groups:
  anchor=g['reports'][0];f=anchor['facts'];best=max(g['reports'],key=lambda r:r['facts']['location']['precision']=='address');location=best['facts']['location'].copy();review=g.get('reviewed',{})
  if review.get('state'):location['state']=review['state']
  cases.append({'id':g['id'],'title':anchor['title'],'summary':anchor['summary'],'summary_kind':anchor['summary_kind'],'date':review.get('date',f['when']['date']),'minute':f['when']['minute'],'location':location,'casualties':f['casualties'],'reports':[{k:r[k] for k in ['id','title','url','source','published_at']} for r in g['reports']],'report_count':len(g['reports']),'evidence':f['evidence'],'match_basis':review.get('reason','Same source-supported street/location, event date, local time within 30 minutes and matching reported casualty fields'),'verification':'reviewed' if review else 'automatically grouped; not independently verified'})
 return cases,pending

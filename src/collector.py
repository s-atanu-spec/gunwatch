"""Bounded RSS ingestion, durable SQLite storage and source-level backoff."""
from pathlib import Path
import datetime as dt,email.utils,hashlib,html,json,re,sqlite3,time,urllib.request,urllib.error,urllib.parse,urllib.robotparser,xml.etree.ElementTree as ET
from html.parser import HTMLParser
from incidents import extract,group_reports
from google_search import parse_search
from locations import census_match,STATES,locate

class PlainText(HTMLParser):
 def __init__(self):super().__init__();self.parts=[];self.hidden=0
 def handle_starttag(self,tag,attrs):
  if tag in ('script','style'):self.hidden+=1
  if tag in ('p','br','li','div'):self.parts.append(' ')
 def handle_endtag(self,tag):
  if tag in ('script','style'):self.hidden=max(0,self.hidden-1)
  if tag in ('p','li','div'):self.parts.append(' ')
 def handle_data(self,data):
  if not self.hidden:self.parts.append(data)
 def text(self):return ' '.join(html.unescape(' '.join(self.parts)).split())
def clean(s):
 p=PlainText();p.feed(s or '');return p.text()
def canonical(url):
 try:
  p=urllib.parse.urlsplit(url.strip())
  if p.scheme not in ('http','https') or not p.hostname or p.username or p.password:return None
  q=[(k,v) for k,v in urllib.parse.parse_qsl(p.query,keep_blank_values=True) if not k.lower().startswith('utm_') and k.lower() not in ('gclid','fbclid')]
  return urllib.parse.urlunsplit((p.scheme.lower(),p.netloc.lower(),p.path or '/',urllib.parse.urlencode(sorted(q)),''))
 except ValueError:return None

def parse_feed(raw,source,now):
 if len(raw)>2_000_000 or re.search(br'<!DOCTYPE|<!ENTITY',raw,re.I):raise ValueError('Unsafe or oversized RSS response')
 root=ET.fromstring(raw)
 if root.tag!='rss' or root.find('channel') is None:raise ValueError('Expected RSS 2.0')
 rows=[]
 for node in root.findall('./channel/item')[:300]:
  url=canonical(node.findtext('link',''));title=clean(node.findtext('title',''));publisher=clean(node.findtext('source',source))
  if not url or not title:continue
  if publisher and title.endswith(' - '+publisher):title=title[:-len(' - '+publisher)]
  published=None
  try:published=int(email.utils.parsedate_to_datetime(node.findtext('pubDate','')).timestamp())
  except (ValueError,TypeError,OverflowError):pass
  rawdesc=node.findtext('{http://purl.org/rss/1.0/modules/content/}encoded') or node.findtext('description','')
  body=clean(rawdesc)[:6000]
  if re.search(r'<(?:ol|ul)\b',rawdesc,re.I) or len(body.replace(title,'').replace(publisher,''))<65:body=''
  rows.append({'id':hashlib.sha256(url.encode()).hexdigest(),'url':url,'title':title[:1000],'source':publisher,'published_at':published,'text':body,'first_seen_at':now})
 if root.findall('./channel/item') and not rows:raise ValueError('No valid RSS items')
 return rows

class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):return None

def request(url,user_agent,limit=2_000_000):
 if urllib.parse.urlsplit(url).scheme!='https':raise ValueError('HTTPS is required')
 op=urllib.request.build_opener(NoRedirect)
 req=urllib.request.Request(url,headers={'User-Agent':user_agent,'Accept':'application/rss+xml, application/xml, application/json, text/html;q=0.8'})
 try:
  with op.open(req,timeout=20) as r:body=r.read(limit+1);status=r.status;headers=dict(r.headers)
 except urllib.error.HTTPError as e:status=e.code;headers=dict(e.headers);body=e.read(min(limit+1,10000))
 if len(body)>limit:raise ValueError('Response too large')
 return status,{k.lower():v for k,v in headers.items()},body

def redirect_note(url,headers):
 """Expose only redirect host and known route; never tokens, queries or arbitrary paths."""
 location=headers.get('location')
 if not location:return ''
 try:
  target=urllib.parse.urlsplit(urllib.parse.urljoin(url,location));host=target.hostname or ''
  if target.scheme not in ('http','https') or not re.fullmatch(r'[a-zA-Z0-9.-]+',host):return '; redirect destination invalid'
  route='/sorry/' if target.path.startswith('/sorry') else '/search' if target.path=='/search' else '/[path omitted]'
  return '; redirect to '+host+route
 except ValueError:return '; redirect destination invalid'

def database(path):
 path.parent.mkdir(parents=True,exist_ok=True);db=sqlite3.connect(path);db.row_factory=sqlite3.Row
 db.executescript('''PRAGMA busy_timeout=5000;
 CREATE TABLE IF NOT EXISTS reports(id TEXT PRIMARY KEY,url TEXT UNIQUE NOT NULL,first_seen_at INTEGER NOT NULL,last_seen_at INTEGER NOT NULL,payload TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS source_state(url TEXT PRIMARY KEY,next_allowed_at INTEGER NOT NULL,last_status TEXT);
 CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY AUTOINCREMENT,started_at INTEGER,status TEXT,message TEXT,added INTEGER DEFAULT 0);
 CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY,payload TEXT,expires INTEGER);
 CREATE TABLE IF NOT EXISTS cases(id TEXT PRIMARY KEY,payload TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS case_reports(case_id TEXT,report_id TEXT,PRIMARY KEY(case_id,report_id));''')
 return db

def cached(db,key,now):
 row=db.execute('SELECT payload FROM cache WHERE key=? AND expires>?',(key,now)).fetchone()
 return (True,json.loads(row[0])) if row else (False,None)
def cache(db,key,value,expires):db.execute('INSERT OR REPLACE INTO cache VALUES(?,?,?)',(key,json.dumps(value),expires));db.commit()

def article_body(url,config,db,now):
 """Only configured publishers, robots-aware, no redirects/paywalls/challenge bypass."""
 p=urllib.parse.urlsplit(url)
 if p.hostname not in config['article_hosts'] or p.scheme!='https':return ''
 origin='https://'+p.netloc
 hit,rules=cached(db,'robots:'+origin,now)
 if not hit:
  code,_,raw=request(origin+'/robots.txt',config['user_agent'],200000)
  if code==404:rules='User-agent: *\nDisallow:'
  elif code==200:rules=raw.decode('utf-8','replace')
  else:rules='User-agent: *\nDisallow: /'
  cache(db,'robots:'+origin,rules,now+86400)
 rp=urllib.robotparser.RobotFileParser();rp.parse(rules.splitlines())
 if not rp.can_fetch(config['user_agent'],url):return ''
 if (rp.crawl_delay(config['user_agent']) or 0)>1:return ''
 code,_,raw=request(url,config['user_agent'])
 if code!=200:return ''
 text=raw.decode('utf-8','replace')
 if re.search(r'captcha|verify you are human|unusual traffic|access denied',text[:15000],re.I):return ''
 values=[]
 for block in re.findall(r'<script[^>]+type=["\x27]application/ld\+json["\x27][^>]*>(.*?)</script>',text,re.S|re.I):
  try:values.append(json.loads(block))
  except ValueError:continue
 def walk(x):
  if isinstance(x,dict):
   if isinstance(x.get('articleBody'),str):return clean(x['articleBody'])[:6000]
   for v in x.values():
    if isinstance(v,(dict,list)):
     out=walk(v)
     if out:return out
  elif isinstance(x,list):
   for v in x:
    out=walk(v)
    if out:return out
  return ''
 return walk(values)

def brief(r):
 body=r.get('text','')
 if body:
  sentences=re.split(r'(?<=[.!?])\s+(?=[A-Z])',body)
  relevant=[s for s in sentences if re.search(r'\b(shoot|shot|gunfire|killed|injured|wounded|police)\b',s,re.I)]
  text=' '.join((relevant or sentences)[:2]);return text[:480].rsplit(' ',1)[0]+'…' if len(text)>480 else text,'source excerpt'
 return r['title'].rstrip('.')+'. The feed supplied no article summary; event details require source review.','headline only'

def collect(db,config,now,fetch=request):
 added=0;errors=[];statuses=[];geocodes=0;articles=0;successful_sources=0
 for src in config['sources']:
  old=db.execute('SELECT next_allowed_at FROM source_state WHERE url=?',(src['url'],)).fetchone()
  if old and old[0]>now:statuses.append(src['name']+': source cooldown');continue
  db.execute('INSERT OR REPLACE INTO source_state VALUES(?,?,?)',(src['url'],now+max(1800,config['interval_seconds']),'started'));db.commit()
  try:
   code,headers,body=fetch(src['url'],config['user_agent'])
   if code!=200:
    until=now+3600 if code in (403,429,503) else now+1800
    ra=headers.get('retry-after','')
    try:until=max(until,now+int(ra))
    except ValueError:
     try:until=max(until,int(email.utils.parsedate_to_datetime(ra).timestamp()))
     except (ValueError,TypeError):pass
    db.execute('UPDATE source_state SET next_allowed_at=?,last_status=? WHERE url=?',(until,f'HTTP {code}',src['url']));db.commit();raise ValueError(f'HTTP {code}'+(redirect_note(src['url'],headers) if 300<=code<400 else '')+'; no retries')
   if re.search(br'unusual traffic|g-recaptcha|before you continue to google|verify you are human|consent.google.com',body,re.I):
    db.execute('UPDATE source_state SET next_allowed_at=? WHERE url=?',(now+3600,src['url']));db.commit();raise ValueError('Source challenge; no bypass')
   rows=parse_search(body,src['name'],now,canonical) if src.get('type')=='google_search' else parse_feed(body,src['name'],now);saved=0
   for row in rows:
    old=db.execute('SELECT payload,first_seen_at FROM reports WHERE id=?',(row['id'],)).fetchone()
    row['fingerprint']=hashlib.sha256((row['title']+row['text']+str(row['published_at'])).encode()).hexdigest()
    if old:
     previous=json.loads(old[0]);row['first_seen_at']=old[1]
     if previous.get('fingerprint')==row['fingerprint']:
      db.execute('UPDATE reports SET last_seen_at=? WHERE id=?',(now,row['id']));saved+=1;continue
    row['facts']=extract(row)
    # Retain only gun-related leads, not every national news story.
    if row['facts']['relevance']=='excluded':continue
    if articles<config['article_limit_per_run'] and urllib.parse.urlsplit(row['url']).hostname in config['article_hosts']:
     articles+=1
     try:
      bodytext=article_body(row['url'],config,db,now)
      if bodytext:row['text']=bodytext;row['facts']=extract(row)
     except Exception:pass
     time.sleep(1.05)
    loc=row['facts']['location'];key='census:'+str(loc.get('match_key'));hit,geo=cached(db,key,now)
    if hit and geo:row['facts']['location']=geo
    elif not hit and loc.get('address') and loc.get('city') and geocodes<config['geocode_limit_per_run']:
     geocodes+=1
     def get_json(url):
      code,_,raw=fetch(url,config['user_agent'])
      if code!=200:raise ValueError('Geocoder unavailable')
      return json.loads(raw)
     try:
      geo=census_match(loc,get_json);cache(db,key,geo,now+30*86400);row['facts']['location']=geo
     except Exception:cache(db,key,None,now+86400)
    row['source_text']=row.get('text','')[:7000]
    row['summary'],row['summary_kind']=brief(row)
    if row.get('text_kind')=='search snippet' and row['text']:row['summary_kind']='search snippet'
    if old and previous.get('fingerprint')==row['fingerprint']:
     row['facts']=previous['facts'];row['summary']=previous['summary'];row['summary_kind']=previous['summary_kind']
    row['text']=row['summary'] if row['summary_kind'] in ('source excerpt','search snippet') else ''
    if not old:added+=1
    db.execute('INSERT INTO reports VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET last_seen_at=excluded.last_seen_at,payload=excluded.payload',(row['id'],row['url'],row['first_seen_at'],now,json.dumps(row)))
    saved+=1
   db.execute('UPDATE source_state SET last_status=? WHERE url=?',(f'OK, {saved} relevant records',src['url']));db.commit();successful_sources+=1;statuses.append(src['name']+f': {saved} saved')
  except Exception as exc:
   db.execute('UPDATE source_state SET last_status=? WHERE url=?',('Error: '+str(exc)[:180],src['url']));db.commit();errors.append(src['name']+': '+str(exc)[:180])
 status='partial' if errors and successful_sources else 'error' if errors else 'success' if successful_sources else 'cooldown'
 message='; '.join(statuses+errors);db.execute('INSERT INTO runs(started_at,status,message,added) VALUES(?,?,?,?)',(now,status,message,added));db.execute('DELETE FROM runs WHERE id NOT IN (SELECT id FROM runs ORDER BY id DESC LIMIT 1000)');db.commit()
 return {'status':status,'message':message,'added':added}

def refresh_locations(db):
 """Reprocess old records after matcher upgrades without fetching publishers again."""
 for stored in db.execute('SELECT id,payload FROM reports').fetchall():
  row=json.loads(stored['payload'])
  if row.get('location_version')==3:continue
  old=row['facts']['location'];fresh=locate(row['title']+'. '+row.get('source_text',row.get('text','')))
  if old.get('precision')=='address' and old.get('address')==fresh.get('address') and old.get('state')==fresh.get('state'):fresh=old
  row['facts']['location']=fresh;row['location_version']=3
  db.execute('UPDATE reports SET payload=? WHERE id=?',(json.dumps(row),stored['id']))
 db.commit()

def export(db,config,state,now):
 refresh_locations(db)
 reports=[json.loads(r[0]) for r in db.execute('SELECT payload FROM reports')]
 review_path=Path(__file__).resolve().parents[1]/'NEWS_REVIEW.json'
 audit=json.loads(review_path.read_text()) if review_path.exists() else {'items':[]}
 decisions={item['id']:item for item in audit['items']}
 from incidents import classify
 for r in reports:
  r['facts']['relevance']=classify(r['title'],r.get('text',''))
  from summaries import format_summary
  r['summary']=format_summary(r);r['summary_kind']='Structured source brief' if r.get('source_text',r.get('text','')) else 'Structured headline brief'
  decision=decisions.get(r['id'])
  if decision and decision['title']==r['title']:
   r['facts']['relevance']=decision['classification'];r['review_reason']=decision['reason'];r['relevance_reviewed']=True
 excluded=sum(r['facts']['relevance']=='excluded' for r in reports)
 reports=[r for r in reports if r['facts']['relevance']!='excluded']
 cases,pending=group_reports(reports,config.get('overrides'))
 db.execute('DELETE FROM cases');db.execute('DELETE FROM case_reports')
 for c in cases:
  db.execute('INSERT INTO cases VALUES(?,?)',(c['id'],json.dumps(c)))
  db.executemany('INSERT INTO case_reports VALUES(?,?)',[(c['id'],r['id']) for r in c['reports']])
 db.commit()
 # Full source bodies stay in the database; the public feed contains bounded excerpts and evidence.
 public=[{k:v for k,v in r.items() if k not in ('text','source_text')} for r in pending if r['facts']['relevance']!='excluded']
 return {'version':3,'generated_at':now,'state':state,'states':STATES,'cases':cases,'review':public,'report_count':len(reports),'runs':[dict(r) for r in db.execute('SELECT * FROM runs ORDER BY id DESC LIMIT 20')],'sources':[dict(r) for r in db.execute('SELECT * FROM source_state')],'calendar':'America/New_York','excluded_count':excluded,'audit':{'date':audit.get('review_date'),'reviewed':len(audit['items'])}}

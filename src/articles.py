"""Bounded public article reads with robots, SSRF checks and persistent caching."""
import ipaddress,json,re,socket,urllib.parse,urllib.robotparser
from google_search import Tree
BLOCKED_HOSTS=('google.com','youtube.com','youtu.be','facebook.com','instagram.com','tiktok.com')

def public_url(url):
 try:
  p=urllib.parse.urlsplit(url);host=p.hostname
  if p.scheme!='https' or not host or p.username or p.password or p.port not in (None,443):return False
  if any(host==h or host.endswith('.'+h) for h in BLOCKED_HOSTS):return False
  addresses=socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
  return bool(addresses) and all(ipaddress.ip_address(x[4][0]).is_global for x in addresses)
 except (ValueError,OSError):return False

def parse_article(raw):
 text=raw.decode('utf-8','replace')
 if re.search(r'unusual traffic|g-recaptcha|verify you are human|access denied|enable cookies to continue',text[:40000],re.I):return '', 'publisher challenge'
 tree=Tree();tree.feed(text)
 for node in tree.root.nodes():
  if node.tag=='meta' and node.attrs.get('property')=='og:type' and node.attrs.get('content','').startswith('video'):return '', 'video page'
 # Prefer structured publisher articleBody over navigation or comments.
 def walk(value):
  if isinstance(value,dict):
   typ=value.get('@type',[]);typ=[typ] if isinstance(typ,str) else typ
   if any(t in ('NewsArticle','Article','ReportageNewsArticle') for t in typ) and isinstance(value.get('articleBody'),str):return value['articleBody']
   for child in value.values():
    found=walk(child)
    if found:return found
  elif isinstance(value,list):
   for child in value:
    found=walk(child)
    if found:return found
  return ''
 for block in re.findall(r'<script[^>]+type=["\x27]application/ld\+json["\x27][^>]*>(.*?)</script>',text,re.S|re.I):
  try:
   body=walk(json.loads(block))
   if len(body)>100:return ' '.join(body.split())[:10000],'publisher article text'
  except (ValueError,TypeError):pass
 regions=[n for n in tree.root.nodes() if n.tag=='article'] or [n for n in tree.root.nodes() if n.tag=='main']
 paragraphs=[]
 for region in regions[:1]:
  for n in region.nodes():
   if n.tag!='p':continue
   parent=n.parent;hidden=False
   while parent and parent!=region:
    if parent.tag in ('aside','nav','footer','form') or re.search(r'comment|related|promo|advert',parent.attrs.get('class',''),re.I):hidden=True;break
    parent=parent.parent
   body=n.text()
   if not hidden and len(body)>45 and not re.search(r'accept.*cookies|subscribe to|sign up for|all rights reserved',body,re.I):paragraphs.append(body)
 body=' '.join(dict.fromkeys(paragraphs))[:10000]
 return (body,'publisher article text') if len(body)>150 else ('','no readable article text')

def retrieve(url,config,db,now,fetch,check=public_url):
 key='article:v2:'+url
 cached=db.execute('SELECT payload FROM cache WHERE key=? AND expires>?',(key,now)).fetchone()
 if cached:return json.loads(cached[0])
 result={'text':'','status':'unsupported or non-public source link','url':url}
 current=url
 for hop in range(3):
  if not check(current):break
  p=urllib.parse.urlsplit(current)
  if re.search(r'/(?:videos?|watch)(?:/|$)',p.path,re.I):result['status']='video page';break
  origin='https://'+p.netloc
  robotkey='robots:'+origin;hit=db.execute('SELECT payload FROM cache WHERE key=? AND expires>?',(robotkey,now)).fetchone()
  if hit:rules=json.loads(hit[0])
  else:
   code,_,raw=fetch(origin+'/robots.txt',config['user_agent'],200000)
   rules=raw.decode('utf-8','replace') if code==200 else 'User-agent: *\nDisallow:' if code==404 else 'User-agent: *\nDisallow: /'
   db.execute('INSERT OR REPLACE INTO cache VALUES(?,?,?)',(robotkey,json.dumps(rules),now+86400));db.commit()
  robot=urllib.robotparser.RobotFileParser();robot.parse(rules.splitlines())
  if not robot.can_fetch(config['user_agent'],current) or (robot.crawl_delay(config['user_agent']) or 0)>2:result['status']='publisher robots restriction';break
  code,headers,raw=fetch(current,config['user_agent'])
  if code in (301,302,303,307,308) and headers.get('location'):
   current=urllib.parse.urljoin(current,headers['location']);continue
  if code!=200:result['status']='publisher HTTP '+str(code);break
  if 'text/html' not in headers.get('content-type','text/html'):result['status']='non-HTML source';break
  body,status=parse_article(raw);result={'text':body,'status':status,'url':current};break
 db.execute('INSERT OR REPLACE INTO cache VALUES(?,?,?)',(key,json.dumps(result),now+86400));db.commit()
 return result

def hydrate(db,config,now,fetch):
 remaining=min(5,config.get('article_limit_per_run',5));read=0;available=0
 apply_supplements(db)
 rows=[json.loads(x[0]) for x in db.execute('SELECT payload FROM reports ORDER BY first_seen_at DESC')]
 rows.sort(key=lambda r:r.get('published_at') or 0,reverse=True)
 for row in rows:
  if row['facts']['relevance']=='excluded' or row.get('source_supplement') or (row.get('article_version')==3 and row.get('article_checked_at',0)>now-86400):continue
  if 'news.google.com/' in row['url'] and remaining>0:
   remaining-=1;read+=1
   try:direct=discover_publisher(row,config,db,now,fetch)
   except Exception:direct=None
   if direct:row['aggregator_url']=row['url'];row['url']=direct
  host=urllib.parse.urlsplit(row['url']).hostname or ''
  if any(host==h or host.endswith('.'+h) for h in BLOCKED_HOSTS):
   row['article_status']='Aggregator or video link; direct publisher text unavailable';row['article_checked_at']=now
  else:
   if remaining<=0:continue
   remaining-=1;read+=1
   try:result=retrieve(row['url'],config,db,now,fetch)
   except Exception:result={'text':'','status':'publisher request failed'}
   row['article_status']=result['status'];row['article_checked_at']=now
   if result['text']:
    row['source_text']=result['text'];row['text_kind']='publisher article text';available+=1
    from incidents import extract
    row['facts']=extract({**row,'text':row['source_text']});row['location_version']=3
  row['article_version']=3
  db.execute('UPDATE reports SET payload=? WHERE id=?',(json.dumps(row),row['id']));db.commit()
 return f'{read} publisher links checked; {available} readable articles'

def geocode_stored(db,config,now,fetch):
 from locations import census_match
 used=0
 for stored in db.execute('SELECT id,payload FROM reports').fetchall():
  row=json.loads(stored['payload']);loc=row['facts']['location']
  if not(loc.get('address') and loc.get('city') and loc.get('state')) or loc['precision']=='address':continue
  key='census-address:'+json.dumps([loc['address'],loc['city'],loc['state']]);hit=db.execute('SELECT payload FROM cache WHERE key=? AND expires>?',(key,now)).fetchone()
  if hit:resolved=json.loads(hit[0])
  else:
   if used>=min(5,config.get('geocode_limit_per_run',5)):continue
   used+=1
   def get_json(url):
    status,_,raw=fetch(url,config['user_agent'])
    if status!=200:raise ValueError('Geocoder unavailable')
    return json.loads(raw)
   try:resolved=census_match(loc,get_json)
   except Exception:resolved=None
   db.execute('INSERT OR REPLACE INTO cache VALUES(?,?,?)',(key,json.dumps(resolved),now+(2592000 if resolved else 86400)))
  if resolved and resolved.get('precision')=='address':row['facts']['location']=resolved;db.execute('UPDATE reports SET payload=? WHERE id=?',(json.dumps(row),stored['id']))
 db.commit()
 return used


def apply_supplements(db):
 from pathlib import Path
 from incidents import extract
 from locations import locate
 entries=json.loads((Path(__file__).resolve().parents[1]/'reference/source-supplements.json').read_text())
 bytitle={x['title']:x for x in entries}
 for stored in db.execute('SELECT id,payload FROM reports').fetchall():
  row=json.loads(stored['payload']);entry=bytitle.get(row['title'])
  if not entry:continue
  row['reviewed_details']={'time_reference':entry['time_reference'],'updates':entry['updates']}
  if row.get('source_supplement'):
   db.execute('UPDATE reports SET payload=? WHERE id=?',(json.dumps(row),stored['id']));continue
  row.update(source_text=entry['text'],source_supplement=entry['provenance'],article_status=entry['provenance'],url=entry['url'])
  row['facts']=extract({**row,'text':entry['text']})
  loc=locate('Shooting in '+entry['city']+', '+entry['state'])
  loc.update(street=entry['street'],basis='City center; street intersection is stated in the supplied publisher text. Exact intersection not geocoded.',match_key=None)
  row['facts']['location']=loc;row['location_version']=4
  row['ai_details']={'time_reference':entry['time_reference'],'updates':entry['updates']}
  db.execute('UPDATE reports SET payload=? WHERE id=?',(json.dumps(row),stored['id']))
 db.commit()

def discover_publisher(row,config,db,now,fetch):
 """Find matching article on the publisher's own homepage/RSS. No Google decoding service."""
 homes={'wkyc':'https://www.wkyc.com','fox4kc.com':'https://fox4kc.com','fox4':'https://fox4kc.com'}
 home=row.get('source_home') or homes.get(row.get('source','').casefold())
 if not home and re.fullmatch(r'[a-z0-9.-]+\.(?:com|org|net)',row.get('source','').casefold()):home='https://'+row['source'].casefold()
 if not home:return None
 key='publisher-discovery:'+home
 cached=db.execute('SELECT payload FROM cache WHERE key=? AND expires>?',(key,now)).fetchone()
 if cached:links=json.loads(cached[0])
 else:
  links=[]
  # Reuse all URL and robots checks; no challenges or paywalls are bypassed.
  pages=[]
  def capture(url,ua,limit=2000000):
   code,headers,raw=fetch(url,ua,limit)
   if code==200 and not url.endswith('/robots.txt'):pages.append((url,raw))
   return code,headers,raw
  retrieve(home,config,db,now,capture)
  for url,raw in pages[:1]:
   tree=Tree();tree.feed(raw.decode('utf-8','replace'))
   for n in tree.root.nodes():
    if n.tag=='a' and n.attrs.get('href'):links.append([n.text(),urllib.parse.urljoin(url,n.attrs['href'])])
   feeds=[urllib.parse.urljoin(url,n.attrs['href']) for n in tree.root.nodes() if n.tag=='link' and n.attrs.get('type') in ('application/rss+xml','application/atom+xml') and n.attrs.get('href')]
   for feed in feeds[:1]:
    feedpages=[]
    def readfeed(u,ua,limit=2000000):
     code,headers,raw=fetch(u,ua,limit)
     if code==200 and u==feed:feedpages.append(raw)
     return code,headers,raw
    retrieve(feed,config,db,now,readfeed)
    for body in feedpages:
     try:
      from collector import parse_feed
      links.extend([r['title'],r['url']] for r in parse_feed(body,row['source'],now))
     except Exception:pass
  db.execute('INSERT OR REPLACE INTO cache VALUES(?,?,?)',(key,json.dumps(links),now+1800));db.commit()
 def norm(s):return re.sub(r'[^a-z0-9]+',' ',s.casefold()).strip()
 matches={url for title,url in links if norm(title)==norm(row['title']) and public_url(url) and urllib.parse.urlsplit(url).hostname==urllib.parse.urlsplit(home).hostname}
 return next(iter(matches)) if len(matches)==1 else None

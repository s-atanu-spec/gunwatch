"""Parse one Google News search HTML response without executing page JavaScript."""
import hashlib,re,datetime as dt
from html.parser import HTMLParser
from urllib.parse import urlsplit,parse_qs

class Node:
 def __init__(self,tag='',attrs=(),parent=None):self.tag=tag;self.attrs=dict(attrs);self.parent=parent;self.children=[]
 def nodes(self):
  yield self
  for child in self.children:
   if isinstance(child,Node):yield from child.nodes()
 def text(self):
  if self.tag in ('script','style','noscript'):return ''
  return ' '.join(' '.join(x.text() if isinstance(x,Node) else x for x in self.children).split())
class Tree(HTMLParser):
 def __init__(self):super().__init__(convert_charrefs=True);self.root=Node();self.current=self.root
 def handle_starttag(self,tag,attrs):
  n=Node(tag,attrs,self.current);self.current.children.append(n)
  if tag not in ('area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'):self.current=n
 def handle_endtag(self,tag):
  n=self.current
  while n.parent:
   if n.tag==tag:self.current=n.parent;return
   n=n.parent
 def handle_data(self,data):self.current.children.append(data)

def destination(href):
 p=urlsplit(href)
 if p.path=='/url' and (not p.netloc or p.hostname in ('www.google.com','google.com')):
  values=parse_qs(p.query);href=(values.get('q') or values.get('url') or [''])[0];p=urlsplit(href)
 if p.scheme not in ('https','http') or not p.hostname or p.username or p.password:return None
 if p.hostname in ('google.com','www.google.com','news.google.com','accounts.google.com','support.google.com','policies.google.com','consent.google.com'):return None
 return href

def parse_search(raw,source,now,canonical):
 if len(raw)>2_000_000:raise ValueError('Oversized Google search response')
 text=raw.decode('utf-8','replace')
 if re.search(r'unusual traffic|g-recaptcha|before you continue to google|verify you are human|consent.google.com',text,re.I):raise ValueError('Google challenge or consent page; no bypass')
 tree=Tree();tree.feed(text);rows=[];seen=set()
 for a in tree.root.nodes():
  if a.tag!='a':continue
  url=destination(a.attrs.get('href',''))
  if not url:continue
  url=canonical(url)
  if not url or url in seen:continue
  heading=next((n for n in a.nodes() if n.tag in ('h2','h3') or n.attrs.get('role')=='heading' or 'vvjwJb' in n.attrs.get('class','').split()),None)
  if heading is None:continue
  title=heading.text()
  if len(title)<8:continue
  # Modern Google News cards wrap the headline, publisher, snippet and time in one anchor.
  # A legacy result can instead place its snippet in the nearest result-card ancestor.
  scope=a
  for _ in range(3):
   if any('GI74Re' in n.attrs.get('class','').split() for n in scope.nodes()):break
   if not scope.parent:break
   parent=scope.parent
   if sum(n.tag=='a' and bool(destination(n.attrs.get('href',''))) for n in parent.nodes())>1:break
   scope=parent
  snippet=next((n.text() for n in scope.nodes() if 'GI74Re' in n.attrs.get('class','').split()),'')
  publisher=next((n.text() for n in a.nodes() if 'MgUUmf' in n.attrs.get('class','').split()),urlsplit(url).hostname)
  published=None
  for n in scope.nodes():
   if n.tag=='time' and n.attrs.get('datetime'):
    try:
     value=dt.datetime.fromisoformat(n.attrs['datetime'].replace('Z','+00:00'))
     if value.tzinfo:published=int(value.timestamp())
    except ValueError:pass
  rows.append({'id':hashlib.sha256(url.encode()).hexdigest(),'url':url,'title':title[:1000],'source':publisher,'published_at':published,'text':snippet[:6000],'text_kind':'search snippet','discovery':source,'first_seen_at':now})
  seen.add(url)
  if len(rows)>=100:break
 if not rows:
  visible=tree.root.text()
  if re.search(r'did not match any (?:news )?(?:results|documents)|no (?:news )?results found',visible,re.I):return []
  raise ValueError('Google search HTML has no recognized news cards; layout or JavaScript requirement; no retries')
 return rows

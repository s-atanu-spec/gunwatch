import sys,unittest,tempfile,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from google_search import parse_search
from collector import canonical,collect,database,redirect_note
class GoogleSearch(unittest.TestCase):
 def parse(self,html):return parse_search(html.encode(),'Google direct',1000,canonical)
 def test_modern(self):
  r=self.parse('<a href="https://local.com/news"><div class="MgUUmf">Local News</div><div role="heading">Two injured in shooting in Austin</div><div class="GI74Re">Police said two people were injured.</div><time datetime="2026-09-27T10:00:00Z">Today</time></a>')[0]
  self.assertEqual(r['title'],'Two injured in shooting in Austin');self.assertEqual(r['source'],'Local News');self.assertEqual(r['text'],'Police said two people were injured.');self.assertIsNotNone(r['published_at'])
 def test_legacy(self):
  r=self.parse('<a href="/url?q=https%3A%2F%2Flocal.com%2Fstory%3Futm_source%3Dgoogle&amp;sa=U"><h3>Police investigate shooting</h3></a>')[0]
  self.assertEqual(r['url'],'https://local.com/story');self.assertIsNone(r['published_at'])
 def test_no_navigation(self):
  with self.assertRaises(ValueError):self.parse('<a href="https://support.google.com"><h3>Search help details</h3></a><a href="https://other.com">Privacy policy</a>')
 def test_unknown_layout(self):
  with self.assertRaises(ValueError):self.parse('<html>Please enable JavaScript</html>')
 def test_challenge(self):
  with self.assertRaises(ValueError):self.parse('<p>Our systems have detected unusual traffic</p>')
 def test_real_empty(self):self.assertEqual(self.parse('<p>Your search did not match any documents</p>'),[])
 def test_direct_failure_rss_continues(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=database(Path(tmp)/'db.sqlite');calls=[]
   cfg={'sources':[{'name':'HTML','type':'google_search','url':'https://www.google.com/search?q=test'},{'name':'RSS','url':'https://local.com/rss'}],'interval_seconds':1800,'user_agent':'Test','article_hosts':[],'article_limit_per_run':0,'geocode_limit_per_run':0}
   def fetch(url,ua):
    calls.append(url)
    if 'google' in url:return 429,{},b'blocked'
    return 200,{},b'<rss><channel><item><title>Police investigate shooting</title><link>https://local.com/story</link></item></channel></rss>'
   result=collect(db,cfg,1000,fetch);self.assertEqual(result['status'],'partial');self.assertEqual(len(calls),2);self.assertEqual(db.execute('select count(*) from reports').fetchone()[0],1)
   collect(db,cfg,1001,fetch);self.assertEqual(len(calls),2);self.assertGreaterEqual(db.execute('select next_allowed_at from source_state where url like "%google%"').fetchone()[0],4600)

 def test_redirect_diagnostic_redacts_tokens(self):
  self.assertEqual(redirect_note('https://www.google.com/search',{'location':'https://www.google.com/sorry/index?secret=hidden'}),'; redirect to www.google.com/sorry/')
  self.assertNotIn('secret',redirect_note('https://www.google.com/search',{'location':'https://consent.google.com/secret?token=hidden'}))
  self.assertEqual(redirect_note('https://www.google.com/search',{'location':'/search?q=hidden'}),'; redirect to www.google.com/search')

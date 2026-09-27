import json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from articles import parse_article,retrieve
from collector import database
from incidents import extract
from summaries import format_summary
class Articles(unittest.TestCase):
 def test_structured_article(self):
  body='One person was injured in a shooting in Austin, TX on Friday. Police closed Main Street while officers investigated the incident.'
  raw=('<script type="application/ld+json">'+json.dumps({'@type':'NewsArticle','articleBody':body})+'</script>').encode();self.assertEqual(parse_article(raw)[0],body)
 def test_video_and_challenge(self):
  self.assertFalse(parse_article(b'<meta property="og:type" content="video.other">')[0]);self.assertFalse(parse_article(b'Verify you are human')[0])
 def test_article_paragraph_not_navigation(self):
  raw=b'<nav><p>Navigation content ignored.</p></nav><article><p>A man was injured in a shooting in Austin, TX on Friday night, police said in a statement.</p><p>The shooting happened near Main Street and officers closed the road while investigators searched the area.</p></article>'
  self.assertIn('Austin',parse_article(raw)[0]);self.assertNotIn('Navigation',parse_article(raw)[0])
 def test_robots_denial_and_cached_result(self):
  with tempfile.TemporaryDirectory() as d:
   db=database(Path(d)/'db');calls=[]
   def fetch(*args):calls.append(args[0]);return 200,{},b'User-agent: *\nDisallow: /'
   r=retrieve('https://example.com/story',{'user_agent':'test'},db,1,fetch,lambda u:True);self.assertIn('robots',r['status']);retrieve('https://example.com/story',{'user_agent':'test'},db,2,fetch,lambda u:True);self.assertEqual(len(calls),1)
class Summaries(unittest.TestCase):
 def row(self,text):
  r={'title':'Shooting in Austin, TX','source':'Local News','text':text,'published_at':1790514000};r['facts']=extract(r);return r
 def test_event_date_and_second_line(self):
  r=self.row('Three people were injured in a shooting on Friday at 10:30 p.m. at 120 Main Street in Austin, TX.');r['ai_details']={'time_reference':'Friday at 10:30 p.m.','updates':['Police closed Main Street.']};s=format_summary(r);self.assertTrue(s.startswith('3 people were injured'));self.assertIn('Friday at 10:30 p.m.',s);self.assertIn('120 Main Street',s);self.assertIn('\nReported update:',s);self.assertNotIn('published on',s)
 def test_publication_fallback_and_unknown(self):
  r=self.row('Police reported gunfire in Austin, TX.');s=format_summary(r);self.assertTrue(s.startswith('According to a report from Local News published on'));self.assertNotIn('0 people',s);self.assertIn('Texas',s)
 def test_missing_publication_not_invented(self):
  r=self.row('');r['published_at']=None;self.assertIn('publication time unavailable',format_summary(r));self.assertIn('Headline only',format_summary(r))

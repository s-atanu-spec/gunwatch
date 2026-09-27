import copy,datetime as dt,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from locations import locate,census_match
from incidents import extract,duplicate,group_reports,casualties,event_time
from collector import database,collect,export,parse_feed,canonical
PUB=int(dt.datetime(2026,9,27,18,tzinfo=dt.timezone.utc).timestamp())
def report(i=1,street='120 Main Street',clock='10:30 p.m.',injured='two',date='September 26, 2026'):
 r={'id':str(i).zfill(64),'url':f'https://example.com/{i}','source':'Test source','title':'Police investigate fatal shooting in Austin, TX','published_at':PUB,'first_seen_at':PUB+i,'text':f'A shooting at {street} in Austin, TX on {date} at {clock} left one person killed and {injured} people injured.','summary':'A source-backed test excerpt.','summary_kind':'source excerpt'};r['facts']=extract(r);return r
class Locations(unittest.TestCase):
 def test_city(self):
  l=locate('Shooting in Austin, TX at 120 Main Street');self.assertEqual(l['city'],'Austin');self.assertEqual(l['address'],'120 Main Street');self.assertEqual(l['pin_color'],'yellow')
 def test_county(self):
  l=locate('Shooting in Travis County, TX near Main Street');self.assertEqual(l['county'],'Travis County');self.assertEqual(l['pin_color'],'yellow')
 def test_city_without_state(self):self.assertEqual(locate('Shooting in Chicago')['state'],'IL')
 def test_ambiguous(self):self.assertIsNone(locate('Shooting in Springfield')['lat'])
 def test_multiple(self):self.assertIsNone(locate('Shooting in Austin, TX; suspect arrested in Boston, MA')['lat'])
 def test_duplicate_place(self):self.assertEqual(locate('Shooting in Mount Olive, AL')['precision'],'state')
 def test_area(self):self.assertEqual(locate('Shooting in Austin, TX in the Hyde Park neighborhood')['area'],'Hyde Park')
 def test_block_not_exact(self):
  l=locate('Shooting in Austin, TX in the 1200 block of Main Street');self.assertIsNone(l['address']);self.assertIsNotNone(l['match_key'])
 def test_address_geocode(self):
  l=locate('Shooting in Austin, TX at 120 Main Street');g=census_match(l,lambda _: {'result':{'addressMatches':[{'matchedAddress':'120 MAIN ST, AUSTIN, TX','addressComponents':{'city':'Austin','state':'TX'},'coordinates':{'x':-97.7,'y':30.2}}]}});self.assertEqual(g['pin_color'],'red')
 def test_geocode_wrong_state(self):
  l=locate('Shooting in Austin, TX at 120 Main Street');g=census_match(l,lambda _: {'result':{'addressMatches':[{'addressComponents':{'city':'Austin','state':'MA'},'coordinates':{'x':-97.7,'y':30.2}}]}});self.assertEqual(g['pin_color'],'yellow')
class Incidents(unittest.TestCase):
 def test_merge_different_urls(self):
  a,b=report(1),report(2);self.assertTrue(duplicate(a['facts'],b['facts']));cases,pending=group_reports([a,b]);self.assertEqual(len(cases),1);self.assertEqual(cases[0]['report_count'],2);self.assertFalse(pending)
 def test_different_street(self):self.assertFalse(duplicate(report(1)['facts'],report(2,street='300 Elm Street')['facts']))
 def test_different_time(self):self.assertFalse(duplicate(report(1)['facts'],report(2,clock='11:30 p.m.')['facts']))
 def test_different_date(self):self.assertFalse(duplicate(report(1)['facts'],report(2,date='September 25, 2026')['facts']))
 def test_different_casualties(self):self.assertFalse(duplicate(report(1)['facts'],report(2,injured='three')['facts']))
 def test_unknown_not_zero(self):
  c,_=casualties('One person killed');self.assertIsNone(c['injured']);c,_=casualties('No injuries reported');self.assertEqual(c['injured'],0)
 def test_missing_time_not_publication(self):
  r=report();r['text']='A shooting in Austin, TX left one person killed.';r['facts']=extract(r);cases,pending=group_reports([r]);self.assertFalse(cases);self.assertEqual(len(pending),1)
 def test_relative_weekday(self):self.assertEqual(event_time('The shooting happened Friday at 10:30 p.m.',PUB)['date'],'2026-09-25')
 def test_publication_not_event_date(self):self.assertIsNone(event_time('Police investigate a shooting.',PUB)['date'])
 def test_no_transitive_merge(self):
  rows=[report(1,clock='10:00 p.m.'),report(2,clock='10:25 p.m.'),report(3,clock='10:50 p.m.')];cases,_=group_reports(rows);self.assertEqual(len(cases),2)
 def test_street_abbreviation(self):self.assertTrue(duplicate(report(1,street='120 Main St')['facts'],report(2)['facts']))
class Collector(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=database(Path(self.tmp.name)/'db.sqlite');self.config={'sources':[{'name':'Fixture','url':'https://example.com/rss'}],'interval_seconds':1800,'user_agent':'Test','article_limit_per_run':0,'geocode_limit_per_run':0,'article_hosts':[],'overrides':[]}
 def tearDown(self):self.db.close();self.tmp.cleanup()
 def xml(self):return b'<rss><channel><item><title>Police investigate shooting in Austin, TX</title><link>https://example.com/one</link><pubDate>Sun, 27 Sep 2026 18:00:00 GMT</pubDate><description>A shooting at 120 Main Street in Austin, TX on September 26, 2026 at 10:30 p.m. left one person killed and two people injured.</description></item></channel></rss>'
 def test_cooldown_and_history(self):
  calls=[]
  def fetch(*a):calls.append(a);return 200,{},self.xml()
  collect(self.db,self.config,PUB,fetch);collect(self.db,self.config,PUB+1799,fetch);self.assertEqual(len(calls),1);collect(self.db,self.config,PUB+1800,fetch);self.assertEqual(len(calls),2);self.assertEqual(self.db.execute('SELECT COUNT(*) FROM reports').fetchone()[0],1)
  data=export(self.db,self.config,{},PUB);self.assertEqual(len(data['cases']),1);self.assertEqual(data['report_count'],1)
 def test_source_cooldown_is_not_success(self):
  collect(self.db,self.config,PUB,lambda *a:(429,{},b''))
  result=collect(self.db,self.config,PUB+1800,lambda *a: self.fail('Backoff must not fetch'))
  self.assertEqual(result['status'],'cooldown')
 def test_backoff(self):
  collect(self.db,self.config,PUB,lambda *a:(429,{'retry-after':'7200'},b''));self.assertEqual(self.db.execute('SELECT next_allowed_at FROM source_state').fetchone()[0],PUB+7200)
 def test_malformed_retains_data(self):
  collect(self.db,self.config,PUB,lambda *a:(200,{},self.xml()));collect(self.db,self.config,PUB+1800,lambda *a:(200,{},b'not RSS'));self.assertEqual(self.db.execute('SELECT COUNT(*) FROM reports').fetchone()[0],1)
 def test_unsafe_xml(self):
  with self.assertRaises(ValueError):parse_feed(b'<!DOCTYPE rss><rss/>','Fixture',PUB)
 def test_link_list_not_summary(self):
  rows=parse_feed(b'<rss><channel><item><title>Shooting</title><link>https://example.com/x</link><description>&lt;ol&gt;&lt;li&gt;Publisher headline link&lt;/li&gt;&lt;/ol&gt;</description></item></channel></rss>','Fixture',PUB);self.assertEqual(rows[0]['text'],'')
 def test_unsafe_url(self):self.assertIsNone(canonical('javascript:alert(1)'))
if __name__=='__main__':unittest.main()

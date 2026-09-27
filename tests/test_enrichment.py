import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from enrichment import validate,enrich
from collector import database,refresh_locations
from incidents import extract
from locations import locate
class GeographyUpgrade(unittest.TestCase):
 def test_punctuation_and_headline_forms(self):
  for text,place in [('Shooting in San Francisco.','San Francisco'),('Fort Worth shooting leaves man dead.','Fort Worth'),('Three sought after shooting in Roanoke County.','Roanoke County'),('Shooting at Winston-Salem gas station.','Winston-Salem')]:
   l=locate(text);self.assertEqual(l['city'] or l['county'],place)
 def test_no_partial_venue_or_direction_matches(self):
  for text in ['Man injured in North Philadelphia shooting','Two injured in shooting at Caraway Speedway','Shooting near Lamb and Lake Mead Blvd','Sacramento shooting near Arden Way','Shooting on Bay Bridge near Treasure Island']:
   self.assertIsNone(locate(text)['lat'],text)
 def test_same_state_ambiguity(self):
  l=locate('Shooting in Kailua.');self.assertEqual(l['state'],'HI');self.assertEqual(l['precision'],'state');self.assertIsNone(l['city'])
 def test_multi_state_ambiguity(self):self.assertIsNone(locate('Shooting in Greensboro.')['state'])
 def test_reprocess_old_record(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=database(Path(tmp)/'db');r={'title':'Shooting in San Francisco.','text':'','facts':{'location':{'state':None}}};db.execute('insert into reports values(?,?,?,?,?)',('one','https://x.com',1,1,json.dumps(r)));db.commit();refresh_locations(db)
   row=json.loads(db.execute('select payload from reports').fetchone()[0]);self.assertEqual(row['facts']['location']['state'],'CA')
class AIValidation(unittest.TestCase):
 def result(self,**kwargs):
  r={'place':'Austin','state':'TX','evidence':'Shooting in Austin, TX.','state_evidence':'Austin, TX','summary_quotes':[],'ambiguous':False};r.update(kwargs);return r
 def test_validated_location(self):self.assertEqual(validate(self.result(),{'headline':'Shooting in Austin, TX.','excerpt':''})['location']['state'],'TX')
 def test_no_hallucinated_state(self):self.assertNotIn('location',validate(self.result(evidence='Shooting in Austin.',state_evidence=None),{'headline':'Shooting in Austin.','excerpt':''}))
 def test_wrong_evidence(self):self.assertNotIn('location',validate(self.result(),{'headline':'Shooting in Boston, MA.','excerpt':''}))
 def test_summary_must_be_exact(self):
  with self.assertRaises(ValueError):validate(self.result(summary_quotes=['Two killed.']),{'headline':'Shooting in Austin, TX.','excerpt':'One person injured.'})
 def test_headline_only_no_summary(self):
  with self.assertRaises(ValueError):validate(self.result(summary_quotes=['Shooting in Austin, TX.']),{'headline':'Shooting in Austin, TX.','excerpt':''})
 def test_ambiguous_location_rejected(self):self.assertNotIn('location',validate(self.result(ambiguous=True),{'headline':'Shooting in Austin, TX.','excerpt':''}))
 def test_duplicate_records_cached_and_error_backoff(self):
  with tempfile.TemporaryDirectory() as tmp,patch.dict('os.environ',{'GROQ_API_KEY':'fake-test-key'}),patch('enrichment.time.sleep'):
   db=database(Path(tmp)/'db');calls=[]
   for i in range(2):
    r={'id':str(i),'title':'Shooting in Austin, TX.','text':'','summary':'Existing','summary_kind':'headline only'};r['facts']=extract(r)
    db.execute('insert into reports values(?,?,?,?,?)',(str(i),'https://x.com/'+str(i),i,i,json.dumps(r)))
   db.commit();cfg={'ai':{'enabled':True,'max_reports_per_run':8}}
   def call(*args):calls.append(args);return self.result()
   enrich(db,cfg,1000,call);self.assertEqual(len(calls),1);enrich(db,cfg,1001,call);self.assertEqual(len(calls),1)
   db.execute('delete from ai_cache');db.commit()
   def fail(*args):raise RuntimeError('AI provider HTTP 429')
   self.assertIn('backoff',enrich(db,cfg,1100,fail));self.assertEqual(enrich(db,cfg,1101,call),'provider cooldown')

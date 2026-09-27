import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from locations import locate_report,STATES
from collector import database,export
from articles import apply_supplements
from summaries import format_summary
from history import parse
from enrichment import infer
class Followup(unittest.TestCase):
 def test_cleveland_context_and_ambiguity(self):
  row={'title':'Suspect arrested after woman injured in Cleveland shooting','source':'WKYC'}
  loc=locate_report(row);self.assertEqual((loc['city'],loc['state']),('Cleveland','OH'));self.assertEqual(loc['precision'],'city');self.assertIn('inferred',loc['basis'])
  row['source']='Unknown';loc=locate_report(row);self.assertIsNone(loc['lat']);self.assertEqual(loc['named_place'],'Cleveland')
 def test_complete_future_year_only(self):
  rows=[{'YEAR':'2025','STATE':s,'DEATHS':'10','RATE':'1.0'} for s in STATES]
  rows.append({'YEAR':'2026','STATE':'AL','DEATHS':'10','RATE':'1.0'})
  self.assertEqual(len(parse(json.dumps({'data':rows}))),51)
  with self.assertRaises(ValueError):parse(json.dumps({'data':rows[:3]}))
 def test_screenshot_summary_and_public_diagnostics(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=database(Path(tmp)/'db');row={'id':'x','title':'Woman killed in overnight shooting near 79th, Wornall Road','source':'FOX4','url':'https://example.com/a','published_at':1790507940,'first_seen_at':1,'facts':{'location':{}},'summary':'','summary_kind':''}
   db.execute('insert into reports values(?,?,?,?,?)',('x',row['url'],1,1,json.dumps(row)));db.commit();apply_supplements(db)
   saved=json.loads(db.execute('select payload from reports').fetchone()[0]);summary=format_summary(saved)
   for value in ('One person was killed','Sunday','1:30 a.m.','West 79th Street','Kansas City','Missouri','no suspects'):self.assertIn(value,summary)
   public=export(db,{'overrides':[]},{'ai_status':'test secret diagnostic','status':'partial'},1)
   self.assertNotIn('ai_status',public['state']);self.assertNotIn('ai_details',public['review'][0]);self.assertNotIn('source_text',public['review'][0])
 def test_sdk_endpoint_no_retries_and_structured_response(self):
  calls={}
  class Client:
   def __init__(self,**kwargs):calls.update(kwargs);self.responses=self
   def __enter__(self):return self
   def __exit__(self,*args):pass
   def create(self,**kwargs):calls['payload']=kwargs;return SimpleNamespace(output_text='{"ok":true}')
  with patch.dict(sys.modules,{'openai':SimpleNamespace(OpenAI=Client,APIStatusError=type('APIStatusError',(Exception,),{}))}):
   self.assertEqual(infer({'headline':'test','excerpt':'test'},'fake-key'),{'ok':True})
  self.assertEqual(calls['base_url'],'https://api.groq.com/openai/v1');self.assertEqual(calls['max_retries'],0);self.assertFalse(calls['payload']['store'])

import importlib.util,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('runner',ROOT/'scripts/run.py');runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
class Reservation(unittest.TestCase):
 def test_failed_remote_claim_never_collects(self):
  with tempfile.TemporaryDirectory() as d,patch.object(sys,'argv',['run.py','--github','--state-dir',d,'--output',d+'/out']),patch.object(runner,'checkout_state',return_value=False),patch.object(runner,'persist',side_effect=RuntimeError('Remote ref conflict')),patch.object(runner,'collect') as collect:
   with self.assertRaises(RuntimeError):runner.main()
   collect.assert_not_called();self.assertGreater(json.loads((Path(d)/'state.json').read_text())['next_allowed_at'],0)
 def test_existing_cooldown_does_not_fetch(self):
  with tempfile.TemporaryDirectory() as d:
   state={'next_allowed_at':9999999999,'last_attempt_at':1,'last_success_at':None,'status':'error'};(Path(d)/'state.json').write_text(json.dumps(state))
   with patch.object(sys,'argv',['run.py','--state-dir',d,'--output',d+'/out']),patch.object(runner,'collect') as collect:runner.main();collect.assert_not_called()
   self.assertEqual(json.loads((Path(d)/'state.json').read_text()),state)

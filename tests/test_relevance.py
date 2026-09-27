import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from incidents import classify
class Relevance(unittest.TestCase):
 def test_foreign(self):
  self.assertEqual(classify('Two mass shootings in South Africa leave 27 dead',''),'excluded')
 def test_topic(self):self.assertEqual(classify('Mass Shooting',''),'excluded')
 def test_non_firearm(self):self.assertEqual(classify('Mistress testifies in murder trial',''),'excluded')
 def test_shooting(self):self.assertEqual(classify('Shooting investigation underway in Greensboro',''),'likely')
 def test_follow_up(self):self.assertEqual(classify('Vigil marks three years since fatal shooting',''),'follow_up')
 def test_sports(self):self.assertEqual(classify('Team signs a new shooting guard',''),'excluded')

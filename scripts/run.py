#!/usr/bin/env python3
"""One Actions job owns collection, state persistence and site generation."""
import argparse,fcntl,json,os,shutil,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from collector import database,collect,export,refresh_locations
from enrichment import enrich

def git(*args,cwd=ROOT):
 return subprocess.run(['git',*args],cwd=cwd,text=True,capture_output=True,check=True).stdout.strip()
def checkout_state(folder):
 refs=git('ls-remote','--heads','origin','collector-state')
 if refs:
  git('fetch','origin','collector-state');git('worktree','add','--detach',str(folder),'FETCH_HEAD')
 else:
  git('worktree','add','--detach',str(folder),'HEAD');git('checkout','--orphan','collector-state',cwd=folder)
  git('rm','-rf','--ignore-unmatch','.',cwd=folder)
 return bool(refs)
def persist(folder,message):
 git('add','state.json','gunwatch.sqlite',cwd=folder) if (folder/'gunwatch.sqlite').exists() else git('add','state.json',cwd=folder)
 if subprocess.run(['git','diff','--cached','--quiet'],cwd=folder).returncode==0:return
 git('-c','user.name=github-actions[bot]','-c','user.email=41898282+github-actions[bot]@users.noreply.github.com','commit','-m',message,cwd=folder)
 # No force push: a competing reservation must fail BEFORE any upstream request.
 git('push','origin','HEAD:refs/heads/collector-state',cwd=folder)
def write_json(path,data):
 temp=path.with_suffix('.tmp');temp.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')));temp.replace(path)
def build(db,config,state,now,out):
 shutil.copytree(ROOT/'site',out,dirs_exist_ok=True);(out/'data').mkdir(exist_ok=True)
 write_json(out/'data/latest.json',export(db,config,state,now));(out/'.nojekyll').touch()
def main():
 p=argparse.ArgumentParser();p.add_argument('--github',action='store_true');p.add_argument('--build-only',action='store_true');p.add_argument('--state-dir',type=Path,default=ROOT/'work');p.add_argument('--output',type=Path,default=ROOT/'output');args=p.parse_args()
 config=json.loads((ROOT/'config.json').read_text());folder=args.state_dir.resolve();existing=False
 if args.github:existing=checkout_state(folder)
 folder.mkdir(parents=True,exist_ok=True)
 with open(folder/'collector.lock','w') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  statefile=folder/'state.json';dbfile=folder/'gunwatch.sqlite'
  if existing and not statefile.exists():raise RuntimeError('Existing state branch is incomplete; refusing to reset cooldown')
  state=json.loads(statefile.read_text()) if statefile.exists() else {'next_allowed_at':0,'last_attempt_at':None,'last_success_at':None,'status':'awaiting first collection'}
  if existing and state.get('last_success_at') and not dbfile.exists():raise RuntimeError('Persistent database missing; refusing to reset history')
  db=database(dbfile);now=int(time.time())
  if not args.build_only and now>=state['next_allowed_at']:
   state.update(next_allowed_at=now+max(1800,config['interval_seconds']),last_attempt_at=now,status='running')
   write_json(statefile,state);db.commit()
   if args.github:persist(folder,'Reserve collection cooldown')
   # No network access is possible before the durable claim above succeeds.
   try:
    result=collect(db,config,now);state['status']=result['status']
    refresh_locations(db)
    state['ai_status']=enrich(db,config,now)
    db.execute('UPDATE runs SET message=message || ? WHERE id=(SELECT MAX(id) FROM runs)',('; AI: '+state['ai_status'],));db.commit()
    if result['status'] in ('success','partial'):state['last_success_at']=now
   except Exception as exc:
    state['status']='error';state['message']=str(exc)[:180]
   write_json(statefile,state)
  build(db,config,state,int(time.time()),args.output);db.close()
  write_json(statefile,state)
  if args.github:persist(folder,'Save collected reports, incident groups and run status')
  print(json.dumps({'status':state['status'],'next_allowed_at':state['next_allowed_at'],'output':str(args.output)}))
if __name__=='__main__':main()

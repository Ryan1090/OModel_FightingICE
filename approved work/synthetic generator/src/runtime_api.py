"""One installation of the final selector, witness and engineering controls."""
import atexit,functools,inspect,os,shutil,types
from pathlib import Path
import common as c
from gmtv.schema import sha
def context_for(item):
 from selection_override import context_for
 return context_for(item)
def runtime_source(relative):
 """Resolve and verify the shared approved engine relative to this package."""
 relative=Path(relative)
 if relative.is_absolute() or '..' in relative.parts:raise ValueError('Invalid runtime asset path')
 if relative.as_posix()=='FightingICE.jar':
  from gmtv.engine import ENGINE_SHA
  path=c.BASE.parent/'engine/observation_enabled_v1/FightingICE.observation-enabled.jar'
  if not path.is_file():raise RuntimeError('Shared approved engine missing: '+str(path))
  if sha(path)!=ENGINE_SHA:raise RuntimeError('Shared approved engine checksum mismatch: '+str(path))
  return path
 return c.BASE/'assets/runtime'/relative

def directory_link(target,source):
 import _winapi
 target=Path(target);source=Path(source)
 if not target.resolve().is_relative_to(c.HOT.resolve()) or not source.resolve().is_relative_to(c.HOT.resolve()):raise RuntimeError('Graphics path outside run')
 if target.exists() or target.is_junction():
  if target.resolve()!=source.resolve():raise RuntimeError('Unexpected existing graphics path')
  return
 try:_winapi.CreateJunction(str(source.resolve()),str(target.absolute()))
 except FileExistsError:
  if target.resolve()!=source.resolve():raise
 if not target.is_junction() or target.resolve()!=source.resolve():raise RuntimeError('Graphics junction verification failed')
def provision(home):
 home=Path(home)
 if not home.resolve().is_relative_to(c.HOT.resolve()):raise RuntimeError('Runtime outside this run')
 import json
 from gmtv.storage import atomic
 source=c.BASE/'assets';m=json.loads((source/'runtime_manifest.json').read_text());files=[]
 # Stage immutable bytes on the run's drive once, then preserve the original
 # hard-link provisioning behaviour even when the package lives on D:.
 from oracle_cache import byte_lock
 from gmtv.schema import digest
 mirror=c.HOT/'runtime_assets';ready=c.HOT/'RUNTIME_ASSETS_READY.json';identity=digest(m)
 if not ready.exists():
  with byte_lock(c.HOT/'RUNTIME_ASSETS.lock'):
   if not ready.exists():
    for row in m['files']:
     origin=runtime_source(row['path']);target=mirror/row['path'];target.parent.mkdir(parents=True,exist_ok=True)
     if not target.exists():shutil.copyfile(origin,target)
     if sha(target)!=row['sha256']:raise RuntimeError('Run asset staging mismatch')
    atomic(ready,{'manifest_sha256':identity,'files':len(m['files'])})
 if json.loads(ready.read_text())['manifest_sha256']!=identity:raise RuntimeError('Run asset manifest mismatch')
 for row in m['files']:
  origin=mirror/row['path'];target=home/'runtime'/row['path'];target.parent.mkdir(parents=True,exist_ok=True)
  if not target.exists():
   if target.name in {'Motion.csv','gSetting.txt'}:shutil.copyfile(origin,target)
   else:
    try:os.link(origin,target)
    except OSError:shutil.copyfile(origin,target)
  if sha(target)!=row['sha256']:raise RuntimeError('Private runtime asset mismatch: '+str(target))
  files.append({'destination':str(target),'sha256':row['sha256']})
 for rel in ('data/ai','data/aiData','log'):(home/'runtime'/rel).mkdir(parents=True,exist_ok=True)
 for root in c.load_config()['roots']:
  for name in ('Motion.csv','gSetting.txt'):
   p=home/'stock_reference'/root/name;p.parent.mkdir(parents=True,exist_ok=True)
   if not p.exists():shutil.copyfile(source/'stock_reference'/root/name,p)
   if sha(p)!=sha(source/'stock_reference'/root/name):raise RuntimeError('Stock reference mismatch')
 atomic(home/'ASSET_MANIFEST.json',{'runtime':str(home/'runtime'),'files':files,'engine_unmodified':True,'stock_only':True})
 return home
@functools.lru_cache(maxsize=1)
def install():
 import validation_v8 as api
 import gmtv.materialise as materialise,gmtv.storage as storage,gmtv.status as status
 import reach_witness,oracle_cache,resources
 materialise.directory_link=directory_link
 # The only non-durable publications are non-authoritative display status.
 source=inspect.getsource(storage.atomic)
 if source.count('os.fsync(stream.fileno())')!=2:raise RuntimeError('Display writer precondition changed')
 source=source.replace('def atomic(','def atomic_display(').replace('os.fsync(stream.fileno())','None')
 scope=dict(vars(storage));ns={};exec(compile(source,__file__,'exec'),scope,ns)
 original_status=status.best_effort_status
 text=inspect.getsource(original_status).replace('def best_effort_status(','def best_effort_display(').replace('try:atomic(path,payload);return True','try:atomic_display(path,payload);return True')
 local={};exec(compile(text,__file__,'exec'),{**vars(status),'atomic_display':ns['atomic_display']},local)
 def writer(path,payload):
  p=Path(path)
  return local['best_effort_display'](path,payload) if p.name.lower()=='status.json' and p.resolve().is_relative_to(c.HOT.resolve()) else original_status(path,payload)
 status.best_effort_status=writer
 oracle_cache.install(c.HOT/'compiled_oracle_cache')
 sampler=resources.install(c.HOT);atexit.register(sampler.close)
 original=api.s.geometry_effect
 async def geometry(ex,inputs,group,changes):
  return await reach_witness.geometry(ex,inputs,group,changes,original=original,metadata=api.s.metadata,is_projectile=api.s.is_projectile)
 api.s.geometry_effect=geometry
 return api
def validate(*a,**kw):
 c.verify_release();api=install()
 kw['context']={**(kw.get('context') or {}),'release':sha(c.RELEASE),'reach_witness':sha(Path(__file__).with_name('reach_witness.py')),'run_configuration':c.load_config()['configuration_sha256']}
 return api.validate(*a,**kw)

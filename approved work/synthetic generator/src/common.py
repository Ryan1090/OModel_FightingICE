"""Single-release production paths and integrity; no historical run imports."""
import importlib,importlib.util,json,os,sys,ctypes
from pathlib import Path
from settings import current,PACKAGE
from gmtv.schema import sha,digest
from gmtv.storage import atomic
HERE=Path(__file__).resolve().parent;BASE=PACKAGE;OUT=PACKAGE/'provenance'
import generator as original
HOT=Path(current()['authorised_hot']);CONFIG=HOT/'RUN_CONFIG.json';RELEASE=PACKAGE/'RELEASE.json'
POOLS=('A','B','C_iid','C_near','C_far');QUOTAS=current()['quotas_per_root'];TOTAL=5*sum(QUOTAS.values());NAMESPACE=current()['production_namespace']
ALIASES={'generator_production':'generator','api_r2':'runtime_api','io_release_v30':'runtime_api'}
def local_module(name):
 name=ALIASES.get(name,name);key='_production_v28_'+name;path=HERE/(name+'.py')
 if name=='generator':return original
 if name=='runtime_api':return importlib.import_module('runtime_api')
 if key in sys.modules:return sys.modules[key]
 spec=importlib.util.spec_from_file_location(key,path);m=importlib.util.module_from_spec(spec);sys.modules[key]=m;spec.loader.exec_module(m);return m
def load_config():return current()
def verify_release(config=None):
 r=json.loads(RELEASE.read_text());h=r.pop('checksum')
 if digest(r)!=h:raise RuntimeError('Release manifest checksum mismatch')
 for p,h in r['files'].items():
  # Runtime assets are verified byte-for-byte at provisioning and by Check;
  # their hashed manifest is still verified at every screen.
  if p.startswith('assets/runtime/'):continue
  if sha(PACKAGE/p)!=h:raise RuntimeError('Frozen release changed: '+p)
 return r
def authorise_output(path,namespace,config):
 p=Path(path).resolve()
 if namespace!=NAMESPACE or not config.get('production_write_enabled') or config.get('release_checksum')!=current()['release_checksum'] or Path(config['authorised_hot']).resolve()!=HOT.resolve() or not p.is_relative_to(HOT.resolve()):raise RuntimeError('Output outside this run denied')
def item_config(c,item):
 return {**c,'runtime_reference_vectors':item['admission_references'],'configuration_sha256':digest({'production_configuration':c['configuration_sha256'],'admission_references':item['admission_references'],'execution_policy_sha256':c['execution_policy_sha256']})}
def item_binding(c,item):
 cc=item_config(c,item);adapted=digest({'source_configuration':cc['configuration_sha256'],'V28_R4_engine_startup_adapter':sha(HERE/'admission_r4.py'),'timeout_retries':0})
 return digest({'config':adapted,'job':item})
def strata(pool):
 if pool=='C_near':return [(p,s,a,b) for p,s in ((0,1),(1,0),(2,3),(3,2)) for a in (-1,1) for b in (-1,1)]
 return [(p,s) for p in range(5) for s in (-1,1)]
def stratum_target(pool):return QUOTAS[pool]//len(strata(pool))
def actual_stratum(meta,pool):return tuple(meta[k] for k in ('primary','secondary','sign','secondary_sign')) if pool=='C_near' else (meta['primary'],meta['sign'])
def candidate_id(root,pool,slot,draw):return pool+'-'+root+'-'+digest([list(slot),draw])[:20]
def pid_alive(pid):
 if not pid:return False
 kernel=ctypes.windll.kernel32;kernel.OpenProcess.restype=ctypes.c_void_p;handle=kernel.OpenProcess(0x1000,False,int(pid))
 if not handle:return False
 try:
  code=ctypes.c_ulong();return bool(kernel.GetExitCodeProcess(ctypes.c_void_p(handle),ctypes.byref(code)) and code.value==259)
 finally:kernel.CloseHandle(ctypes.c_void_p(handle))
def summary_numbers(values):
 import numpy as np
 return {'n':len(values),'min':float(np.min(values)),'q1':float(np.percentile(values,25)),'median':float(np.median(values)),'q3':float(np.percentile(values,75)),'p90':float(np.percentile(values,90)),'max':float(np.max(values))} if values else {'n':0}

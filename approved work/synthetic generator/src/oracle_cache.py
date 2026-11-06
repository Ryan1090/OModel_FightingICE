"""Run-local immutable compiled-artifact reuse; actual decoder is unchanged."""
import contextlib,functools,hashlib,json,os,shutil,subprocess,tempfile,time,uuid
from pathlib import Path

METRICS=[]
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def durable_bytes(path,data):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
 try:
  with tmp.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
  os.replace(tmp,path)
 finally:
  if tmp.exists():tmp.unlink()

@functools.lru_cache(maxsize=8)
def version_for(executable,executable_sha,release_sha):
 p=subprocess.run([executable,'-version'],capture_output=True,text=True,timeout=45,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 if p.returncode:raise RuntimeError('CommandOracle compiler identity failed: '+p.stderr)
 return {'version':(p.stdout+p.stderr).strip(),'executable_sha256':executable_sha,'jdk_release_sha256':release_sha}

def compiler_identity():
 exe=shutil.which('javac')
 if not exe:raise RuntimeError('CommandOracle compiler not found')
 exe=Path(exe).resolve();release=exe.parent.parent/'release'
 return version_for(str(exe),sha(exe),sha(release) if release.exists() else None)

def inputs(runtime,source):
 runtime=Path(runtime);entries=[{'group':0,'name':'FightingICE.jar','sha256':sha(runtime/'FightingICE.jar')}]
 # The original two wildcard classpath entries expand JARs only. Bind all
 # regular contents as well, conservatively invalidating for any other change.
 for group,rel in enumerate(('lib','lib/grpc'),1):
  folder=runtime/rel
  if not folder.is_dir():entries.append({'group':group,'missing':rel});continue
  for p in sorted(folder.iterdir(),key=lambda p:p.name):
   if p.is_file():entries.append({'group':group,'name':rel+'/'+p.name,'sha256':sha(p)})
 return {'schema':'command-oracle-compiled-v33','source_sha256':sha(source),'classpath':entries,'compiler':compiler_identity()}

@contextlib.contextmanager
def byte_lock(path,timeout=50):
 """Permanent non-truncated byte lock; never write before acquiring a lock."""
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 if not path.exists():
  temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.init')
  try:
   with temp.open('xb') as f:f.write(b'0');f.flush();os.fsync(f.fileno())
   try:os.link(temp,path)
   except FileExistsError:pass
  finally:temp.unlink(missing_ok=True)
 with path.open('r+b') as f:
  deadline=time.monotonic()+timeout
  while True:
   try:
    f.seek(0)
    if os.name=='nt':
     import msvcrt
     msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
    else:
     import fcntl
     fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    break
   except OSError:
    if time.monotonic()>=deadline:raise RuntimeError('CommandOracle compilation cache lock timeout')
    time.sleep(.05)
  try:
   f.seek(0)
   if f.read(1)!=b'0':raise RuntimeError('INTEGRITY: invalid CommandOracle lock byte')
   yield
  finally:
   f.seek(0)
   if os.name=='nt':msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
   else:fcntl.flock(f.fileno(),fcntl.LOCK_UN)

def verified(entry,key):
 entry=Path(entry)
 if not entry.exists():return None
 try:
  manifest=json.loads((entry/'MANIFEST.json').read_text());checksum=manifest.pop('checksum')
  if digest(manifest)!=checksum or manifest['key']!=key or digest(manifest['inputs'])!=key:raise ValueError('binding')
  if set(manifest['files'])!={p.name for p in entry.iterdir() if p.name!='MANIFEST.json'}:raise ValueError('file set')
  if 'CommandOracle.class' not in manifest['files'] or 'COMPILE_BINDING.json' not in manifest['files']:raise ValueError('required files')
  for name,h in manifest['files'].items():
   if Path(name).name!=name or sha(entry/name)!=h:raise ValueError('class/binding digest')
  if (entry/'COMPILE_BINDING.json').read_text().strip()!=manifest['inputs']['source_sha256']:raise ValueError('source binding')
  return manifest
 except (OSError,ValueError,KeyError,TypeError) as e:raise RuntimeError('INTEGRITY: corrupt compiled CommandOracle cache '+str(entry)) from e

def make_prepare(original,source,cache_root):
 source=Path(source);cache_root=Path(cache_root)
 def prepare(runtime,output):
  start=time.perf_counter();runtime=Path(runtime);output=Path(output);bound=inputs(runtime,source);key=digest(bound);entry=cache_root/key
  lookup_seconds=time.perf_counter()-start;compiled=False;compile_seconds=0.
  m=verified(entry,key)
  if m is None:
   with byte_lock(cache_root/'locks'/(key+'.lock')):
    m=verified(entry,key)
    if m is None:
     temp=Path(tempfile.mkdtemp(prefix=key+'.building.',dir=cache_root))
     try:
      t=time.perf_counter();original(runtime,temp);compile_seconds=time.perf_counter()-t;compiled=True
      if inputs(runtime,source)!=bound:raise RuntimeError('INTEGRITY: compiler inputs changed during compilation')
      files={p.name:sha(p) for p in temp.iterdir() if p.is_file()}
      if any(not (n.endswith('.class') or n=='COMPILE_BINDING.json') for n in files):raise RuntimeError('Unexpected compiler output')
      for name in files:durable_bytes(temp/name,(temp/name).read_bytes())
      manifest={'key':key,'inputs':bound,'files':files}
      durable_bytes(temp/'MANIFEST.json',(json.dumps({**manifest,'checksum':digest(manifest)},sort_keys=True,indent=2)+'\n').encode())
      os.replace(temp,entry);m=verified(entry,key)
     finally:
      if temp.exists():shutil.rmtree(temp)
  output.mkdir(parents=True,exist_ok=True)
  # Revalidate source bytes immediately before copying and validate destination
  # bytes before the original decoder is allowed to start.
  m=verified(entry,key)
  for name,h in m['files'].items():
   dest=output/name
   if dest.exists():
    if sha(dest)!=h:raise RuntimeError('INTEGRITY: existing CommandOracle output differs from compiled cache')
   else:durable_bytes(dest,(entry/name).read_bytes())
   if sha(dest)!=h:raise RuntimeError('INTEGRITY: staged CommandOracle digest mismatch')
  METRICS.append({'key':key,'compiled':compiled,'compile_seconds':compile_seconds,'lookup_inputs_seconds':lookup_seconds,'seconds':time.perf_counter()-start,'files':m['files'],'output':str(output)})
  return str(output)+';'+str(runtime/'FightingICE.jar')+';'+str(runtime/'lib/*')+';'+str(runtime/'lib/grpc/*')
 return prepare

def install(cache_root):
 import gmtv.oracle as oracle
 if getattr(oracle.prepare,'v33_cache_root',None):
  if Path(oracle.prepare.v33_cache_root)!=Path(cache_root):raise RuntimeError('CommandOracle cache scope collision')
  return
 original=oracle.prepare;source=Path(oracle.__file__).resolve().parents[1]/'engine_evidence/CommandOracle.java'
 prepare=make_prepare(original,source,cache_root);prepare.v33_cache_root=str(cache_root);oracle.prepare=prepare
 return {'original_prepare':original,'installed_prepare':prepare}

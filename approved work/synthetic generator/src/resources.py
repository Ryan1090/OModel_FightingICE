"""One-minute system counters, non-authoritative and independent of admission."""
import copy,datetime,json,threading,time,os
from pathlib import Path
import psutil

def counter_sample(previous=None,clock=time.monotonic):
 now=clock();cpu=psutil.cpu_times()._asdict();disk={n:v._asdict() for n,v in (psutil.disk_io_counters(perdisk=True) or {}).items()};mem=psutil.virtual_memory()
 percent=None;dt=None;disks={}
 if previous:
  dt=max(.001,now-previous['monotonic']);before=previous['cpu'];total=sum(cpu[k]-before.get(k,cpu[k]) for k in cpu if k not in ('guest','guest_nice'));idle=cpu.get('idle',0)-before.get('idle',0)
  percent=max(0,min(100,100*(total-idle)/total)) if total>0 else None
 for n,v in disk.items():
  d={'cumulative':v,'per_second':None}
  if previous and n in previous['disk']:
   prior=previous['disk'][n];d['per_second']={k:max(0,v[k]-prior.get(k,v[k]))/dt for k in ('read_count','write_count','read_bytes','write_bytes') if k in v}
   d['interval_read_time_ms']=max(0,v.get('read_time',0)-prior.get('read_time',0));d['interval_write_time_ms']=max(0,v.get('write_time',0)-prior.get('write_time',0))
  disks[n]=d
 public={'sampled_Perth':datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),'epoch':time.time(),'interval_seconds':dt,
 'interval_target_seconds':60,'cpu_percent_machine':percent,'logical_processors':psutil.cpu_count(),'memory':{'total_bytes':mem.total,'available_bytes':mem.available,'used_percent':mem.percent},
 'disks':disks,'scope':'Whole-machine counters, not validator CPU attribution. Disk transfer counters do not measure forced-flush latency; no historical reconstruction.'}
 return public,{'monotonic':now,'cpu':cpu,'disk':disk}

class Sampler:
 def __init__(self,root,interval=60):self.root=Path(root);self.interval=interval;self.lock=threading.Lock();self.latest=None;self.stop_event=threading.Event();self.thread=None
 def tick(self,previous):
  try:
   latest,next_state=counter_sample(previous)
   folder=self.root/'resource_samples_v33';folder.mkdir(parents=True,exist_ok=True);path=folder/(str(time.time_ns())+'.json');tmp=path.with_suffix('.tmp')
   # Telemetry never certifies evidence or an admission. Same atomic complete
   # JSON publication as display status, without a forced durable flush.
   with tmp.open('w',encoding='utf-8') as f:json.dump(latest,f,sort_keys=True);f.write('\n');f.flush()
   os.replace(tmp,path)
   with self.lock:self.latest=latest
   return next_state
  except Exception as e:
   with self.lock:self.latest={'sampled_epoch':time.time(),'sampling_error':type(e).__name__+': '+str(e),'admission_effect':None}
   return previous
 def start(self):
  if self.thread:return
  def loop():
   previous=None
   while not self.stop_event.is_set():
    previous=self.tick(previous)
    if self.stop_event.wait(self.interval):break
  self.thread=threading.Thread(target=loop,name='v33-resource-minute',daemon=True);self.thread.start()
 def snapshot(self):
  with self.lock:return copy.deepcopy(self.latest)
 def close(self):
  self.stop_event.set()
  if self.thread:self.thread.join(timeout=2)

def install(root):
 import gmtv.status as status
 original=status.best_effort_status;sampler=Sampler(root)
 target=(Path(root)/'status.json').resolve()
 def writer(path,payload):
  if Path(path).resolve()==target:
   sampler.start();payload={**payload,'resource_usage':sampler.snapshot() or {'state':'initial sample pending','interval_target_seconds':60}}
  return original(path,payload)
 status.best_effort_status=writer
 return sampler

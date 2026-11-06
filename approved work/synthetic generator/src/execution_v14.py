from transport_readiness import listening as production_tcp_listening
"""Integrated, resumable stock/candidate execution in one engine process.

No earlier experiment registry or recipe is imported. A baseline cache belongs
to this validator and is keyed by stock bytes, exact scenario and controller.
"""
import asyncio
import contextlib
import os
import socket
import subprocess
import time
from pathlib import Path
from pyftg.socket.aio.gateway import Gateway
from gmtv.schema import sha,digest
from gmtv.storage import atomic,commit,load_commit,Lock
from gmtv.staging import canonical
from gmtv.integrity import runtime_digest,verify
from early_probe import EarlyProbe as Probe
from dependencies import projection
from gmtv.engine import ENGINE_SHA
from gmtv.fingerprint import environment
from gmtv.status import publish


class ScreenBudgetExceeded(TimeoutError):
    """Incomplete screening budget, never a scientific failure or pass."""


class CandidateSession:
    def __init__(self,hot,output,root,identity,stock,candidate,horizon,*,fast_mode=False,deadline=None):
        self.hot=Path(hot);self.runtime=self.hot/'runtime';self.output=Path(output);self.output.mkdir(parents=True,exist_ok=True)
        self.root=root;self.identity=identity;self.tables={'stock':stock,'candidate':candidate};self.horizon=horizon
        self.fast_mode=fast_mode;self.deadline=deadline;self.short_horizon=horizon;self.partial_cells=[]
        # Full validation has separate ordinary/energy launch horizons. The
        # public planner sets these before execution; adaptive witness probes
        # use the same prospective bucket rule. No measurement/acceptance rule
        # changes, and a horizon remains part of every atomic fixture binding.
        self.full_horizons=None
        self.verification_unsplit=os.environ.get('GMTV_VERIFY_UNSPLIT_ENERGY')=='1'
        self.horizons_used=set();self.decoder=None;self.budget_interrupted=False
        self.motions={'stock':self.hot/'stock_reference'/root/'Motion.csv',
            'candidate':self.runtime/'data/characters'/identity/'Motion.csv'}
        self.hashes={k:sha(p) for k,p in self.motions.items()}
        import gmtv.execution as original_execution
        source=Path(original_execution.__file__).parent
        runtime_files=('execution.py','probe.py','rules.py','schema.py','integrity.py','staging.py','energy_setup.py')
        self.controller={name:sha(source/name) for name in runtime_files}
        self.controller['installed_environment_sha256']=environment()['sha256'];self.controller.update({name:sha(Path(__file__).with_name(name)) for name in ('execution_v14.py','early_probe.py','dependencies.py')});self.controller_hash=digest(self.controller)
        snapshot=self.output/'source_snapshot';snapshot.mkdir(exist_ok=True)
        for p in source.glob('*.py'):
            dest=snapshot/(sha(p)+'.'+p.name)
            if not dest.exists():dest.write_bytes(p.read_bytes())
        oracle_source=source.parent/'engine_evidence/CommandOracle.java'
        oracle_copy=snapshot/(sha(oracle_source)+'.CommandOracle.java')
        if not oracle_copy.exists():oracle_copy.write_bytes(oracle_source.read_bytes())
        self.proc=None;self.gateway=None;self.records={};self.failures=[];self.requested={};self.new_commits=0;self.launches=0
        self.stop_after=int(os.environ.get('GMTV_STOP_AFTER_NEW_PROBES','0'))
        # Verification-only modes exercise the public validator. They never
        # change a scenario, expected outcome or measurement rule.
        self.separate_probes=os.environ.get('GMTV_VERIFY_SEPARATE_PROBES')=='1'
        self.fresh_stock=os.environ.get('GMTV_VERIFY_FRESH_STOCK')=='1'
        self.current_role='planning';self.log=None;self.lock=None;self.timings={}
        self.dependency_hits=0;self.early_stops=0
        self.status('planning')
    def status(self,state):
        status={'state':state,'activity':'validator invocation','base_character':self.root,'candidate_sha256':self.hashes['candidate'],
            'phase':self.current_role,'completed_probes':len(self.records),'requested_probes':len(self.requested),
            'progress':f'{len(self.records)}/{len(self.requested)} requested probes','new_probes_this_invocation':self.new_commits,
            'engine_launches_this_invocation':self.launches,'infrastructure_failures':len(self.failures),
            'active_engine_runs':int(self.proc is not None and self.proc.poll() is None),
            'pid':os.getpid(),'updated_epoch':time.time(),'report_directory':str(self.output),'validator_release':'development'}
        if getattr(self,'fast_mode',False):
            status.update(mode='fast',planning_estimate=getattr(self,'planning_estimate',None),
                budget_seconds_remaining=max(0,self.deadline-time.monotonic()) if self.deadline else None,
                progress=f'{len(self.records)} committed probes; {len(self.requested)} requested so far (adaptive plan)')
        publish(self.hot,status,self.output/'status.json')
    def paused(self):
        cohort_pause=os.environ.get('GMTV_COHORT_PAUSE')
        return (self.hot/'PAUSE_REQUESTED').exists() or (self.output/'PAUSE_REQUESTED').exists() or bool(cohort_pause and Path(cohort_pause).exists())
    def check_budget(self,reserve=0):
        deadline=getattr(self,'deadline',None)
        if deadline is not None and time.monotonic()>=deadline-reserve:
            self.budget_interrupted=True
            raise ScreenBudgetExceeded('fast-screen execution budget exhausted; committed probes are resumable')
    async def start(self):
        self.check_budget()
        if self.proc is not None:return
        if sha(self.runtime/'FightingICE.jar')!=ENGINE_SHA:raise RuntimeError('approved engine SHA differs')
        self.lock=Lock(self.runtime/'GMTV.lock');self.lock.__enter__()
        with socket.socket() as s:s.bind(('127.0.0.1',0));self.port=s.getsockname()[1]
        self.log=self.output/('engine.'+str(time.time_ns())+'.log')
        args=['java','-Xms64m','-Xmx512m','--enable-native-access=ALL-UNNAMED','-Dfightingice.certificationEnergyTopUp=false','-cp',
            'FightingICE.jar;./lib/*;./lib/lwjgl/*;./lib/lwjgl/natives/windows/amd64/*;./lib/grpc/*',
            'Main','--pyftg-mode','--lightweight-mode','--input-sync','--mute','--err-log','-r','1','-f',str(self.horizon),'--port',str(self.port)]
        launch={'command':args,'engine_sha256':ENGINE_SHA,'controller':self.controller,
            'candidate_sha256':self.hashes['candidate'],'stock_sha256':self.hashes['stock']}
        atomic(self.output/('LAUNCH.'+str(time.time_ns())+'.json'),launch)
        atomic(self.output/'LAUNCH.json',launch)
        self.stream=self.log.open('w',encoding='utf-8');started=time.perf_counter()
        self.proc=subprocess.Popen(args,cwd=self.runtime,stdout=self.stream,stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));self.launches+=1
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            self.check_budget()
            if self.proc.poll() is not None:raise RuntimeError('engine exited at launch')
            text=self.log.read_text(encoding='utf-8',errors='replace')
            if 'Exception in thread' in text or 'FATAL' in text:raise RuntimeError('engine fatal launch error')
            if ('Socket server is started' in text or 'Waiting to launch a game' in text) and production_tcp_listening(self.port,self.proc.pid):break
            await asyncio.sleep(.1)
        else:raise TimeoutError('engine startup ceiling')
        self.timings['launch_seconds']=self.timings.get('launch_seconds',0)+time.perf_counter()-started
        self.gateway=Gateway(host='127.0.0.1',port=self.port)
    async def execute(self,spec,role):
        self.check_budget()
        wanted_horizon=self.horizon
        if getattr(self,'fast_mode',False):
            from gmtv.fast import fixed_horizon
            wanted_horizon=fixed_horizon(self.tables['stock'],self.tables['candidate'],
                self.zen_table,[spec],energy=bool(spec.get('energy_setup')))
        elif getattr(self,'full_horizons',None):
            bucket='energy' if spec.get('energy_setup') else 'ordinary'
            wanted_horizon=self.full_horizons[bucket]
        request={'scenario':spec,'table_role':role,'motion_sha256':self.hashes[role],
            'stock_zen_sha256':sha(self.runtime/'data/characters/ZEN/Motion.csv'),
            'engine_sha256':ENGINE_SHA,'controller_sha256':self.controller_hash,'horizon':wanted_horizon}
        if getattr(self,'full_horizons',None):request['full_session_policy']='verification-unsplit-energy' if getattr(self,'verification_unsplit',False) else 'isolated-energy-sessions-v1'
        if getattr(self,'fast_mode',False):request['observation_policy']='fast-fixed-horizon-v1'
        fixture_id=digest(request);self.requested[fixture_id]=request;self.current_role=role
        if fixture_id in self.records:
            self.memo_hits=getattr(self,'memo_hits',0)+1
            return self.records[fixture_id]['record']
        binding=digest(request)
        cache=self.hot/'cache/stock'/self.hashes['stock']/self.controller_hash if role=='stock' else self.output/'probes'
        if role=='stock' and self.fresh_stock:cache=self.output/'verification_stock_probes'
        path=cache/(fixture_id+'.json.gz');saved=load_commit(path,binding)
        if saved is None and role=='candidate':saved=self.load_dependency_reuse(request,spec,path)
        if saved is not None:
            self.records[fixture_id]={'request':request,'raw_path':str(path),'record':saved,'cached':True};self.status('running');return saved
        if self.paused():self.status('paused');raise InterruptedError('validator pause requested at checkpoint')
        self.check_budget(reserve=1)
        if wanted_horizon!=self.horizon:
            await self.shutdown();self.horizon=wanted_horizon
        if hasattr(self,'horizons_used'):self.horizons_used.add(self.horizon)
        await self.start();offset=self.log.stat().st_size;started=time.perf_counter();sink=[];coord={}
        internal={**spec,'zen_rows':self.zen_table};target=Probe(internal,self.tables[role],coord,sink,True);op=Probe(internal,self.tables[role],coord,sink,False)
        self.gateway.register_ai(target.name(),target);self.gateway.register_ai(op.name(),op)
        context=canonical(self.runtime,self.root,self.identity,self.motions['candidate'],self.output/'canonical_staging') if role=='candidate' else contextlib.nullcontext(self.root)
        task=None;early=False;probe_deadline=None
        try:
            with context as identity:
                chars=[identity,'ZEN'];names=[target.name(),op.name()]
                if spec['orientation']=='P2':chars.reverse();names.reverse()
                task=asyncio.create_task(self.gateway.run_game(chars,names,1));deadline=time.monotonic()+self.probe_wall_seconds(spec);probe_deadline=deadline
                while not task.done():
                    self.check_budget()
                    if coord.get('observations_complete'):
                        early=True
                        if not sink:target.round_end(None)
                        task.cancel();await asyncio.gather(task,return_exceptions=True);break
                    if self.proc.poll() is not None:raise ConnectionError('engine exited during probe')
                    if time.monotonic()>deadline:raise ScreenBudgetExceeded('Per-probe wall limit reached; required evidence incomplete, no automatic retry')
                    await asyncio.wait({task},timeout=.2)
                if not early:await task
                if len(sink)!=1:raise RuntimeError('missing or duplicate probe observation')
                fragment=self.log.read_bytes()[offset:]
                if not verify(fragment.decode(errors='replace'),identity,spec['orientation'],
                    runtime_digest(self.motions[role],self.root),runtime_digest(self.runtime/'data/characters/ZEN/Motion.csv','ZEN')):
                    raise RuntimeError('full runtime identity/table digest mismatch')
                if sha(self.motions[role])!=self.hashes[role]:raise RuntimeError('input bytes changed during probe')
            audit=cache/(fixture_id+'.engine.log');audit.parent.mkdir(parents=True,exist_ok=True)
            if audit.exists():audit=audit.with_name(audit.name+'.'+str(time.time_ns()))
            audit.write_bytes(fragment)
            record={'fixture_id':fixture_id,'spec':spec,'table_role':role,'observation':sink[0],'load_verified':True,
                'seconds':time.perf_counter()-started,'request':request,'early_stopped':early,'completion_frame':coord.get('observations_complete'),
                'timing':{'connection_load_seconds':None if target.first_frame_wall is None else target.first_frame_wall-started,
                    'setup_seconds':None if target.issue_wall is None else target.issue_wall-target.first_frame_wall,
                    'observation_seconds':None if target.issue_wall is None else target.last_frame_wall-target.issue_wall}}
            commit(path,binding,record,[audit]);checked=load_commit(path,binding)
            if checked is None:raise RuntimeError('new atomic record failed validation')
            self.records[fixture_id]={'request':request,'raw_path':str(path),'record':checked,'cached':False};self.new_commits+=1
            if role=='candidate':self.save_dependency_reuse(request,record,path)
            self.status('running')
            if self.stop_after and self.new_commits>=self.stop_after:
                atomic(self.output/'PAUSE_REQUESTED',{'reason':'deliberate validator lifecycle verification','after_commits':self.new_commits})
            return checked
        except BaseException as error:
            if task is not None and not task.done():task.cancel();await asyncio.gather(task,return_exceptions=True)
            if isinstance(error,ScreenBudgetExceeded):
                self.status('incomplete_budget');raise
            failure={'fixture_id':fixture_id,'request':request,'error':repr(error),'log':str(self.log)}
            self.failures.append(failure);atomic(self.output/'failures'/(fixture_id+'.'+str(time.time_ns())+'.json'),failure)
            self.status('running_with_isolated_failures')
            if isinstance(error,(SystemExit,ConnectionError,TimeoutError)):raise RuntimeError('engine unavailable; resume missing fixtures') from error
            return {'spec':spec,'table_role':role,'infrastructure_failure':repr(error),'load_verified':False}
        finally:
            if early:self.early_stops+=1
            if early or self.separate_probes:await self.shutdown()
    def probe_wall_seconds(self,spec):
        return 24 if spec.get('energy_setup') else 12
    def dependency_key(self,request):
        return digest({k:v for k,v in request.items() if k!='motion_sha256'})
    def dependency_folder(self,request):
        return self.hot/'cache/dependency_v14'/self.controller_hash/self.dependency_key(request)
    def save_dependency_reuse(self,request,record,path):
        key,rows=projection(self.tables['candidate'],record)
        self_folder=self.dependency_folder(request);self_folder.mkdir(parents=True,exist_ok=True)
        commit(self_folder/(self.hashes['candidate']+'.json'),self.dependency_key(request),
            {'raw_path':str(path),'raw_binding':digest(request),'projection':key,'complete_rows':rows},[path])
    def load_dependency_reuse(self,request,spec,path):
        folder=self.dependency_folder(request)
        if not folder.exists():return None
        for index in sorted(folder.glob('*.json')):
            saved=load_commit(index,self.dependency_key(request))
            if saved is None:continue
            original=load_commit(saved['raw_path'],saved['raw_binding'])
            if original is None:continue
            key,rows=projection(self.tables['candidate'],original)
            if key!=saved['projection']:continue
            record={**original,'fixture_id':digest(request),'request':request,'spec':spec,
                'dependency_reuse':{'original_motion_sha256':original['request']['motion_sha256'],'original_raw_path':saved['raw_path'],
                    'original_raw_sha256':sha(saved['raw_path']),'projection':key,'complete_rows':rows,
                    'basis':'Unchanged exact executed/setup/cancel-linked rows and all global input permissions/costs; deterministic engine and same scenario/horizon.'}}
            commit(path,digest(request),record,[Path(saved['raw_path']),index]);self.dependency_hits+=1
            return load_commit(path,digest(request))
    async def shutdown(self):
        """Release only this session's owned resources; preserve committed probes."""
        try:
            if self.gateway is not None:
                try:await self.gateway.close_game()
                except Exception:pass
            pending=[t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()]
            for t in pending:t.cancel()
            if pending:await asyncio.gather(*pending,return_exceptions=True)
        finally:
            if self.proc is not None and self.proc.poll() is None:
                self.proc.terminate()
                try:self.proc.wait(1 if getattr(self,'fast_mode',False) else 10)
                except subprocess.TimeoutExpired:self.proc.kill();self.proc.wait(5)
            if self.proc is not None:self.stream.close()
            if self.lock is not None:self.lock.__exit__(None,None,None)
            self.proc=None;self.gateway=None;self.lock=None
    async def close(self):
        try:
            await self.shutdown()
            if getattr(self,'decoder',None) is not None:self.decoder.close()
        finally:
            ledger=[{'fixture_id':key,'request':x['request'],'raw_path':x['raw_path'],'raw_sha256':sha(x['raw_path']),
                'cached_this_invocation':x['cached']} for key,x in sorted(self.records.items())]
            atomic(self.output/'LEDGER.json',{'records':ledger,'unique_fixture_ids':len(ledger),'infrastructure_failures':self.failures,
                'engine_launches_this_invocation':self.launches,'timing':self.timings,
                'execution_mode':'separate launches for verification' if self.separate_probes else
                    'chained sessions isolated by energy-setup horizon' if getattr(self,'full_horizons',None) else 'one chained session',
                'full_session_horizons':getattr(self,'full_horizons',None),
                'stock_cache_mode':'isolated verification cache' if self.fresh_stock else 'shared immutable stock cache'})

"""One launch per candidate; atomically resume only verified probe commits."""
import asyncio
import json
import socket
import subprocess
import time
import os
from pathlib import Path
from pyftg.socket.aio.gateway import Gateway
from .probe import Probe
from .integrity import runtime_digest,verify
from .schema import sha,digest,read
from .storage import atomic,commit,load_commit,Lock
from .staging import canonical

ENGINE_SHA='0b1defaff286e892481f27572b2d951c3da1ab60ce04928e4a6453510a8b5635'


class Session:
    def __init__(self,runtime,output,root,identity,table,specs,horizon=360):
        self.runtime=Path(runtime);self.output=Path(output);self.root=root;self.identity=identity
        self.table=table;self.specs=specs;self.horizon=horizon;self.output.mkdir(parents=True,exist_ok=True)
        self.motion=self.runtime/'data/characters'/identity/'Motion.csv';self.motion_sha=sha(self.motion)
        source=Path(__file__).parent
        self.binding=digest({'motion':self.motion_sha,'root':root,'specs':specs,'horizon':horizon,
            'code':{p.name:sha(p) for p in sorted(source.glob('*.py'))},'engine':sha(self.runtime/'FightingICE.jar')})
        snapshot=self.output/'source_snapshot';snapshot.mkdir(exist_ok=True)
        for p in sorted(source.glob('*.py')):
            archived=snapshot/(sha(p)+'.'+p.name)
            if not archived.exists():archived.write_bytes(p.read_bytes())
        self.records={};self.errors=[]
        for s in specs:
            record=load_commit(self.output/'probes'/(digest(s)+'.json.gz'),self.binding)
            if record:self.records[digest(s)]=record
    def status(self,state):
        atomic(self.output/'progress_status.json',{'state':state,'completed':len(self.records),'total':len(self.specs),
            'progress':f'{len(self.records)}/{len(self.specs)}','isolated_failures':len(self.errors),'binding':self.binding,
            'pid':os.getpid(),'updated_epoch':time.time()})
    async def play(self,port,log):
        gateway=Gateway(host='127.0.0.1',port=port)
        try:
            for spec in self.specs:
                if digest(spec) in self.records:continue
                if (self.output/'PAUSE_REQUESTED').exists():break
                offset=log.stat().st_size;start=time.perf_counter();sink=[];coordinator={}
                internal={**spec,'zen_rows':read(self.runtime/'data/characters/ZEN/Motion.csv','ZEN')}
                target=Probe(internal,self.table,coordinator,sink,True);opponent=Probe(internal,self.table,coordinator,sink,False)
                gateway.register_ai(target.name(),target);gateway.register_ai(opponent.name(),opponent)
                chars=[self.loaded_identity,'ZEN'];names=[target.name(),opponent.name()]
                if spec['orientation']=='P2':chars.reverse();names.reverse()
                try:
                    game=asyncio.create_task(gateway.run_game(chars,names,1))
                    deadline=start+max(90,self.horizon/10+60)
                    while not game.done():
                        if self.proc.poll() is not None:raise RuntimeError('engine exited')
                        if time.perf_counter()>deadline:raise TimeoutError('scenario wall ceiling')
                        await asyncio.wait({game},timeout=.2)
                    await game
                    if len(sink)!=1:raise RuntimeError('missing or duplicate round result')
                    fragment=log.read_bytes()[offset:]
                    if not verify(fragment.decode(errors='replace'),self.loaded_identity,spec['orientation'],
                        runtime_digest(self.motion,self.root),runtime_digest(self.runtime/'data/characters/ZEN/Motion.csv','ZEN')):
                        raise RuntimeError('whole-table runtime load audit mismatch')
                    if sha(self.motion)!=self.motion_sha:raise RuntimeError('staged bytes changed')
                    evidence=self.output/'probes'/(digest(spec)+'.engine.log');evidence.parent.mkdir(exist_ok=True)
                    evidence.write_bytes(fragment)
                    record={'spec':spec,'observation':sink[0],'load_verified':True,'seconds':time.perf_counter()-start,
                        'timing':{'connection_and_load_seconds':None if target.first_frame_wall is None else target.first_frame_wall-start,
                            'setup_seconds':None if target.issue_wall is None or target.first_frame_wall is None else target.issue_wall-target.first_frame_wall,
                            'observation_seconds':None if target.last_frame_wall is None or target.issue_wall is None else target.last_frame_wall-target.issue_wall}}
                    commit(self.output/'probes'/(digest(spec)+'.json.gz'),self.binding,record,[evidence])
                    self.records[digest(spec)]=record;self.status('running')
                except Exception as error:
                    self.errors.append({'spec':spec,'error':repr(error)})
                    atomic(self.output/'failures'/(digest(spec)+'.'+str(time.time_ns())+'.json'),self.errors[-1])
                    self.status('running_with_isolated_failures')
                    if not game.done():
                        game.cancel();await asyncio.gather(game,return_exceptions=True)
                    if isinstance(error,TimeoutError) or self.proc.poll() is not None:break
        finally:
            try:await gateway.close_game()
            finally:
                pending=[t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()]
                for task in pending:task.cancel()
                if pending:await asyncio.gather(*pending,return_exceptions=True)
    def run(self):
        if sha(self.runtime/'FightingICE.jar')!=ENGINE_SHA:raise RuntimeError('approved engine differs')
        if len(self.records)==len(self.specs):self.status('complete');return self.records
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        log=self.output/('session.'+str(time.time_ns())+'.log')
        command=['java','-Xms64m','-Xmx512m','--enable-native-access=ALL-UNNAMED','-cp',
            'FightingICE.jar;./lib/*;./lib/lwjgl/*;./lib/lwjgl/natives/windows/amd64/*;./lib/grpc/*',
            'Main','--pyftg-mode','--lightweight-mode','--input-sync','--mute','--err-log',
            '-r','1','-f',str(self.horizon),'--port',str(port)]
        # Default non-limit-HP mode measures damage without a KO ceiling.
        # HP-sensitive logic still needs an explicit audit before the final
        # evaluation; neutrality is not assumed. Record launch parameters.
        atomic(self.output/'LAUNCH.json',{'command':command,'cwd':str(self.runtime),'binding':self.binding})
        with Lock(self.runtime/'GMTV.lock'),canonical(self.runtime,self.root,self.identity,self.motion,self.output) as loaded,log.open('w',encoding='utf-8') as stream:
            self.loaded_identity=loaded
            self.proc=subprocess.Popen(command,cwd=self.runtime,stdout=stream,stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            try:
                launch_started=time.perf_counter();deadline=time.monotonic()+60;ready=False
                while time.monotonic()<deadline:
                    if self.proc.poll() is not None:raise RuntimeError('engine exited at startup; '+str(log))
                    text=log.read_text(errors='replace')
                    if 'Exception in thread' in text or 'FATAL' in text:raise RuntimeError('fatal engine launch; '+str(log))
                    if any(s in text for s in ('Socket server is started','Waiting to launch a game','Waiting for connection','Waiting for a connection','Server started')):
                        ready=True;break
                    # A successful TCP accept probe would consume the game
                    # endpoint. Wait for its readiness log instead.
                    time.sleep(.1)
                if not ready:raise TimeoutError('engine readiness not observed; '+str(log))
                atomic(self.output/'LAUNCH_TIMING.json',{'startup_seconds':time.perf_counter()-launch_started,
                    'horizon_frames':self.horizon,'probe_count':len(self.specs)-len(self.records)})
                self.status('running');asyncio.run(self.play(port,log))
            finally:
                if self.proc.poll() is None:
                    self.proc.terminate()
                    try:self.proc.wait(10)
                    except subprocess.TimeoutExpired:self.proc.kill();self.proc.wait(5)
        self.status('complete' if len(self.records)==len(self.specs) else ('paused' if (self.output/'PAUSE_REQUESTED').exists() else 'incomplete_with_isolated_failures'))
        return self.records

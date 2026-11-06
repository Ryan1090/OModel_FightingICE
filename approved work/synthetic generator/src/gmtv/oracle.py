"""Ask the approved engine's actual CommandTable to decode recorded inputs."""
import subprocess
import queue
import threading
import time
from pathlib import Path
from .schema import sha
from .storage import atomic


def lever(keys,front):
    x=int(keys['R'])-int(keys['L']);y=int(keys['U'])-int(keys['D'])
    # Key.getLever prioritises opposing directions as neutral (verified below
    # against our generated sequences, which never hold opposing directions).
    if not front:x=-x
    return 5+x+3*y


def prepare(runtime,output):
    runtime=Path(runtime);output=Path(output);output.mkdir(parents=True,exist_ok=True)
    source=Path(__file__).resolve().parents[1]/'engine_evidence/CommandOracle.java'
    cp=str(output)+';'+str(runtime/'FightingICE.jar')+';'+str(runtime/'lib/*')+';'+str(runtime/'lib/grpc/*')
    compiled=output/'CommandOracle.class';binding=output/'COMPILE_BINDING.json'
    if not compiled.exists() or not binding.exists() or binding.read_text().strip()!=sha(source):
        result=subprocess.run(['javac','-classpath',cp,'-d',str(output),str(source)],capture_output=True,text=True,timeout=45)
        if result.returncode:raise RuntimeError('command oracle compile failed: '+result.stderr)
        binding.write_text(sha(source),encoding='utf-8')
    return cp


def encoded_rows(inputs):
    history=[];rows=[];last=None
    for sample in inputs:
        keys=sample['keys'];history.append(keys);history=history[-30:]
        commands=[5,5,5,5];length=0
        for item in reversed(history):
            if length>=3:break
            d=lever(item,sample['front'])
            if d!=commands[length]:
                if commands[length]!=5:length+=1
                commands[length]=d
        push=[keys[k] and not (last or {}).get(k,False) for k in ('A','B','C')]
        rows.append('\t'.join([sample['state'],str(sample['front']).lower(),*[str(x).lower() for x in push],
            ''.join('1' if keys[k] else '0' for k in ('A','B','C','U','D','L','R')),*map(str,commands)]))
        last=keys
    return rows


def replay(runtime,output,inputs):
    cp=prepare(runtime,output)
    rows=encoded_rows(inputs)
    result=subprocess.run(['java','-cp',cp,'CommandOracle'],input='\n'.join(rows)+'\n',capture_output=True,text=True,timeout=45)
    if result.returncode:raise RuntimeError('command oracle failed: '+result.stderr)
    actions=result.stdout.splitlines()
    if len(actions)!=len(inputs):raise RuntimeError('oracle returned wrong record count')
    return [{**sample,'interpreted_action':action} for sample,action in zip(inputs,actions)]


class CommandDecoder:
    """One owned Java decoder per validator invocation, framed independent rows.

    It calls the same approved converter as replay(). No engine modification,
    prediction substitute or cross-candidate process is involved.
    """
    def __init__(self,runtime,output,deadline=None):
        self.runtime=runtime;self.output=Path(output);self.deadline=deadline
        self.proc=None;self.lines=queue.Queue();self.seconds=0;self.batches=0

    def decode(self,inputs):
        started=time.perf_counter()
        if self.proc is None:
            cp=prepare(self.runtime,self.output)
            self.errors=(self.output/'decoder.stderr.log').open('w',encoding='utf-8')
            self.proc=subprocess.Popen(['java','-cp',cp,'CommandOracle'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                stderr=self.errors,text=True,bufsize=1,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            proc=self.proc;lines=self.lines
            def reader():
                for line in proc.stdout:lines.put(line.rstrip('\r\n'))
                lines.put(None)
            self.reader=threading.Thread(target=reader,daemon=True);self.reader.start()
        if self.deadline is not None and time.monotonic()>=self.deadline:
            raise TimeoutError('command decoder screen budget exhausted')
        self.proc.stdin.write('\n'.join(encoded_rows(inputs))+ '\n__GMTV_END__\n');self.proc.stdin.flush()
        actions=[];deadline=min(time.monotonic()+45,self.deadline or float('inf'))
        while True:
            try:line=self.lines.get(timeout=max(.001,deadline-time.monotonic()))
            except queue.Empty:raise TimeoutError('command decoder budget exhausted')
            if line is None:raise RuntimeError('command decoder exited before batch completion')
            if line=='__GMTV_END__':break
            actions.append(line)
        if len(actions)!=len(inputs):raise RuntimeError('oracle returned wrong batch record count')
        self.batches+=1;self.seconds+=time.perf_counter()-started
        return [{**sample,'interpreted_action':action} for sample,action in zip(inputs,actions)]

    def close(self):
        if self.proc is None:return
        try:
            self.proc.stdin.close()
            try:self.proc.wait(1)
            except subprocess.TimeoutExpired:self.proc.terminate();self.proc.wait(2)
        finally:
            self.reader.join(timeout=1)
            self.proc.stdout.close();self.errors.close();self.proc=None

"""Atomic, checksummed commits. Invalid records never count as completed."""
import json
import gzip
import zlib
import os
import time
from pathlib import Path
from .schema import digest,sha


def atomic(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.'+str(os.getpid())+'.tmp')
    if path.suffix=='.gz':
        data=gzip.compress((json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode(),compresslevel=3,mtime=0)
        with temporary.open('wb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
    else:
        with temporary.open('w',encoding='utf-8',newline='\n') as stream:
            json.dump(value,stream,sort_keys=True,indent=2);stream.write('\n')
            stream.flush();os.fsync(stream.fileno())
    # Windows readers/security software can briefly deny replacement even
    # after our own writer has closed. Retry the same complete temporary file;
    # never fall back to truncating the destination or weakening a commit.
    deadline=time.monotonic()+3;delay=.01
    while True:
        try:os.replace(temporary,path);break
        except PermissionError:
            if time.monotonic()>=deadline:raise
            time.sleep(delay);delay=min(.2,delay*2)


def commit(path,binding,payload,files=()):
    record={'binding':binding,'payload':payload,'files':{str(p):sha(p) for p in files}}
    atomic(path,{**record,'checksum':digest(record)})


def load_commit(path,binding):
    try:
        path=Path(path)
        record=json.loads(gzip.decompress(path.read_bytes()) if path.suffix=='.gz' else path.read_text(encoding='utf-8'))
        checksum=record.pop('checksum')
        if checksum!=digest(record) or record['binding']!=binding:return None
        if any(sha(p)!=s for p,s in record['files'].items()):return None
        return record['payload']
    except (OSError,EOFError,ValueError,KeyError,TypeError,zlib.error):return None


class Lock:
    def __init__(self,path):self.path=Path(path)
    def __enter__(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        # An OS-owned lock is released even on abrupt process exit. A leftover
        # metadata file is not proof that a worker is still running.
        self.stream=self.path.open('a+b')
        self.stream.seek(0,os.SEEK_END)
        if self.stream.tell()==0:self.stream.write(b'\0');self.stream.flush()
        self.stream.seek(0)
        deadline=time.monotonic()+1
        while True:
            try:
                if os.name=='nt':
                    import msvcrt
                    msvcrt.locking(self.stream.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(self.stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                break
            except OSError as error:
                # Windows can finish releasing a terminated process's byte
                # lock shortly after wait() returns. Do not delete its file or
                # bypass ownership; retry the same OS lock briefly.
                if time.monotonic()<deadline:time.sleep(.02);self.stream.seek(0);continue
                self.stream.close()
                raise RuntimeError('Another validator owns the execution lock: '+str(self.path)) from error
        self.stream.seek(0);self.stream.truncate()
        self.stream.write(json.dumps({'pid':os.getpid(),'created':time.time(),'state':'held'}).encode());self.stream.flush()
        return self
    def __exit__(self,*args):
        try:
            self.stream.seek(0);self.stream.truncate()
            self.stream.write(json.dumps({'pid':os.getpid(),'released':time.time(),'state':'idle'}).encode());self.stream.flush()
            self.stream.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(),fcntl.LOCK_UN)
        finally:self.stream.close()

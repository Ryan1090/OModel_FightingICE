"""User-bound encrypted runner archive; no C record is a public JSON export."""
import ctypes,ctypes.wintypes,hashlib,io,json,os,sqlite3,zipfile,zlib,contextlib,time,threading
from pathlib import Path
from gmtv.schema import sha,digest
from gmtv.storage import atomic

class Blob(ctypes.Structure):_fields_=[('cbData',ctypes.wintypes.DWORD),('pbData',ctypes.POINTER(ctypes.c_ubyte))]

def protect(data,entropy,decrypt=False):
    if os.name!='nt':raise RuntimeError('This sealed store requires Windows DPAPI')
    def blob(value):
        buffer=ctypes.create_string_buffer(value);return Blob(len(value),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte))),buffer
    source,source_buffer=blob(data);extra,extra_buffer=blob(entropy);out=Blob()
    api=ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    if not api(ctypes.byref(source),None,ctypes.byref(extra),None,None,1,ctypes.byref(out)):raise ctypes.WinError()
    try:return ctypes.string_at(out.pbData,out.cbData)
    finally:ctypes.windll.kernel32.LocalFree(out.pbData)

def safe_remove(root,workspace):
    root=Path(root);workspace=Path(workspace).resolve()
    if not root.exists():return
    if not root.resolve().is_relative_to(workspace) or root.resolve()==workspace:raise RuntimeError('Unsafe workspace cleanup target')
    if root.is_symlink() or root.is_junction():raise RuntimeError('Workspace root must not be a link')
    for p in list(root.iterdir()):
        if p.is_symlink():p.unlink()
        elif p.is_junction():os.rmdir(p)
        elif p.is_dir():safe_remove(p,workspace)
        else:p.unlink()
    root.rmdir()

def files(root):
    stack=[Path(root)]
    while stack:
        for p in stack.pop().iterdir():
            if p.is_symlink() or p.is_junction():continue
            if p.is_dir():stack.append(p)
            elif p.is_file():yield p

class Store:
    def __init__(self,hot,run_id):
        self.hot=Path(hot);self.hot.mkdir(parents=True,exist_ok=True);self.path=self.hot/'PRIVATE_ARCHIVE_BUILD.sqlite'
        self.final=self.hot/'SEALED_POOL_C.FINAL.json';self.entropy=('fightICE:'+run_id).encode()
        if self.final.exists():raise RuntimeError('Final sealed archive will not be reopened')
        with self.connection() as db:db.execute('CREATE TABLE IF NOT EXISTS objects(k TEXT PRIMARY KEY, body BLOB NOT NULL, checksum TEXT NOT NULL)')
    @contextlib.contextmanager
    def connection(self):
        if self.final.exists():raise RuntimeError('Final sealed archive will not be reopened')
        db=sqlite3.connect(self.path,timeout=60)
        try:
            db.execute('PRAGMA synchronous=FULL');db.execute('PRAGMA journal_mode=DELETE');yield db;db.commit()
        except BaseException:db.rollback();raise
        finally:db.close()
    def key(self,key):return hashlib.sha256(key.encode()).hexdigest()
    def heartbeat_folder(self,key):
        folder=self.hot/'PRIVATE_ARCHIVE_HEARTBEATS_V2'/self.key(key)
        if folder.exists() and (folder.is_symlink() or folder.is_junction()):raise RuntimeError('Invalid heartbeat directory')
        return folder
    def decode_heartbeat(self,data):
        body=zlib.decompress(protect(data[64:],self.entropy,True))
        if hashlib.sha256(body).hexdigest().encode()!=data[:64]:raise RuntimeError('Heartbeat integrity failure')
        return body
    def committed_heartbeat(self,folder):
        for _ in range(4):
            markers=sorted(folder.glob('*.ready'),reverse=True)
            if not markers:return None
            marker=markers[0]
            if not marker.is_dir():
                if not marker.exists():continue # retired between listing and read
                raise RuntimeError('Invalid heartbeat commit marker')
            if marker.is_symlink() or marker.is_junction():raise RuntimeError('Invalid heartbeat commit marker')
            try:data=marker.with_suffix('.hb').read_bytes()
            except FileNotFoundError:
                if marker.exists():raise RuntimeError('Missing committed heartbeat bytes')
                continue # old marker was retired after a newer publication
            return data,self.decode_heartbeat(data)
        raise PermissionError('Heartbeat publication busy; retry the snapshot')
    def publish_heartbeat(self,key,body,encrypted):
        folder=self.heartbeat_folder(key);folder.mkdir(parents=True,exist_ok=True)
        versions=[int(p.stem) for p in folder.glob('*.hb')]
        number=max(versions,default=0)+1
        while True:
            path=folder/(f'{number:020d}.hb')
            try:stream=path.open('xb');break
            except FileExistsError:number+=1
        with stream:
            stream.write(hashlib.sha256(body).hexdigest().encode()+encrypted);stream.flush();os.fsync(stream.fileno())
        # An atomic empty-directory creation publishes the closed, durable file.
        # Neither the data nor the marker is ever overwritten.
        path.with_suffix('.ready').mkdir()
        for marker in sorted(folder.glob('*.ready'),reverse=True)[4:]:
            if marker.is_symlink() or marker.is_junction():raise RuntimeError('Invalid heartbeat commit marker')
            try:marker.rmdir();marker.with_suffix('.hb').unlink()
            except OSError:pass # optional retirement; a held reader retains its snapshot
    def put_bytes(self,key,body):
        if self.final.exists():raise RuntimeError('Final sealed archive will not be reopened')
        encrypted=protect(zlib.compress(body,3),self.entropy)
        if key.startswith('heartbeat:'):
            self.publish_heartbeat(key,body,encrypted)
            return
        with self.connection() as db:db.execute('INSERT OR REPLACE INTO objects VALUES(?,?,?)',(self.key(key),encrypted,hashlib.sha256(body).hexdigest()))
    def get_bytes(self,key):
        if self.final.exists():raise RuntimeError('Final sealed archive will not be reopened')
        if key.startswith('heartbeat:'):
            record=self.committed_heartbeat(self.heartbeat_folder(key))
            if record is not None:return record[1]
        hb=self.hot/'PRIVATE_ARCHIVE_HEARTBEATS'/(self.key(key)+'.hb')
        if key.startswith('heartbeat:') and hb.exists():
            return self.decode_heartbeat(hb.read_bytes())
        with self.connection() as db:row=db.execute('SELECT body,checksum FROM objects WHERE k=?',(self.key(key),)).fetchone()
        if row is None:return None
        body=zlib.decompress(protect(row[0],self.entropy,True))
        if hashlib.sha256(body).hexdigest()!=row[1]:raise RuntimeError('Sealed-record integrity failure')
        return body
    def put(self,key,value):self.put_bytes(key,json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode())
    def get(self,key):
        b=self.get_bytes(key);return None if b is None else json.loads(b)
    def capture(self,key,root):
        root=Path(root);manifest={};immutable={}
        asset=root/'home/ASSET_MANIFEST.json'
        if asset.exists():immutable={str(Path(r['destination']).resolve()):r['sha256'] for r in json.loads(asset.read_text())['files']}
        memory=io.BytesIO()
        with zipfile.ZipFile(memory,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=3) as archive:
            for p in sorted(files(root)):
                checksum=sha(p)
                if immutable.get(str(p.resolve()))==checksum:continue
                relative=str(p.relative_to(root)).replace('\\','/');manifest[relative]=checksum;archive.write(p,relative)
            archive.writestr('SNAPSHOT_HASHES.json',json.dumps(manifest,sort_keys=True))
        self.put_bytes(key,memory.getvalue())
        return {'sha256':hashlib.sha256(memory.getvalue()).hexdigest(),'files':len(manifest)}
    def restore(self,key,root):
        body=self.get_bytes(key)
        if body is None:return False
        root=Path(root);root.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            manifest=json.loads(archive.read('SNAPSHOT_HASHES.json'))
            for name,checksum in manifest.items():
                target=(root/name).resolve()
                if not target.is_relative_to(root.resolve()):raise RuntimeError('Unsafe archive member')
                data=archive.read(name)
                if hashlib.sha256(data).hexdigest()!=checksum:raise RuntimeError('Workspace archive integrity failure')
                target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        return True
    def finalise(self):
        folder=self.hot/'PRIVATE_ARCHIVE_HEARTBEATS'
        versions=self.hot/'PRIVATE_ARCHIVE_HEARTBEATS_V2'
        with self.connection() as db:
            if folder.exists():
                for p in folder.glob('*.hb'):
                    data=p.read_bytes();body=zlib.decompress(protect(data[64:],self.entropy,True))
                    if hashlib.sha256(body).hexdigest().encode()!=data[:64]:raise RuntimeError('Heartbeat seal integrity failure')
                    db.execute('INSERT OR REPLACE INTO objects VALUES(?,?,?)',(p.stem,data[64:],data[:64].decode()))
            if versions.exists():
                for key_folder in versions.iterdir():
                    if key_folder.is_symlink() or key_folder.is_junction():raise RuntimeError('Invalid heartbeat directory')
                    record=self.committed_heartbeat(key_folder)
                    if record is not None:
                        data,body=record
                        db.execute('INSERT OR REPLACE INTO objects VALUES(?,?,?)',(key_folder.name,data[64:],data[:64].decode()))
            n=db.execute('SELECT count(*) FROM objects').fetchone()[0]
        sealed=self.hot/'SEALED_POOL_C.sqlite'
        if sealed.exists():raise RuntimeError('A sealed archive already exists')
        deadline=time.monotonic()+3
        while True:
            try:os.replace(self.path,sealed);break
            except PermissionError:
                if time.monotonic()>=deadline:raise
                time.sleep(.05)
        checksum=sha(sealed);atomic(self.final,{'archive_sha256':checksum,'encrypted_objects':n,'user_bound_encryption':'Windows DPAPI','archive_reopen_permitted':False,'split_frozen':False})
        if folder.exists():safe_remove(folder,self.hot)
        if versions.exists():safe_remove(versions,self.hot)
        return checksum

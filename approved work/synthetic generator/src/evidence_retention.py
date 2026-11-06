"""Keep final characters; optionally discard working evidence AFTER verification.

No assessment or probe rule is changed. Cleanup is a recoverable finalisation
transaction. A failed/interrupted run keeps the original evidence for Resume.
"""
import base64,hashlib,io,json,os,re,shutil,time,uuid,zipfile
from pathlib import Path
import common as c
from gmtv.schema import digest,sha
from gmtv.storage import atomic

READY='FINALIZATION_READY.json'
DIRECTORIES=('characters','workers','private_work','PRIVATE_ARCHIVE_HEARTBEATS',
             'PRIVATE_ARCHIVE_HEARTBEATS_V2','runtime_assets','compiled_oracle_cache','.compact_final')
FILES=('PRIVATE_ARCHIVE_BUILD.sqlite','PRIVATE_ARCHIVE_BUILD.sqlite-journal',
       'PRIVATE_ARCHIVE_BUILD.sqlite-wal','PRIVATE_ARCHIVE_BUILD.sqlite-shm',
       'RUNTIME_ASSETS_READY.json','RUNTIME_ASSETS.lock')

def retention_enabled(config):return config.get('retain_evidence',True)

def policy(config):
    return {'retain_evidence':retention_enabled(config),'temporary_evidence_during_run':True,
            'cleanup_only_after_successful_final_verification':True,
            'completed_character_reuse':True,'partial_screen_resume_and_probe_reuse':True,
            'post_completion_raw_evidence_audit':retention_enabled(config)}

def _inside(path):
    path=Path(path)
    if not path.resolve().is_relative_to(c.HOT.resolve()) or path.resolve()==c.HOT.resolve():
        raise RuntimeError('Finalisation path outside this run')
    return path

def _bytes(path,data):
    path=_inside(path);path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        if path.read_bytes()!=data:raise RuntimeError('Existing compact output differs')
        return
    temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with temporary.open('xb') as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:temporary.unlink(missing_ok=True)

def _json_bytes(value):return (json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()

def _metadata(row):
    if not re.fullmatch(r'[A-Za-z0-9_-]+',row['id']) or row['pool'] not in c.POOLS or row['root'] not in c.load_config()['roots']:
        raise RuntimeError('Invalid final character identity')
    fields=('id','root','pool','stratum','traits','meta','profile','final_sha256','retained_edit_count')
    return {key:row[key] for key in fields if key in row}

def _motion(store,row):
    path=_inside(row['final_path'])
    if row['pool'].startswith('C_'):
        item=store.get('job:'+row['id'])
        if not item:raise RuntimeError('Missing private final character job')
        worker=c.local_module('worker');work,_,_=worker.paths(item,item['runtime_slot'])
        relative=path.relative_to(work).as_posix()
        snapshot=store.get_bytes('workspace:'+row['id'])
        if snapshot is None:raise RuntimeError('Missing private final character workspace')
        with zipfile.ZipFile(io.BytesIO(snapshot)) as archive:
            hashes=json.loads(archive.read('SNAPSHOT_HASHES.json'));data=archive.read(relative)
            if hashlib.sha256(data).hexdigest()!=hashes.get(relative):raise RuntimeError('Private final table snapshot checksum mismatch')
    else:data=path.read_bytes()
    if hashlib.sha256(data).hexdigest()!=row['final_sha256']:raise RuntimeError('Final table checksum mismatch during export')
    return data

def _binding(config,accepted):
    return digest({'configuration':config['configuration_sha256'],
                   'characters':sorted((r['id'],r['pool'],r['final_sha256']) for r in accepted)})

def _export(store,accepted,config):
    """Only accepted final bytes and compact metadata enter the new archive."""
    stage=_inside(c.HOT/'.compact_final');stage.mkdir(exist_ok=True)
    record=stage/'EXPORT.json';binding=_binding(config,accepted)
    if record.exists():
        saved=json.loads(record.read_text())
        if saved['binding']!=binding:raise RuntimeError('Compact export binding mismatch')
        if sha(stage/'SEALED_POOL_C.sqlite')!=saved['archive_sha256']:raise RuntimeError('Compact export archive checksum mismatch')
        for relative,h in saved['public_files'].items():
            if sha(_inside(c.HOT/relative))!=h:raise RuntimeError('Compact exported table checksum mismatch')
        return saved
    # A crash between sealing and EXPORT publication must not reopen a sealed
    # archive. Its marker carries the binding needed to finish publication.
    sealed=stage/'SEALED_POOL_C.FINAL.json';archive_path=stage/'SEALED_POOL_C.sqlite'
    public_files={};index=[];private_ids=[]
    if archive_path.exists():
        pending=json.loads((stage/'EXPORT_PENDING.json').read_text())
        if pending['binding']!=binding or sha(archive_path)!=pending['archive_sha256']:
            raise RuntimeError('Interrupted compact seal mismatch')
        info={'archive_sha256':pending['archive_sha256'],'encrypted_objects':pending['C_characters']+1,
              'user_bound_encryption':'Windows DPAPI','archive_reopen_permitted':False,'split_frozen':False}
        if sealed.exists() and json.loads(sealed.read_text())!=info:raise RuntimeError('Compact seal marker mismatch')
        if not sealed.exists():atomic(sealed,info)
        saved={**pending,'archive_sha256':info['archive_sha256'],'archive_marker':info}
        atomic(record,saved);return _export(store,accepted,config)
    Store=c.local_module('sealed_store').Store;compact=Store(stage,config['run_id'])
    for row in accepted:
        if not row.get('screen_passed') or not row.get('profile',{}).get('passed'):
            raise RuntimeError('Unaccepted character cannot enter compact output')
        meta=_metadata(row);data=_motion(store,row)
        setting=(c.BASE/'assets/stock_reference'/row['root']/'gSetting.txt').read_bytes()
        if row['pool'].startswith('C_'):
            compact.put('character:'+row['id'],{**meta,'motion_csv_base64':base64.b64encode(data).decode('ascii'),
                        'gSetting_txt_base64':base64.b64encode(setting).decode('ascii'),
                        'gSetting_sha256':hashlib.sha256(setting).hexdigest()})
            private_ids.append(row['id'])
        else:
            folder=_inside(c.HOT/'catalogue'/row['pool']/row['id'])
            for name,payload in (('Motion.csv',data),('gSetting.txt',setting),('CHARACTER.json',_json_bytes(meta))):
                target=folder/name;_bytes(target,payload);public_files[target.relative_to(c.HOT).as_posix()]=sha(target)
            index.append({**meta,'motion_csv':(folder/'Motion.csv').relative_to(c.HOT).as_posix()})
    compact.put('catalogue',{'format':'compact-final-characters-v1','character_ids':private_ids,
                'configuration_sha256':config['configuration_sha256'],'release_checksum':config['release_checksum']})
    _bytes(c.HOT/'catalogue/A_B_CHARACTERS.json',_json_bytes(index))
    public_files['catalogue/A_B_CHARACTERS.json']=sha(c.HOT/'catalogue/A_B_CHARACTERS.json')
    pending={'binding':binding,'public_files':public_files,'accepted':len(accepted),
             'C_characters':len(private_ids),'archive_kind':'compact-final-characters-v1'}
    # All SQLite puts above have committed with synchronous=FULL and closed.
    # Bind those exact bytes before the rename, making even a crash between
    # rename and marker publication recoverable without reopening a seal.
    pending['archive_sha256']=sha(compact.path)
    atomic(stage/'EXPORT_PENDING.json',pending)
    os.replace(compact.path,archive_path)
    return _export(store,accepted,config)

def _publish_archive(stage,expected):
    target=_inside(c.HOT/'SEALED_POOL_C.sqlite')
    if not target.exists():
        temporary=target.with_suffix('.sqlite.publishing')
        shutil.copyfile(stage/'SEALED_POOL_C.sqlite',temporary)
        with temporary.open('r+b') as stream:stream.flush();os.fsync(stream.fileno())
        if sha(temporary)!=expected:raise RuntimeError('Compact archive publication mismatch')
        os.replace(temporary,target)
    if sha(target)!=expected:raise RuntimeError('Published compact archive mismatch')

def _checked_ready(config):
    plan=json.loads((c.HOT/READY).read_text());check=plan.pop('checksum')
    if digest(plan)!=check or plan['configuration_sha256']!=config['configuration_sha256'] or plan['release_checksum']!=config['release_checksum']:
        raise RuntimeError('Finalisation transaction binding mismatch')
    if sha(c.HOT/'PRE_FREEZE_VERIFICATION.json')!=plan['verification_sha256'] or not json.loads((c.HOT/'PRE_FREEZE_VERIFICATION.json').read_text())['integrity_passed']:
        raise RuntimeError('Final verification proof mismatch')
    if sha(c.HOT/'SEALED_POOL_C.sqlite')!=plan['archive_sha256']:raise RuntimeError('Final character archive mismatch')
    for relative,h in plan['public_files'].items():
        if sha(_inside(c.HOT/relative))!=h:raise RuntimeError('Final character output mismatch')
    return plan

def _remove_working_evidence():
    """Fixed, checked targets only; character exports are outside this list."""
    remove=c.local_module('sealed_store').safe_remove
    for name in DIRECTORIES:
        path=_inside(c.HOT/name)
        if path.exists():remove(path,c.HOT)
    for name in FILES:
        path=_inside(c.HOT/name)
        if path.is_symlink() or path.is_junction():raise RuntimeError('Invalid working-evidence file')
        path.unlink(missing_ok=True)

def _finish_ready(config):
    plan=_checked_ready(config);started=time.perf_counter()
    marker={**plan['archive_marker'],'archive_kind':'compact-final-characters-v1',
            'retained_evidence':False,'C_characters':plan['C_characters']}
    # READY is already durable before this seals the old Store against use.
    atomic(c.HOT/'SEALED_POOL_C.FINAL.json',marker)
    _remove_working_evidence()
    atomic(c.HOT/'A_B_FINAL_CHARACTERS.json',json.loads((c.HOT/'catalogue/A_B_CHARACTERS.json').read_text()))
    final={**plan['final'],'state':'complete_review_required','evidence_storage':{
            **policy(config),'working_evidence_removed':True,'C_archive_kind':'compact-final-characters-v1'}}
    final['elapsed_seconds']=final.get('elapsed_seconds',0)+time.perf_counter()-started
    atomic(c.HOT/'FINAL.json',final)
    atomic(c.HOT/'EVIDENCE_RETENTION.json',final['evidence_storage'])
    manifest={'format':'compact-final-characters-v1','configuration_sha256':config['configuration_sha256'],
              'release_checksum':config['release_checksum'],'accepted':plan['accepted'],
              'public_character_index':'catalogue/A_B_CHARACTERS.json','public_files':plan['public_files'],
              'C_archive':'SEALED_POOL_C.sqlite','C_archive_sha256':plan['archive_sha256'],
              'C_characters':plan['C_characters'],'retain_evidence':False}
    manifest['checksum']=digest(manifest);atomic(c.HOT/'CATALOGUE.json',manifest)
    atomic(c.HOT/'PRODUCTION_COMPLETED.json',{'accepted':plan['accepted'],'archive_sha256':plan['archive_sha256'],
           'archive_reopened':False,'split_frozen':False,'retain_evidence':False,'archive_kind':'compact-final-characters-v1',
           'catalogue_manifest_sha256':sha(c.HOT/'CATALOGUE.json')})
    from gmtv.status import best_effort_status
    best_effort_status(c.HOT/'status.json',final)
    # Completion is already durable. Retiring a held plan/display file must
    # never turn a successfully completed catalogue into an apparent failure.
    try:(c.HOT/READY).unlink(missing_ok=True)
    except OSError:pass
    stop=c.HOT/'STOP_CONDITION.json'
    try:
        if stop.exists() and json.loads(stop.read_text()).get('reason','').startswith('Character export/evidence finalisation incomplete'):
            stop.unlink()
    except (OSError,ValueError):pass
    return final

def _failed():
    atomic(c.HOT/'STOP_CONDITION.json',{'reason':'Character export/evidence finalisation incomplete; Resume retries committed finalisation',
           'infrastructure_fault':True,'admission_decisions_changed':False,'split_frozen':False})

def resume_finalization(config):
    if (c.HOT/'PRODUCTION_COMPLETED.json').exists():return False
    if not (c.HOT/READY).exists():return False
    if retention_enabled(config):raise RuntimeError('Unexpected compact finalisation with retain_evidence enabled')
    try:_finish_ready(config)
    except Exception:_failed();raise
    return True

def finalise_compact(store,accepted,config,verification,final):
    if retention_enabled(config):raise RuntimeError('Compact finalisation requires retain_evidence=false')
    if not verification.get('integrity_passed') or len(accepted)!=c.TOTAL:
        raise RuntimeError('Successful complete final verification required before evidence removal')
    try:
        if (c.HOT/READY).exists():return _finish_ready(config)
        start=time.perf_counter();export=_export(store,accepted,config)
        _publish_archive(c.HOT/'.compact_final',export['archive_sha256'])
        verification={**verification,'raw_evidence_verified_before_cleanup':True,'raw_evidence_retained':False}
        atomic(c.HOT/'PRE_FREEZE_VERIFICATION.json',verification)
        final={**final,'pre_freeze_verification':verification}
        final['elapsed_seconds']=final.get('elapsed_seconds',0)+time.perf_counter()-start
        plan={**export,'configuration_sha256':config['configuration_sha256'],'release_checksum':config['release_checksum'],
              'verification_sha256':sha(c.HOT/'PRE_FREEZE_VERIFICATION.json'),'final':final}
        plan['checksum']=digest(plan);atomic(c.HOT/READY,plan)
        return _finish_ready(config)
    except Exception:_failed();raise

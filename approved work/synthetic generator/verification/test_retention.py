"""Storage lifecycle controls only. No gameplay or historical archive access."""
import copy,hashlib,json,os
from pathlib import Path
import common as c
from gmtv.schema import digest,sha
from gmtv.storage import atomic

def run_checks(work):
    retention=c.local_module('evidence_retention');Store=c.local_module('sealed_store').Store
    saved_hot,saved_total=c.HOT,c.TOTAL;checks=[]
    def fixture(name):
        c.HOT=Path(work)/'retention'/name;c.HOT.mkdir(parents=True);c.TOTAL=2
        config={**c.load_config(),'authorised_hot':str(c.HOT),'retain_evidence':False}
        config['configuration_sha256']=digest({**config,'configuration_sha256':None})
        atomic(c.HOT/'RUN_CONFIG.json',config);store=Store(c.HOT,config['run_id'])
        source=c.BASE/'assets/stock_reference/ZEN/Motion.csv';data=source.read_bytes();h=sha(source)
        accepted=[]
        for pool,ident in [('A','A-storage-fixture'),('C_far','C-private-storage-fixture')]:
            item={'id':ident,'root':'ZEN','pool':pool,'runtime_slot':0,'execution_revision':'R4'}
            private,folder,home=c.local_module('worker').paths(item,0)
            folder.mkdir(parents=True);path=folder/'FINAL_Motion.csv';path.write_bytes(data)
            row={'id':ident,'root':'ZEN','pool':pool,'final_path':str(path),'final_sha256':h,
                 'stratum':[0,1],'traits':[.4,.25,.15,-.1,.15,0.],
                 'meta':{'primary':0,'secondary':1,'sign':1,'secondary_sign':1,'pool':pool},
                 'profile':{'passed':True},'screen_passed':True,'retained_edit_count':0}
            accepted.append(row);store.put('job:'+ident,item)
            if private:
                home.mkdir(parents=True);(home/'raw-trace.bin').write_bytes(os.urandom(512*1024))
                store.capture('workspace:'+ident,private)
                c.local_module('sealed_store').safe_remove(private,c.HOT)
        raw=c.HOT/'workers/worker_0/raw-probe.bin';raw.parent.mkdir(parents=True);raw.write_bytes(os.urandom(512*1024))
        store.put('coordinator',{'completed':2,'accepted':2})
        verification={'integrity_passed':True,'validated_characters':2,'scope':'predeclared software fixture; not a scientific verification'}
        atomic(c.HOT/'PRE_FREEZE_VERIFICATION.json',verification)
        final={'accepted':2,'completed':2,'elapsed_seconds':1.,'state':'verifying_before_seal','pre_freeze_verification':verification}
        return store,accepted,config,verification,final,data
    def check(name,fn):fn();checks.append(name);print('PASS '+name,flush=True)
    def option():
        import settings
        x=json.loads((c.BASE/'config.json').read_text());x['retain_evidence']=False;settings.validate(x)
        x['retain_evidence']=True;settings.validate(x);x['retain_evidence']='off'
        try:settings.validate(x)
        except ValueError:pass
        else:raise AssertionError('Nonboolean retention accepted')
        assert retention.retention_enabled({}) is True
    def keep():
        store,rows,cfg,v,f,data=fixture('keep');cfg['retain_evidence']=True
        assert retention.policy(cfg)['post_completion_raw_evidence_audit']
        try:retention.finalise_compact(store,rows,cfg,v,f)
        except RuntimeError:pass
        else:raise AssertionError('Retention-on evidence compacted')
        h=store.finalise();assert sha(c.HOT/'SEALED_POOL_C.sqlite')==h
        assert (c.HOT/'characters').exists() and (c.HOT/'workers/worker_0/raw-probe.bin').exists()
    def no_verification():
        store,rows,cfg,v,f,data=fixture('verification-required')
        try:retention.finalise_compact(store,rows,cfg,{**v,'integrity_passed':False},f)
        except RuntimeError:pass
        else:raise AssertionError('Unverified evidence removed')
        assert store.get('coordinator')['accepted']==2 and (c.HOT/'workers/worker_0/raw-probe.bin').exists()
    def compact():
        store,rows,cfg,v,f,data=fixture('compact');before=store.path.stat().st_size
        retention.finalise_compact(store,rows,cfg,v,f)
        assert not store.path.exists() and not (c.HOT/'workers').exists() and not (c.HOT/'characters').exists()
        for relative in retention.DIRECTORIES:assert not (c.HOT/relative).exists()
        index=json.loads((c.HOT/'A_B_FINAL_CHARACTERS.json').read_text());assert len(index)==1
        assert (c.HOT/index[0]['motion_csv']).read_bytes()==data
        assert (c.HOT/'SEALED_POOL_C.sqlite').stat().st_size<before/2
        assert b'C-private-storage-fixture' not in (c.HOT/'SEALED_POOL_C.sqlite').read_bytes()
        assert not (c.HOT/retention.READY).exists()
        marker=json.loads((c.HOT/'PRODUCTION_COMPLETED.json').read_text())
        assert marker['retain_evidence'] is False and marker['catalogue_manifest_sha256']==sha(c.HOT/'CATALOGUE.json')
        manifest=json.loads((c.HOT/'CATALOGUE.json').read_text());h=manifest.pop('checksum');assert digest(manifest)==h
        # Completed character reuse needs no raw Store/probe workspace.
        runner=c.local_module('catalogue');old=runner.Store
        def forbidden(*args,**kwargs):raise AssertionError('Completed dataset tried to open working evidence')
        runner.Store=forbidden
        try:assert runner.run(1) is None
        finally:runner.Store=old
    def interrupted_cleanup():
        store,rows,cfg,v,f,data=fixture('cleanup-interrupted');old=retention._remove_working_evidence
        def interrupt():
            c.local_module('sealed_store').safe_remove(c.HOT/'workers',c.HOT)
            raise RuntimeError('Deliberate software interruption')
        retention._remove_working_evidence=interrupt
        try:
            try:retention.finalise_compact(store,rows,cfg,v,f)
            except RuntimeError:pass
            else:raise AssertionError('Expected software interruption')
        finally:retention._remove_working_evidence=old
        assert (c.HOT/retention.READY).exists() and not (c.HOT/'PRODUCTION_COMPLETED.json').exists()
        assert retention.resume_finalization(cfg)
        assert (c.HOT/'PRODUCTION_COMPLETED.json').exists() and not store.path.exists()
    def interrupted_publication():
        store,rows,cfg,v,f,data=fixture('completion-interrupted');old=retention.atomic
        def interrupt(path,value):
            if Path(path).name=='PRODUCTION_COMPLETED.json':raise RuntimeError('Deliberate completion interruption')
            return old(path,value)
        retention.atomic=interrupt
        try:
            try:retention.finalise_compact(store,rows,cfg,v,f)
            except RuntimeError:pass
            else:raise AssertionError('Expected software interruption')
        finally:retention.atomic=old
        assert (c.HOT/retention.READY).exists() and not store.path.exists()
        assert retention.resume_finalization(cfg)
        assert json.loads((c.HOT/'PRODUCTION_COMPLETED.json').read_text())['accepted']==2
    def corrupt_source():
        store,rows,cfg,v,f,data=fixture('source-corruption');Path(rows[0]['final_path']).write_bytes(b'corrupt')
        try:retention.finalise_compact(store,rows,cfg,v,f)
        except RuntimeError:pass
        else:raise AssertionError('Corrupt final character exported')
        assert store.path.exists() and (c.HOT/'workers/worker_0/raw-probe.bin').exists()
        assert not (c.HOT/'PRODUCTION_COMPLETED.json').exists()
    def corrupt_ready():
        store,rows,cfg,v,f,data=fixture('ready-corruption');old=retention._remove_working_evidence
        retention._remove_working_evidence=lambda:(_ for _ in ()).throw(RuntimeError('software interruption'))
        try:
            try:retention.finalise_compact(store,rows,cfg,v,f)
            except RuntimeError:pass
        finally:retention._remove_working_evidence=old
        (c.HOT/'catalogue/A/A-storage-fixture/Motion.csv').write_bytes(b'corrupt')
        try:retention.resume_finalization(cfg)
        except RuntimeError:pass
        else:raise AssertionError('Corrupt export caused evidence removal')
        assert store.path.exists() and (c.HOT/'workers/worker_0/raw-probe.bin').exists()
        assert not (c.HOT/'PRODUCTION_COMPLETED.json').exists()
    def interruption_before_seal_marker():
        store,rows,cfg,v,f,data=fixture('seal-interrupted');old=retention.atomic
        def interrupt(path,value):
            if Path(path).name=='SEALED_POOL_C.FINAL.json' and Path(path).parent.name=='.compact_final':raise RuntimeError('Deliberate seal interruption')
            return old(path,value)
        retention.atomic=interrupt
        try:
            try:retention.finalise_compact(store,rows,cfg,v,f)
            except RuntimeError:pass
        finally:retention.atomic=old
        assert store.path.exists() and (c.HOT/'.compact_final/SEALED_POOL_C.sqlite').exists()
        retention.finalise_compact(store,rows,cfg,v,f)
        assert (c.HOT/'PRODUCTION_COMPLETED.json').exists()
    def held_plan():
        store,rows,cfg,v,f,data=fixture('held-plan');old=Path.unlink
        def held(path,*args,**kwargs):
            if path==c.HOT/retention.READY:raise PermissionError('Software-held reader')
            return old(path,*args,**kwargs)
        Path.unlink=held
        try:result=retention.finalise_compact(store,rows,cfg,v,f)
        finally:Path.unlink=old
        assert result['state']=='complete_review_required' and (c.HOT/'PRODUCTION_COMPLETED.json').exists()
        assert (c.HOT/retention.READY).exists() and retention.resume_finalization(cfg) is False
    try:
        for name,fn in [('boolean retention option and legacy default',option),('retention on preserves full evidence',keep),
                        ('failed verification never removes evidence',no_verification),
                        ('retention off keeps exact tables, private compact C and completed reuse',compact),
                        ('interrupted cleanup resumes without screening',interrupted_cleanup),
                        ('interrupted completion resumes after working data removal',interrupted_publication),
                        ('source corruption preserves working evidence',corrupt_source),
                        ('export corruption blocks resumed cleanup',corrupt_ready),
                        ('interrupted compact seal resumes without opening a sealed archive',interruption_before_seal_marker),
                        ('held plan reader cannot invalidate durable completion',held_plan)]:check(name,fn)
    finally:c.HOT=saved_hot;c.TOTAL=saved_total
    return checks

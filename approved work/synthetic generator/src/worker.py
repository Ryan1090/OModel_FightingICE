"""Isolated workers; durable C records enter only the encrypted runner archive."""
import json,os,shutil,sys,time,traceback,threading,contextlib
from pathlib import Path
import common as c
from gmtv.schema import digest,sha
from gmtv.storage import atomic,load_commit,commit
Store=c.local_module('sealed_store').Store;safe_remove=c.local_module('sealed_store').safe_remove

def paths(item,slot):
    if item['pool'].startswith('C_'):
        root=c.HOT/'private_work'/digest(item['id'])[:24]
        return root,root/'candidate',root/'home'
    folder=c.HOT/'characters'/item['id']
    if item.get('execution_revision')=='R2':folder=folder/'execution_r2'
    elif item.get('execution_revision')=='R4':folder=folder/'execution_r4'
    return None,folder,c.HOT/'workers'/f'worker_{item.get("runtime_slot",slot)}'

def provision_home(home):
    return c.local_module('runtime_api').provision(home)

def resume_c_workspace(store,item,slot):
    root,folder,home=paths(item,slot)
    if root.exists():
        # Recover an abrupt exit without publishing or dropping raw fixtures.
        store.capture('workspace:'+item['id'],root);safe_remove(root,c.HOT)
    provision_home(home)
    restored=store.restore('workspace:'+item['id'],root)
    if not restored:
        stock=c.HOT/'workers'/f'worker_{slot}'/'cache/stock'
        if stock.exists():shutil.copytree(stock,home/'cache/stock',dirs_exist_ok=True)
    return root,folder,home

def worker(slot,tasks,output):
    os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
    config=c.load_config();c.verify_release(config);store=Store(c.HOT,config['run_id'])
    c.local_module('io_release_v30').install() # exact-equivalence-tested display I/O fix
    import importlib.util
    while True:
        ident=tasks.get()
        if ident is None:return
        item=store.get('job:'+ident)
        admission=c.local_module('admission_r4')
        root,folder,home=paths(item,slot);is_c=root is not None;result=None
        heartbeat_stop=None;heartbeat_thread=None
        try:
            prior_hb=store.get('heartbeat:'+ident);job_wall_start=time.time()
            store.put('heartbeat:'+ident,{'phase':'preparing_runtime','work_phase':'runtime_integrity_verification','pid':os.getpid()})
            if is_c:root,folder,home=resume_c_workspace(store,item,slot)
            else:provision_home(home)
            os.environ['GMTV_HOME']=str(home);os.environ['GMTV_CASE_NAMESPACE']=c.NAMESPACE
            os.environ['GMTV_COHORT_PAUSE']=str(c.HOT/'PAUSE_REQUESTED')
            for k in ('GMTV_STOP_AFTER_NEW_PROBES','GMTV_VERIFY_SEPARATE_PROBES','GMTV_VERIFY_FRESH_STOCK'):os.environ.pop(k,None)
            folder.mkdir(parents=True,exist_ok=True);atomic(folder/'JOB.json',item)
            cc=c.item_config(config,item)
            binding=c.item_binding(config,item);saved=load_commit(folder/'STATE.json',binding);done=load_commit(folder/'COMMIT.json',binding)
            if prior_hb and prior_hb['phase']=='running' and not done:
                if c.pid_alive(prior_hb['pid']):raise RuntimeError('Previous worker still owns this pending candidate')
                if saved is not None:
                    charge=max(saved['active_seconds'],prior_hb['charged_active_seconds'])
                    store.put('interruption_state_before:'+ident,saved)
                    saved['active_seconds']=charge;saved['interruption_accounted_from_heartbeat']=True
                    commit(folder/'STATE.json',binding,saved)
            base_active=saved['active_seconds'] if saved else 0.;started=time.perf_counter();heartbeat_stop=threading.Event()
            def heartbeat():
                while not heartbeat_stop.wait(2):
                    probe={}
                    try:
                        q=json.loads((home/'status.json').read_text())
                        if q.get('pid')==os.getpid() and q.get('updated_epoch',0)>=job_wall_start:
                            probe={'probe_records':q.get('completed_probes',0),'new_physical_probes':q.get('new_probes_this_invocation',0),'probe_epoch':q.get('updated_epoch') if q.get('completed_probes',0)>0 else None}
                    except (OSError,ValueError):pass
                    store.put('heartbeat:'+ident,{'phase':'running','work_phase':'screening_or_repair','pid':os.getpid(),'charged_active_seconds':base_active+time.perf_counter()-started+2,'rule':'active clock plus two-second heartbeat cushion',**probe})
            if not done:
                store.put('heartbeat:'+ident,{'phase':'running','pid':os.getpid(),'charged_active_seconds':base_active+2,'rule':'active clock plus two-second heartbeat cushion'})
                heartbeat_thread=threading.Thread(target=heartbeat,daemon=True);heartbeat_thread.start()
            with contextlib.ExitStack() as scope:
                if is_c:
                    private_log=scope.enter_context((root/'PRIVATE_EXECUTION_LOG.txt').open('a',encoding='utf-8'))
                    scope.enter_context(contextlib.redirect_stdout(private_log));scope.enter_context(contextlib.redirect_stderr(private_log))
                result=admission.run_job(item,home,folder,cc,c.HOT/'PAUSE_REQUESTED')
            result={**result,'worker_slot':slot}
            if result.get('state')=='assessed':
                if load_commit(folder/'COMMIT.json',c.item_binding(config,item)) is None:raise RuntimeError('Candidate commitment failed')
        except Exception:
            result={'id':ident,'state':'infrastructure_failure','worker_slot':slot,'reason':'Worker execution/integrity failure'}
            store.put('error:'+ident,{'traceback':traceback.format_exc(),'pool':item['pool']})
        finally:
            if heartbeat_stop is not None:heartbeat_stop.set()
            if heartbeat_thread is not None:heartbeat_thread.join(timeout=10)
            if result is not None:store.put('heartbeat:'+ident,{'phase':'finished_or_paused','pid':os.getpid()})
            if is_c and root.exists():
                try:
                    snapshot=store.capture('workspace:'+ident,root)
                    store.put('workspace_receipt:'+ident,snapshot)
                    safe_remove(root,c.HOT)
                except Exception:
                    store.put('error:'+ident,{'traceback':traceback.format_exc(),'phase':'seal workspace'})
                    result={'id':ident,'state':'integrity_failure','worker_slot':slot,'reason':'C workspace could not be sealed'}
            if result is not None:
                store.put('execution:'+ident,result)
                output.put({'id':ident,'state':result['state'],'slot':slot})

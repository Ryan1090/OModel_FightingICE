"""630-slot resumable production coordinator; public outputs are aggregate only."""
import argparse,collections,datetime,importlib.util,json,multiprocessing as mp,os,queue,time,traceback
from pathlib import Path
import numpy as np
import common as c
from gmtv.schema import sha,digest
from gmtv.storage import atomic,Lock
from gmtv.status import best_effort_status
Store=c.local_module('sealed_store').Store
gen=c.local_module('generator_production');policy=c.local_module('policy')

def worker_entry(slot,tasks,output):
    spec=importlib.util.spec_from_file_location('v28_worker_runtime',c.HERE/'worker.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.worker(slot,tasks,output)

def fresh_state(config):
    schedule=c.original.schedule();slots={}
    for root in config['roots']:
        for i,meta in enumerate(schedule):slots[root+'/'+str(i)]={'root':root,'meta':meta,'stratum':list(c.actual_stratum(meta,meta['pool']))}
    return {'roots':config['roots'],'slots':slots,'accepted_slots':{},'items':{},'decisions':{},'draws':{},'checkpoints':{},
      'construction_rejections':{},'far_supply':{},'active_seconds':0.,'inflight':{}}

def counts(state,pool,root=None):
    return sum(state['slots'][k]['meta']['pool']==pool and (root is None or state['slots'][k]['root']==root) for k in state['accepted_slots'])

def live_work_summary(items,store,now=None):
    now=time.time() if now is None else now
    phases=collections.Counter();records=physical=0;epochs=[];unavailable=0
    for item in items:
        try:heartbeat=store.get('heartbeat:'+item['id']) or {}
        except PermissionError:
            phases['progress_temporarily_unavailable']+=1;unavailable+=1;continue
        phases[heartbeat.get('work_phase','worker_initialisation')]+=1
        if heartbeat.get('phase')=='running':
            records+=heartbeat.get('probe_records',0);physical+=heartbeat.get('new_physical_probes',0)
            if heartbeat.get('probe_epoch'):epochs.append(heartbeat['probe_epoch'])
    return {'phase_counts':dict(phases),'current_screen_probe_records':records,'current_screen_new_physical_probes':physical,'latest_probe_activity_age_seconds':max(0,now-max(epochs)) if epochs else None,'temporarily_unavailable_heartbeats':unavailable,'scope':'Aggregates across in-flight screens; counts reset per invocation; reused records included'}

def replacement_roles(meta,draw):
    if meta['pool']=='C_near':return meta['secondary'],meta['secondary_sign']
    p=meta['primary'];choices=[s for s in range(5) if s!=p and tuple(sorted((p,s))) not in gen.model.RESERVED]
    return choices[(choices.index(meta['secondary'])+draw)%len(choices)],meta['secondary_sign']*(-1 if draw%2 else 1)

def phase(state):return next((p for p in c.POOLS if counts(state,p)<5*c.QUOTAS[p]),None)

def allowed_slot(state,key,inflight):
    slot=state['slots'][key];pool=phase(state)
    if slot['meta']['pool']!=pool or key in state['accepted_slots'] or any(i['slot_key']==key for i in inflight.values()):return False
    if pool=='A' and 'first_50_A' not in state['checkpoints']:
        return counts(state,pool,slot['root'])+sum(i['root']==slot['root'] for i in inflight.values())<min(10,c.QUOTAS['A'])
    if pool=='C_far' and 'first_10_far' not in state['checkpoints']:
        return counts(state,pool,slot['root'])+sum(i['root']==slot['root'] for i in inflight.values())<min(2,c.QUOTAS['C_far'])
    return True

def accepted_rows(state,results):return [results[i] for i,d in state['decisions'].items() if d['accepted']]

def integrate(state,item,result,accepted,config):
    ident=item['id']
    if ident in state['decisions']:return False
    reasons=[] if result['admitted'] else ['screen/profile admission']
    row={**result,'stratum':item['stratum'],'construction_trim_count':sum(r.get('trimmed',False) for r in item['initial_audit'])}
    reasons+=policy.distance_reasons(config,row,accepted)
    if item['slot_key'] in state['accepted_slots']:reasons.append('slot already committed')
    state['decisions'][ident]={'accepted':not reasons,'reasons':reasons,'slot_key':item['slot_key']}
    if not reasons:state['accepted_slots'][item['slot_key']]=ident
    return row

def recover_committed(state,store,config):
    results={};accepted=[];pending=[]
    for ident,entry in state['items'].items():
        if ident in state.get('infrastructure_quarantined',{}):continue
        result=store.get('execution:'+ident)
        if ident in state['decisions']:
            if result is None:raise RuntimeError('INTEGRITY: lost committed candidate')
            item=store.get('job:'+ident)
            result={**result,'stratum':entry['stratum'],'construction_trim_count':sum(a.get('trimmed',False) for a in item['initial_audit'])};results[ident]=result
            if state['decisions'][ident]['accepted']:accepted.append(result)
        elif result and result.get('state')=='assessed':
            item=store.get('job:'+ident);row=integrate(state,item,result,accepted,config);results[ident]=row
            if state['decisions'][ident]['accepted']:accepted.append(row)
        else:pending.append(ident)
    return results,accepted,pending

def record_infrastructure(state,item,result):
    kind=result['fault']['kind'];state.setdefault('infrastructure_faults',[]).append({'pool':item['pool'],'kind':kind,'epoch':time.time()})
    if result['state']=='infrastructure_retry':return 'retry'
    if kind=='integrity_failure':return 'stop'
    state.setdefault('infrastructure_quarantined',{})[item['id']]={'kind':kind,'reason':result['fault']['reason'],'excluded_from_acceptance':True}
    return 'quarantine'

def make_item(key,state,accepted,config,runtime_slot):
    slot=state['slots'][key];root=slot['root'];meta=slot['meta'];pool=meta['pool'];model=gen.models()[0][root]
    for _ in range(8):
        draw=state['draws'].get(key,0)
        if draw>=config['production_max_draws_per_stratum']:raise RuntimeError('STRATUM_UNFILLABLE: production draw limit reached')
        state['draws'][key]=draw+1;ident=c.candidate_id(root,pool,[key,slot['stratum']],draw)
        if ident in state['items']:continue # migrated inputs keep their original IDs
        secondary,secondary_sign=replacement_roles(meta,draw)
        T,actual_meta=gen.sample(root,meta['primary'],secondary,meta['sign'],secondary_sign,pool,ident,c.NAMESPACE)
        refs={p:[r['final_vector'] for r in accepted if r['root']==root and r['pool']==p] for p in ('A','B')}
        if pool.startswith('C_') and (len(refs['A'])!=c.QUOTAS['A'] or len(refs['B'])!=c.QUOTAS['B']):raise RuntimeError('INTEGRITY: held-out reference set incomplete')
        reference=refs['A'] if pool=='C_far' else None
        cc={**config,'runtime_reference_vectors':refs}
        y,noise,audit=gen.build(root,T,c.NAMESPACE,ident,cc,reference=reference)
        score=float(gen.design_context.c.core_score(model,y[None,:],meta['primary'])[0])
        profile=gen.assess_profile(root,y,T,actual_meta,score,cc,reference,gen.reversion_keys(audit))
        if pool=='C_far':
            supply_key=root+'/'+','.join(map(str,slot['stratum']))
            supply=state['far_supply'].setdefault(supply_key,{'construction_draws':0,'initial_qualifiers':0,'best_nearest_AB':None,'trimmed_cell_events':0})
            supply['construction_draws']+=1;supply['trimmed_cell_events']+=sum(a.get('trimmed',False) for a in audit)
            nearest=min(profile['reference_distances'].values())
            supply['best_nearest_AB']=max(nearest,supply['best_nearest_AB']) if supply['best_nearest_AB'] is not None else nearest
            supply['initial_qualifiers']+=bool(profile['passed'])
        if not profile['passed']:
            reason='construction profile/distance/support';state['construction_rejections'][reason]=state['construction_rejections'].get(reason,0)+1
            continue
        return {'id':ident,'root':root,'pool':pool,'stratum':slot['stratum'],'slot_key':key,'namespace':c.NAMESPACE,
          'traits':T.tolist(),'meta':actual_meta,'initial_vector':y.tolist(),'initial_noise':noise.tolist(),'initial_audit':audit,
          'reference':reference,'admission_references':refs,'runtime_slot':runtime_slot,
          'context':{'usage':{name:float(model['usage'][j]) for j,name in enumerate(model['names'])}},'construction_draws':draw+1,'permanently_pool_ineligible':False,'execution_revision':'R4'}
    return None # checkpoint construction progress before the next small batch

def run(workers,stage_seconds=None,stage_label=None):
    config=c.load_config();c.verify_release(config);c.HOT.mkdir(parents=True,exist_ok=True)
    if (c.HOT/'PRODUCTION_COMPLETED.json').exists():return
    retention=c.local_module('evidence_retention')
    if retention.resume_finalization(config):return
    binding=config['configuration_sha256']
    with Lock(c.HOT/'COORDINATOR.lock'):
        store=Store(c.HOT,config['run_id']);state=store.get('coordinator') or fresh_state(config)
        if state.get('configuration_sha256',binding)!=binding:raise RuntimeError('Run/state configuration mismatch')
        state['configuration_sha256']=binding
        # Durable execution records are reconciled before any scheduling. A
        # crash after worker commit can never cause a second admission.
        results,accepted,pending=recover_committed(state,store,config)
        for ident in pending:
            hb=store.get('heartbeat:'+ident)
            if hb and hb.get('phase')=='running' and c.pid_alive(hb['pid']):raise RuntimeError('An original worker is still active; refuse duplicate execution')
        tasks=[mp.Queue() for _ in range(workers)];out=mp.Queue();procs=[];inflight={};start=time.perf_counter();base=state['active_seconds'];stopped=None
        state.pop('stop_reason',None)
        state['current_session']={'workers':workers,'accepted_start':len(accepted),'active_start':base,'completed_start':len(results),'throughput_stage':stage_label}
        for slot in range(workers):
            p=mp.Process(target=worker_entry,args=(slot,tasks[slot],out));p.start();procs.append(p)
        def persist(status='running'):
            state['active_seconds']=base+time.perf_counter()-start;state['inflight']={str(k):v['id'] for k,v in inflight.items()}
            store.put('coordinator',state)
            done=list(results.values());summary=policy.public_summary(accepted,done,state,state['active_seconds'],workers)
            summary['state']=status;summary['active_workers']=len(inflight);summary['configuration_sha256']=binding
            summary['updated_Perth']=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()
            summary['throughput_stage']=stage_label
            summary['stage_elapsed_seconds']=time.perf_counter()-start
            summary['live_work']=live_work_summary(inflight.values(),store)
            best_effort_status(c.HOT/'status.json',summary)
            return summary
        def schedule(slot):
            nonlocal stopped
            if stopped or (c.HOT/'PAUSE_REQUESTED').exists():return
            item=None
            for ident in list(pending):
                candidate=store.get('job:'+ident)
                if candidate['pool']==phase(state) and (candidate['pool'].startswith('C_') or candidate['runtime_slot'] not in {i['runtime_slot'] for i in inflight.values()}):
                    item=candidate;pending.remove(ident);break
            if item is None and pending:return
            if item is None:
                available=[k for k in state['slots'] if allowed_slot(state,k,inflight)]
                if not available:return
                available.sort(key=lambda k:(counts(state,phase(state),state['slots'][k]['root'])+sum(i['root']==state['slots'][k]['root'] for i in inflight.values()),state['slots'][k]['root'],int(k.split('/')[-1])))
                busy={i['runtime_slot'] for i in inflight.values()};runtime_slot=next(i for i in range(max(12,workers)) if i not in busy)
                item=make_item(available[0],state,accepted,config,runtime_slot)
                if item is None:persist();return
                store.put('job:'+item['id'],item);state['items'][item['id']]={k:item[k] for k in ('root','pool','stratum','slot_key','runtime_slot')}
            inflight[slot]=item;persist();tasks[slot].put(item['id'])
        def prepare_far_forecast():
            # These are the next real production proposals, durably queued for
            # later screening, not an additional experiment or altered bank.
            for root in state['roots']:
                for stratum in c.strata('C_far'):
                    keys=[k for k,v in state['slots'].items() if v['root']==root and v['meta']['pool']=='C_far' and tuple(v['stratum'])==stratum and k not in state['accepted_slots']]
                    if not keys:continue
                    key=keys[0]
                    if any(entry['slot_key']==key and ident not in state['decisions'] for ident,entry in state['items'].items()):continue
                    item=None
                    while item is None:
                        item=make_item(key,state,accepted,config,0);persist()
                    store.put('job:'+item['id'],item);state['items'][item['id']]={k:item[k] for k in ('root','pool','stratum','slot_key','runtime_slot')};pending.append(item['id']);persist()
        try:
            persist()
            while phase(state) is not None or inflight:
                if stage_seconds is not None and time.perf_counter()-start>=stage_seconds and not stopped:
                    stopped='Throughput stage boundary';atomic(c.HOT/'PAUSE_REQUESTED',{'reason':stopped})
                for slot in range(workers):
                    if slot not in inflight:schedule(slot)
                if not inflight:
                    if phase(state) is not None and not stopped and not (c.HOT/'PAUSE_REQUESTED').exists():persist();continue
                    break
                try:message=out.get(timeout=2)
                except queue.Empty:
                    if any(not procs[s].is_alive() for s in inflight):stopped='Worker exited; committed records retained';atomic(c.HOT/'PAUSE_REQUESTED',{'reason':stopped})
                    persist('pausing' if stopped else 'running')
                    if stopped:break
                    continue
                slot=message['slot'];item=inflight.pop(slot);r=store.get('execution:'+item['id'])
                if r and r.get('state')=='assessed':
                    row=integrate(state,item,r,accepted,config);results[item['id']]=row
                    if state['decisions'][item['id']]['accepted']:accepted.append(row)
                elif r and r.get('state') in ('infrastructure_retry','infrastructure_fault'):
                    action=record_infrastructure(state,item,r)
                    if action=='retry':pending.append(item['id'])
                    elif action=='stop':stopped='Integrity failure; excluded from acceptance'
                elif r and r.get('state')=='paused':stopped=stopped or ('Pause requested' if stage_label is None else 'Throughput stage boundary' if time.perf_counter()-start>=stage_seconds else 'User pause requested')
                else:stopped='Integrity/infrastructure failure; private details retained'
                s=persist('pausing' if stopped else 'running');reason=policy.stop_reason(s,config)
                if reason:stopped=reason
                if not stopped and 'first_10_far' not in state['checkpoints'] and policy.checkpoint_ready('first_10_far',accepted,state['roots']):prepare_far_forecast()
                policy.write_checkpoints(state,accepted,list(results.values()),config,state['active_seconds'],workers)
                if stopped:atomic(c.HOT/'PAUSE_REQUESTED',{'reason':stopped})
                persist('pausing' if stopped else 'running')
                if stopped and not inflight:break
        except Exception as error:
            stopped='Stratum appears unfillable' if str(error).startswith('STRATUM_UNFILLABLE') else 'Integrity/engineering failure'
            store.put('coordinator_error',{'traceback':traceback.format_exc()});atomic(c.HOT/'PAUSE_REQUESTED',{'reason':stopped})
        finally:
            for q in tasks:q.put(None)
            for p in procs:p.join(timeout=45)
            for p in procs:
                if p.is_alive():p.terminate();p.join()
            inflight.clear() # workers have exited; durable pending jobs stay in items
            if stopped:state['stop_reason']=stopped
            persist('stopped_or_paused' if stopped or phase(state) is not None else 'verifying_before_seal')
            policy.write_checkpoints(state,accepted,list(results.values()),config,state['active_seconds'],workers)
            store.put('coordinator',state)
        if phase(state) is None and not stopped:
            final_start=time.perf_counter()
            verify=c.local_module('final_verify').verify
            verification=verify(store,state,accepted,config)
            atomic(c.HOT/'PRE_FREEZE_VERIFICATION.json',verification)
            if not verification['integrity_passed']:atomic(c.HOT/'STOP_CONDITION.json',{'reason':'Final integrity verification failed'});return
            final=policy.public_summary(accepted,list(results.values()),state,state['active_seconds']+time.perf_counter()-final_start,workers)
            final['state']='complete_review_required';final['pre_freeze_verification']=verification;atomic(c.HOT/'FINAL.json',final)
            store.put('final_coordinator',state)
            if retention.retention_enabled(config):
                checksum=store.finalise()
                final['elapsed_seconds']=state['active_seconds']+time.perf_counter()-final_start
                atomic(c.HOT/'FINAL.json',final)
                atomic(c.HOT/'PRODUCTION_COMPLETED.json',{'accepted':c.TOTAL,'archive_sha256':checksum,'archive_reopened':False,'split_frozen':False,'retain_evidence':True})
                best_effort_status(c.HOT/'status.json',final)
            else:
                retention.finalise_compact(store,accepted,config,verification,final)
        elif stopped:atomic(c.HOT/'STOP_CONDITION.json',{'reason':stopped,'split_frozen':False})
        return stopped

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--action',choices=['Run','Resume','Pause','Status'],required=True);p.add_argument('--workers',type=int,default=12);a=p.parse_args()
    if a.action=='Status':print((c.HOT/'status.json').read_text())
    elif a.action=='Pause':atomic(c.HOT/'PAUSE_REQUESTED',{'reason':'User pause'})
    else:
        if a.action=='Resume' and (c.HOT/'PAUSE_REQUESTED').exists():(c.HOT/'PAUSE_REQUESTED').unlink()
        run(a.workers)

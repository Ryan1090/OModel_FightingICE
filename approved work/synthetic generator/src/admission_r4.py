"""V28 R2 work-bounded V26 repair stages; elapsed limits never reject."""
import json,os,time,sys
from pathlib import Path
import numpy as np
BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE))
import common as production_common
gen=production_common.local_module('generator_production')
d=gen.design_context
from gmtv.schema import sha,digest
from gmtv.storage import atomic,commit,load_commit

from repair_batch import apply_batch

def failing_cells(report):
    failures={};rejected=set()
    for x in report.get('static_issues',[]):
        key=x['move'],x['property'];failures[key]=x.get('reason','static failure');rejected.add(key)
    for group in report.get('groups',[]):
        for x in group.get('results',[]):
            if x.get('status')=='PASSED' or 'cell' not in x:continue
            key=x['cell']['move'],x['cell']['property'];failures[key]=x.get('reason',group.get('reason','unresolved'))
            if x.get('status')=='REJECTED':rejected.add(key)
    return failures,rejected

def invariant_closure(m,y):
    y=np.array(y,copy=True);events=[]
    for name in m['names']:
        f,s,a=[m['pos'][name,p] for p in ('frameNumber','attack.StartUp','attack.Active')]
        if y[s]>=y[f] or (not d.c.v1.is_projectile(m['table'][name]) and y[a]>y[f]-y[s]):
            for j in (f,s,a):
                if y[j]!=m['stock'][j]:events.append({'move':name,'property':m['cells'][j][1],'cause':'revert closure: preserve move invariant'});y[j]=m['stock'][j]
    return y,events


def interruption_kind(report):
    reason=report.get('reason','').lower()
    if report.get('verdict')!='SCREEN_INCOMPLETE':return None
    if 'engine startup ceiling' in reason:return 'engine_startup_timeout'
    if any(x in reason for x in ('budget exhausted','execution budget','screen budget','deadline')):return 'safety_cap'
    if any(x in reason for x in ('timed out twice','per-probe wall limit','timeout','time limit')):return 'probe_timeout_exhausted'
    return None

def run_job(item,home,folder,config,pause_path,stop_after_probes=0):
    config={**config,'same_input_timeout_retry_limit':0}
    config['configuration_sha256']=digest({'source_configuration':config['configuration_sha256'],'V28_R4_engine_startup_adapter':sha(__file__),'timeout_retries':0})
    _production_api=production_common.local_module('api_r2')
    validate,context_for=_production_api.validate,_production_api.context_for
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);home=Path(home)
    binding=digest({'config':config['configuration_sha256'],'job':item})
    done=load_commit(folder/'COMMIT.json',binding)
    if done is not None:return {**done,'reused_candidate_commit':True}
    if (folder/'COMMIT.json').exists():raise RuntimeError('Invalid completed candidate commitment')
    root=item['root'];m=d.prior.models()[0][root];g=d.prior.models()[1][root]
    reference=np.array(item['reference']) if item.get('reference') is not None else None
    statepath=folder/'STATE.json';state=load_commit(statepath,binding)
    if state is None and statepath.exists():raise RuntimeError('Invalid committed repair state')
    if state is None:
        if 'initial_vector' in item:y,noise,audit=np.array(item['initial_vector']),np.array(item['initial_noise']),item['initial_audit']
        else:y,noise,audit=gen.build(root,item['traits'],item['namespace'],item['id'],config,reference=reference)
        initial=float(d.c.core_score(m,y[None,:],item['meta']['primary'])[0])
        state={'y':y.tolist(),'noise':noise.tolist(),'audit':audit,'attempt':0,'redraws':{},'reverts':[],'attempts':[],
            'repair_rounds':0,'final_reversion_done':False,'batches':[],'repair_seconds':0.,'initial_primary_score':initial,'active_seconds':0.,'budget_spent':False,'selftest_interruption_done':False,'timeout_retries':0,'budget_epoch_seconds':0.}
        commit(statepath,binding,state)
    session_start=time.perf_counter();terminal=None
    def store():commit(statepath,binding,state)
    def infrastructure(kind,reason,used):
        state['active_seconds']=used
        fault={'kind':kind,'reason':reason,'accrued_seconds':used,'attempt':state['attempt']}
        state.setdefault('infrastructure_faults',[]).append(fault)
        retry=kind=='safety_cap' and state.get('safety_retries',0)<1
        if retry:
            state['safety_retries']=1;state['safety_epoch_seconds']=used
        store()
        return {'state':'infrastructure_retry' if retry else 'infrastructure_fault','id':item['id'],'root':item['root'],'pool':item['pool'],'fault':fault,'excluded_from_acceptance':True,'retry_same_committed_state':retry}

    try:
        while True:
            if Path(pause_path).exists():return {'state':'paused','id':item['id']}
            used=state['active_seconds']+time.perf_counter()-session_start
            remaining=1800-(used-state.get('safety_epoch_seconds',0.))
            if remaining<12:
                return infrastructure('safety_cap','Thirty-minute infrastructure safety cap reached',used)
            y=np.array(state['y']);attempt=state['attempt'];p=folder/f'attempt_{attempt:02d}'/'Motion.csv'
            if not p.exists():gen.write(root,y,p,item['namespace'],config,state['audit'])
            else:
                from gmtv.schema import read
                actual=read(p,root)
                if not np.array_equal(y,np.array([actual[n][prop] for n,prop in m['cells']])):raise RuntimeError('Committed attempt input changed')
            start=time.perf_counter()
            if stop_after_probes and not state['selftest_interruption_done']:os.environ['GMTV_STOP_AFTER_NEW_PROBES']=str(stop_after_probes)
            else:os.environ.pop('GMTV_STOP_AFTER_NEW_PROBES',None)
            report=validate(p,root,home=home,budget_seconds=remaining,context=context_for(item))
            runtime=time.perf_counter()-start
            interrupted=Path(pause_path).exists() or ('pause' in report.get('reason','').lower())
            if stop_after_probes and not state['selftest_interruption_done'] and report.get('verdict')=='SCREEN_INCOMPLETE':
                output=Path(report['output']);flag=output/'PAUSE_REQUESTED'
                if flag.exists():
                    # Only the deliberate verification's flag is cleared here;
                    # user/cohort pause flags are controlled by Resume.
                    content=json.loads(flag.read_text())
                    if content.get('reason')=='deliberate validator lifecycle verification':
                        state['selftest_interruption_done']=True
                        commit(folder/'INTERRUPTION_CONTROL.json',binding,{'verdict':report['verdict'],'fixture_pause_flag':str(flag),'input_sha256':sha(p),
                            'seconds':runtime,'statement':'Deliberate stop after atomic fixture commits; no mechanic failure/revert inferred.'})
                        flag.unlink();state['active_seconds']+=time.perf_counter()-session_start;store();return {'state':'verification_paused','id':item['id']}
            if interrupted:state['active_seconds']+=time.perf_counter()-session_start;store();return {'state':'paused','id':item['id']}
            if report.get('verdict')=='INFRASTRUCTURE_FAILURE':
                atomic(folder/('INFRASTRUCTURE_FAILURE.'+str(time.time_ns())+'.json'),report)
                errors=' '.join(str(r.get('error','')) for r in report.get('cost',{}).get('infrastructure_failures',[])).lower()
                integrity=any(t in errors for t in ('digest mismatch','input bytes changed','atomic record failed','checksum','sha differs','integrity failure'))
                return infrastructure('integrity_failure' if integrity else 'validator_infrastructure',report.get('reason','Infrastructure failure'),state['active_seconds']+time.perf_counter()-session_start)
            kind=interruption_kind(report)
            if kind:
                state.setdefault('infrastructure_invocations',[]).append({'attempt':attempt,'report':report.get('output'),'seconds':runtime,'kind':kind,'reason':report.get('reason')})
                return infrastructure(kind,report.get('reason','Unfinished infrastructure evidence'),state['active_seconds']+time.perf_counter()-session_start)
            state['attempts'].append({'attempt':attempt,'input_sha256':sha(p),'screen_verdict':report.get('verdict'),'seconds':runtime,
                'phase':'initial' if attempt==0 else 'final' if state['final_reversion_done'] else 'repair_round_'+str(state['repair_rounds']),
                'report':report.get('output'),'cost':report.get('cost',{}),'coverage':report.get('verified_share',{})})
            state['logical_screens_completed']=state.get('logical_screens_completed',state['repair_rounds'])+1
            if state['logical_screens_completed']>5:raise RuntimeError('More than five logical screening stages')
            if report.get('screen_passed'):
                profile=gen.assess_profile(root,y,item['traits'],item['meta'],state['initial_primary_score'],config,reference,gen.reversion_keys(state['audit'],state['reverts']))
                terminal={'state':'assessed','screen_passed':True,'profile':profile,'reason':'Complete candidate passed bounded screen; table-only fields are not individually gameplay-certified'};break
            if state['final_reversion_done']:
                terminal={'state':'assessed','screen_passed':False,'reason':'Final screen after three batch repair rounds and joint reversion did not pass; no further repairs'};break
            failures,rejected=failing_cells(report)
            if not failures:
                terminal={'state':'assessed','screen_passed':False,'reason':'Screen incomplete without a fully assessed failing cell; no inference/revert from absent evidence'};break
            repair_started=time.perf_counter()
            batch=apply_batch(item,state,report,config,final=state['repair_rounds']>=3)
            state['repair_seconds']+=time.perf_counter()-repair_started
            state['attempt']+=1;store()
            if not batch['changed']:
                terminal={'state':'assessed','screen_passed':False,'reason':'Batch produced no changed complete table; non-passing evidence never becomes a pass'};break
        state['active_seconds']+=time.perf_counter()-session_start;store()
        final_y=np.array(state['y']);final_path=folder/'FINAL_Motion.csv'
        gen.write(root,final_y,final_path,item['namespace'],config,state['audit'])
        profile=terminal.get('profile') or gen.assess_profile(root,final_y,item['traits'],item['meta'],state['initial_primary_score'],config,reference,gen.reversion_keys(state['audit'],state['reverts']))
        result={**terminal,'id':item['id'],'root':root,'pool':item['pool'],'traits':item['traits'],'meta':item['meta'],
            'admitted':bool(terminal['screen_passed'] and profile['passed']),'profile':profile,'final_path':str(final_path),
            'final_sha256':sha(final_path),'final_vector':final_y.tolist(),'attempts':state['attempts'],'redraws':state['redraws'],
            'batches':state['batches'],'repair_rounds':state['repair_rounds'],'final_reversion_done':state['final_reversion_done'],
            'reverts':state['reverts'],'repair_seconds':state['repair_seconds'],'seconds':state['active_seconds'],'permanently_pool_ineligible':item['namespace']==config['diagnostic_namespace'],
            'configuration_sha256':config['configuration_sha256'],'initial_edit_count':sum(r['retained'] for r in state['audit']),
            'retained_edit_count':int(np.sum(final_y!=m['stock'])),'interruption_control':state['selftest_interruption_done'],'timeout_retries':state.get('timeout_retries',0)}
        files=[final_path,final_path.with_suffix('.provenance.json')]
        for row in state['attempts']:
            if row['report'] and (Path(row['report'])/'REPORT.json').exists():files.append(Path(row['report'])/'REPORT.json')
        commit(folder/'COMMIT.json',binding,result,files)
        return result
    finally:os.environ.pop('GMTV_STOP_AFTER_NEW_PROBES',None)

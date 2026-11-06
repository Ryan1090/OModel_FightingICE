"""The two-argument public entry point; baselines and controls are internal."""
import asyncio
import gzip
import json
import os
import time
from pathlib import Path
from . import __version__
from .schema import ROOTS,sha,digest,read,diff,invariants
from .storage import atomic,commit,load_commit,Lock
from .stock_inputs import references
from .materialise import stage
from .execution import CandidateSession,ScreenBudgetExceeded
from .planning import move_scenarios,cancel_scenarios,horizon
from .assessment import assess,roles_for,applicability
from .geometry import assess_geometry
from .measure import effect,compact
from .stock_refinement import contact_placement,whiff_avoidance
from .kinematics import jump_profile
from .cancel_evidence import evaluate as cancel_evaluate
from .oracle import replay
from .rules import INPUT_ACTIONS,attributed_relationships
from .construct import scenarios
from .tolerances import policy
from .fingerprint import instrument
from .status import publish
from .screening import POLICY,check_relationship
from . import fast


def home():
    return Path(os.environ.get('GMTV_HOME',str(Path(__file__).resolve().parents[2]/'generated characters/validator_runtime')))


def metadata(record,table):
    if record.get('infrastructure_failure'):
        return {'method_gaps':[record['infrastructure_failure']]}
    measured=effect(record,table)
    if record.get('request',{}).get('observation_policy')=='fast-fixed-horizon-v1':
        trace=record['observation'].get('trace',[])
        if trace and record['observation'].get('issued'):
            last=trace[-1]['me']
            if last['action']==record['spec']['move'] and not last['control'] and last['remaining']>1:
                measured.setdefault('method_gaps',[]).append('Short fixed horizon ended before source completion; effect not accepted from truncated action.')
    return measured


def verify_cell_accounting(changes,cells):
    expected={(c['move'],c['property']) for c in changes}
    actual=[(c['move'],c['property']) for c in cells]
    if len(actual)!=len(expected) or set(actual)!=expected:
        raise RuntimeError('Incomplete or duplicated per-edit assessment; candidate cannot be accepted')


def finish(report,hot,output,started):
    """Persist a readable result for rejected inputs as well as gameplay runs."""
    if report.get('mode')=='fast':fast.finalise(report)
    report['seconds']=time.perf_counter()-started
    atomic(output/'REPORT.json',report)
    text=['# Move-table validation','','**'+report['verdict']+'** - '+report['reason'],'',
        'Root: '+report['base_character']+'. Edited cells: '+str(report.get('changed_cells','unknown'))+'. Release: development.','',
        '| Move | Property | Verdict | Reason |','| --- | --- | --- | --- |']
    text+=['| '+c['move']+' | '+c['property']+' | '+c['verdict']+' | '+c['reason'].replace('|','/')+' |' for c in report['cells']]
    if report.get('cost'):text+=['','Execution cost: `'+json.dumps(report['cost'],sort_keys=True)+'`.']
    if report.get('coverage'):text+=['','Coverage: `'+json.dumps(report['coverage'],sort_keys=True)+'`.','',
        'SCREEN_PASSED does not mean every edit received gameplay evidence. TABLE_CHECKED edits have no gameplay-effect claim.']
    (output/'REPORT.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
    publish(hot,{'state':report['run_state'],'activity':'validator invocation','verdict':report['verdict'],
        'valid':report['valid'],'candidate_sha256':report.get('candidate_sha256'),'base_character':report['base_character'],
        'report':str(output/'REPORT.md'),'report_json':str(output/'REPORT.json'),'release_status':'DEVELOPMENT',
        'updated_epoch':time.time(),'active_engine_runs':0,'progress':report.get('cost',{}).get('progress','0/0 gameplay probes')})
    if report['run_state']=='complete':
        files=[output/'REPORT.json',output/'REPORT.md'];ledger_path=output/'LEDGER.json'
        if ledger_path.exists():
            files.append(ledger_path)
            for entry in json.loads(ledger_path.read_text())['records']:
                raw=Path(entry['raw_path']);files.append(raw)
                envelope=json.loads(gzip.decompress(raw.read_bytes()))
                files.extend(Path(p) for p in envelope['files'])
        commit(output/'CANDIDATE_COMMIT.json',digest({'candidate':report.get('candidate_sha256'),
            'root':report['base_character'],'code':report.get('instrument_sha256',report['source_sha256'])}),report,files)
    return report


def suitable(spec,metrics):
    if metrics.get('method_gaps'):return False
    role=spec['role']
    if role=='hit':return bool(metrics.get('contact_count')) and not metrics.get('guarded')
    if role=='guard':return bool(metrics.get('guarded'))
    if role=='whiff':return not metrics.get('contact_count')
    return True


async def baseline(executor,spec,inputs):
    """Construct/refine stock-only controls before looking at candidate effects."""
    root=executor.root;stock=inputs[root]['table'];zen=inputs['ZEN']['table'];current=dict(spec)
    attempts=[]
    for design in range(3):
        record=await executor.execute(current,'stock');metrics=metadata(record,stock)
        attempts.append({'scenario':current,'stock_metrics':compact(metrics)})
        if suitable(current,metrics):return current,record,attempts
        if record.get('infrastructure_failure') or metrics.get('method_gaps'):return current,record,attempts
        if current['role']=='whiff' and metrics.get('contact_count'):
            next_spec=whiff_avoidance(record,jump_profile(zen))
        elif current['role'] in {'hit','guard'}:
            next_spec=contact_placement(record,stock,zen,inputs[root]['width'],inputs['ZEN']['width'])
        else:return current,record,attempts
        if digest(next_spec)==digest(current):return current,record,attempts
        current=next_spec
    return current,record,attempts


def cancel_attempt(record,runtime,output,table,decoder=None):
    spec=record['spec'];obs=record.get('observation',{});request=obs.get('request');transition=None;verified=False;pre=None
    if request:
        decoded=decoder.decode(obs['inputs']) if decoder is not None else replay(runtime,output/'command_oracle',obs['inputs'])
        match=next((x for x in decoded if request['frame']<=x['frame']<=request['frame']+12 and x['interpreted_action']==spec['followup']),None)
        if match:
            verified=True;pre=next((x['me'] for x in obs['trace'] if x['frame']==match['frame']),None)
            for before,now in zip(obs['trace'],obs['trace'][1:]):
                if now['frame']<=match['frame']:continue
                if before['me']['action']==spec['move'] and now['me']['action']==spec['followup']:
                    transition={'from':spec['move'],'to':spec['followup'],'source_remaining':before['me']['remaining'],
                        'source_control':before['me']['control'],'frame':now['frame']};break
    return {'orientation':spec['orientation'],'role':spec['role'],'source':spec['move'],'followup':spec['followup'],
        'pre_input':pre,'transition':transition,'command_verified':verified,'load_verified':record.get('load_verified',False)}


async def execute(executor,inputs,changes):
    stock=inputs[executor.root]['table'];candidate=executor.tables['candidate'];zen=inputs['ZEN']['table']
    pairs={};method_notes=[];results=[]
    executor.partial_cells=results
    for move in dict.fromkeys(c['move'] for c in changes):
        cells=[c for c in changes if c['move']==move]
        if move not in INPUT_ACTIONS:
            results.extend({**c,'verdict':'UNDETERMINED','reason':'Automatic/non-input row requires an induced-event method; no recipe whitelist is substituted.'} for c in cells)
            continue
        planned=move_scenarios(stock,candidate,zen,move,cells,inputs[executor.root]['width'],inputs['ZEN']['width'])
        if getattr(executor,'fast_mode',False):planned=fast.selected_scenarios(planned,cells)
        paired=[];stock_records=[]
        for spec in planned:
            actual,base,construction=await baseline(executor,spec,inputs)
            method_notes.append({'move':move,'construction':construction})
            stock_records.append(base)
            modified=await executor.execute(actual,'candidate')
            pair={'scenario':actual,'stock_metrics':metadata(base,stock),'candidate_metrics':metadata(modified,candidate),
                'stock_fixture_id':base.get('fixture_id'),'candidate_fixture_id':modified.get('fixture_id'),
                'infrastructure_failure':base.get('infrastructure_failure') or modified.get('infrastructure_failure')}
            paired.append(pair)
        pairs[move]=paired
        for cell in cells:
            if cell['property'] in {'cancelAbleFrame','cancelAbleMotionLevel','motionLevel'}:continue
            if getattr(executor,'fast_mode',False) and not fast.gameplay_selected(cell,planned):
                unused=applicability(stock[move],candidate[move],cell['property'])
                results.append({**cell,'verdict':'NOT_APPLICABLE' if unused else 'TABLE_CHECKED',
                    'check_level':'static','reason':unused or 'Static checks only: no additional gameplay scenario allocated for this simple damage/energy edit.'})
                continue
            if 'hitArea' in cell['property'] and not applicability(stock[move],candidate[move],cell['property']):
                results.append(await assess_geometry(executor,inputs,cell,stock_records,metadata,cells,paired))
            else:results.append(assess(cell,cells,stock[move],candidate[move],
                fast.shared_pairs(cell,paired) if getattr(executor,'fast_mode',False) else paired,
                **({'allow_shared_onset':True} if getattr(executor,'fast_mode',False) and cell['property']=='attack.StartAddEnergy' else {})))
            results[-1]['check_level']='gameplay'
    cancel_cells=[c for c in changes if c['move'] in INPUT_ACTIONS and c['property'] in {'cancelAbleFrame','cancelAbleMotionLevel','motionLevel'}]
    catalogue=[];cancel_stock_controls=[];cancel_coverage=None
    if cancel_cells:
        catalogue,specs=cancel_scenarios(stock,candidate,zen,cancel_cells,inputs[executor.root]['width'],inputs['ZEN']['width'])
        selected_ids=None
        if getattr(executor,'fast_mode',False):
            selected_ids,cancel_coverage=fast.select_cancel_relationships(stock,candidate,cancel_cells,catalogue)
            specs=[s for s in specs if s['move']+'->'+s['followup'] in selected_ids]
        # Source contact/whiff controls are shared across its relationships.
        # The old loop also ran stock with every requested follow-up, but no
        # classifier consumed those stock relationship results. Candidate
        # relationship tests and their acceptance rules remain unchanged.
        for source in ([] if getattr(executor,'fast_mode',False) else dict.fromkeys(s['move'] for s in specs)):
            controls=scenarios(stock,zen,source,inputs[executor.root]['width'],inputs['ZEN']['width'],jump_profile(stock),jump_profile(zen))
            for control in controls:
                if control['role'] not in {'hit','whiff'}:continue
                actual,record,construction=await baseline(executor,control,inputs)
                measured=metadata(record,stock)
                cancel_stock_controls.append({'source':source,'scenario':actual,'fixture_id':record.get('fixture_id'),
                    'established':suitable(actual,measured),'stock_metrics':compact(measured),'construction':construction,
                    'role':'shared source control; live candidate preconditions still govern each relationship verdict'})
        checked=[]
        for link in catalogue:
            if link['claim'] in {'predicted_ineligible','unchanged_eligible'}:continue
            if selected_ids is not None and fast.relationship_id(link) not in selected_ids:continue
            matching=[s for s in specs if s['move']==link['source'] and s['followup']==link['followup']]
            checked.append(await check_relationship(executor,link,matching,candidate,
                lambda record:cancel_attempt(record,executor.runtime,executor.output,candidate,getattr(executor,'decoder',None))))
        for cell in cancel_cells:
            relevant=attributed_relationships(stock,candidate,cell,checked)
            # Attribution establishes this edit's own effect. It must never
            # exempt a required relationship from vetoing the candidate.
            touching=[r for r in checked if r['followup']==cell['move']] if cell['property']=='motionLevel' else [r for r in checked if r['source']==cell['move']]
            blockers=[r for r in touching if r['verdict']!='VALID']
            if not relevant:
                unused=applicability(stock[cell['move']],candidate[cell['move']],cell['property'])
                results.append({**cell,'verdict':'NOT_APPLICABLE' if unused else 'INVALID','reason':unused or 'Edit changes no engine-derived relationship or reachable cancel window; no intended effect.',
                    'relationships':touching,'attributed_relationships':[]});continue
            assessed=relevant+blockers
            verdict='INVALID' if any(r['verdict']=='INVALID' for r in assessed) else ('UNDETERMINED' if any(r['verdict']=='UNDETERMINED' for r in assessed) else 'VALID')
            problem=next((r for r in assessed if r['verdict']==verdict),None)
            reasons=(problem.get('failed',[]) or problem.get('method_gaps',[])) if problem else []
            passed_reason=('Selected representative relationships and required controls verified in both orientations; other predicted relationships remain untested.'
                if selected_ids is not None else 'Every changed engine-derived relationship and required control verified in both orientations.')
            reason=(passed_reason if verdict=='VALID' else
                ('Cancel '+problem['source']+'->'+problem['followup']+': '+reasons[0].get('reason','prediction contradicted or required evidence missing') if reasons else 'Cancel relationship evidence incomplete or contradicted.'))
            results.append({**cell,'verdict':verdict,'reason':reason,
                'check_level':'gameplay','relationships':touching,'attributed_relationships':relevant,
                **({'relationship_coverage':'representative','unchecked_relationships':[r for r in cancel_coverage['unchecked']
                    if r['followup']==cell['move']] if cell['property']=='motionLevel' else
                    [r for r in cancel_coverage['unchecked'] if r['source']==cell['move']]} if selected_ids is not None else {})})
    return results,{'moves':{m:[{**p,'stock_metrics':compact(p['stock_metrics']),'candidate_metrics':compact(p['candidate_metrics'])} for p in ps] for m,ps in pairs.items()},
        'stock_construction':method_notes,'cancel_catalogue':catalogue,'cancel_stock_controls':cancel_stock_controls,
        'cancel_relationship_results':checked if cancel_cells else [],'cancel_coverage':cancel_coverage}


def validate(candidate_motion_csv,base_character,*,mode='full',budget_seconds=50):
    if mode not in {'full','fast'}:raise ValueError('mode must be full or fast')
    if mode=='fast' and not 0<budget_seconds<=3600:raise ValueError('fast-screen budget must be positive and at most 3600 seconds')
    started=time.perf_counter();hot=home();hot.mkdir(parents=True,exist_ok=True);candidate_path=Path(candidate_motion_csv)
    deadline=time.monotonic()+budget_seconds if mode=='fast' else None
    root=str(base_character).upper();report={'schema':'general-move-table-validator-report-v1','version':__version__,
        'candidate_path':str(candidate_path),'base_character':root,'valid':False,'cells':[],'release_status':'DEVELOPMENT',
        'measurement_policy':policy(),'validation_policy':POLICY,
        'mode':mode,'screen_passed':False,
        'assessment_scope':'bounded effectiveness of this complete input table under recorded controlled scenarios against stock ZEN; no exact-range or universal combination claim'}
    if mode=='fast':report.update(validation_policy=fast.POLICY,budget_seconds=budget_seconds,
        assessment_scope='Risk-focused screen of the complete candidate against stock ZEN; some simple damage/energy edits may be table-checked only. See per-edit coverage.')
    frozen=instrument();report.update(frozen);code=frozen['instrument_sha256']
    rejection=None
    input_sha=None
    if root not in ROOTS:rejection='Unknown stock root.'
    try:
        input_sha=sha(candidate_path)
        if not rejection:candidate=read(candidate_path,root)
    except (OSError,ValueError,TypeError) as error:
        rejection='Malformed or unreadable input table: '+str(error)
    if rejection:
        output=hot/'rejected_inputs'/digest({'path':str(candidate_path),'root':root,'input_sha256':input_sha})/code
        report.update(verdict='INVALID',reason=rejection,run_state='complete',candidate_sha256=input_sha,
            output_directory=str(output),engine_launches=0)
        with Lock(hot/'VALIDATOR.lock'):return finish(report,hot,output,started)
    namespace=os.environ.get('GMTV_CASE_NAMESPACE','default')
    if any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in namespace):raise ValueError('invalid verification namespace')
    output=hot/'validations'/root/input_sha/code/namespace
    if mode=='fast':output=output/'fast'
    output.mkdir(parents=True,exist_ok=True)
    report.update(candidate_sha256=input_sha,output_directory=str(output))
    with Lock(hot/'VALIDATOR.lock'):
        changes=[]
        try:
            inputs=references(hot);stock=inputs[root]['table']
            try:changes=diff(stock,candidate)
            except ValueError as error:
                report.update(verdict='INVALID',reason='Malformed action set: '+str(error),run_state='complete',engine_launches=0)
                return finish(report,hot,output,started)
            report['stock_sha256']=inputs[root]['motion_sha256'];report['changed_cells']=len(changes)
            invalid=[]
            for c in changes:
                errors=invariants(candidate[c['move']])
                if c['structural'] or errors:invalid.append({**c,'verdict':'INVALID','check_level':'static','reason':'Structural edit outside the 29-property interface.' if c['structural'] else '; '.join(errors)})
            if mode=='fast' and not invalid:
                # Cheap no-op/applicability checks before paying any gameplay.
                from .rules import cancel_catalogue
                cancel_changes=[c for c in changes if c['move'] in INPUT_ACTIONS and c['property'] in fast.CANCEL]
                catalogue=cancel_catalogue(stock,candidate,cancel_changes) if cancel_changes else []
                changed_links=[r for r in catalogue if r['claim'] not in {'predicted_ineligible','unchanged_eligible'}]
                for c in changes:
                    unused=applicability(stock[c['move']],candidate[c['move']],c['property'])
                    if unused:invalid.append({**c,'verdict':'NOT_APPLICABLE','check_level':'static','reason':unused})
                    elif c in cancel_changes and not attributed_relationships(stock,candidate,c,changed_links):
                        invalid.append({**c,'verdict':'INVALID','check_level':'static',
                            'reason':'Edit changes no engine-derived cancel relationship/window; table-derived no-op.'})
            if invalid:
                rejected={(c['move'],c['property']) for c in invalid}
                report.update(cells=invalid+[dict(c,verdict='UNDETERMINED',reason='Candidate rejected by static checks before gameplay.') for c in changes if (c['move'],c['property']) not in rejected],verdict='INVALID',reason='Input failed inexpensive structural, value, applicability or cancel-effect checks.',run_state='complete')
            elif not changes:
                report.update(valid=True,verdict='VALID',reason='No edited cells; supplied mechanics equal stock.',run_state='complete',engine_launches=0)
            else:
                identity=stage(hot,candidate_path,root,input_sha)
                prelim=[]
                for move in dict.fromkeys(c['move'] for c in changes):
                    if move in INPUT_ACTIONS:
                        cells=[c for c in changes if c['move']==move]
                        specs=move_scenarios(stock,candidate,inputs['ZEN']['table'],move,cells,inputs[root]['width'],inputs['ZEN']['width'])
                        prelim+=fast.selected_scenarios(specs,cells) if mode=='fast' else specs
                cancel_changes=[c for c in changes if c['move'] in INPUT_ACTIONS and c['property'] in fast.CANCEL]
                pre_catalogue,cancel_specs=cancel_scenarios(stock,candidate,inputs['ZEN']['table'],cancel_changes,inputs[root]['width'],inputs['ZEN']['width'])
                cancel_plan=None
                if mode=='fast' and cancel_changes:
                    selected_ids,cancel_plan=fast.select_cancel_relationships(stock,candidate,cancel_changes,pre_catalogue)
                    cancel_specs=[s for s in cancel_specs if s['move']+'->'+s['followup'] in selected_ids]
                frames=fast.fixed_horizon(stock,candidate,inputs['ZEN']['table'],prelim+cancel_specs) if mode=='fast' else horizon(candidate,[s for s in prelim+cancel_specs if not s.get('energy_setup')])
                executor=CandidateSession(hot,output,root,identity,stock,candidate,frames,fast_mode=mode=='fast',deadline=deadline);executor.zen_table=inputs['ZEN']['table']
                if mode=='full':
                    all_specs=prelim+cancel_specs
                    ordinary=[s for s in all_specs if not s.get('energy_setup')]
                    energy=[s for s in all_specs if s.get('energy_setup')]
                    executor.full_horizons={'ordinary':horizon(candidate,ordinary),
                        'energy':horizon(candidate,energy) if energy else horizon(candidate,ordinary)+2400}
                    if executor.verification_unsplit:
                        combined=horizon(candidate,all_specs)
                        executor.full_horizons={'ordinary':combined,'energy':combined}
                    # Start the first owned launch with the ordinary bucket;
                    # execute() switches and closes sessions at bucket changes.
                    executor.horizon=executor.full_horizons['ordinary']
                report['plan']={'selected_move_probes':len(prelim),'cancel_relationship_probes':len(cancel_specs),
                    'ordinary_horizon_frames':frames,'note':'Stock refinements and boundary witnesses are conditional additions, each checkpointed; counts are planning counts, not a runtime guarantee.'}
                if mode=='full':report['plan'].update(ordinary_horizon_frames=executor.full_horizons['ordinary'],
                    energy_horizon_frames=executor.full_horizons['energy'],energy_setup_isolated=not executor.verification_unsplit)
                if cancel_plan:report['plan']['cancel_coverage']=cancel_plan
                executor.planning_estimate=report['plan']
                if mode=='fast':
                    from .oracle import CommandDecoder
                    executor.decoder=CommandDecoder(executor.runtime,output/'command_oracle',deadline)
                async def run():
                    try:return await execute(executor,inputs,changes)
                    finally:await executor.close()
                try:
                    cells,evidence=asyncio.run(run())
                    verify_cell_accounting(changes,cells)
                    report.update(cells=cells,evidence=evidence,run_state='complete')
                except InterruptedError as error:
                    report.update(run_state='paused',reason=str(error),cells=[dict(c,verdict='UNDETERMINED',reason='Validation paused; valid commits preserved.') for c in changes])
                except (ScreenBudgetExceeded,TimeoutError) as error:
                    if mode!='fast':raise
                    completed=list(executor.partial_cells);done={(c['move'],c['property']) for c in completed}
                    report.update(run_state='incomplete_budget',reason=str(error),
                        cells=completed+[dict(c,verdict='UNDETERMINED',reason='Screen budget exhausted before this edit was assessed; committed probes preserved.')
                                         for c in changes if (c['move'],c['property']) not in done])
                report['engine_launches']=executor.launches
                total=len(executor.records);requested=len(executor.requested)
                raw=[r['record'] for r in executor.records.values() if not r['cached']]
                phases=('connection_load_seconds','setup_seconds','observation_seconds')
                report['cost']={'validated_commits':total,'requested_fixtures':requested,
                    'progress':f'{total}/{requested} gameplay probes','new_probes':executor.new_commits,
                    'cached_probes':sum(r['cached'] for r in executor.records.values()),'engine_launches':executor.launches,
                    'within_invocation_reuses':getattr(executor,'memo_hits',0),
                    'new_stock_baselines':sum(not r['cached'] and r['request']['table_role']=='stock' for r in executor.records.values()),
                    'new_candidate_probes':sum(not r['cached'] and r['request']['table_role']=='candidate' for r in executor.records.values()),
                    'launch_seconds':executor.timings.get('launch_seconds',0),'probe_seconds':sum(r['seconds'] for r in raw),
                    'phase_seconds':{p:sum(r['timing'].get(p) or 0 for r in raw) for p in phases},
                    'phase_timing_scope':'newly executed probes only; cached costs are not charged again',
                    'early_termination':'fixed shorter horizon per probe; owned gameplay interrupted on budget exhaustion' if mode=='fast' else 'not enabled; full horizons isolated into ordinary and energy-setup sessions',
                    'horizons_used':sorted(executor.horizons_used),
                    'decoder_batches':executor.decoder.batches if executor.decoder else 0,
                    'decoder_seconds':executor.decoder.seconds if executor.decoder else 0,
                    'shared_cancel_negative_controls':sum('control_reuse' in e for r in report.get('evidence',{}).get('cancel_relationship_results',[]) for e in r['evidence']),
                    'infrastructure_failures':len(executor.failures)}
                if report['run_state']=='complete':
                    verdicts=[c['verdict'] for c in report['cells']]
                    report['valid']=all(v=='VALID' for v in verdicts)
                    report['verdict']='VALID' if report['valid'] else ('INVALID' if any(v in {'INVALID','NOT_APPLICABLE'} for v in verdicts) else 'UNDETERMINED')
                    report['reason']='Every edited cell is VALID.' if report['valid'] else 'See per-cell verdicts; missing evidence is not silently accepted.'
                else:report['verdict']='UNDETERMINED'
            if sha(candidate_path)!=input_sha:raise RuntimeError('user input changed during validation')
        except Exception as error:
            report.update(run_state='technical_failure',verdict='UNDETERMINED',valid=False,reason=repr(error))
            if changes and not report['cells']:
                report['cells']=[dict(c,verdict='UNDETERMINED',reason='Validation could not complete: '+repr(error)) for c in changes]
        return finish(report,hot,output,started)

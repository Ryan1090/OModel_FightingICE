import argparse,asyncio,json,os,sys,time,gzip
from pathlib import Path
from resolution_selection import select_resolution,resolution_summary,coverage_resolution
from gmtv.schema import sha,digest,read,diff,invariants,ROOTS
from gmtv.storage import atomic,commit,load_commit,Lock
from gmtv.stock_inputs import references
from gmtv.materialise import stage
from execution_v14 import CandidateSession,ScreenBudgetExceeded
from gmtv.api import metadata,baseline,cancel_attempt,suitable
from gmtv.planning import move_scenarios,cancel_scenarios
from gmtv.construct import command_frames
from gmtv.assessment import applicability,assess,GUARDS
from gmtv.rules import INPUT_ACTIONS,cancel_catalogue,attributed_relationships,is_projectile
from gmtv.fast import CANCEL,SIMPLE,fixed_horizon
from gmtv.screening import check_relationship
from gmtv.oracle import CommandDecoder
from gmtv.measure import compact
from gmtv.expectations import RULES
from gmtv.tolerances import tolerance

from selection_v8 import select_for_families, coverage
from probe_retry import ProbeRetryMixin
SCREEN_CONTEXT={}
POLICY={
 'version':'critical-family-screen-v16-one-identical-probe-timeout-retry',
 'claim':'SCREEN_PASSED is representative family-level screening, not every-edit or isolated causal certification.',
 'selection':'Eight named critical families. For each edited critical member property, select the most-used edited move (fixed usage and mechanical tie-breaks); combine checks under the family. Every selected member check must pass. Compatible same-move probes are reused.',
 'families':'Timing (startup, active and duration); damage; forward/upward reach; movement/jumps; knockdown/attack type; guard damage/stun; source cancels; projectile velocity.',
 'paper_only':'Body edges, rear/downward reach, all energy fields and motionLevel receive static checks only. Existing impact/launch checks remain under movement/jumps.',
 'budget':'Target100 seconds, 150-second screening-attempt budget;12-second engine cleanup/report reserve. One infrastructure retry for the timed-out probe only, identical inputs; second timeout remains incomplete. No whole-character timeout retry. Per-probe wall cap20s ordinary/40s energy; incomplete evidence cannot pass. Missing selected evidence cannot pass.',
 'criteria':'Existing engine-unit tolerances, both orientations, directed meaningful numeric effects; no precision requirement. Unintended independent observables still veto. One-sided contact change for reach. Configured guard/down behaviour and cancel controls retained.',
 'cancel':'One attributable changed source-permission/window relationship on the most-used edited source. Positive and negative controls in both orientations. Other links remain explicitly predicted/untested; motionLevel remains paper-only.',
 'geometry':'Forward fixed midpoint and upward existing stock-anchored jump/contact witness. One separating contact per orientation. No exact envelope or boundary search.',
 'playability':'Controlled whole-candidate probes only; no additional per-character historical-controller panel.',
 'scope':'Five traits, same construction/rounding/exclusions/repair/retention/distance/far rules. Pool C remains quarantined; no learner selection; stop after pre-freeze verification without split freeze.'}

def family(prop):
    if prop in CANCEL:return 'cancel'
    if prop in ('attack.AttackType','attack.DownProp'):return 'category'
    if prop in ('speedX','speedY','attack.speedX','attack.speedY','attack.ImpactX','attack.ImpactY'):return 'motion'
    if prop in ('frameNumber','attack.StartUp','attack.Active','attack.GiveGuardRecov'):return 'timing'
    if 'hitArea' in prop:return 'geometry_health'
    return 'simple_health'

def static_checks(stock,full,changes):
    issues=[];cancel=[x for x in changes if x['property'] in CANCEL]
    catalogue=cancel_catalogue(stock,full,cancel) if cancel else []
    links=[x for x in catalogue if x['claim'] not in ('predicted_ineligible','unchanged_eligible')]
    for cell in changes:
        n,p=cell['move'],cell['property'];row=full[n];why=[]
        if cell['structural']:why.append('Structural field outside editable screening interface')
        if n not in INPUT_ACTIONS:why.append('Automatic/non-input row has no input-onset method')
        why+=invariants(row)
        unused=applicability(stock[n],row,p)
        if unused:why.append(unused)
        if stock[n]['attack.Active']>0 and 0<stock[n]['attack.StartUp']<stock[n]['frameNumber'] and not (row['attack.Active']>0 and 0<row['attack.StartUp']<row['frameNumber']):
            why.append('Complete candidate removes the stock attack opportunity')
        if p in CANCEL and not attributed_relationships(stock,full,cell,links):why.append('Table-derived cancel edit has no attributed relationship/window effect')
        if p in ('attack.StartAddEnergy','attack.HitAddEnergy','attack.GuardAddEnergy','attack.GiveEnergy') and abs(cell['value'])>300:
            why.append('Edited energy value exceeds the frozen 300-unit engine range')
        if why:issues.append({**cell,'status':'STATIC_REJECTED','reason':'; '.join(dict.fromkeys(why))})
    return issues,catalogue

def select(stock,full,changes,catalogue):
    return select_for_families(stock,full,changes,catalogue,SCREEN_CONTEXT)

def screen_binding(input_sha256,context):
    return digest({'input':input_sha256,'policy':digest(POLICY),'context':digest(context or {})})


class Session(ProbeRetryMixin,CandidateSession):
    def probe_wall_seconds(self,spec):
        return 40 if spec.get('energy_setup') else 20
    async def execute(self,spec,role):
        if len(self.requested)>=80 and (digest(spec),role) not in getattr(self,'seen_screen',set()):
            raise ScreenBudgetExceeded('Fixed80-request screen ceiling reached')
        self.seen_screen=getattr(self,'seen_screen',set());self.seen_screen.add((digest(spec),role))
        return await super().execute(spec,role)

async def geometry_effect(ex,inputs,group,changes):
    from gmtv.probe import placement
    from gmtv.construct import scenarios
    from gmtv.kinematics import jump_profile
    stock=inputs[ex.root]['table'];full=ex.tables['candidate'];zen=inputs['ZEN']['table'];cell=group['cell'];n=cell['move'];p=cell['property']
    if p=='attack.hitAreaUp':return await upward_effect(ex,inputs,group,changes)
    if p!='attack.hitAreaRight':return {**group,'status':'UNRESOLVED','reason':'Main-effect geometry handler only covers forward offensive reach'}
    centre=(stock['STAND']['hitAreaLeft']+stock['STAND']['hitAreaRight'])/2
    half=(zen['STAND']['hitAreaRight']-zen['STAND']['hitAreaLeft'])/2
    distance=(stock[n][p]+full[n][p])/2-centre+half
    templates=[x for x in scenarios(stock,zen,n,inputs[ex.root]['width'],inputs['ZEN']['width'],jump_profile(stock),jump_profile(zen)) if x['role']=='hit']
    evidence=[]
    for spec in templates:
        spec={**spec,**placement(stock,zen,n,inputs[ex.root]['width'],spec['orientation'],distance,inputs['ZEN']['width']),'role':'boundary'}
        a=await ex.execute(spec,'stock');b=await ex.execute(spec,'candidate');am=metadata(a,stock);bm=metadata(b,full)
        usable=not(a.get('infrastructure_failure') or b.get('infrastructure_failure') or am.get('method_gaps') or bm.get('method_gaps')) and am.get('issued') and bm.get('issued')
        contact_a=bool(am.get('contact_count'));contact_b=bool(bm.get('contact_count'))
        expected=(not contact_a and contact_b) if cell['value']>cell['stock'] else (contact_a and not contact_b)
        evidence.append({'orientation':spec['orientation'],'stock_contact':contact_a,'candidate_contact':contact_b,'passed':bool(usable and expected),'stock_fixture':a.get('fixture_id'),'candidate_fixture':b.get('fixture_id'),'scenario':spec})
    passed={x['orientation'] for x in evidence if x['passed']}=={'P1','P2'}
    return {**group,'status':'PASSED' if passed else 'UNRESOLVED','reason':'One-sided separating reach contact in both orientations' if passed else 'Fixed midpoint did not establish separating reach contact in both orientations','evidence':evidence,'effect_claim':'coedit_present_reach_contact_change'}

async def ordinary(ex,inputs,group,changes):
    stock=inputs[ex.root]['table'];full=ex.tables['candidate'];zen=inputs['ZEN']['table'];cell=group['cell'];move=cell['move'];p=cell['property']
    cells=[x for x in changes if x['move']==move]
    planned=move_scenarios(stock,full,zen,move,cells,inputs[ex.root]['width'],inputs['ZEN']['width'])
    kind=group['kind'];
    if group.get('effect_required') and kind=='geometry_health':return await geometry_effect(ex,inputs,group,changes)
    health=kind in ('geometry_health','simple_health')
    role=('guard' if p in ('attack.GiveGuardRecov','attack.GuardDamage','attack.GuardAddEnergy') else 'hit') if health or p in ('attack.ImpactX','attack.ImpactY','attack.DownProp','attack.GiveGuardRecov') else 'whiff'
    if p=='attack.HitDamage':role='hit'
    if p=='attack.GuardDamage':role='guard'
    if group.get('effect_required') and kind=='simple_health':health=False
    if p=='attack.AttackType':
        roles=[r for r in ('stand_guard','crouch_guard') if (stock[move][p] in GUARDS[r])!=(full[move][p] in GUARDS[r])]
        role=roles[0] if roles else 'stand_guard'
    specs=[s for s in planned if s['role']==role]
    categorical=p in ('attack.AttackType','attack.DownProp')
    if health or categorical:
        from gmtv.construct import scenarios
        from gmtv.kinematics import jump_profile
        specs=[s for s in scenarios(full,zen,move,inputs[ex.root]['width'],inputs['ZEN']['width'],jump_profile(full),jump_profile(zen)) if s['role']=='hit']
        if p=='attack.AttackType':specs=[{**s,'role':role,'defence':role} for s in specs]
        from gmtv.energy_setup import paired_setup_for
        setup=paired_setup_for(zen,full[move],full[move])
        if setup:specs=[{**s,'energy_setup':setup} for s in specs]
    if {s['orientation'] for s in specs}!={'P1','P2'}:return {**group,'status':'UNRESOLVED','reason':'Required two-orientation representative scenario unavailable'}
    pairs=[];observations=[];problems=[]
    for spec in specs:
        if health or categorical:
            raw=await ex.execute(spec,'candidate');m=metadata(raw,full);observations.append({'scenario':spec,'metrics':compact(m),'fixture':raw.get('fixture_id')})
            if raw.get('infrastructure_failure') or m.get('method_gaps') or not m.get('contact_count'):
                problems.append('Representative candidate contact not established');continue
            if p=='attack.AttackType' and bool(m.get('guarded'))!=(full[move][p] in GUARDS[role]):
                return {**group,'status':'REJECTED','reason':'Representative guard posture contradicts engine attack-type rule','observations':observations}
            if p=='attack.DownProp' and bool(m.get('down_seen'))!=bool(full[move][p]):
                return {**group,'status':'REJECTED','reason':'Representative knockdown state contradicts configured engine flag','observations':observations}
        else:
            actual,a,notes=await baseline(ex,spec,inputs);b=await ex.execute(actual,'candidate')
            pairs.append({'scenario':actual,'stock_metrics':metadata(a,stock),'candidate_metrics':metadata(b,full),
                'stock_fixture_id':a.get('fixture_id'),'candidate_fixture_id':b.get('fixture_id'),
                'infrastructure_failure':a.get('infrastructure_failure') or b.get('infrastructure_failure')})
    if health or categorical:
        return {**group,'status':'UNRESOLVED' if problems else 'PASSED','reason':problems[0] if problems else ('Complete-candidate contact health observed; individual edit effects remain untested' if health else 'Selected changed guard posture observed in both orientations'),
            'observations':observations,'effect_claim':'contact_health_only' if health else 'configured_categorical_state'}
    opportunistic=[]
    for pair in pairs:
        a,b=pair['stock_metrics'],pair['candidate_metrics']
        for other in cells:
            if other['property'] not in SIMPLE:continue
            prop=other['property'];observable=RULES[prop][2];x,y=a.get(observable),b.get(observable)
            if x is None or y is None:continue
            matched=bool(a.get('contact_count') and b.get('contact_count')) and a.get('guarded')==b.get('guarded')
            applicable=matched and ((prop=='attack.HitDamage' and not b.get('guarded')) or (prop=='attack.GuardDamage' and b.get('guarded')))
            entry={'property':prop,'orientation':pair['scenario']['orientation'],'stock':x,'candidate':y,
                'status':'OBSERVED_NOT_INDIVIDUALLY_ATTRIBUTED'}
            if applicable and (y-x)*(1 if other['value']>other['stock'] else -1)<-tolerance(observable):
                return {**group,'status':'REJECTED','reason':'Unambiguous matching-contact HP damage reversal','opportunistic':opportunistic+[entry]}
            opportunistic.append(entry)
    result=assess(cell,cells,stock[move],full[move],pairs)
    return {**group,'status':{'VALID':'PASSED','INVALID':'REJECTED'}.get(result['verdict'],'UNRESOLVED'),'reason':result['reason'],'assessment':result,'opportunistic':opportunistic}

async def execute_members(ex,inputs,changes,groups,catalogue):
    outcomes=[]
    for group in groups:
        if ex.paused():raise InterruptedError('Paused at fixture boundary')
        if group['kind']=='missing':
            outcomes.append({**group,'status':'UNRESOLVED'})
        elif group['kind']=='cancel':
            all_cancel=[x for x in changes if x['property'] in CANCEL]
            cats,specs=cancel_scenarios(inputs[ex.root]['table'],ex.tables['candidate'],inputs['ZEN']['table'],all_cancel,inputs[ex.root]['width'],inputs['ZEN']['width'])
            link=group['link'];specs=[s for s in specs if s['move']==link['source'] and s['followup']==link['followup']]
            ex.decoder=CommandDecoder(ex.runtime,ex.output/'command_oracle',ex.deadline)
            result=await check_relationship(ex,link,specs,ex.tables['candidate'],lambda raw:cancel_attempt(raw,ex.runtime,ex.output,ex.tables['candidate'],ex.decoder))
            outcomes.append({**group,'status':{'VALID':'PASSED','INVALID':'REJECTED'}.get(result['verdict'],'UNRESOLVED'),'reason':'Representative changed relationship and required controls','assessment':result})
        else:outcomes.append(await ordinary(ex,inputs,group,changes))
        if outcomes[-1]['status']!='PASSED':break
    return outcomes

async def execute_batch(ex,inputs,changes,groups,catalogue):
    outcomes=[]
    for group in groups:
        completed=[]
        for member in group['checks']:
            # Maintain family-shaped partial records if a deadline interrupts a member.
            ex.partial_groups=outcomes+[{**group,'results':completed,'status':'UNRESOLVED','reason':'Selected member evidence incomplete'}]
            values=await execute_members(ex,inputs,changes,[member],catalogue)
            if group['family']=='projectile' and values[-1]['status']=='PASSED':
                contact=await ordinary(ex,inputs,{**member,'kind':'geometry_health','effect_required':False},changes)
                values[-1]['projectile_contact']=contact
                if contact['status']!='PASSED':values[-1].update(status=contact['status'],reason='Projectile velocity observed but contact health not established')
            completed.extend(values)
        passed=len(completed)==len(group['checks']) and all(x['status']=='PASSED' for x in completed)
        status='PASSED' if passed else 'REJECTED' if any(x['status']=='REJECTED' for x in completed) else 'UNRESOLVED'
        outcomes.append({**group,'results':completed,'status':status,'reason':'Every edited member representative passed' if passed else 'A required family member failed or was unobservable'})
        ex.partial_groups=outcomes
    return outcomes


async def upward_effect(ex,inputs,group,changes):
    from gmtv.geometry import vertical_witness
    from gmtv.screening import boundary_offset
    from gmtv.construct import scenarios
    from gmtv.kinematics import jump_profile
    stock=inputs[ex.root]['table'];full=ex.tables['candidate'];zen=inputs['ZEN']['table'];cell=group['cell'];move=cell['move']
    records=[]
    for spec in scenarios(stock,zen,move,inputs[ex.root]['width'],inputs['ZEN']['width'],jump_profile(stock),jump_profile(zen)):
        if spec['role'] in ('hit','whiff'):records.append(await ex.execute(spec,'stock'))
    expands=cell['value']<cell['stock'];evidence=[]
    for side in ('P1','P2'):
        spec=vertical_witness(records,stock,zen,inputs[ex.root]['width'],inputs['ZEN']['width'],move,cell['property'],expands,boundary_offset(cell),side)
        if spec is None:evidence.append({'orientation':side,'passed':False,'reason':'No prospective stock-anchored vertical contact placement'});continue
        a=await ex.execute(spec,'stock');b=await ex.execute(spec,'candidate');am=metadata(a,stock);bm=metadata(b,full)
        usable=not(a.get('infrastructure_failure') or b.get('infrastructure_failure') or am.get('method_gaps') or bm.get('method_gaps')) and am.get('issued') and bm.get('issued')
        ac=bool(am.get('contact_count'));bc=bool(bm.get('contact_count'))
        expected=(not ac and bc) if expands else (ac and not bc)
        evidence.append({'orientation':side,'passed':bool(usable and expected),'stock_contact':ac,'candidate_contact':bc,'stock_fixture':a.get('fixture_id'),'candidate_fixture':b.get('fixture_id'),'scenario':spec})
    passed={x['orientation'] for x in evidence if x['passed']}=={'P1','P2'}
    return {**group,'status':'PASSED' if passed else 'UNRESOLVED','reason':'One-sided upward separating contact in both orientations' if passed else 'Stock-anchored upward contact witness unobservable','evidence':evidence,'effect_claim':'coedit_present_upward_contact_change'}

def screen(path,root,home,output,budget_seconds=150,context=None):
    global SCREEN_CONTEXT
    SCREEN_CONTEXT=context or {}
    budget_seconds=min(1800,budget_seconds)
    started=time.perf_counter();deadline=time.monotonic()+max(1,budget_seconds-12);path=Path(path);home=Path(home);output=Path(output);output.mkdir(parents=True,exist_ok=True)
    report={'orchestration_override':{'infrastructure_safety_cap':1800,'wall_clock_admission_limit':None,'collect_all_selected_members':True,'V16_files_unchanged':True},'policy':POLICY,'input':str(path),'root':root,'input_sha256':sha(path),'screen_passed':False,'valid':False,'groups':[],
        'budget_seconds':budget_seconds,'scope':'Representative risk screen of the complete input, not individual-edit certification'}
    inputs=references(home);stock=inputs[root]['table'];full=read(path,root);changes=diff(stock,full)
    issues,catalogue=static_checks(stock,full,changes);groups=select_resolution(stock,full,changes,catalogue,SCREEN_CONTEXT)
    report.update(edited_cells=len(changes),static_issues=issues,plan=groups,
        cells=[{**x,'status':'TABLE_CHECKED','gameplay_effect_verified':False} for x in changes],
        untested_cancel_relationships=[r for r in catalogue if r['claim'] not in ('unchanged_eligible','predicted_ineligible') and not any(x.get('kind')=='cancel' and x['link']['source']==r['source'] and x['link']['followup']==r['followup'] for g in groups for x in g['checks'])])
    report["resolution_selection"]=resolution_summary(changes,groups)
    ex=None
    if issues:report.update(verdict='SCREEN_REJECTED',reason='Inexpensive static check failed')
    elif not changes:report.update(verdict='SCREEN_REJECTED',reason='No synthetic edits')
    elif not groups:report.update(verdict='SCREEN_INCOMPLETE',reason='No gameplay representative could be constructed')
    else:
        identity=stage(home,path,root,sha(path));ex=Session(home,output,root,identity,stock,full,240,fast_mode=True,deadline=deadline);ex.zen_table=inputs['ZEN']['table'];ex.partial_groups=[]
        async def run():
            try:return await execute_batch(ex,inputs,changes,groups,catalogue)
            finally:await ex.close()
        try:report['groups']=asyncio.run(run())
        except (ScreenBudgetExceeded,TimeoutError,InterruptedError) as e:report.update(groups=ex.partial_groups,verdict='SCREEN_INCOMPLETE',reason=str(e))
        except Exception as e:report.update(groups=ex.partial_groups,verdict='INFRASTRUCTURE_FAILURE',reason=repr(e))
        if ex.failures:report.update(verdict='INFRASTRUCTURE_FAILURE',reason='Infrastructure failure; no mechanic or admission decision inferred')
        if 'verdict' not in report:
            statuses=[g['status'] for g in report['groups']]
            passed=len(statuses)==len(groups) and all(x=='PASSED' for x in statuses)
            report.update(screen_passed=passed,verdict='SCREEN_PASSED' if passed else 'SCREEN_REJECTED' if 'REJECTED' in statuses else 'SCREEN_INCOMPLETE',
                reason='Static checks and all selected gameplay representatives passed' if passed else 'A selected representative failed or remained unresolved')
        report['cost']={'new_probes':ex.new_commits,'stock_cached':sum(x['cached'] for x in ex.records.values()),'launches':ex.launches,
            'launch_seconds':ex.timings.get('launch_seconds',0),'probe_seconds':sum(x['record'].get('seconds',0) for x in ex.records.values() if not x['cached']),
            'probe_timeout_retries':getattr(ex,'probe_timeout_retries',0),'probe_timeouts':getattr(ex,'probe_timeouts',0),'early_stopped_probes':ex.early_stops,'dependency_reused_probes':ex.dependency_hits,'horizons':sorted(ex.horizons_used),'infrastructure_failures':ex.failures}
    report['verified_share']=coverage_resolution(changes,report.get('groups',[]),SCREEN_CONTEXT)
    report['seconds']=time.perf_counter()-started;atomic(output/'REPORT.json',report)
    (output/'REPORT.md').write_text('# V8 primary/secondary/risk fast screen\n\n**'+report['verdict']+'**\n\n'+report['reason']+'\n\nEvery edit was table-checked. Only the recorded gameplay groups were exercised. This is not every-edit VALID.\n',encoding='utf-8')
    if report['verdict'] in ('SCREEN_PASSED','SCREEN_REJECTED'):
        files=[path,output/'REPORT.json']
        ledger=output/'LEDGER.json'
        if ledger.exists():
            files.append(ledger)
            for row in json.loads(ledger.read_text())['records']:
                raw=Path(row['raw_path']);files.append(raw)
                envelope=json.loads(gzip.decompress(raw.read_bytes()));files.extend(Path(p) for p in envelope['files'])
        commit(output/'SCREEN_COMMIT.json',screen_binding(sha(path),SCREEN_CONTEXT),report,files)
    return report





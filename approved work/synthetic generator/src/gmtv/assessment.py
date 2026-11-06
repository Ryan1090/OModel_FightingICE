"""Per-cell effects on the complete candidate, with explicit method gaps."""
from .expectations import RULES,DOWNSTREAM
from .tolerances import UNITS,EXACT,tolerance,same,directed_effect
from .rules import is_projectile

GUARDS={'stand_guard':{1,2},'crouch_guard':{1,3},'air_guard':{1,2}}
SIDE_MEASURES=set(UNITS)|EXACT
FIXTURE={'command_to_onset'}


def roles_for(prop):
    if prop in {'attack.HitDamage','attack.HitAddEnergy','attack.ImpactY','attack.DownProp'}:return {'hit'}
    if prop in {'attack.GuardDamage','attack.GuardAddEnergy','attack.GiveGuardRecov'}:return {'guard'}
    if prop=='attack.AttackType':return {'stand_guard','crouch_guard','hit'}
    if prop in {'attack.GiveEnergy','attack.ImpactX'}:return {'hit','guard'}
    if prop in {'attack.speedX','attack.speedY','speedX','speedY'}:return {'whiff','hit'}
    if prop.startswith('attack.hitArea'):return {'hit','whiff','boundary'}
    if prop.startswith('hitArea'):return {'whiff','incoming_boundary'}
    if prop in {'cancelAbleFrame','cancelAbleMotionLevel','motionLevel'}:return {'cancel'}
    return {'whiff'}


def applicability(stock,row,prop):
    if prop.startswith('attack.') and prop!='attack.StartAddEnergy':
        # Onset/active edits can create attacks and are never excluded merely
        # because stock lacks one. Other fields cannot act without a reachable
        # attack instance in either table under this fixed action definition.
        if prop not in {'attack.StartUp','attack.Active'} and not any(
            0<r['attack.StartUp']<r['frameNumber'] and r['attack.Active']>0 for r in (stock,row)):
            return 'Neither stock nor candidate has a reachable active attack instance (Character.startActive/update).'
    if stock['attack.AttackType']==row['attack.AttackType']==4 and prop in {
        'attack.ImpactX','attack.ImpactY','attack.DownProp','attack.GuardDamage','attack.GuardAddEnergy','attack.GiveGuardRecov'}:
        return 'The engine throw branch does not consume this field and does not enter guarded contact.'
    if prop in {'cancelAbleFrame','cancelAbleMotionLevel'} and row['control']:
        return 'Ordinary control bypasses the cancel-window/permission branch in Fighting.ableAction.'
    return None


def independent_changes(changes):
    permitted=set(FIXTURE)
    for change in changes:
        family,scenario,observable,direction,basis=RULES[change['property']]
        permitted.add(observable);permitted.update(DOWNSTREAM[family])
        if change['property']=='frameNumber':permitted|={'control_return','source_frames_observed'}
        if change['property'] in {'attack.StartUp','attack.Active'}:
            # Each timing field retains the other's metric as independent unless
            # that other field is also edited in the complete candidate.
            if change['property']=='attack.Active':permitted.add('projectile_frames_observed')
        if change['property']=='attack.AttackType' and 4 in (change['stock'],change['value']):
            permitted|={'control_return','source_frames_observed'}
    return SIDE_MEASURES-permitted


def compare_side_observables(pair,independent):
    baseline=pair['stock_metrics'];candidate=pair['candidate_metrics'];changes=[];conditions=[]
    for name in sorted(independent):
        a,b=baseline.get(name),candidate.get(name)
        if a is None or b is None:continue
        if same(name,a,b):continue
        if name in {'hit_energy_delta','received_energy_delta'}:
            which='me' if name=='hit_energy_delta' else 'op'
            contact=pair['candidate_metrics'].get('contact')
            if contact and contact['before'][which]['energy']>=300 and contact['after'][which]['energy']==300:
                conditions.append({'observable':name,'condition':'recorded recipient is at engine energy cap before/after contact'});continue
        changes.append({'observable':name,'stock':a,'candidate':b,'tolerance':tolerance(name)})
    return changes,conditions


def contact_changed_by_coedit(change,all_changes):
    return any(c['property']!=change['property'] and
        (c['property'] in {'attack.AttackType','frameNumber'} or
         'contact_count' in DOWNSTREAM[RULES[c['property']][0]]) for c in all_changes)


def assess(change,all_changes,stock,row,pairs,*,allow_shared_onset=False):
    prop=change['property'];family,scenario,observable,direction,basis=RULES[prop]
    result={**change,'engine_basis':basis,'verdict':'UNDETERMINED','reason':'No applicable gameplay evidence.',
        'evidence':[],'magnitude_fidelity':None}
    unused=applicability(stock,row,prop)
    if unused:return {**result,'verdict':'NOT_APPLICABLE','reason':unused}
    if family in {'body_geometry','offensive_geometry','cancel'}:
        return {**result,'reason':'This field requires its boundary/relationship evidence handler; a loaded value alone is not gameplay validation.'}
    relevant=roles_for(prop)
    if allow_shared_onset and prop=='attack.StartAddEnergy':
        relevant=relevant|{'hit','guard','stand_guard','crouch_guard'}
    selected=[p for p in pairs if p['scenario']['role'] in relevant]
    missing=[];failures=[];observations=[];independent=independent_changes(all_changes)
    for side in ('P1','P2'):
        available=[p for p in selected if p['scenario']['orientation']==side]
        if not available:missing.append(side+': required scenario missing');continue
        realised=False
        for pair in available:
            b,c=pair['stock_metrics'],pair['candidate_metrics'];role=pair['scenario']['role']
            if pair.get('infrastructure_failure') or b.get('method_gaps') or c.get('method_gaps'):
                missing.append(side+'/'+role+': source/setup/load evidence incomplete');continue
            if allow_shared_onset and prop=='attack.StartAddEnergy' and role!='whiff':
                if any(m.get('contact_count') and (m.get('contact_delay') is None or m['contact_delay']<=0) for m in (b,c)):
                    missing.append(side+'/'+role+': onset and contact energy cannot be temporally separated');continue
            if role=='whiff' and (b.get('contact_count') or c.get('contact_count')):
                missing.append(side+'/'+role+': contact contaminates whiff measurement');continue
            if prop=='frameNumber' and role=='whiff' and b.get('active_frames_observed',0)>0 and c.get('active_frames_observed')==0:
                if c.get('control_return') is None:
                    missing.append(side+': source completion not observed; attack preservation unresolved');continue
                failures.append({'orientation':side,'role':role,
                    'reason':'duration edit removed the stock attack from a successfully observed complete source action',
                    'stock_active_frames':b['active_frames_observed'],'candidate_active_frames':0,
                    'candidate_control_return':c['control_return']});continue
            if role=='hit' and (not b.get('contact_count') or b.get('guarded')):
                missing.append(side+'/'+role+': stock clean-hit baseline not established');continue
            if role=='guard' and not b.get('guarded'):
                missing.append(side+'/'+role+': stock guarded-contact baseline not established');continue
            if role=='hit' and (not c.get('contact_count') or c.get('guarded')):
                if contact_changed_by_coedit(change,all_changes):
                    missing.append(side+'/'+role+': co-edit changes the contact context; clean comparison not established');continue
                failures.append({'orientation':side,'role':role,'reason':'intended clean contact not realised'});continue
            if role=='guard' and not c.get('guarded'):
                if contact_changed_by_coedit(change,all_changes):
                    missing.append(side+'/'+role+': co-edit changes the guard/contact context; guarded comparison not established');continue
                failures.append({'orientation':side,'role':role,'reason':'intended guarded contact not realised'});continue
            if prop=='attack.AttackType':
                if role=='hit':continue
                expected_stock=stock['attack.AttackType'] in GUARDS[role]
                expected_candidate=row['attack.AttackType'] in GUARDS[role]
                if not b.get('contact_count') or not c.get('contact_count'):
                    missing.append(side+'/'+role+': contact absent in posture comparison');continue
                if bool(b.get('guarded'))!=expected_stock:
                    missing.append(side+'/'+role+': stock guard rule not established');continue
                if bool(c.get('guarded'))!=expected_candidate:
                    failures.append({'orientation':side,'role':role,'reason':'observed blocking contradicts engine attack-type rule'});continue
                if expected_stock!=expected_candidate:realised=True
                observations.append({'orientation':side,'role':role,'stock_guarded':expected_stock,'candidate_guarded':expected_candidate})
            elif prop=='attack.DownProp':
                if bool(b.get('down_seen'))!=bool(stock[prop]):
                    missing.append(side+': stock knockdown direction not established');continue
                if bool(c.get('down_seen'))!=bool(row[prop]):
                    failures.append({'orientation':side,'role':role,'reason':'down-state prediction not realised'});continue
                realised=True;observations.append({'orientation':side,'role':role,'stock':b['down_seen'],'candidate':c['down_seen']})
            else:
                x,y=b.get(observable),c.get(observable)
                if prop in {'attack.speedX','attack.speedY'}:
                    if x is None and not b.get('projectile_seen') and b.get('active_frames_observed',0)>0 and not is_projectile(stock):x=0
                    if y is None and not c.get('projectile_seen') and c.get('active_frames_observed',0)>0 and not is_projectile(row):y=0
                if x is None or y is None:
                    missing.append(side+'/'+role+': '+observable+' not observed');continue
                configured_delta=change['value']-change['stock'];expected_direction=1 if configured_delta>0 else -1
                good=directed_effect(observable,x,y,expected_direction)
                observation={'orientation':side,'role':role,'observable':observable,'stock':x,'candidate':y,
                    'realised_delta':y-x,'configured_delta':configured_delta,'tolerance':tolerance(observable),
                    'magnitude_fidelity':'FAITHFUL' if abs((y-x)-configured_delta)<=tolerance(observable) else 'DISTORTED'}
                observations.append(observation)
                if good:realised=True
                else:failures.append({**observation,'reason':'no detectable correctly directed effect'})
            side_effects,conditions=compare_side_observables(pair,independent)
            if side_effects:failures.append({'orientation':side,'role':role,'reason':'mechanically independent observable changed','changes':side_effects})
            if conditions:observations.append({'orientation':side,'role':role,'recorded_conditions':conditions})
        if not realised and not any(f.get('orientation')==side for f in failures):missing.append(side+': intended effect not established')
    result.update(evidence=observations,method_gaps=missing,failures=failures)
    if failures:result.update(verdict='INVALID',reason=failures[0]['reason'])
    elif missing:result.update(reason=missing[0])
    else:result.update(verdict='VALID',reason='Intended effect and independent observables verified in both orientations.')
    fidelities=[x.get('magnitude_fidelity') for x in observations if x.get('magnitude_fidelity')]
    if fidelities:result['magnitude_fidelity']='FAITHFUL' if all(x=='FAITHFUL' for x in fidelities) else 'DISTORTED'
    return result

"""Gameplay contact-envelope witnesses, with stock-anchored physical inputs.

No loaded rectangle alone is accepted as proof of a gameplay effect. If a
reachable separating contact cannot be established, retain UNDETERMINED.
"""
from .schema import digest
from .probe import placement
from .stock_refinement import attack_samples
from .kinematics import jump_profile
from .assessment import independent_changes,compare_side_observables
from .construct import command_frames
from .energy_setup import setup_for
from .rules import COMMANDS
from .screening import boundary_offset


def incoming_contact(record):
    obs=record.get('observation',{});issue=obs.get('issue_frame');trace=obs.get('trace',[])
    if issue is None:return {'established':False,'reason':'focal move not issued'}
    move=record['spec']['move']
    for pre,now in zip(trace,trace[1:]):
        if now['frame']<=issue or pre['me']['action']!=move:continue
        # The focal move can itself hit: its attacker reward is not evidence
        # that the focal body was struck. These stock-ZEN incoming attacks all
        # have positive HitDamage, so require observed incoming HP loss.
        if now['me']['hp']<pre['me']['hp']:
            return {'established':True,'contact':True,'frame':now['frame'],'hp_loss':pre['me']['hp']-now['me']['hp'],
                'focal_body':{k:pre['me'][k] for k in ('left','right','top','bottom')},
                'attacker_action':pre['op']['action'],'energy_delta':now['me']['energy']-pre['me']['energy']}
    source_observed=any(x['frame']>issue and x['me']['action']==move for x in trace)
    incoming=obs.get('incoming_issue_frame')
    incoming_active=any(x['frame']>issue and x['me']['action']==move and x['op']['action']==record['spec'].get('incoming_action')
        and not x['op']['attack'].get('empty_flag',True) for x in trace)
    established=source_observed and incoming is not None and incoming_active
    return {'established':established,'contact':False,
        'incoming_issue_frame':incoming,'reason':None if established else 'focal/incoming active action unavailable'}


def horizontal_witness(records,stock,zen,width,zw,move,field,expands,offset,side):
    useful=[]
    for r in records:
        obs=r.get('observation',{});issue=obs.get('issue_frame')
        if issue is None:continue
        origin=next((x for x in obs['trace'] if x['frame']==issue),None)
        if origin is None:continue
        centre=(origin['me']['left']+origin['me']['right'])/2;sign=1 if r['spec']['orientation']=='P1' else -1
        for x,a in attack_samples(r):
            area=a['current_hit_area']
            if min(area['bottom'],x['op']['bottom'])-max(area['top'],x['op']['top'])<2:continue
            left,right=(area['left']-centre,area['right']-centre) if sign>0 else (centre-area['right'],centre-area['left'])
            useful.append((left,right,r['spec']))
    if not useful:return None
    if field.endswith('Right'):
        edge=max(x[1] for x in useful);distance=edge+20+(offset if expands else -offset)
        template=max(useful,key=lambda x:x[1])[2]
    else:
        edge=min(x[0] for x in useful);distance=edge-20+(-offset if expands else offset)
        template=min(useful,key=lambda x:x[0])[2]
    min_distance=(stock['STAND']['hitAreaRight']-stock['STAND']['hitAreaLeft']+40)/2+2
    if not min_distance<distance<760:return None
    # Use stock coordinates/timing only. Strip observation annotations so the
    # exact scenario can be cached across future submitted candidates.
    keep={'move','defence','jump_age','opponent_jump_delay','energy_setup','input_history_settle_frames'}
    spec={k:v for k,v in template.items() if k in keep}
    spec.update(placement(stock,zen,move,width,side,distance,zw))
    return {**spec,'role':'outgoing_boundary','geometry_field':field,'expected_stock_contact':not expands,
        'stock_boundary_offset':offset}


def vertical_witness(records,stock,zen,width,zw,move,field,expands,offset,side):
    zprofile=jump_profile(zen)['runs'][0]['samples'];by_age={z['issue_age']:z for z in zprofile};options=[]
    contact_templates=[r['spec'] for r in records if r['spec']['role']=='hit']
    for r in records:
        obs=r.get('observation',{});ready=obs.get('ready')
        samples=attack_samples(r)
        # A clean hit consumes the attack early. Use its whiff lifetime to
        # establish a stock miss throughout the entire collision opportunity.
        if ready is None or not samples or r['spec']['role']!='whiff':continue
        for z in zprofile:
            delay=samples[0][0]['frame']-ready-z['issue_age'];gaps=[]
            for x,a in samples:
                op=by_age.get(x['frame']-ready-delay)
                if op is None:break
                area=a['current_hit_area']
                if field.endswith('Up'):
                    gap=area['top']-op['body_bottom'] if expands else op['body_bottom']-area['top']
                else:
                    gap=op['body_top']-area['bottom'] if expands else area['bottom']-op['body_top']
                gaps.append(gap)
            if len(gaps)!=len(samples):continue
            # Expansion requires a full stock miss; contraction a reachable
            # stock contact. Actual stock execution still validates the model.
            gap=min(gaps) if expands else max(gaps)
            if gap<offset:continue
            contact=next((s for s in contact_templates if s['orientation']==side),r['spec'])
            # Preserve the source jump phase used to measure this trajectory.
            # The contact template contributes only horizontal placement.
            template={**r['spec'],'stock_body_centre_distance':contact['stock_body_centre_distance']}
            options.append((gap,abs(delay),delay,template))
    if not options:return None
    gap,_,delay,template=min(options,key=lambda x:(x[0],x[1]))
    keep={'move','jump_age','energy_setup','input_history_settle_frames'}
    spec={k:v for k,v in template.items() if k in keep}
    spec.update(placement(stock,zen,move,width,side,template['stock_body_centre_distance'],zw))
    return {**spec,'role':'outgoing_boundary','defence':'jump',
        'opponent_jump_delay':max(0,delay),'target_wait_frames':max(0,-delay),
        'geometry_field':field,'expected_stock_contact':not expands,'stock_boundary_gap':gap}


def aerial_body_witness(records,stock,zen,width,zw,move,field,expands,offset,side):
    """Synchronise an ordinary incoming attack with the stock airborne pose."""
    zprofile=jump_profile(zen)['runs'][0]['samples'];zby={z['issue_age']:z for z in zprofile}
    records=[r for r in records if r['spec']['role']=='whiff' and r['spec']['orientation']==side]
    options=[]
    if field.endswith('Down'):attack='STAND_A'
    else:
        eligible=[r for n,r in zen.items() if n.startswith('AIR') and n in COMMANDS
            and r['attack.Active']>0 and r['attack.StartAddEnergy']>=0
            and r['speedX']==r['speedY']==r['attack.speedX']==r['attack.speedY']==0]
        if not eligible:return None
        # A longer stationary incoming move avoids having the focal attack
        # interrupt the incoming attacker before its contact boundary is tested.
        attack=min(eligible,key=lambda r:(-r['attack.hitAreaRight'],r['motionName']))['motionName']
    z=zen[attack]
    for record in records:
        obs=record['observation'];issue=obs['issue_frame'];ready=obs['ready']
        if issue is None or ready is None:continue
        focal=[x for x in obs['trace'] if x['frame']>issue and x['me']['action']==move]
        for first in focal:
            relative=first['frame']-ready
            ages=[s['issue_age'] for s in zprofile if s['control']] if attack.startswith('AIR') else [0]
            for age in ages:
                start=relative-age-command_frames(attack)-z['attack.StartUp']+1
                gaps=[]
                for x in focal:
                    phase=x['frame']-first['frame']
                    if not 0<=phase<=z['attack.Active']:continue
                    sample=zby.get(age+command_frames(attack)+z['attack.StartUp']-1+phase) if age else None
                    if age and sample is None:break
                    raw_y=sample['raw_y'] if sample else 640-zen['STAND']['hitAreaDown']
                    top=raw_y+z['attack.hitAreaUp'];bottom=raw_y+z['attack.hitAreaDown']
                    body=x['me']
                    if field.endswith('Up'):gap=body['top']-bottom if expands else bottom-body['top']
                    elif field.endswith('Down'):gap=top-body['bottom'] if expands else body['bottom']-top
                    else:gap=min(bottom,body['bottom'])-max(top,body['top'])
                    gaps.append(gap)
                if not gaps:continue
                gap=min(gaps) if expands or field.endswith('Right') else max(gaps)
                if gap<offset:continue
                options.append((gap,abs(start),age,start,record['spec']))
    if not options:return None
    gap,_,age,start,template=min(options,key=lambda x:(x[0],x[1],x[2]))
    owncentre=(stock['STAND']['hitAreaLeft']+stock['STAND']['hitAreaRight'])/2
    zcentre=(zen['STAND']['hitAreaLeft']+zen['STAND']['hitAreaRight'])/2
    reach=z['attack.hitAreaRight']-zcentre+stock[move]['hitAreaRight']-owncentre
    source_reach=stock[move]['attack.hitAreaRight']-owncentre+(zen['STAND']['hitAreaRight']-zen['STAND']['hitAreaLeft'])/2
    distance=reach+(offset if expands else -offset) if field.endswith('Right') else max(48,reach-20)
    if field.endswith('Up'):distance=min(reach-12,max(distance,source_reach+12))
    spec={**placement(stock,zen,move,width,side,distance,zw),'move':move,'role':'incoming_boundary',
        'defence':'passive','incoming_action':attack,'jump_age':template.get('jump_age',6),
        'target_wait_frames':max(0,-start),'geometry_field':field,'expected_stock_contact':not expands,
        'stock_predicted_vertical_gap':gap}
    if age:spec.update(incoming_jump_age=age,incoming_jump_delay=max(0,start))
    else:spec['incoming_delay']=max(0,start)
    return spec


def body_witness(stock,zen,width,zw,move,field,delta,offset,side,records=()):
    row=stock[move];expands=delta>0 if field.endswith(('Right','Down')) else delta<0
    if row['state']=='AIR':return aerial_body_witness(records,stock,zen,width,zw,move,field,expands,offset,side)
    owncentre=(stock['STAND']['hitAreaLeft']+stock['STAND']['hitAreaRight'])/2
    if field.endswith('Right'):
        attack='STAND_B';z=zen[attack];zcentre=(zen['STAND']['hitAreaLeft']+zen['STAND']['hitAreaRight'])/2
        boundary=z['attack.hitAreaRight']-zcentre+row['hitAreaRight']-owncentre
        distance=boundary+(offset if expands else -offset)
        pose_age=max(1,min(row['frameNumber']-2,6));wait=max(0,z['attack.StartUp']-pose_age)
        delay=max(0,pose_age-z['attack.StartUp'])
        spec={**placement(stock,zen,move,width,side,distance,zw),'move':move,'defence':'passive',
            'incoming_action':attack,'incoming_delay':delay,'target_wait_frames':wait,
            'role':'incoming_boundary','expected_stock_contact':not expands,'geometry_field':field}
        return spec
    if field.endswith('Up') or field.endswith('Down') and row['state']!='AIR' and not row['speedY']:
        # On the floor, changing bottom also moves the sprite to preserve floor
        # contact, changing the upper vulnerable edge. That is an observed
        # spacing/vulnerability effect, not a loader-only rectangle check.
        if row['state']=='AIR':return None
        attack='AIR_A';z=zen[attack];profile=jump_profile(zen)['runs'][0]['samples']
        boundary=640-row['hitAreaDown']+row['hitAreaUp'];options=[]
        for s in profile:
            if not s['control']:continue
            active=[v for v in profile if s['issue_age']+z['attack.StartUp']-1<=v['issue_age']<=s['issue_age']+z['attack.StartUp']+z['attack.Active']-1]
            if not active:continue
            # The collision pass precedes motion/attack updates. Include the
            # last box used for collision, rather than extrapolating a box
            # after updateAttackParameter has expired it.
            attack_bottom=max(v['raw_y']+z['attack.hitAreaDown'] for v in active)
            gap=boundary-attack_bottom if expands else attack_bottom-boundary
            if gap>=offset:options.append((gap,s['issue_age']))
        if not options:return None
        gap,age=min(options)
        distance=zen[attack]['attack.hitAreaRight']-(zen['STAND']['hitAreaLeft']+zen['STAND']['hitAreaRight'])/2
        spec={**placement(stock,zen,move,width,side,distance,zw),'move':move,'role':'incoming_boundary','defence':'passive',
            'incoming_action':attack,'incoming_jump_age':age,'target_wait_frames':max(0,age+z['attack.StartUp']-4),
            'expected_stock_contact':not expands,'geometry_field':field,'stock_vertical_gap':gap}
        return spec
    return None


async def body_wall_witness(executor,inputs,change,side,metrics):
    """Rear-body edits can change a stage-wall collision without a rear attacker.

    This claims a realised spacing effect only. A rectangle loaded at a new
    coordinate with no wall-induced displacement is not accepted as evidence.
    """
    root=executor.root;stock=inputs[root]['table'];candidate=executor.tables['candidate']
    width=inputs[root]['width'];zw=inputs['ZEN']['width'];move=change['move']
    front=side=='P1'
    spec={'move':move,'role':'rear_wall_boundary','orientation':side,'defence':'passive',
        'target_x':-stock['STAND']['hitAreaLeft'] if front else 960-width+stock['STAND']['hitAreaLeft'],
        'opponent_x':700-(zw-inputs['ZEN']['table']['STAND']['hitAreaLeft']) if front else 260-inputs['ZEN']['table']['STAND']['hitAreaLeft'],
        'rear_wall_anchor':True,'geometry_field':change['property']}
    if move.startswith('AIR'):
        controls=[s['issue_age'] for s in jump_profile(stock)['runs'][0]['samples'] if s['control']]
        if not controls:return None
        spec['jump_age']=controls[0]+1
    setup=setup_for(inputs['ZEN']['table'],candidate[move],{'attack.StartAddEnergy':0})
    if setup:spec['energy_setup']=setup
    base=await executor.execute(spec,'stock');modified=await executor.execute(spec,'candidate')
    observations=[]
    for record,table in ((base,stock),(modified,candidate)):
        if record.get('infrastructure_failure'):return {'orientation':side,'witness':False,'reason':'wall probe infrastructure failure'}
        obs=record['observation'];issue=obs['issue_frame']
        samples=[x for x in obs['trace'] if issue is not None and x['frame']>issue and x['me']['action']==move]
        at_wall=[x for x in samples if x['me']['left']<=0] if front else [x for x in samples if x['me']['right']>=960]
        if not at_wall:return {'orientation':side,'witness':False,'reason':'focal move did not establish rear-wall collision in both tables'}
        x=at_wall[0];row=table[move];raw=x['me']['left']-(row['hitAreaLeft'] if x['me']['front'] else width-row['hitAreaRight'])
        observations.append({'frame':x['frame'],'facing':x['me']['front'],'raw_x':raw,
            'body':{k:x['me'][k] for k in ('left','right','top','bottom')},'fixture_id':record['fixture_id']})
    a,b=observations;delta=(b['raw_x']-a['raw_x'])*(1 if front else -1)
    expected=change['stock']-change['value']
    witness=abs(delta)>1 and delta*expected>0 and a['facing']==front and b['facing']==front
    return {'orientation':side,'scenario':spec,'witness':witness,'method':'observed rear-wall clamping and resulting spacing',
        'stock':a,'candidate':b,'signed_spacing_delta':delta,'expected_direction':1 if expected>0 else -1}


async def assess_geometry(executor,inputs,change,stock_records,metrics,all_changes=(),pairs=()):
    root=executor.root;stock=inputs[root]['table'];zen=inputs['ZEN']['table'];move=change['move'];field=change['property']
    delta=change['value']-change['stock'];expands=delta>0 if field.endswith(('Right','Down')) else delta<0
    body=not field.startswith('attack.');evidence=[];gaps=[];witness_sides=set();failures=[]
    for pair in pairs:
        b,c=pair['stock_metrics'],pair['candidate_metrics']
        if pair.get('infrastructure_failure') or b.get('method_gaps') or c.get('method_gaps'):continue
        # Compare consequences of the same contact event. A boundary switching
        # hit to miss cannot supply a matched HP/energy/impact comparison.
        if bool(b.get('contact_count'))!=bool(c.get('contact_count')):continue
        changes,conditions=compare_side_observables(pair,independent_changes(all_changes or (change,)))
        if changes:failures.append({'orientation':pair['scenario']['orientation'],'role':pair['scenario']['role'],
            'reason':'mechanically independent observable changed','changes':changes})
    for side in ('P1','P2'):
        if body and field=='hitAreaLeft':
            wall=await body_wall_witness(executor,inputs,change,side,metrics)
            if wall:
                evidence.append(wall)
                if wall['witness']:witness_sides.add(side);continue
        tried=set()
        # A bounded effectiveness screen, not an envelope/range search. Place
        # the witness inside the known edit rather than trying three fixed
        # offsets that can all lie outside a small edit's changed region.
        for offset in (boundary_offset(change),):
            if body:spec=body_witness(stock,zen,inputs[root]['width'],inputs['ZEN']['width'],move,field,delta,offset,side,stock_records)
            elif field.endswith(('Left','Right')):spec=horizontal_witness(stock_records,stock,zen,inputs[root]['width'],inputs['ZEN']['width'],move,field,expands,offset,side)
            else:spec=vertical_witness(stock_records,stock,zen,inputs[root]['width'],inputs['ZEN']['width'],move,field,expands,offset,side)
            if spec is None:
                gaps.append(side+': no physically constructed separating boundary for offset '+str(offset));continue
            if digest(spec) in tried:continue
            tried.add(digest(spec))
            base=await executor.execute(spec,'stock')
            if base.get('infrastructure_failure'):
                gaps.append(side+': stock boundary infrastructure failure');break
            b=incoming_contact(base) if body else metrics(base,stock)
            b_contact=bool(b.get('contact',b.get('contact_count',False)))
            established=b.get('established',not b.get('method_gaps'))
            if not established or b_contact!=spec['expected_stock_contact']:
                evidence.append({'orientation':side,'scenario':spec,'stock_control_established':False,'stock':b});continue
            modified=await executor.execute(spec,'candidate')
            if modified.get('infrastructure_failure'):
                gaps.append(side+': candidate boundary infrastructure failure');break
            c=incoming_contact(modified) if body else metrics(modified,executor.tables['candidate'])
            c_contact=bool(c.get('contact',c.get('contact_count',False)))
            established=c.get('established',not c.get('method_gaps'))
            witness=established and b_contact!=c_contact and c_contact==expands
            evidence.append({'orientation':side,'scenario':spec,'stock_control_established':True,
                'stock_contact':b_contact,'candidate_contact':c_contact,'witness':witness,
                'stock_fixture_id':base['fixture_id'],'candidate_fixture_id':modified['fixture_id']})
            if witness:witness_sides.add(side);break
    return {**change,'verdict':'INVALID' if failures else ('VALID' if len(witness_sides)==2 else 'UNDETERMINED'),
        'reason':failures[0]['reason'] if failures else ('Changed contact envelope or wall-induced spacing demonstrated at fixed stock anchors in both orientations.' if len(witness_sides)==2 else
            'A physically separating stock/candidate contact boundary was not established in both orientations; loaded geometry alone is insufficient.'),
        'method_gaps':gaps,'evidence':evidence,'failures':failures,'magnitude_fidelity':'CONTACT_ENVELOPE_VERIFIED' if len(witness_sides)==2 else None}

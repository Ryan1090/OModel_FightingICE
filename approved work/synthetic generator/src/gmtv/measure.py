"""Event-relative measurements from this experiment's raw gameplay traces."""


def effect(record,table=None):
    spec=record['spec'];obs=record['observation'];trace=obs['trace'];move=spec['move'];issue=obs['issue_frame']
    missing=[];result={'issued':obs['issued'],'setup_ready':obs['ready'] is not None,
        'energy_setup_failure':obs.get('energy_setup_failure')}
    if issue is None:return {**result,'method_gaps':['source command not issued']}
    started=next((i for i,x in enumerate(trace) if x['frame']>issue and x['me']['action']==move),None)
    if started is None:return {**result,'method_gaps':['source action not observed after command']}
    first=trace[started];before=trace[max(0,started-1)];onset=first['frame'];samples=trace[started:]
    source=[]
    for x in samples:
        if x['me']['action']!=move:break
        source.append(x)
    events=[]
    for prev,now in zip(trace[max(0,started-1):],trace[started:]):
        # Zero guard damage and 0/1-frame recovery can leave no HP or recovery
        # state in the post-update observation. Recipient energy / a rising
        # normal-hit confirm still establish the physical contact trigger.
        if now['op']['hp']!=prev['op']['hp'] or now['op']['energy']!=prev['op']['energy'] or (now['me']['hit_confirm'] and not prev['me']['hit_confirm']) or ('RECOV' in now['op']['action'] and now['op']['action']!=prev['op']['action']) or now['op']['action']=='CHANGE_DOWN' and prev['op']['action']!='CHANGE_DOWN':
            events.append((prev,now))
    # A projectile can survive the source. The full observation interval is
    # retained; first-trigger attribution is separate from repeated contacts.
    attacks=[];projectiles=[]
    for x in samples:
        a=x['me']['attack']
        if x['me']['action']==move and not a.get('empty_flag',True):attacks.append((x['frame'],a))
        for p in x['projectiles']:
            if p.get('player_number')==(spec['orientation']=='P1') and not p.get('empty_flag',True):projectiles.append((x['frame'],p))
    first_active=min([f for f,a in attacks+projectiles],default=None)
    exit_frame=onset+len(source) if len(source)<len(samples) else None
    sign=1 if first['me']['front'] else -1
    result.update(action_onset=onset,command_to_onset=onset-issue,source_frames_observed=len(source),
        control_return=None if exit_frame is None else exit_frame-onset,
        attack_onset=None if first_active is None else first_active-onset,
        active_frames_observed=len({f for f,a in attacks+projectiles}),
        initial_velocity_x=sign*first['me']['speed_x'],initial_velocity_y=first['me']['speed_y'],
        onset_energy_delta=first['me']['energy']-before['me']['energy'],
        source_displacement_x=sign*(source[-1]['me']['x']-first['me']['x']),
        source_displacement_y=source[-1]['me']['y']-first['me']['y'],
        contact_count=len(events),hit_confirm_seen=any(x['me']['hit_confirm'] for x in source),
        projectile_seen=bool(projectiles),onset_positions={'me':{k:first['me'][k] for k in ('x','y','left','right','top','bottom')},
            'op':{k:first['op'][k] for k in ('x','y','left','right','top','bottom')}})
    if events:
        pre,hit=events[0];guard='GUARD_RECOV' in hit['op']['action']
        guard_basis='observed guard-recovery state' if guard else None
        attack=pre['me']['attack'];kind=attack.get('attack_type') if not attack.get('empty_flag',True) else None
        if kind is None and table is not None:kind=table[move]['attack.AttackType']
        posture=pre['op']['action']
        accepted={'STAND_GUARD':{1,2},'CROUCH_GUARD':{1,3},'AIR_GUARD':{1,2}}
        if not guard and (posture in accepted and kind in accepted[posture] or 'GUARD_RECOV' in posture):
            guard=True;guard_basis='observed pre-contact guard posture and engine isGuard category rule; contact independently observed'
        if not guard and pre['op']['control']:
            op_input=next((i for i in obs.get('opponent_inputs',[]) if i['frame']==pre['frame']),None)
            if op_input:
                keys=op_input['keys'];back=keys['L'] if op_input['front'] else keys['R']
                effective='AIR_GUARD' if op_input['state']=='AIR' else ('CROUCH_GUARD' if keys['D'] else 'STAND_GUARD')
                if back and not keys['A'] and not keys['B'] and not keys['C'] and kind in accepted[effective]:
                    guard=True;guard_basis='recorded same-frame guard input with ordinary control and engine isGuard category rule; contact independently observed'
        direction=1 if (pre['op']['left']+pre['op']['right'])>=(pre['me']['left']+pre['me']['right']) else -1
        returns=next((x for x in trace if x['frame']>=hit['frame'] and x['op']['control'] and 'GUARD_RECOV' not in x['op']['action']),None)
        result.update(contact_delay=hit['frame']-onset,hp_loss=pre['op']['hp']-hit['op']['hp'],
            guarded=guard,guard_evidence_basis=guard_basis,hit_energy_delta=hit['me']['energy']-pre['me']['energy'],
            received_energy_delta=hit['op']['energy']-pre['op']['energy'],
            impact_velocity_x=direction*hit['op']['speed_x'],impact_velocity_y=hit['op']['speed_y'],
            down_seen=any(x['op']['state']=='DOWN' or x['op']['action'] in ('CHANGE_DOWN','DOWN') for x in samples),
            guard_duration=None if not guard or returns is None else returns['frame']-hit['frame'],
            contact={'before':pre,'after':hit})
    if projectiles:
        f,p=projectiles[0]
        result.update(projectile_velocity_x=sign*p['speed_x'],projectile_velocity_y=p['speed_y'],
            projectile_frames_observed=len({f for f,p in projectiles}))
    airborne=[x for x in samples if x['me']['state']=='AIR']
    if airborne:
        result.update(airborne_frames=len(airborne),apex=min(x['me']['y'] for x in airborne),
            landing_seen=any(x['frame']>airborne[0]['frame'] and x['me']['state']!='AIR' for x in samples))
    result['method_gaps']=missing
    return result


def compact(metrics):
    return {k:v for k,v in metrics.items() if k not in {'contact'}}

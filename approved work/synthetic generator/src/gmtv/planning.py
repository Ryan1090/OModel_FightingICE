"""Requested scenarios per edited move, derived from tables and engine rules."""
from .construct import scenarios,command_frames
from .assessment import roles_for,GUARDS
from .rules import COMMANDS,cancel_catalogue
from .kinematics import jump_profile
from .energy_setup import paired_setup_for


def move_scenarios(stock,candidate,zen,move,changes,width,zen_width):
    required=set().union(*(roles_for(c['property']) for c in changes))
    profile=jump_profile(stock);zp=jump_profile(zen)
    full=scenarios(stock,zen,move,width,zen_width,profile,zp)
    selected=[]
    # Hit/guard cases also measure movement/projectile effects, so no per-field
    # games are created. The role union is computed once for the complete move.
    for spec in full:
        if spec['role'] in required:
            spec=dict(spec)
            if spec['role']=='guard':
                # Prefer a posture that blocks both tables so the same two
                # probes can compare guard damage/energy/stun after a type edit.
                choices=('air_guard',) if spec['defence']=='air_guard' else ('stand_guard','crouch_guard')
                common=[p for p in choices if stock[move]['attack.AttackType'] in GUARDS[p]
                        and candidate[move]['attack.AttackType'] in GUARDS[p]]
                if common:spec['defence']=common[0]
            setup=paired_setup_for(zen,stock[move],candidate[move])
            if setup:spec['energy_setup']=setup
            selected.append(spec)
    if 'stand_guard' in required or 'crouch_guard' in required:
        for spec in full:
            if spec['role']!='hit':continue
            for role in ('stand_guard','crouch_guard'):
                # Keep physical jumping context where required, and record
                # the actual posture. A requested posture alone is no proof.
                selected.append({**spec,'role':role,'defence':role})
    return selected


def cancel_scenarios(stock,candidate,zen,changes,width,zen_width):
    catalogue=cancel_catalogue(stock,candidate,changes);result=[]
    for link in catalogue:
        if link['claim']=='predicted_ineligible':continue
        # Unchanged eligible links are recorded, not extra experimental claims
        # that the edit must have newly enabled. Changed links are all exercised.
        if link['claim']=='unchanged_eligible':continue
        source=link['source'];followup=link['followup']
        needed_airtime=max(link['stock']['window_start'],link['candidate']['window_start'])+command_frames(followup)+3
        base=scenarios(stock,zen,source,width,zen_width,jump_profile(stock),jump_profile(zen),remaining_airtime=needed_airtime)
        for side in ('P1','P2'):
            for role in (('removed_window','no_hit_confirm') if link['claim']=='removed' else ('within','before_window','no_hit_confirm')):
                if role=='before_window' and candidate[source]['cancelAbleFrame']<=0:continue
                window=link['stock']['window_start'] if link['claim']=='removed' else link['candidate']['window_start']
                template=next((s for s in base if s['orientation']==side and s['role']==('whiff' if role=='no_hit_confirm' else 'hit')),None)
                if template is None:continue
                setup=paired_setup_for(zen,stock[source],candidate[source],stock[followup],candidate[followup])
                result.append({**template,'move':source,'followup':followup,'role':role,
                    'request_elapsed':max(0,window-command_frames(followup)) if role=='before_window' else window,
                    'relationship_key':source+'->'+followup,'energy_setup':setup} if setup else
                    {**template,'move':source,'followup':followup,'role':role,
                    'request_elapsed':max(0,window-command_frames(followup)) if role=='before_window' else window,
                    'relationship_key':source+'->'+followup})
    return catalogue,result


def horizon(candidate,specs):
    moves={s['move'] for s in specs};tail=max((candidate[m]['frameNumber']+candidate[m]['attack.Active']+
        candidate[m]['attack.GiveGuardRecov'] for m in moves),default=0)
    needed=max(420,tail+300)
    if any(s.get('energy_setup') for s in specs):needed+=2400
    if needed>9000:raise RuntimeError('required probe horizon exceeds the diagnostic resource ceiling; result must remain UNDETERMINED')
    return needed

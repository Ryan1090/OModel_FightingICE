"""Generic stock-trajectory placement refinement; never read candidate outcomes."""
import math
from .probe import placement


def attack_samples(record):
    obs=record['observation'];issue=obs['issue_frame'];side=record['spec']['orientation']=='P1'
    if issue is None:return []
    found=[]
    for x in obs['trace']:
        if x['frame']<=issue:continue
        candidates=[]
        a=x['me']['attack']
        # Automatic STAND/AIR rows can instantiate their own zero-area attack
        # after the requested action finishes. That is a different action's
        # attack, not an extra frame of this move's active window.
        if x['me']['action']==record['spec']['move'] and not a.get('empty_flag',True):candidates.append(a)
        candidates += [p for p in x['projectiles'] if p.get('player_number')==side and not p.get('empty_flag',True)]
        for attack in candidates:found.append((x,attack))
    return found


def contact_placement(record,stock,zen,width,zen_width):
    spec=record['spec'];obs=record['observation'];move=spec['move'];trace=obs['trace'];issue=obs['issue_frame']
    if issue is None:return {**spec,'construction_gap':'source was never issued in stock evidence'}
    origin=next((x for x in trace if x['frame']==issue),None)
    if origin is None:return {**spec,'construction_gap':'stock issue anchor unavailable'}
    if not any(x['frame']>issue and x['me']['action']==move for x in trace):
        # Do not derive geometry from a different move produced by a bad key.
        return {**spec,'stock_refinement':'corrected command encoding; geometry still table-derived'}
    sign=1 if spec['orientation']=='P1' else -1
    origin_centre=(origin['me']['left']+origin['me']['right'])/2
    min_distance=(stock['STAND']['hitAreaRight']-stock['STAND']['hitAreaLeft']+zen['STAND']['hitAreaRight']-zen['STAND']['hitAreaLeft'])/2+4
    choices=[]
    for x,attack in attack_samples(record):
        area=attack['current_hit_area'];left,right=area['left'],area['right']
        if sign<0:left,right=2*origin_centre-right,2*origin_centre-left
        lo=max(min_distance,left-origin_centre-20+2);hi=min(760,right-origin_centre+20-2)
        if hi<lo:continue
        # Use the observed stock opponent's vertical phase. New horizontal
        # anchoring remains fixed before any modified-table evidence is run.
        overlap=min(area['bottom'],x['op']['bottom'])-max(area['top'],x['op']['top'])
        if overlap<2:continue
        for fraction in (.1,.25,.5,.75,.9):
            distance=lo+(hi-lo)*fraction;collisions=0
            for before in trace:
                if before['frame']<=issue:continue
                if before['frame']>x['frame']:break
                body=before['me'];op=before['op']
                l,r=(body['left']-origin_centre,body['right']-origin_centre) if sign>0 else (origin_centre-body['right'],origin_centre-body['left'])
                if l<=distance+20 and r>=distance-20 and body['top']<=op['bottom'] and body['bottom']>=op['top']:
                    collisions+=1
            penetration=min(right-origin_centre,distance+20)-max(left-origin_centre,distance-20)
            choices.append((collisions,overlap,penetration,x['frame'],distance))
    if not choices:return {**spec,'construction_gap':'no stock observed active box intersects the planned opponent vertical phase'}
    chosen=min(choices,key=lambda x:(x[0],-x[1],-x[2],x[3],x[4]))
    return {**spec,**placement(stock,zen,move,width,spec['orientation'],chosen[4],zen_width),
        'stock_refinement':'fixed anchor from observed stock attack/body trajectory; no candidate data',
        'stock_model_contact_frame':chosen[3],'stock_model_vertical_overlap':chosen[1],
        'stock_model_precontact_body_overlaps':chosen[0]}


def whiff_avoidance(record,zen_profile):
    spec=record['spec'];obs=record['observation'];trace=obs['trace'];ready=obs['ready']
    contacts=[]
    for pre,now in zip(trace,trace[1:]):
        if obs['issue_frame'] is not None and now['frame']>obs['issue_frame'] and (now['op']['hp']!=pre['op']['hp'] or now['op']['energy']!=pre['op']['energy']):
            contacts.append(now['frame'])
    if not contacts or ready is None:return {**spec,'construction_gap':'no stock contact timing for an evasion control'}
    # Align the peak of a stock ZEN jump with the previously observed contact.
    # This is a prospective, physically executed control; verify the resulting
    # full attack lifetime is a miss, never assume the model guarantees one.
    apex=min(zen_profile['runs'][0]['samples'],key=lambda x:(x['raw_y'],x['issue_age']))
    delay=max(0,contacts[0]-ready-apex['issue_age'])
    return {**spec,'defence':'jump','opponent_jump_delay':delay,
        'stock_refinement':'stock jump apex aligned to stock projectile arrival; full no-contact control must still pass'}

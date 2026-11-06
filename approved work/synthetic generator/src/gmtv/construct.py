"""Construct scenarios from stock tables and this experiment's jump census."""
from .rules import COMMANDS
from .probe import placement
from .energy_setup import setup_for


def command_frames(action):
    tokens=COMMANDS[action].split()
    return len(tokens)-2*tokens.count('_')


def aerial_context(stock,zen,move,profile,zen_profile,contact=True,remaining_airtime=0):
    if not move.startswith('AIR'):return {}
    row=stock[move];samples=profile['runs'][0]['samples'];by_age={s['issue_age']:s for s in samples}
    last_age=max((s['issue_age'] for s in samples),default=0)
    controls=[s for s in samples if s['control'] and (not remaining_airtime or s['issue_age']+remaining_airtime<last_age)]
    if not controls:return {'construction_gap':'stock jump exposes no controllable airborne frame'}
    if not contact:return {'jump_age':controls[0]['issue_age']+1,'defence':'passive'}
    delay=command_frames(move)-1+row['attack.StartUp']
    op=zen['STAND'];top=640-op['hitAreaDown']+op['hitAreaUp'];bottom=640
    options=[]
    for issue in controls:
        age=issue['issue_age'];at=by_age.get(age+delay)
        if at is None:continue
        raw_y=at['raw_y']+row['speedY']*max(0,delay)
        a,b=raw_y+row['attack.hitAreaUp'],raw_y+row['attack.hitAreaDown']
        overlap=min(b,bottom)-max(a,top)
        options.append((overlap,age,a,b))
    feasible=[x for x in options if x[0]>=2]
    if feasible:
        # Maximum stock geometric penetration, earliest issue as a tie break;
        # no candidate outcome participates in choosing timing or position.
        best=min(feasible,key=lambda x:(-x[0],x[1]))
        return {'jump_age':best[1],'defence':'passive','stock_predicted_vertical_overlap':best[0],
            'aerial_timing_basis':'table/engine stock trajectory plus move startup/vertical impulse; stock only'}
    # If standing cannot be reached, synchronise a physically jumped ZEN body.
    airborne=[]
    for overlap,age,a,b in options:
        for op_sample in zen_profile['runs'][0]['samples']:
            op_age=op_sample['issue_age'];jump_delay=age+delay-op_age
            if jump_delay<0:continue
            overlap=min(b,op_sample['body_bottom'])-max(a,op_sample['body_top'])
            if overlap>=2:airborne.append((overlap,age,jump_delay))
    if airborne:
        best=min(airborne,key=lambda x:(-x[0],x[1],x[2]))
        return {'jump_age':best[1],'defence':'jump','opponent_jump_delay':best[2],
            'stock_predicted_vertical_overlap':best[0],'aerial_timing_basis':'synchronised table/engine stock jump trajectories'}
    return {'jump_age':controls[0]['issue_age']+1,'defence':'passive',
        'construction_gap':'stock trajectory model finds no vertical contact; retain in coverage as a method gap'}


def scenarios(stock,zen,move,width,zen_width,profile,zen_profile,sides=('P1','P2'),remaining_airtime=0):
    row=stock[move];attack=row['attack.Active']>0 and 0<row['attack.StartUp']<row['frameNumber']
    centre=(stock['STAND']['hitAreaLeft']+stock['STAND']['hitAreaRight'])/2
    reach=row['attack.hitAreaRight']-centre+20
    travel=abs(row['attack.speedX'])*row['attack.Active']+abs(row['speedX'])*row['frameNumber']
    far=max(400,min(760,reach+travel+80))
    setup=setup_for(zen,row,{'attack.StartAddEnergy':0})
    result=[]
    for side in sides:
        whiff={'move':move,'role':'whiff','defence':'passive',
            **placement(stock,zen,move,width,side,far,zen_width),
            **aerial_context(stock,zen,move,profile,zen_profile,False)}
        if setup:whiff['energy_setup']=setup
        result.append(whiff)
        if not attack:continue
        context=aerial_context(stock,zen,move,profile,zen_profile,True,remaining_airtime)
        hit={'move':move,'role':'hit','defence':'passive',
            **placement(stock,zen,move,width,side,None,zen_width),**context}
        if setup:hit['energy_setup']=setup
        result.append(hit)
        if row['attack.AttackType'] in (1,2,3):
            defence='crouch_guard' if row['attack.AttackType']==3 else 'stand_guard'
            if hit['defence']=='jump':defence='air_guard'
            result.append({**hit,'role':'guard','defence':defence})
    return result

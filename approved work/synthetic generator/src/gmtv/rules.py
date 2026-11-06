"""Engine-derived applicability and cancel permissions; no historical lookup."""
import ast
import inspect
import re
from pathlib import Path
from pyftg.aiinterface.command_center import CommandCenter


def commands():
    tree=ast.parse(inspect.getsource(CommandCenter))
    out={}
    for node in ast.walk(tree):
        if isinstance(node,ast.If) and isinstance(node.test,ast.Compare) and len(node.test.comparators)==1:
            action=node.test.comparators[0]
            if isinstance(action,ast.Constant) and isinstance(action.value,str):
                calls=[x for statement in node.body for x in ast.walk(statement) if isinstance(x,ast.Call) and isinstance(x.func,ast.Attribute) and x.func.attr=='create_keys']
                if calls and calls[0].args and isinstance(calls[0].args[0],ast.Constant):out[action.value]=calls[0].args[0].value
    out.update({'STAND':'5','AIR':'5'})
    # The installed helper uses diagonals here. This engine's AIR branch
    # explicitly tests lever 6 for FA/FB and lever 4 for guard. Override only
    # diagnostic command encoding; never modify the installed helper/policies.
    out.update({'AIR_FA':'6 _ A','AIR_FB':'6 _ B','AIR_GUARD':'4'})
    return out


COMMANDS=commands()
# Neutral inputs are useful inside probes, but do not establish a new runAction
# onset for these automatic state rows.
AUTOMATIC_ACTIONS=frozenset({'STAND','AIR'})
INPUT_ACTIONS=frozenset(COMMANDS)-AUTOMATIC_ACTIONS


def is_projectile(row):
    # Approved Attack.isProjectile uses an int32 iadd followed by != 0.
    return ((row.get('attack.speedX',0)+row.get('attack.speedY',0)) & 0xffffffff)!=0


def input_state_compatible(source,followup):
    # CommandTable.convertKeyToAction branches on current State.AIR. JUMP is
    # a ground command although its resulting Motion.state is AIR.
    return (source['state']=='AIR')==(followup['motionName'].startswith('AIR'))


def able_action(source,followup,elapsed,energy,hit_confirm,control=False):
    if energy < -followup['attack.StartAddEnergy']:return False
    if control:return True
    return bool(hit_confirm and source['cancelAbleFrame']<=elapsed and source['cancelAbleMotionLevel']>=followup['motionLevel'])


def relationship(table,source,followup,energy=None):
    a,b=table[source],table[followup]
    reasons=[]
    if source==followup:reasons.append('same action does not restart in Character.runAction')
    if source in AUTOMATIC_ACTIONS or followup not in INPUT_ACTIONS:reasons.append('not an explicitly input-reachable relationship')
    if not input_state_compatible(a,b):reasons.append('input-state incompatible')
    if a['control']:reasons.append('source permits ordinary action changes; not a cancel window')
    if a['cancelAbleFrame']>=a['frameNumber']:reasons.append('window does not open before source lifetime ends')
    if a['cancelAbleMotionLevel']<b['motionLevel']:reasons.append('follow-up level exceeds source permission')
    if energy is not None and energy < -b['attack.StartAddEnergy']:reasons.append('insufficient energy')
    if is_projectile(a):
        reasons.append('projectile-only contact path does not set source hitConfirm in Fighting.calculationHit')
    if a.get('attack.AttackType')==4:
        reasons.append('throw contact replaces the source with THROW_HIT before a post-contact source cancel')
    if 'attack.Active' in a and (a['attack.Active']<=0 or not 0<a['attack.StartUp']<a['frameNumber']):
        reasons.append('source has no reachable contact onset to establish hitConfirm')
    return {'source':source,'followup':followup,'predicted':not reasons,'window_start':a['cancelAbleFrame'],
        'source_length':a['frameNumber'],'requires_hit_confirm':True,'minimum_energy':max(0,-b['attack.StartAddEnergy']),
        'energy_is_conditional':energy is None,
        'reasons':reasons,'engine_basis':'Fighting.ableAction; Character.runAction; CommandTable.convertKeyToAction'}


def changed_relationships(stock,candidate,changed_cells,energy=None):
    affected_sources={x['move'] for x in changed_cells if x['property'] in {'cancelAbleFrame','cancelAbleMotionLevel','frameNumber','state','control'}}
    affected_followups={x['move'] for x in changed_cells if x['property'] in {'motionLevel','attack.StartAddEnergy','state'}}
    out=[]
    for source in stock:
        for followup in COMMANDS:
            if followup not in stock or not (source in affected_sources or followup in affected_followups):continue
            before=relationship(stock,source,followup,energy);after=relationship(candidate,source,followup,energy)
            changed_window=before['window_start']!=after['window_start'] or before['source_length']!=after['source_length']
            changed_energy=before['minimum_energy']!=after['minimum_energy']
            if before['predicted']!=after['predicted'] or (before['predicted'] and after['predicted'] and (changed_window or changed_energy)):
                out.append({'source':source,'followup':followup,'stock':before,'candidate':after,
                    'claim':'enabled' if after['predicted'] and not before['predicted'] else ('removed' if before['predicted'] and not after['predicted'] else ('window_changed' if changed_window else 'energy_changed'))})
    return out


def cancel_catalogue(stock,candidate,changed_cells):
    """All affected links, including ineligible links and their reasons.

    Eligibility here is a conditional prediction, not a claim that the fixture
    has attained the necessary energy, hit-confirm or airborne state. Gameplay
    evidence must establish those preconditions before testing a prediction.
    """
    sources={x['move'] for x in changed_cells if x['property'] in {'cancelAbleFrame','cancelAbleMotionLevel'}}
    incoming={x['move'] for x in changed_cells if x['property']=='motionLevel'}
    changed={(r['source'],r['followup']):r for r in changed_relationships(stock,candidate,changed_cells)}
    result=[]
    for source in stock:
        if source not in INPUT_ACTIONS:continue
        for followup in stock:
            if followup not in INPUT_ACTIONS or not (source in sources or followup in incoming):continue
            before=relationship(stock,source,followup);after=relationship(candidate,source,followup)
            row=changed.get((source,followup))
            result.append(row or {'source':source,'followup':followup,'stock':before,'candidate':after,
                'claim':'unchanged_eligible' if after['predicted'] else 'predicted_ineligible'})
    return result


def attributed_relationships(stock,candidate,cell,checked):
    """A cell contributes only if reverting that cell changes a usable link.

    Counterfactual table arithmetic attributes existing gameplay evidence; no
    additional gameplay is inferred or substituted for a missing link check.
    Disabled links with different unused numeric limits are mechanically equal.
    """
    move,prop=cell['move'],cell['property']
    reverted={**candidate,move:{**candidate[move],prop:stock[move][prop]}}
    def signature(link):
        return (False,) if not link['predicted'] else (True,link['window_start'],link['source_length'],link['minimum_energy'])
    result=[]
    for link in checked:
        if prop=='motionLevel':
            if link['followup']!=move:continue
        elif link['source']!=move:continue
        full=relationship(candidate,link['source'],link['followup'])
        without=relationship(reverted,link['source'],link['followup'])
        if signature(full)==signature(without):continue
        result.append({**link,'cell_attribution':{'move':move,'property':prop,
            'complete_candidate':full,'only_this_cell_reverted':without}})
    return result


def prediction_at(table,source,followup,sample):
    """Exact permission at a recorded pre-input game state (no energy cap guess)."""
    a,b=table[source],table[followup]
    elapsed=a['frameNumber']-sample['remaining']
    compatible=(sample['state']=='AIR')==followup.startswith('AIR')
    return {'elapsed':elapsed,'energy':sample['energy'],'hit_confirm':sample['hit_confirm'],
        'control':sample['control'],'input_state_compatible':compatible,
        'able_action':able_action(a,b,elapsed,sample['energy'],sample['hit_confirm'],sample['control']),
        'cancellable':bool(sample['action']==source and source!=followup and not sample['control']
            and sample['remaining']>0 and compatible
            and able_action(a,b,elapsed,sample['energy'],sample['hit_confirm'],False))}


def applicability(row,prop):
    attack=row['attack.Active']>0 and 0<row['attack.StartUp']<row['frameNumber']
    projectile=is_projectile(row)
    if prop.startswith('attack.') and prop!='attack.StartAddEnergy' and not attack:
        return {'applicable':False,'reason':'stock has no positive active interval with reachable onset; candidate-created attacks require a separate gameplay probe, not this stock applicability inference','engine_basis':'Character.createAttackInstance; Character.startActive'}
    if row['attack.AttackType']==4 and prop in {'attack.ImpactX','attack.ImpactY','attack.DownProp','attack.GuardDamage','attack.GuardAddEnergy','attack.GiveGuardRecov'}:
        return {'applicable':False,'reason':'throw hit branch does not consume this field and cannot be guarded','engine_basis':'Character.hitAttack'}
    if prop in {'cancelAbleFrame','cancelAbleMotionLevel'} and row['control']:
        return {'applicable':False,'reason':'ordinary-control branch bypasses the cancel-window and level tests','engine_basis':'Fighting.ableAction'}
    return {'applicable':True,'projectile':projectile,'engine_basis':'engine source semantics; gameplay proof still required'}

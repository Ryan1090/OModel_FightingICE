"""Physical preconditioning, not energy injection or affordability evidence."""
from .rules import COMMANDS


def setup_for(zen,source,followup):
    required=max(0,-source['attack.StartAddEnergy'])+max(0,-followup['attack.StartAddEnergy'])
    if not required:return None
    options=[r for r in zen.values() if r['motionName'] in COMMANDS and r['state']=='STAND'
        and not r['control'] and r['attack.AttackType'] in (1,2) and r['attack.StartAddEnergy']>=0
        and r['attack.Active']>0 and r['attack.GiveEnergy']>0 and r['speedX']==0 and r['speedY']==0
        and r['attack.speedX']==0 and r['attack.speedY']==0]
    if not options:return {'required_energy':required,'method_gap':'no stock-ZEN ground guarding setup'}
    chosen=min(options,key=lambda r:(-r['attack.GiveEnergy']/r['frameNumber'],r['motionName']))
    return {'required_energy':required,'opponent_action':chosen['motionName'],
        'guard_posture':'STAND_GUARD','budget_frames':2400,'settle_frames':80,
        'selection':'largest stock GiveEnergy/frameNumber among stationary free ground attacks blockable standing; action-name tie break',
        'purpose':'establish actual pre-input energy; makes no natural-affordability claim'}


def paired_setup_for(zen,stock_source,candidate_source,stock_followup=None,candidate_followup=None):
    """One physical precondition sufficient for both sides of a comparison.

    Reducing a cost must not make its stock baseline unaffordable. Choose the
    larger complete source+follow-up requirement, not a hybrid sum of unrelated
    component maxima. Actual pre-input energy is still observed in gameplay.
    """
    free={'attack.StartAddEnergy':0}
    before=setup_for(zen,stock_source,stock_followup or free)
    after=setup_for(zen,candidate_source,candidate_followup or free)
    if before is None and after is None:return None
    chosen=max((x for x in (before,after) if x is not None),key=lambda x:x['required_energy'])
    return {**chosen,'stock_required_energy':0 if before is None else before['required_energy'],
        'candidate_required_energy':0 if after is None else after['required_energy'],
        'paired_precondition':'maximum complete stock/candidate requirement; no injected energy'}

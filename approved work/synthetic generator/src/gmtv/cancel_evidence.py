"""Evaluate engine-derived cancel claims, without a user claims sidecar.

An absent precondition is a method gap, not contrary gameplay evidence. Negative
probes hold energy/state constant and attempt the same follow-up before the
window (when one exists) and without hit-confirm. Only actual early transitions
count: execution after natural source completion is never a successful cancel.
"""
from .rules import prediction_at


def evaluate(relationship,table,attempts):
    expected=relationship['candidate']['predicted']
    required={'within','no_hit_confirm'}
    if relationship['candidate']['window_start']>0:required.add('before_window')
    if relationship['claim']=='removed':required={'removed_window','no_hit_confirm'}
    details=[];missing=[];failed=[]
    for orientation in ('P1','P2'):
        for role in sorted(required):
            matches=[a for a in attempts if a['orientation']==orientation and a['role']==role]
            if not matches:missing.append({'orientation':orientation,'role':role,'reason':'probe missing'});continue
            for attempt in matches:
                pre=attempt.get('pre_input')
                if not pre or not attempt.get('load_verified') or not attempt.get('command_verified'):
                    missing.append({'orientation':orientation,'role':role,'reason':'input/load/pre-state not established'});continue
                p=prediction_at(table,relationship['source'],relationship['followup'],pre)
                # A negative control must remove only its named precondition.
                affordable=pre['energy']>=relationship['candidate']['minimum_energy']
                context=pre['action']==relationship['source'] and not pre['control'] and pre['remaining']>0 and p['input_state_compatible'] and affordable
                if role=='within':context=context and pre['hit_confirm'] and p['cancellable']
                elif role=='before_window':context=context and pre['hit_confirm'] and p['elapsed']<relationship['candidate']['window_start']
                elif role=='no_hit_confirm':
                    window=relationship['stock']['window_start'] if relationship['claim']=='removed' else relationship['candidate']['window_start']
                    context=context and not pre['hit_confirm'] and p['elapsed']>=window
                elif role=='removed_window':
                    # Removed timing can have no window at all. Test the old
                    # window while the original source still exists.
                    context=context and pre['hit_confirm'] and p['elapsed']>=relationship['stock']['window_start']
                if not context:
                    missing.append({'orientation':orientation,'role':role,'reason':'required mechanical preconditions not attained','prediction':p});continue
                transition=attempt.get('transition')
                # A source with one frame left expires in this update. Its
                # ordinary successor (notably CROUCH) is not cancel evidence.
                if role=='within' and transition and transition.get('source_remaining')==1:
                    missing.append({'orientation':orientation,'role':role,
                        'reason':'transition coincides with natural source expiry; early cancel not established'});continue
                executed=bool(transition and transition['from']==relationship['source']
                    and transition['to']==relationship['followup'] and transition['source_remaining']>1
                    and not transition.get('source_control',True))
                should_execute=role=='within' and expected
                ok=executed==should_execute
                evidence={'orientation':orientation,'role':role,'prediction':p,'executed':executed,'expected':should_execute,'pass':ok}
                if attempt.get('control_reuse'):evidence['control_reuse']=attempt['control_reuse']
                details.append(evidence)
                if not ok:failed.append(evidence)
    return {'verdict':'INVALID' if failed else ('UNDETERMINED' if missing else 'VALID'),
        'source':relationship['source'],'followup':relationship['followup'],
        'claim':relationship['claim'],'failed':failed,'method_gaps':missing,'evidence':details}

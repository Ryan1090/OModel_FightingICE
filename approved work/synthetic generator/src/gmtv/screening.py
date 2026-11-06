"""Bounded effectiveness screen; exact magnitude is informational.

No acceptance is inferred from a loaded value or an unexecuted prediction.
Stopping early can leave a candidate UNDETERMINED; it cannot make one VALID.
"""
from .cancel_evidence import evaluate
from .rules import COMMANDS
from .schema import digest

POLICY = {
    'version': 'effectiveness-v3.1-mandatory-cancel-gates',
    'purpose': 'Demonstrate a usable, correctly directed gameplay effect efficiently; not certify absolute limits or exact magnitude.',
    'magnitude_fidelity': 'Informational only; existing unit tolerances and direction checks remain.',
    'geometry': 'One separating placement per field/orientation, at half the configured edit (integer floor, minimum 1 px, maximum 24 px from stock boundary); rear-wall witness retained. No extra descending-phase search.',
    'cancel': 'For every changed table-derived relationship, test its positive/removal gate first. If that gate cannot be established or contradicts the prediction, skip its remaining controls and return the evidenced INVALID or UNDETERMINED result. Every gate and negative control in both orientations remains mandatory for VALID.',
    'acceptance': 'All edited cells must be VALID. Missing evidence is never accepted. Engine invariants, observed independent side effects and both orientations remain checked.',
    'per_edit_attribution': 'Cancel evidence must change when only that cell is reverted; automatic STAND/AIR rows are UNDETERMINED without induced-event validation.',
    'mandatory_cancel_links': 'Attribution supplies positive evidence only. Every checked relationship touching a cancel cell can block it, including redundant or co-edit-induced relationships with no individual owner.',
    'attack_preservation': 'A duration edit that observably removes the stock attack is INVALID; incomplete observation remains UNDETERMINED.',
}


def boundary_offset(change):
    return max(1, min(24, abs(change['value'] - change['stock']) // 2))


async def check_relationship(executor, link, specs, table, decode):
    """Cheap gate first; never spend controls on an already undecidable link."""
    primary = 'removed_window' if link['claim'] == 'removed' else 'within'
    attempts = []
    if {s['orientation'] for s in specs if s['role'] == primary} != {'P1', 'P2'}:
        result = evaluate(link, table, attempts)
        result['screening_stop'] = {'reason': 'Required gate could not be constructed in both orientations.',
                                   'executed_probes': 0, 'planned_probes': len(specs)}
        return result
    ordered = sorted(specs, key=lambda s: (s['role'] != primary, s['orientation'], s['role']))
    for spec in ordered:
        # Negative ableAction gates depend on source elapsed/hit-confirm, not
        # which otherwise-admissible follow-up button is requested. Keep the
        # entire physical scenario and command input-phase layout equal. Each new
        # relationship still proves its own command in its primary probes.
        reuse=getattr(executor,'fast_mode',False) and spec['role'] in {'before_window','no_hit_confirm'}
        cache=getattr(executor,'negative_controls',None)
        if reuse and cache is None:executor.negative_controls={};cache=executor.negative_controls
        key=negative_control_key(link,spec) if reuse else None
        if reuse and key in cache:
            original=cache[key]
            attempts.append({**original,'control_reuse':{
                'representative_followup':original['followup'],'applied_to_followup':spec['followup'],
                'equivalence_key':key,'basis':'same source gate and complete physical scenario, energy requirement and input-phase layout; this link independently passed its own primary command probes'}})
        else:
            record = await executor.execute(spec, 'candidate')
            if not record.get('infrastructure_failure'):
                attempt=decode(record);attempts.append(attempt)
                # Only established successful negatives can be shared. A bad
                # or unresolved representative never supplies inferred proof.
                result=evaluate(link,table,attempts)
                details=[e for e in result['evidence'] if e['role']==spec['role'] and e['orientation']==spec['orientation']]
                if reuse and details and all(e['pass'] for e in details):cache[key]=attempt
        if spec['role'] == primary:
            result = evaluate(link, table, attempts)
            problems = [p for p in result['failed'] + result['method_gaps']
                        if p['orientation'] == spec['orientation'] and p['role'] == primary]
            if problems:
                result['screening_stop'] = {'reason': 'Required relationship gate failed or could not be established; remaining probes cannot make this link VALID.',
                    'orientation': spec['orientation'], 'role': primary,
                    'executed_probes': len(attempts), 'planned_probes': len(specs)}
                return result
    return evaluate(link, table, attempts)


def negative_control_key(link,spec):
    """Same physical setup, energy and lever/button/release input phases.

    Window and hit-confirm fail before the follow-up motion-level comparison in
    the same ableAction conjunction; both candidate primary probes independently
    establish the requested command, state and permission for every follow-up.
    When that source gate is false, the requested action cannot execute whatever
    its decoded lever/button identity. Retain input-phase counts/layout to keep
    decoding timing comparable; never share a positive transition this way.
    """
    pattern=['release' if token=='_' else 'button' if token in {'A','B','C'} else 'lever'
             for token in COMMANDS[spec['followup']].split()]
    physical={k:v for k,v in spec.items() if k not in {'followup','relationship_key'}}
    return digest({'scenario':physical,'command_pattern':pattern,
        'minimum_energy':link['candidate']['minimum_energy'],
        'candidate_window':link['candidate']['window_start'],
        'stock_window':link['stock']['window_start'],'source_length':link['candidate']['source_length']})

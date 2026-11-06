"""Explicit risk-focused screen, not an assertion that every edit was exercised.

Selection is prospective and mechanical. No historical outcome rate selects a
property, move, value or relationship. Raw commits retain exact horizons.
"""
import math
from .assessment import roles_for
from .rules import attributed_relationships
from .construct import command_frames

SIMPLE = frozenset({'attack.HitDamage', 'attack.GuardDamage',
    'attack.StartAddEnergy', 'attack.HitAddEnergy', 'attack.GuardAddEnergy', 'attack.GiveEnergy'})
CANCEL = frozenset({'cancelAbleFrame', 'cancelAbleMotionLevel', 'motionLevel'})
POLICY = {
    'version': 'fast-risk-screen-v1.2-representative-cancels',
    'claim': 'SCREEN_PASSED means static checks passed and the selected gameplay checks passed; it does not prove every edit effective.',
    'selection': 'All non-simple editable properties receive their existing gameplay handlers. Simple damage/energy edits use already selected scenarios. On a move with only simple edits choose hit, else guard, else whiff; do not add scenarios for the other simple fields.',
    'cancel': 'Statically predict every affected relationship. Select a deterministic small set of representative changed relationships covering each cancel edit with its own leave-one-edit-out attribution. Test every selected positive/removal gate and mandatory negative controls in both orientations; unselected relationships are TABLE_PREDICTED_UNTESTED, never gameplay-certified. Do not try different representatives after inspecting results. Selected touching links can veto an edit even without attribution. Full mode retains exhaustive changed-link coverage.',
    'cancel_selection': 'Greedy coverage of still-unwitnessed cancel edits, then lowest required physical energy, ground source, attacking follow-up, shortest diagnostic command, shortest source lifetime, lexicographic source/follow-up. This usually selects one relationship per edited source; multiple distinct effects or incoming motionLevel edits may require more. Every changed edit retains at least one directly attributable representative, never another edit\'s success. Selection uses frozen tables only, not gameplay outcomes.',
    'cancel_shared_controls': 'Retain existing matching-context negative-control reuse for selected relationships only. Every selected relationship keeps its own primary probes. Candidate, source, orientation, physical scenario, timing, energy and input-phase layout must match. Record the representative and equivalence key.',
    'horizon': 'Per-fixture fixed 60-frame buckets, at least 240 frames, 148-frame setup anchor plus table-derived source/incoming observation lifetime and 60-frame margin. Cancel probes observe the follow-up transition, not the subsequent follow-up lifetime. Incomplete observations remain unresolved. Energy setup gets its own larger horizon and owned engine launch.',
    'deadline': 'Default 50 seconds including required baseline work; stop starting work near deadline and interrupt owned gameplay at the budget boundary. Cleanup/reporting can exceed the target. Unfinished checks cannot pass.',
    'tolerances': 'Unchanged engine-unit tolerances; exact magnitude remains informational.',
    'shared_onset_energy': 'Use existing hit/guard/posture probes for StartAddEnergy too, with no added games. The action-onset energy measurement must be present and temporally separate from any contact; coincident or unobserved onset/contact attribution remains unresolved.',
    'limits': 'Risk priorities follow mechanical context dependence, not an empirically established volatility ranking. Boundary, airborne, energy-heavy or large inputs can remain unresolved within budget.',
}


def relationship_id(link):
    return link['source']+'->'+link['followup']


def select_cancel_relationships(stock,candidate,cells,catalogue):
    """A deterministic witness set, independent of fixture success or outcomes.

    Cover edit identities, not the number of enabled follow-ups. An incoming
    motionLevel edit gets an attributable incoming witness; redundant edits
    cannot inherit one another's successful relationship. A direct source edit
    normally needs one link; add witnesses only to cover a remaining edit.
    """
    changed=[r for r in catalogue if r['claim'] not in {'predicted_ineligible','unchanged_eligible'}]
    keys={relationship_id(r):r for r in changed}
    contributors={key:set() for key in keys}
    for cell in cells:
        identity=(cell['move'],cell['property'])
        for link in attributed_relationships(stock,candidate,cell,changed):
            contributors[relationship_id(link)].add(identity)
    uncovered={(c['move'],c['property']) for c in cells}
    selected=[];selection=[]
    def rank(key):
        r=keys[key];a=candidate[r['source']];b=candidate[r['followup']]
        energy=max(0,-a['attack.StartAddEnergy'])+max(0,-b['attack.StartAddEnergy'])
        attack=bool(b.get('attack.Active',0)>0 and 0<b.get('attack.StartUp',0)<b['frameNumber'])
        return (-len(contributors[key]&uncovered),energy,a['state']=='AIR',not attack,
            command_frames(r['source'])+command_frames(r['followup']),a['frameNumber'],r['source'],r['followup'])
    while uncovered:
        available=[key for key in keys if key not in selected and contributors[key]&uncovered]
        if not available:break
        key=min(available,key=rank);new=contributors[key]&uncovered
        selected.append(key);selection.append({'relationship':key,
            'witnesses':[{'move':m,'property':p} for m,p in sorted(new)]})
        uncovered-=new
    omitted=[{'source':r['source'],'followup':r['followup'],'claim':r['claim'],
              'status':'TABLE_PREDICTED_UNTESTED','reason':'Not selected by prospective representative-cancel coverage.'}
             for r in changed if relationship_id(r) not in selected]
    return set(selected),{'mode':'representative','selection_rule':POLICY['cancel_selection'],
        'changed_relationships':len(changed),'selected_relationships':len(selected),
        'untested_relationships':len(omitted),'selected':selection,'unchecked':omitted,
        'edits_without_attributable_witness':[{'move':m,'property':p} for m,p in sorted(uncovered)],
        'claim':'Passing selected representatives does not certify untested follow-ups or source windows.'}


def selected_scenarios(planned, changes):
    risky = [c for c in changes if c['property'] not in SIMPLE]
    needed = set().union(*(roles_for(c['property']) for c in risky)) if risky else set()
    if not risky:
        wanted = set().union(*(roles_for(c['property']) for c in changes))
        needed = {next(r for r in ('hit', 'guard', 'whiff') if r in wanted)}
    return [s for s in planned if s['role'] in needed]


def gameplay_selected(cell, planned):
    roles={s['role'] for s in planned}
    if cell['property']=='attack.StartAddEnergy':
        return bool(roles & {'whiff','hit','guard','stand_guard','crouch_guard'})
    if roles & {'stand_guard','crouch_guard'}:roles.add('guard')
    return cell['property'] not in SIMPLE or bool(roles_for(cell['property']) & roles)


def shared_pairs(cell,pairs):
    """A type-posture probe can also measure guard effects if both contacts block."""
    result=list(pairs)
    if 'guard' in roles_for(cell['property']):
        for pair in pairs:
            if pair['scenario']['role'] in {'stand_guard','crouch_guard'} and all(
                pair[k].get('guarded') for k in ('stock_metrics','candidate_metrics')):
                result.append({**pair,'scenario':{**pair['scenario'],'role':'guard',
                    'shared_from_role':pair['scenario']['role']}})
    return result


def fixed_horizon(stock, candidate, zen, specs, energy=False):
    tail = 0
    for spec in specs:
        if bool(spec.get('energy_setup')) != energy:
            continue
        move = spec['move']
        for table in (stock, candidate):
            row = table[move]
            length = max(0, row['frameNumber'])
            span = length + max(0, row['attack.Active']) + max(0, row['attack.GiveGuardRecov'])
            # Cancel evidence ends at the early source->follow-up transition.
            # Measuring the follow-up's projectile lifetime is irrelevant and
            # previously stretched all 17-link control games to 480 frames.
            if spec.get('incoming_action'):
                r = zen[spec['incoming_action']]
                span = max(span, r['frameNumber'] + max(0, r['attack.Active']) + max(0, spec.get('incoming_delay', 0)))
            tail = max(tail, span + max(0, spec.get('jump_age', 0)) + max(0, spec.get('target_wait_frames', 0)))
    frames = max(240, 60 * math.ceil((148 + tail + 60) / 60))
    if energy:
        frames += max((s.get('energy_setup', {}).get('budget_frames', 0) for s in specs), default=2400)
    if frames > 9000:
        raise ValueError('required fast-screen horizon exceeds diagnostic ceiling')
    return frames


def finalise(report):
    """Never export full-validator VALID for selectively checked mechanics."""
    verdicts = [c['verdict'] for c in report['cells']]
    report['coverage'] = {
        'edited_cells': len(verdicts),
        'gameplay_checked': sum(c.get('check_level')=='gameplay' for c in report['cells']),
        'gameplay_passed': verdicts.count('VALID'),
        'table_only': verdicts.count('TABLE_CHECKED'),
        'unresolved': verdicts.count('UNDETERMINED'),
        'unchecked_edits': [{'move': c['move'], 'property': c['property'], 'reason': c['reason']}
                            for c in report['cells'] if c['verdict'] != 'VALID'],
    }
    sampling=report.get('evidence',{}).get('cancel_coverage')
    if sampling:report['coverage']['cancel_relationships']=sampling
    rejected=report.get('verdict')=='INVALID' or any(v in {'INVALID','NOT_APPLICABLE'} for v in verdicts)
    passed = not rejected and report['run_state'] == 'complete' and all(v in {'VALID', 'TABLE_CHECKED'} for v in verdicts)
    report['screen_passed'] = passed
    report['valid'] = False  # Intentionally never impersonate full validation.
    report['verdict'] = 'SCREEN_PASSED' if passed else ('SCREEN_REJECTED' if rejected else 'SCREEN_INCOMPLETE')
    report['reason'] = ('Static checks and selected gameplay checks passed; see coverage for unchecked effects.' if passed else
                        'Candidate failed or did not complete the selected checks; see per-edit reasons.')
    return report

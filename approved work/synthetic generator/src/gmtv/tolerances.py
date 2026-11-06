"""Fixed engine-unit rules, with repeatability checked during validator tests.

Do not fit thresholds to candidate results or silently enlarge them when a
verification fixture fails to reproduce. Investigate that fixture instead.
"""
UNITS={
    'command_to_onset':'frame','source_frames_observed':'frame','control_return':'frame',
    'attack_onset':'frame','active_frames_observed':'frame','contact_delay':'frame',
    'guard_duration':'frame','airborne_frames':'frame','projectile_frames_observed':'frame',
    'initial_velocity_x':'px/frame','initial_velocity_y':'px/frame','impact_velocity_x':'px/frame',
    'impact_velocity_y':'px/frame','projectile_velocity_x':'px/frame','projectile_velocity_y':'px/frame',
    'source_displacement_x':'px','source_displacement_y':'px','apex':'px',
    'hp_loss':'HP','onset_energy_delta':'energy','hit_energy_delta':'energy','received_energy_delta':'energy'}
EXACT={'guarded','down_seen','projectile_seen','hit_confirm_seen','landing_seen','contact_count'}


def tolerance(observable):
    if observable in UNITS:return 1
    if observable in EXACT:return 0
    raise KeyError('Observable needs an explicit measurement rule: '+observable)


def same(observable,a,b):
    limit=tolerance(observable)
    if a is None or b is None:return a is b
    return abs(a-b)<=limit if observable in UNITS else type(a) is type(b) and a==b


def directed_effect(observable,stock,edited,configured_direction):
    if observable not in UNITS:raise ValueError('categorical/relational effects need their own explicit rule')
    if stock is None or edited is None:return None
    delta=edited-stock
    return abs(delta)>tolerance(observable) and delta*configured_direction>0


def policy():
    return {'schema':'gmtv-fixed-unit-verification-policy-v1',
        'numeric':{k:{'unit':v,'tolerance':1} for k,v in UNITS.items()},
        'exact':sorted(EXACT),'thresholds_fit_from_candidate_outcomes':False,
        'repeatability':'small representative sample as part of validator verification; investigate inconsistent fixtures, not an automatic full census',
        'on_inconsistency':'record the discrepancy and investigate the affected fixture; never silently widen tolerances',
        'integration':'stock baselines and controls internal to validate(candidate_motion_csv, base_character); no standalone calibration pipeline',
        'authority':'user instructed stop exhaustive calibration and use the recommended fixed-unit rule plus small repeatability check'}

"""Engine-mechanics expectations, independent of prior outcome classifiers.

This is a development specification. Every property remains represented even
when its gameplay method is not yet developed. A missing method is not NA.
"""
from .schema import EDITABLE

RULES={
 'frameNumber':('commitment','whiff','control_return','increase','Character.update: remaining-frame expiry; ordinary controllable motions require separate interruption analysis'),
 'speedX':('movement','whiff','initial_velocity_x','increase','Character.runAction nonzero assignment, facing reversal, then friction; zero retains inertia'),
 'speedY':('movement','whiff','initial_velocity_y','increase','Character.runAction adds vertical velocity; gravity and floor/landing follow'),
 'attack.StartUp':('timing','whiff','attack_onset','increase','Character.startActive compares frameNumber-StartUp with remaining frame'),
 'attack.Active':('timing','whiff','active_frames_observed','increase','Attack.updateAttack/updateProjectileAttack expire currentFrame beyond Active; contact destroys an attack'),
 'attack.speedX':('projectile','projectile','projectile_velocity_x','increase','Attack.isProjectile and facing-aware speed; zero/nonzero may change attack role'),
 'attack.speedY':('projectile','projectile','projectile_velocity_y','increase','Attack.isProjectile and signed vertical projectile velocity'),
 'attack.HitDamage':('damage','hit','hp_loss','increase','Character.hitAttack clean-hit HP subtraction plus measured combo bonus'),
 'attack.GuardDamage':('guard_damage','guard','hp_loss','increase','Character.hitAttack guarded HP subtraction plus measured combo bonus'),
 'attack.StartAddEnergy':('start_energy','whiff','onset_energy_delta','increase','Character.runAction applies once when the action changes; ableAction checks affordability'),
 'attack.HitAddEnergy':('hit_energy','hit','hit_energy_delta','increase','Character.hitAttack credits attacker on an unguarded hit'),
 'attack.GuardAddEnergy':('guard_energy','guard','hit_energy_delta','increase','Character.hitAttack credits attacker only in the guarded branch'),
 'attack.GiveEnergy':('transfer_energy','hit_guard','received_energy_delta','increase','Character.hitAttack credits recipient on hit or guard'),
 'attack.GiveGuardRecov':('guard_stun','guard','guard_duration','increase','Character.hitAttack replaces defender remainingFrame after entering guard recovery'),
 'attack.ImpactX':('impact','hit_guard','impact_velocity_x','increase','Character.hitAttack sets signed horizontal speed; integer division on guard; wall push may move attacker'),
 'attack.ImpactY':('impact','hit','impact_velocity_y','increase','Character.hitAttack sets vertical speed outside throw/guard; gravity and floor can clamp realised motion'),
 'attack.AttackType':('category','all_guards','guard_requirement','categorical','Character.isGuard posture mapping; type4 takes the throw branch'),
 'attack.DownProp':('knockdown','hit','down_seen','categorical','Character.hitAttack chooses CHANGE_DOWN instead of state-specific recovery outside throw'),
 'cancelAbleFrame':('cancel','cancel','derived_relationships','relational','Fighting.ableAction requires hitConfirm and elapsed>=window, sufficient level and energy'),
 'cancelAbleMotionLevel':('cancel','cancel','derived_relationships','relational','Fighting.ableAction source permission>=followup.motionLevel'),
 'motionLevel':('cancel','cancel','derived_relationships','relational','Fighting.ableAction uses this move as the followup in incoming relationships'),
}
for p in ('hitAreaLeft','hitAreaRight','hitAreaUp','hitAreaDown'):
    RULES[p]=('body_geometry','incoming_boundary','contact_envelope','edge',
        'Character.getHitArea*: body-relative defensive bounds; Fighting.detectionHit inclusive overlap and detectionPush body collision; floor handling uses body bottom')
for p in ('attack.hitAreaLeft','attack.hitAreaRight','attack.hitAreaUp','attack.hitAreaDown'):
    RULES[p]=('offensive_geometry','outgoing_boundary','contact_envelope','edge',
        'Attack.initialize mirrors horizontal bounds by facing; Fighting.detectionHit tests inclusive overlap against defender body')
assert set(RULES)==set(EDITABLE)

# Explicit causal dependencies are recorded, not silently called independent.
# Candidate assessment must still test intended effects and all observables that
# remain independent for the actual scenario and complete candidate's edits.
DOWNSTREAM={
 'commitment':['source_frames_observed','source_displacement_x','source_displacement_y','active_frames_observed','landing_seen'],
 'movement':['source_displacement_x','source_displacement_y','contact_delay','contact_count','airborne_frames','apex','landing_seen'],
 'timing':['contact_delay','contact_count','source_displacement_x','source_displacement_y'],
 'projectile':['contact_delay','contact_count','projectile_frames_observed','active_frames_observed','projectile_seen','hit_confirm_seen'],
 'damage':[], 'guard_damage':[], 'start_energy':[], 'hit_energy':[], 'guard_energy':[], 'transfer_energy':[],
 'guard_stun':['contact_count'],
 'impact':['guard_duration','airborne_frames','apex','landing_seen'],
 'knockdown':['impact_velocity_x','impact_velocity_y','airborne_frames','guard_duration','apex','landing_seen'],
 'category':['guarded','hp_loss','hit_energy_delta','received_energy_delta','impact_velocity_x','impact_velocity_y','down_seen','guard_duration'],
 'cancel':['control_return','source_frames_observed','contact_count'],
 'body_geometry':['initial_velocity_y','contact_delay','contact_count','source_displacement_x','source_displacement_y','airborne_frames','apex','landing_seen'],
 'offensive_geometry':['contact_delay','contact_count'],
}


def describe():
    return [{'property':p,'family':RULES[p][0],'scenario':RULES[p][1],'observable':RULES[p][2],
        'direction':RULES[p][3],'engine_basis':RULES[p][4],
        'causally_downstream_observables':DOWNSTREAM[RULES[p][0]],
        'status':'DEVELOPMENT; not a certified applicability or final classifier table'} for p in EDITABLE]

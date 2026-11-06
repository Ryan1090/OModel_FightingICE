"""Cross-repair reuse needs exact executed/setup rows and global permissions."""
from gmtv.schema import digest
from gmtv.rules import INPUT_ACTIONS

# These fields influence physical execution only once their row is entered.
# Permission/cost/state/control and all unknown fields remain global. There is
# no reuse if an edit could enable a previously unexecuted input interpretation.
PHYSICAL={'frameNumber','speedX','speedY','hitAreaLeft','hitAreaRight','hitAreaUp','hitAreaDown',
 'attack.StartUp','attack.Active','attack.HitDamage','attack.GuardDamage','attack.HitAddEnergy',
 'attack.GuardAddEnergy','attack.GiveEnergy','attack.ImpactX','attack.ImpactY','attack.GiveGuardRecov',
 'attack.AttackType','attack.DownProp','attack.hitAreaLeft','attack.hitAreaRight','attack.hitAreaUp',
 'attack.hitAreaDown','attack.speedX','attack.speedY'}

def projection(table,record):
    spec=record['spec'];observed={x['me']['action'] for x in record['observation']['trace']}
    required=observed|{spec['move'],spec.get('followup'),spec.get('incoming_action'),'JUMP','STAND','AIR','CROUCH','FORWARD_WALK','BACK_STEP','DASH'}
    # All potentially linked cancel endpoints retain complete rows. An edit of
    # any motionLevel/cancel permission/cost also invalidates globally below.
    source=spec['move']
    for n,r in table.items():
        if table[source]['cancelAbleMotionLevel']>=r['motionLevel']:required.add(n)
        if r['cancelAbleMotionLevel']>=table[source]['motionLevel']:required.add(n)
    payload={n:{p:v for p,v in row.items() if n in required or n not in INPUT_ACTIONS or p not in PHYSICAL} for n,row in table.items()}
    return digest(payload),sorted(n for n in required if n in table)

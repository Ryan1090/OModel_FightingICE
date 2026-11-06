"""Serialize the already-approved engine's whole-table observation digest."""
import hashlib
from .schema import read


def runtime_digest(path,root):
    rows=read(path,root);h=hashlib.sha256()
    for r in rows.values():
        area=lambda pre:':'.join(str(r[pre+s]) for s in ('Left','Right','Up','Down'))
        v=[r['motionName'],str(r['frameNumber']),str(r['speedX']),str(r['speedY']),area('hitArea'),r['state'],area('attack.hitArea')]
        v += [str(r['attack.'+x]) for x in ('speedX','speedY','StartUp','Active','HitDamage','GuardDamage','StartAddEnergy',
            'HitAddEnergy','GuardAddEnergy','GiveEnergy','ImpactX','ImpactY','GiveGuardRecov','AttackType')]
        v += [str(r['attack.DownProp']).lower(),str(r['cancelAbleFrame']),str(r['cancelAbleMotionLevel']),str(r['motionLevel']),
            str(r['control']).lower(),str(r['landingFlag']).lower()]
        h.update((','.join(v)+'\n').encode())
    return h.hexdigest()


def verify(log,identity,side,expected,zen_expected):
    records=[]
    for line in log.splitlines():
        if 'NAME_MASK_AUDIT|' in line:
            records.append(dict(x.split('=',1) for x in line.split('NAME_MASK_AUDIT|',1)[1].split('|') if '=' in x))
    op='p2' if side=='P1' else 'p1';side=side.lower()
    return bool(records) and all(r.get('actual_'+side)==identity and r.get('actual_motion_'+side)==expected
        and r.get('actual_'+op)=='ZEN' and r.get('actual_motion_'+op)==zen_expected for r in records)

"""The engine's 34-column table, canonical aliases and exact input diff."""
import csv
import hashlib
import json
from pathlib import Path

ROOTS=('ZEN','GARNET','LUD','KFM','NEZ')
FIELDS=('motionName','frameNumber','speedX','speedY','hitAreaLeft','hitAreaRight','hitAreaUp','hitAreaDown','state',
    'attack.hitAreaLeft','attack.hitAreaRight','attack.hitAreaUp','attack.hitAreaDown','attack.speedX','attack.speedY',
    'attack.StartUp','attack.Active','attack.HitDamage','attack.GuardDamage','attack.StartAddEnergy','attack.HitAddEnergy',
    'attack.GuardAddEnergy','attack.GiveEnergy','attack.ImpactX','attack.ImpactY','attack.GiveGuardRecov','attack.AttackType',
    'attack.DownProp','cancelAbleFrame','cancelAbleMotionLevel','motionLevel','control','landingFlag','Image')
STRUCTURAL={'motionName','Image','state','control','landingFlag'}
EDITABLE=tuple(x for x in FIELDS if x not in STRUCTURAL)
BOOL={'control','landingFlag','attack.DownProp'}
assert len(EDITABLE)==29


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def normal(field,value):
    text=str(value).strip()
    if field in BOOL:
        if text.upper() not in {'TRUE','FALSE'}:raise ValueError('invalid boolean: '+field)
        return text.upper()=='TRUE'
    if field in STRUCTURAL:return text
    try:
        number=int(text)
    except ValueError:raise ValueError('integer required: '+field+'='+text)
    if not -(2**31)<=number<2**31:raise ValueError('outside engine signed-int range: '+field)
    return number


def read(path,root):
    with Path(path).open(encoding='utf-8-sig',newline='') as stream:
        reader=csv.DictReader(stream);header=reader.fieldnames;rows=list(reader)
    aliases={'attack.HitDamege':'attack.HitDamage'} if root=='GARNET' else {}
    canonical=[aliases.get(x,x) for x in header or []]
    if canonical!=list(FIELDS):raise ValueError('Motion columns must match engine order, with only the verified GARNET alias allowed')
    result={}
    for row in rows:
        if None in row or any(v is None for v in row.values()):raise ValueError('wrong number of Motion cells')
        value={aliases.get(k,k):normal(aliases.get(k,k),v) for k,v in row.items()}
        action=value['motionName']
        if action in result:raise ValueError('duplicate action '+action)
        result[action]=value
    return result


def invariants(row):
    errors=[]
    if row['frameNumber']<1:errors.append('frameNumber must be positive')
    for prefix in ('','attack.'):
        if row[prefix+'hitAreaLeft']>row[prefix+'hitAreaRight'] or row[prefix+'hitAreaUp']>row[prefix+'hitAreaDown']:errors.append(prefix+'hitbox inverted')
    for field in ('attack.StartUp','attack.Active','attack.HitDamage','attack.GuardDamage','attack.GiveGuardRecov'):
        if row[field]<0:errors.append('negative '+field)
    # -1 cancel values are present in stock; these are signed permission
    # comparisons in ableAction, not unsigned durations.
    if row['attack.AttackType'] not in (0,1,2,3,4):errors.append('attack type outside engine categories')
    # Active duration can outlive the source on a detached projectile. Do not
    # invent a universal startup+active<=duration invariant from prior recipes.
    return errors


def diff(stock,candidate):
    if list(stock)!=list(candidate):raise ValueError('action set/order differs from stock')
    changes=[]
    for action,before in stock.items():
        after=candidate[action]
        for prop in FIELDS:
            if before[prop]!=after[prop]:changes.append({'move':action,'property':prop,'stock':before[prop],'value':after[prop],
                'structural':prop in STRUCTURAL})
    return changes


def write_variant(stock_path,output,root,edits):
    with Path(stock_path).open(encoding='utf-8-sig',newline='') as stream:
        reader=csv.DictReader(stream);header=reader.fieldnames;rows=list(reader)
    for row in rows:
        for prop,value in edits.get(row['motionName'],{}).items():
            actual='attack.HitDamege' if root=='GARNET' and prop=='attack.HitDamage' else prop
            row[actual]=str(value).upper() if isinstance(value,bool) else str(value)
    with Path(output).open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=header,lineterminator='\n');writer.writeheader();writer.writerows(rows)

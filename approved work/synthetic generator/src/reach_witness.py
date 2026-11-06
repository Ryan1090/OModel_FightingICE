"""Versioned, bounded movement-aware fallback; actual contact remains mandatory."""
import math
from pathlib import Path
from gmtv.schema import sha

POLICY={
 'version':'reach-v41-movement-envelope-midpoint-r2',
 'scope':'Existing horizontal representative, non-projectile source with existing horizontal movement, only after original midpoint is unresolved.',
 'plan':'One paired no-contact travel measurement and one predeclared envelope-midpoint contact witness per orientation. No boundary search or alternative representative.',
 'acceptance':'Actual correctly directed separating contact in BOTH orientations; absent, contaminated or contradictory evidence stays unresolved.',
 'limits':'Unchanged per-probe limits/retry, screen request ceiling, repair stages and profile/far criteria.'}

def envelope(record,table,stock,zen,width,zen_width,metadata):
 metrics=metadata(record,table)
 if record.get('infrastructure_failure') or metrics.get('method_gaps') or not metrics.get('issued'):
  raise ValueError('Travel measurement lacks complete source evidence')
 if metrics.get('contact_count'):
  raise ValueError('Contact contaminated travel measurement')
 obs=record['observation'];trace=obs['trace'];issue=obs.get('issue_frame')
 before=[x for x in trace if issue is not None and x['frame']<=issue]
 if not before:raise ValueError('No pre-command anchor')
 sample=before[-1];me=sample['me'];op=sample['op'];direction=1 if record['spec']['orientation']=='P1' else -1
 if bool(me['front'])!=(direction==1):raise ValueError('Source facing contradicts planned orientation')
 row=table[me['action']];raw=me['left']-(row['hitAreaLeft'] if me['front'] else width-row['hitAreaRight'])
 centre=(stock['STAND']['hitAreaLeft']+stock['STAND']['hitAreaRight'])/2
 anchor=raw+(centre if direction==1 else width-centre)
 oprow=zen[op['action']];opraw=op['left']-(oprow['hitAreaLeft'] if op['front'] else zen_width-oprow['hitAreaRight'])
 opcentre=(zen['STAND']['hitAreaLeft']+zen['STAND']['hitAreaRight'])/2
 opanchor=opraw+(opcentre if op['front'] else zen_width-opcentre)
 extents=[]
 for x in trace:
  if x['frame']<=issue or x['me']['action']!=record['spec']['move']:continue
  a=x['me']['attack']
  # Match the approved metadata extractor: source attack observations are
  # non-empty attack_data. The protocol's is_live field is false even on the
  # recorded non-empty stock whiff attacks and cannot be an activity gate.
  if a.get('empty_flag',True):continue
  if bool(x['me']['front'])!=(direction==1):raise ValueError('Source facing changed during travel measurement')
  box=a['current_hit_area'];target=x['op']
  if box['bottom']<target['top'] or box['top']>target['bottom']:continue
  edge=box['right'] if direction==1 else box['left']
  near=target['left'] if direction==1 else target['right']
  extents.append(direction*(edge-anchor)-direction*(near-opanchor))
 if not extents:raise ValueError('No non-empty vertically applicable source hitbox in travel measurement')
 return {'effective_front_distance':max(extents),'attack_samples':len(extents),'fixture_id':record.get('fixture_id')}

async def geometry(ex,inputs,group,changes,*,original,metadata,is_projectile):
 legacy=await original(ex,inputs,group,changes)
 cell=group['cell'];move=cell['move'];p=cell['property']
 stock=inputs[ex.root]['table'];full=ex.tables['candidate'];zen=inputs['ZEN']['table']
 if p!='attack.hitAreaRight' or legacy.get('status')!='UNRESOLVED':return legacy
 if is_projectile(stock[move]) or is_projectile(full[move]) or not (stock[move]['speedX'] or full[move]['speedX']):return legacy
 from gmtv.construct import scenarios
 from gmtv.kinematics import jump_profile
 from gmtv.probe import placement
 width=inputs[ex.root]['width'];zw=inputs['ZEN']['width']
 templates=[x for x in scenarios(stock,zen,move,width,zw,jump_profile(stock),jump_profile(zen)) if x['role']=='hit']
 if {s['orientation'] for s in templates}!={'P1','P2'}:return {**legacy,'movement_witness':{'policy':POLICY,'reason':'Both planned orientations unavailable'}}
 plans=[];evidence=[];problems=[]
 for template in templates:
  side=template['orientation']
  far={**template,**placement(stock,zen,move,width,side,760,zw),'role':'reach_travel_measure'}
  a=await ex.execute(far,'stock');b=await ex.execute(far,'candidate')
  try:
   am=envelope(a,stock,stock,zen,width,zw,metadata);bm=envelope(b,full,stock,zen,width,zw,metadata)
   old=am['effective_front_distance'];new=bm['effective_front_distance']
   correct=new>old if cell['value']>cell['stock'] else old>new
   distance=(old+new)/2
   if not correct or not math.isfinite(distance) or distance<=0 or distance>760:
    raise ValueError('Observed travel envelopes do not supply a correctly directed in-stage separation')
   plans.append({'orientation':side,'stock':am,'candidate':bm,'distance':distance})
  except (ValueError,KeyError,TypeError) as error:
   problems.append({'orientation':side,'reason':str(error)})
   continue
  spec={**template,**placement(stock,zen,move,width,side,distance,zw),'role':'reach_travel_boundary'}
  a=await ex.execute(spec,'stock');b=await ex.execute(spec,'candidate');am=metadata(a,stock);bm=metadata(b,full)
  usable=not(a.get('infrastructure_failure') or b.get('infrastructure_failure') or am.get('method_gaps') or bm.get('method_gaps')) and am.get('issued') and bm.get('issued')
  ca=bool(am.get('contact_count'));cb=bool(bm.get('contact_count'))
  expected=(not ca and cb) if cell['value']>cell['stock'] else (ca and not cb)
  evidence.append({'orientation':side,'stock_contact':ca,'candidate_contact':cb,'passed':bool(usable and expected),'stock_fixture':a.get('fixture_id'),'candidate_fixture':b.get('fixture_id'),'scenario':spec})
 passed={e['orientation'] for e in evidence if e['passed']}=={'P1','P2'}
 return {**group,'status':'PASSED' if passed else 'UNRESOLVED',
  'reason':'Movement-aware separating reach contact in both orientations' if passed else 'Movement-aware reach witness did not establish separating contact in both orientations',
  'evidence':evidence,'legacy_midpoint':legacy,'movement_witness':{'policy':POLICY,'plans':plans,'problems':problems,'source_sha256':sha(__file__)},
  'effect_claim':'coedit_present_reach_contact_change'}

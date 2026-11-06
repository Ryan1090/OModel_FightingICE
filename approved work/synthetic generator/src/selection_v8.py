"""Prospective critical-family selection, independent of candidate outcomes."""
FAMILIES={
 'timing':('attack.StartUp','frameNumber','attack.Active'),
 'damage':('attack.HitDamage',),
 'reach':('attack.hitAreaRight','attack.hitAreaUp'),
 'movement_jumps':('speedX','speedY','attack.ImpactX','attack.ImpactY'),
 'knockdown_type':('attack.DownProp','attack.AttackType'),
 'guard':('attack.GuardDamage','attack.GiveGuardRecov'),
 'cancel':('cancelAbleFrame','cancelAbleMotionLevel'),
 'projectile':('attack.speedX','attack.speedY')}

def kind(p):
    if p in FAMILIES['cancel']:return 'cancel'
    if p in FAMILIES['knockdown_type']:return 'category'
    if p in FAMILIES['reach']:return 'geometry_health'
    if p in FAMILIES['movement_jumps']+FAMILIES['projectile']:return 'motion'
    if p in ('frameNumber','attack.StartUp','attack.Active','attack.GiveGuardRecov'):return 'timing'
    return 'simple_health'

def select_for_families(stock,full,changes,catalogue,context):
    from gmtv.construct import command_frames
    from gmtv.rules import attributed_relationships
    usage=context.get('usage',{})
    def rank(cell):
        n,p=cell['move'],cell['property'];r=full[n]
        return (-usage.get(n,0),max(0,-r['attack.StartAddEnergy']),r['state']=='AIR',command_frames(n),n,p)
    groups=[]
    for name,properties in FAMILIES.items():
        checks=[]
        for p in properties:
            cells=sorted((x for x in changes if x['property']==p),key=rank)
            if not cells:continue
            cell=cells[0];member={'kind':kind(p),'cell':cell,'effect_required':True,'critical_family':name}
            if name=='cancel':
                links=[r for r in catalogue if r['claim'] not in ('predicted_ineligible','unchanged_eligible')]
                own=attributed_relationships(stock,full,cell,links)
                if own:member['link']=min(own,key=lambda r:(-usage.get(r['source'],0),-usage.get(r['followup'],0),command_frames(r['followup']),r['source'],r['followup']))
                else:member.update(kind='missing',reason='Selected source cancel edit has no attributable relationship')
            checks.append(member)
        if checks:groups.append({'kind':'family','family':name,'checks':checks})
    return groups

def coverage(changes,groups,context):
    critical={name for name,props in FAMILIES.items() if any(x['property'] in props for x in changes)}
    paper_map={'body_edges':('hitAreaLeft','hitAreaRight','hitAreaUp','hitAreaDown'),
               'rear_downward_reach':('attack.hitAreaLeft','attack.hitAreaDown'),
               'energy':('attack.StartAddEnergy','attack.HitAddEnergy','attack.GuardAddEnergy','attack.GiveEnergy'),
               'motion_levels':('motionLevel',)}
    paper={name for name,props in paper_map.items() if any(x['property'] in props for x in changes)}
    edited=critical|paper
    verified={g['family'] for g in groups if g.get('status')=='PASSED'}
    members=[x for g in groups for x in g.get('results',[])]
    checked=[x['cell'] for x in members if x.get('status')=='PASSED' and 'cell' in x]
    return {'edited_families':sorted(edited),'verified_families':sorted(verified),
            'edited_family_count':len(edited),'verified_family_count':len(verified),
            'fraction':len(verified&edited)/len(edited) if edited else 0,
            'edited_critical_families':sorted(critical),'paper_checked_families':sorted(paper),
            'critical_fraction':len(verified&critical)/len(critical) if critical else 0,
            'checked_cells':checked,'representative_scope':True,'individual_causal_attribution':False,
            'unverified_families':sorted(edited-verified)}

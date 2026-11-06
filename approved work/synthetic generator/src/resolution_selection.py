"""Resolution-aware representatives; construction and assessment stay frozen."""
from gmtv.expectations import RULES
from gmtv.tolerances import UNITS,tolerance
from selection_v8 import FAMILIES,kind,coverage as original_coverage

def key(move,prop):return move+'|'+prop

def play_eligible(cell):
    observable=RULES[cell['property']][2]
    if observable in UNITS:return abs(cell['value']-cell['stock'])>tolerance(observable)
    # Edge changes need exact separating contact; codes/links use predicates.
    # There is no positive numeric pixel/code tolerance for those methods.
    return cell['value']!=cell['stock']

def select_resolution(stock,full,changes,catalogue,context):
    from gmtv.construct import command_frames
    from gmtv.rules import attributed_relationships
    usage=context.get('usage',{});roles=context.get('selection_roles',{})
    def rank(cell):
        n,p=cell['move'],cell['property'];r=full[n]
        preferred=roles.get(key(n,p)) in ('primary','secondary')
        return (not preferred,-usage.get(n,0),max(0,-r['attack.StartAddEnergy']),r['state']=='AIR',command_frames(n),n,p)
    groups=[]
    for name,properties in FAMILIES.items():
        checks=[]
        for p in properties:
            cells=sorted((x for x in changes if x['property']==p and play_eligible(x)),key=rank)
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

def resolution_summary(changes,groups):
    skipped=[{**c,'status':'TABLE_CHECKED','gameplay_effect_verified':False,'observable':RULES[c['property']][2],
       'tolerance':tolerance(RULES[c['property']][2]),'reason':'Configured numeric magnitude does not exceed observable tolerance'}
       for c in changes if any(c['property'] in pp for pp in FAMILIES.values()) and not play_eligible(c)]
    edited={name for name,props in FAMILIES.items() if any(c['property'] in props for c in changes)}
    required={g['family'] for g in groups}
    return {'policy':'One representative per edited critical member property with an above-tolerance numeric edit; primary/secondary main driver first, then unchanged usage/mechanical ordering. Non-numeric contact/category/link checks retained.',
      'table_checked_cells_at_or_below_tolerance':skipped,'table_checked_resolution_families':sorted(edited-required),
      'required_gameplay_families':sorted(required),'all_edited_critical_families':sorted(edited),
      'thresholds_and_assessments_unchanged':True}

def coverage_resolution(changes,groups,context):
    result=original_coverage(changes,groups,context)
    required={name for name,props in FAMILIES.items() if any(c['property'] in props and play_eligible(c) for c in changes)}
    verified={g['family'] for g in groups if g.get('status')=='PASSED'}
    result.update(required_gameplay_families=sorted(required),required_gameplay_fraction=len(required&verified)/len(required) if required else 0,
        table_checked_resolution_families=sorted(set(result['edited_critical_families'])-required))
    return result

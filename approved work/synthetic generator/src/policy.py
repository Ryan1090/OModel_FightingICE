"""Aggregate-only production checks and final frozen-design verification."""
import collections,csv,math,json,datetime
from pathlib import Path
import numpy as np
import common as c
from gmtv.schema import sha,digest
from gmtv.storage import atomic
RELATIONAL={'attack.DownProp','attack.AttackType','cancelAbleFrame','cancelAbleMotionLevel','motionLevel'}

def distance(n,a,b):return float(np.linalg.norm(c.original.model.features(n,np.asarray([a,b]))[0]-c.original.model.features(n,np.asarray([a,b]))[1]))

def distance_reasons(config,row,accepted):
    n=c.original.models()[0][row['root']];reasons=[]
    for prior in accepted:
        if prior['root']!=row['root']:continue
        d=distance(n,row['final_vector'],prior['final_vector'])
        floor=config['floors']['within'] if prior['pool']==row['pool'] else config['floors']['far_AB' if row['pool']=='C_far' else 'iid_near_AB'] if row['pool'].startswith('C_') and prior['pool'] in ('A','B') else 0.
        if d<1e-12:reasons.append('duplicate across pools')
        elif d+1e-12<floor:reasons.append('within-pool distance' if prior['pool']==row['pool'] else 'held-out A/B distance')
    return sorted(set(reasons))

def public_summary(accepted,completed,state,elapsed,workers):
    pools={};counts={};causes=collections.Counter();properties=collections.Counter();roles=collections.Counter()
    from selection_override import role_map
    for pool in c.POOLS:
        a=[r for r in accepted if r['pool']==pool];done=[r for r in completed if r['pool']==pool]
        strata={}
        for root in state['roots']:
            for slot in c.strata(pool):
                k=root+'/'+','.join(map(str,slot));strata[k]=sum(r['root']==root and tuple(r['stratum'])==slot for r in a)
        pools[pool]={'accepted':len(a),'completed':len(done),'target':5*c.QUOTAS[pool],'acceptance':len(a)/len(done) if done else None,
          'seconds':c.summary_numbers([r['seconds'] for r in done]),'accepted_by_root':dict(collections.Counter(r['root'] for r in a)),
          'accepted_by_stratum':strata,'stratum_target':c.stratum_target(pool),
          'retained_coverage':c.summary_numbers([r['profile']['coverage'] for r in a]),
          'retained_edit_cells':c.summary_numbers([r['retained_edit_count'] for r in a]),
          'primary_retention':c.summary_numbers([r['profile']['primary_retention'] for r in a])}
    for r in completed:
        rm=role_map(r['root'],r['meta']['primary'],r['meta']['secondary'])
        for event in r['reverts']:
            causes[event.get('kind',event.get('cause','unspecified'))]+=1;properties[event['property']]+=1;roles[rm[event['move']+'|'+event['property']]]+=1
    for pool in c.POOLS:
        counts=collections.Counter((r['root'],*r['stratum']) for r in completed if r['pool']==pool)
        pools[pool]['completed_by_stratum']={root+'/'+','.join(map(str,slot)):counts[(root,*slot)] for root in state['roots'] for slot in c.strata(pool)}
        pools[pool]['acceptance_by_stratum']={key:(n/pools[pool]['completed_by_stratum'][key] if pools[pool]['completed_by_stratum'][key] else None) for key,n in pools[pool]['accepted_by_stratum'].items()}
    signature=digest({'configuration':state['configuration_sha256'],'io':sha(c.RELEASE),'workers':workers})
    forecast=c.local_module('forecast_window_v31').calculate(state,elapsed,len(accepted),len(completed),workers,signature)
    projected=forecast['projected_total_seconds'];remaining=forecast['projected_remaining_seconds']
    finish=(datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))+datetime.timedelta(seconds=remaining)).isoformat() if remaining is not None else None
    return {'accepted':len(accepted),'completed':len(completed),'target':c.TOTAL,'pools':pools,'accepted_per_pool':{p:r['accepted'] for p,r in pools.items()},'workers':workers,
      'evidence_storage':c.local_module('evidence_retention').policy(c.load_config()),
      'projection_limit_seconds':c.load_config()['stops']['projection_limit_seconds'],'forecast_basis':forecast['forecast_basis'],'forecast_qualified':forecast['forecast_qualified'],'forecast_unbounded':forecast['forecast_unbounded'],'stop_reason':state.get('stop_reason'),'elapsed_seconds':elapsed,'projected_total_seconds':projected,'projected_remaining_seconds':remaining,'projected_completion_Perth':finish,
      'current_pool':next((p for p in c.POOLS if len([r for r in accepted if r['pool']==p])<5*c.QUOTAS[p]),'complete'),
      'reverts_by_cause':dict(causes),'reverts_by_property':dict(properties),'reverts_by_role':dict(roles),
      'construction_rejections':state['construction_rejections'],'infrastructure_faults':dict(collections.Counter(r['kind'] for r in state.get('infrastructure_faults',[]))),
      'acceptance_denominator':'Completed screening/profile/distance decisions only; infrastructure interruptions excluded',
      'split_frozen':False,'C_records':'aggregates only; runner-private archive build, sealed once at finalisation'}

def stop_reason(summary,config):
    return c.local_module('forecast_window_v31').stop(summary,config)


def checkpoint_ready(name,accepted,roots):
    if name=='first_50_A':return all(sum(r['pool']=='A' and r['root']==root for r in accepted)>=min(10,c.QUOTAS['A']) for root in roots)
    return all(sum(r['pool']=='C_far' and r['root']==root for r in accepted)>=min(2,c.QUOTAS['C_far']) for root in roots)

def write_checkpoints(state,accepted,completed,config,elapsed,workers,writer=None):
    writer=writer or (lambda name,data:atomic(c.HOT/'checkpoints'/f'{name}.json',data));made=[]
    for name in ('first_50_A','first_10_far'):
        if name in state['checkpoints'] or not checkpoint_ready(name,accepted,state['roots']):continue
        s=public_summary(accepted,completed,state,elapsed,workers);s['configuration_sha256']=config['configuration_sha256'];s['stop_reason']=state.get('stop_reason') or stop_reason(s,config)
        if name=='first_10_far':
            far=[r for r in accepted if r['pool']=='C_far'];s['far_checks']={'tested':len(far),'core_support_readout_passed':sum(r['profile']['far_qualified'] is True for r in far),
              'nearest_final_AB':{root:c.summary_numbers([min(r['profile']['reference_distances'].values()) for r in far if r['root']==root]) for root in state['roots']},
              'trimmed_cells':sum(r.get('construction_trim_count',0) for r in far),
              'stratum_supply':state.get('far_supply',{}),'forecast':'Construction-only prepared supply is provisional; untested strata are not certified gameplay-fillable.'}
            s['far_checks'].update(far_context_metrics(far,accepted,state['roots']))
        writer(name,s);state['checkpoints'][name]=True;made.append(name)
    return made

def far_context_metrics(far,accepted,roots):
    result={}
    for root in roots:
        n=c.original.models()[0][root];A=np.asarray([r['final_vector'] for r in accepted if r['root']==root and r['pool']=='A']);rows=[r for r in far if r['root']==root]
        margins=[];extras=[]
        for r in rows:
            trait=r['meta']['primary'];score=c.original.design_context.c.core_score(n,A,trait)
            margins.append(float(r['profile']['primary_core_score']-np.max(score)))
            cols=[j for j,(_,p) in enumerate(n['cells']) if p in c.original.design_context.c.CORE[c.original.model.TRAITS[trait]] and n['L'][j,trait]!=0]
            d=np.asarray(r['final_vector'])-n['stock'];ad=A-n['stock'];excess=[]
            for j in cols:
                if d[j]:excess.append(float(abs(d[j])-np.max(np.sign(d[j])*ad[:,j])))
            extras.append(max(excess) if excess else 0.)
        result[root]={'core_score_margin_above_every_A':c.summary_numbers(margins),'extra_integer_core_margin':c.summary_numbers(extras),
          'nearest_A':c.summary_numbers([r['profile']['reference_distances']['A'] for r in rows]),'nearest_B':c.summary_numbers([r['profile']['reference_distances']['B'] for r in rows])}
    return {'final_A_B_context_by_root':result}

def diversity(root,Y):
    from bank_v20 import diversity as coverage
    n,g=(v[root] for v in c.original.models());Y=np.asarray(Y)
    fractions,changed,props,_=coverage(g,Y);freq=[]
    for i,p in enumerate(props):
        rate=float(changed[:,i].mean());freq.append({'property':p,'changed':int(changed[:,i].sum()),'n':len(Y),'fraction':rate,'numeric_gate':p not in RELATIONAL})
    numeric=[r for r in freq if r['numeric_gate']]
    main=list(csv.DictReader((c.BASE/'assets/ALL_MAIN_EFFECT_CELLS.csv').open(encoding='utf-8')))
    exemptions=list(csv.DictReader((c.BASE/'assets/FINAL_EXEMPTIONS_AND_MISSES_COMPLETE.csv').open(encoding='utf-8')))
    exempt={(r['move'],r['property']):r['all_exemption_causes'] for r in exemptions if r['root']==root and r['final_gate_exempt']=='True'}
    total=passes=0;misses=[];all_exempt=[]
    for row in main:
        if row['root']!=root:continue
        key=row['move'],row['property']
        if key in exempt:all_exempt.append({'move':key[0],'property':key[1],'cause':exempt[key]});continue
        j=g['pos'][key];values=np.unique(Y[:,j]);needed=int(float(row['required_distinct_capped']))
        okay=bool(len(values)>=needed and values[0]<=float(row['required_min']) and values[-1]>=float(row['required_max']))
        total+=1;passes+=okay
        if not okay:misses.append({'move':key[0],'property':key[1],'min':float(values[0]),'max':float(values[-1]),'distinct':len(values),
          'required_min':float(row['required_min']),'required_max':float(row['required_max']),'required_distinct':needed})
    return {'root':root,'n':len(Y),'coverage_min':float(fractions.min()),'coverage_passed':bool(np.all(fractions>=.8)),
      'numeric_frequency_passed':all(r['fraction']>=.4 for r in numeric) and sum(r['fraction']>=.5 for r in numeric)>=math.ceil(.9*len(numeric)),
      'property_frequencies':freq,'property_half_target_misses':[r for r in freq if r['fraction']<.5],
      'main_spread':{'passed':passes>=math.ceil(.9*total),'passes':passes,'gated':total,'fraction':passes/total,'misses':misses,'exemptions':all_exempt}}

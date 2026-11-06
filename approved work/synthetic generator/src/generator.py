"""Unified configurable generator; default arithmetic is the frozen model."""
import hashlib,json,types,functools
from pathlib import Path
import numpy as np
import model
import readout
from diversity import diversity
from settings import current,ranges
from gmtv.schema import sha,digest,write_variant,read
from gmtv.storage import atomic
DIAGNOSTIC='diagnostic-only';PRODUCTION='configured-by-run'
@functools.lru_cache(maxsize=1)
def models():return model.models()[:2]
def load_config():return current()
def rng(namespace,root,candidate,round=0):
    return np.random.default_rng(int.from_bytes(hashlib.sha256(f'{namespace}|{root}|{candidate}|{round}'.encode()).digest()[:8],'little'))

def sample(root,primary,secondary,sign,secondary_sign,pool,candidate,namespace):
    if namespace!=current()['production_namespace']:raise ValueError('Unknown generator namespace')
    if primary==secondary or pool not in ('A','B','C_iid','C_near','C_far'):raise ValueError('Invalid role/pool')
    near=tuple(sorted((primary,secondary))) in model.RESERVED
    if (pool=='C_near')!=near:raise ValueError('Reserved strong pairing belongs only in C-near')
    r=rng(namespace,root,candidate);T=r.uniform(*ranges()['other_background'],6)*r.choice([-1,1],6);T[5]=0
    if pool!='C_near':
        for role in (primary,secondary):
            p=model.PARTNER.get(role)
            if p is not None and p not in (primary,secondary):T[p]=r.choice([-1,1])*r.uniform(*ranges()['reserved_partner_background'])
    bg=[t for t in range(5) if t not in (primary,secondary)];low=max(ranges()['secondary'][0],max(abs(T[t]) for t in bg)+ranges()['secondary_gap'])
    T[secondary]=secondary_sign*r.uniform(low,ranges()['secondary'][1]);T[primary]=sign*r.uniform(*ranges()['far_primary']) if pool=='C_far' else sign*r.uniform(*ranges()['primary'])
    return T,{'primary':primary,'secondary':secondary,'sign':sign,'secondary_sign':secondary_sign,'pool':pool}

def schedule():
    result=[]
    for pool in ('A','B','C_iid','C_near','C_far'):
        reps=current()['quotas_per_root'][pool]//(16 if pool=='C_near' else 10)
        if pool=='C_near':
            for a,b in sorted(model.RESERVED):
                for p,s in ((a,b),(b,a)):
                    for sign in (-1,1):
                        for ss in (-1,1):
                            for _ in range(reps):result.append({'pool':pool,'primary':p,'secondary':s,'sign':sign,'secondary_sign':ss})
        else:
            for rep in range(reps):
                for p in range(5):
                    choices=[s for s in range(5) if s!=p and tuple(sorted((p,s))) not in model.RESERVED]
                    for sign in (-1,1):result.append({'pool':pool,'primary':p,'secondary':choices[rep%len(choices)],'sign':sign,'secondary_sign':1 if (p+rep+(sign>0))%2 else -1})
    return result

def build(root,traits,namespace,candidate,config,*,noise=None,reference=None):
    if namespace not in (config['diagnostic_namespace'],config['production_namespace']):raise ValueError('Unrecognised seed namespace')
    natural,generation=models();g=generation[root];n=natural[root];T=np.array(traits).reshape(1,6);F=np.array(config['directional_multipliers'])
    numeric=rng(namespace,root,candidate,'numeric').uniform(-1,1,(1,len(g['cells']))) if noise is None else np.asarray(noise).reshape(1,-1)
    U=rng(namespace,root,candidate,'categorical').random((1,len(g['names']),4))
    Y,stats=model.construct(g,T,numeric,F,U);before=Y.copy();trims=[]
    if reference is not None:Y,trims=model.d.prior.old.bank.trim_far(n,Y,np.asarray(reference))
    directionmap={}
    for x in model.models()[3]:
        if x['root']==root:directionmap={(r['move'],r['property']):set(r['gained_directions']) for r in x['records']}
    factors=np.where(T>=0,F[:,1],F[:,0]);audit=[]
    for j,(move,p) in enumerate(g['cells']):
        contrib=T[0]*factors[0]*g['L'][j]*g['eligible'][j]*3*g['scales'][j]
        if not np.any(contrib) and p not in model.OPS and Y[0,j]==g['stock'][j]:continue
        causes=[]
        for key,label in [('minimum_step_retained','minimum step retained'),('minimum_step_no_headroom','minimum step lacks headroom'),('minimum_step_unsupported','minimum step sign/role unsupported'),('minimum_step_invariant','minimum step removed by invariant'),('minimum_step_excluded','minimum step excluded')]:
            if stats[key][0,j]:causes.append(label)
        trimmed=bool(Y[0,j]!=before[0,j]);delta=Y[0,j]-g['stock'][j]
        if trimmed:causes.append('unsupported exact A cell/link trim')
        if np.any(contrib) and not delta and not causes:causes.append('bounded/rounded or move-rule/derived-link restoration to stock')
        audit.append({'move':move,'property':p,'stock':float(g['stock'][j]),'value':float(Y[0,j]),'S':float(g['scales'][j]),'natural_S':float(n['scales'][j]),
            'retained':bool(delta),'trimmed':trimmed,'newly_permitted_direction':bool(delta and int(np.sign(delta)) in directionmap.get((move,p),set())),
            'contributions':[{'trait':model.TRAITS[t],'raw_trait':float(T[0,t]),'base_loading':float(g['L'][j,t]),'direction_multiplier':float(factors[0,t]),'shift':float(contrib[t])} for t in range(5) if contrib[t]],'causes':causes})
    return Y[0],numeric[0],audit

def write(root,y,path,namespace,config,audit):
    n=models()[0][root];path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    import common as c
    c.authorise_output(path,namespace,config)
    write_variant(model.d.c.v1.HOT/'stock_reference'/root/'Motion.csv',path,root,model.d.c.edits(n,np.asarray(y)))
    table=read(path,root);actual=np.array([table[a][p] for a,p in n['cells']]);assert np.array_equal(actual,y)
    rows=[]
    for row in audit:
        x=dict(row);j=n['pos'][x['move'],x['property']];x['value']=float(y[j]);x['retained']=bool(y[j]!=n['stock'][j]);rows.append(x)
    atomic(path.with_suffix('.provenance.json'),{'configuration_sha256':config['configuration_sha256'],'namespace':namespace,'permanently_pool_ineligible':False,
        'input_sha256':sha(path),'attempted_retained_trimmed_excluded':rows})
    return sha(path)

def reversion_keys(audit,reverts=()):return {(r['move'],r['property']) for r in audit if r.get('trimmed')}|{(r['move'],r['property']) for r in reverts}

def assess_profile(root,y,traits,meta,initial_score,config,reference=None,revert_cells=()):
    n,g=(z[root] for z in models());F=np.array(config['directional_multipliers']);y=np.asarray(y);T=np.array(traits)
    omit=np.array([key in revert_cells and y[j]==n['stock'][j] for j,key in enumerate(n['cells'])])[None,:]
    inferred=readout.infer(g,y[None,:],F,stock_reverted=omit);p,s=meta['primary'],meta['secondary']
    coherent=bool(inferred['identified'][0] and inferred['primary'][0]==p and inferred['secondary'][0]==s and inferred['primary_sign'][0]==np.sign(T[p]) and inferred['secondary_sign'][0]==np.sign(T[s]))
    score=float(model.d.c.core_score(n,y[None,:],p)[0]);retention=score/initial_score if initial_score else 0
    distance=float(np.linalg.norm(model.features(n,y[None,:])[0]));cover=float(diversity(g,y[None,:])[0][0]);far=None
    if reference is not None:far=bool(model.old.bank.full_qualification(n,y[None,:],T[None,:],np.asarray(reference))[0][0])
    comparisons=[]
    for name,values in config.get('runtime_reference_vectors',{}).items():
        if values:comparisons.append((name,float(np.min(np.linalg.norm(model.features(n,np.asarray(values))-model.features(n,y[None,:]),axis=1)))))
    refdistance=dict(comparisons)
    # Far references are construction-only virtual A, never admitted catalogue
    # members. Diagnostics retain the same AB-distance policy explicitly.
    cross=True
    if meta.get('pool','').startswith('C_'):
        needed=config['floors']['far_AB' if meta['pool']=='C_far' else 'iid_near_AB']
        cross=all(v>=needed for v in refdistance.values())
    return {'profile_coherent':coherent,'primary_core_score':score,'primary_retention':retention,'stock_distance':distance,'coverage':cover,
        'far_qualified':far,'reference_distances':refdistance,'cross_distance_passed':cross,
        'feasible_role_tuples':int(inferred['feasible_tuples'][0]),
        'passed':coherent and retention>=.7 and distance>=config['floors']['stock'] and cover>=.8 and far is not False and cross}

design_context=types.SimpleNamespace(c=model.c,prior=types.SimpleNamespace(models=models,old=model.old))

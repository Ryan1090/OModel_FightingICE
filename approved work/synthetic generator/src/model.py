"""Frozen constructor, metric and support functions from the validated design."""
import functools,json,math,pickle,types
from pathlib import Path
import numpy as np
from gmtv.rules import is_projectile,INPUT_ACTIONS
ASSETS=Path(__file__).resolve().parents[1]/'assets'
CONST=json.loads((ASSETS/'constants.json').read_text())
CORE=CONST['CORE'];NOOPS={tuple(x) for x in CONST['NOOPS']};FAMILY=CONST['FAMILY'];MINIMUM=CONST['MINIMUM'];TRAITS=tuple(CONST['TRAITS'])
RESERVED={(0,1),(2,3)};PARTNER={0:1,1:0,2:3,3:2}
OPS={'attack.DownProp':1,'attack.AttackType':4,'cancelAbleFrame':4,'cancelAbleMotionLevel':4}
v2=types.SimpleNamespace(TRAITS=TRAITS)
def group(kind,n,r):
 if kind=='input':return n in INPUT_ACTIONS
 if kind=='moving_x':return n in INPUT_ACTIONS and r['speedX']!=0
 if kind=='moving_y':return n in INPUT_ACTIONS and r['speedY']!=0
 return group_matches(kind,n,r)
def move_class(n,r):
    if n in {'THROW_A','THROW_B'}:return 'throw'
    if n in {'FORWARD_WALK','DASH','BACK_STEP'}:return 'ground_movement'
    if n in {'JUMP','FOR_JUMP','BACK_JUMP'}:return 'jump'
    if 'GUARD' in n:return 'guard'
    if r['attack.Active']>0 and 0<r['attack.StartUp']<r['frameNumber']:
        if n.startswith('AIR'):return 'aerial_special' if '_D_' in n or '_F_' in n else 'aerial_normal'
        return 'ground_special' if '_D_' in n or '_F_' in n else 'ground_normal'
    return 'other'

def group_matches(group,n,r):
    c=move_class(n,r);attack=c in {'ground_normal','aerial_normal','ground_special','aerial_special','throw'}
    strike=attack and c!='throw'
    if group=='attack':return attack
    if group=='strike':return strike
    if group=='guardable':return strike and r['attack.AttackType'] in (1,2,3)
    if group=='projectile':return strike and is_projectile(r)
    if group=='movement':return c in {'ground_movement','jump'}
    if group=='jump':return c=='jump'
    if group=='launcher':return strike and r['attack.ImpactY']<0
    if group=='costly':return attack and r['attack.StartAddEnergy']<0
    return False

# Source: review_calibration.py
def base_feature(model,Y):
    delta=(Y-model['stock'])/model['scales']
    numeric=delta*model['weights'];N=len(model['names']);families=len(set(FAMILY.values()))
    def col(p):return np.array([model['pos'][(n,p)] for n in model['names']])
    types=Y[:,col('attack.AttackType')].astype(int);base=model['stock'][col('attack.AttackType')].astype(int)
    type_bits=(np.eye(5)[types]-np.eye(5)[base]).reshape(len(Y),-1)/math.sqrt(2*families*N)
    down=(Y[:,col('attack.DownProp')]-model['stock'][col('attack.DownProp')])/math.sqrt(families*N)
    def links(V):
        if V.ndim==1:V=V[None,:]
        duration=V[:,col('frameNumber')];window=V[:,col('cancelAbleFrame')]
        level=V[:,col('motionLevel')];permission=V[:,col('cancelAbleMotionLevel')]
        source=np.array([not model['table'][n]['control'] for n in model['names']])[None,:]
        source=source&(window<duration)&(V[:,col('attack.StartUp')]>0)&(V[:,col('attack.StartUp')]<duration)&(V[:,col('attack.Active')]>0)
        source=source&(V[:,col('attack.AttackType')]!=4)&(V[:,col('attack.speedX')]+V[:,col('attack.speedY')]==0)
        same=np.array([model['table'][n]['state']=='AIR' for n in model['names']])[:,None]==np.array([n.startswith('AIR') for n in model['names']])[None,:]
        adjacency=source[:,:,None]&(permission[:,:,None]>=level[:,None,:])&same[None,:,:]&(~np.eye(N,dtype=bool))[None,:,:]
        effective=np.where(adjacency.any(axis=2),np.clip(window/np.maximum(duration,1),0,1),0)
        return adjacency.astype(float),effective
    graph,window=links(Y);bg,bw=links(model['stock'])
    return np.concatenate([numeric,type_bits,down,(graph-bg).reshape(len(Y),-1)/math.sqrt(2*families*N*N),
                           (window-bw)/math.sqrt(2*families*N)],axis=1)

# Source: review_calibration_v2.py
def graph(m,Y):
    N=len(m['names']);pos=m['pos']
    c=lambda p:Y[:,[pos[(n,p)] for n in m['names']]]
    duration=c('frameNumber');window=c('cancelAbleFrame');permission=c('cancelAbleMotionLevel');level=c('motionLevel')
    source=np.array([not m['table'][n]['control'] for n in m['names']])[None,:]
    source=source&(window<duration)&(c('attack.StartUp')>0)&(c('attack.StartUp')<duration)&(c('attack.Active')>0)
    projectile=((c('attack.speedX').astype(np.int64)+c('attack.speedY').astype(np.int64))&0xffffffff)!=0
    source=source&(~projectile)&(c('attack.AttackType')!=4)
    state=np.array([m['table'][n]['state']=='AIR' for n in m['names']])[:,None]==np.array([n.startswith('AIR') for n in m['names']])[None,:]
    return source[:,:,None]&(permission[:,:,None]>=level[:,None,:])&state[None,:,:]&(~np.eye(N,dtype=bool))[None,:,:]

# Source: construction_v3.py
def edits(m,y):
    result={}
    for j,(move,prop) in enumerate(m['cells']):
        if y[j]!=m['stock'][j]:result.setdefault(move,{})[prop]=bool(y[j]) if prop=='attack.DownProp' else int(y[j])
    return result

def core_score(m,Y,trait):
    cols=[j for j,(_,p) in enumerate(m['cells']) if p in CORE[v2.TRAITS[trait]] and m['L'][j,trait]!=0]
    if not cols:return np.zeros(len(Y))
    return np.sqrt(np.mean(((Y[:,cols]-m['stock'][cols])/m['scales'][cols])**2,axis=1))

# Source: stock_distance_v17/metric_v17.py
def weights(m):
    u=np.asarray(m['usage'],float)
    if np.any(u<0) or not u.sum():raise ValueError('Invalid usage')
    return u/u.sum()

def descriptor_multiplier(m,w):
    N=len(m['names']);k=len(m['cells'])
    return np.r_[np.repeat(np.sqrt(N*w),k//N),np.repeat(np.sqrt(N*w),5),np.sqrt(N*w),
                 (N*np.sqrt(w[:,None]*w[None,:])).ravel(),np.sqrt(N*w)]

# Source: fast_v16/bank_v8.py
def trim_far(m,F,A):
    """Exact same-root cell support; categorical transitions match exactly."""
    F=np.array(F,copy=True);x=m['stock'];events=[];a=A-x
    for j,(n,p) in enumerate(m['cells']):
        changed=F[:,j]!=x[j]
        if p in {'attack.AttackType','attack.DownProp'}:
            supported=np.any((F[:,j,None]==A[None,:,j])&(A[None,:,j]!=x[j]),axis=1)
        else:
            supported=np.array([np.any(np.sign(a[:,j])==np.sign(v-x[j])) for v in F[:,j]])
        bad=changed&~supported
        for i in np.flatnonzero(bad):events.append({'index':int(i),'move':n,'property':p,'before':float(F[i,j]),'after':float(x[j]),'cause':'no exact retained Pool A cell/direction/transition witness'})
        F[bad,j]=x[j]
    # Preserve the standing relationship-support rule too. Drop all edited
    # permission components touching an unsupported changed link, never invent a
    # donor relationship or choose a favourable field to keep.
    BG=c.graph(m,x[None,:])[0];AG=c.graph(m,A)
    additions=np.any(AG&~BG,axis=0);removals=np.any(~AG&BG,axis=0)
    for _ in range(1+len(m['cells'])):
        G=c.graph(m,F);bad=((G&~BG)&~additions)|((~G&BG)&~removals)
        if not bad.any():break
        dropped=False
        for i,src,dst in np.argwhere(bad):
            source_fields=('cancelAbleFrame','cancelAbleMotionLevel','frameNumber','attack.StartUp','attack.Active','attack.speedX','attack.speedY','attack.AttackType')
            touched=[(m['names'][src],p) for p in source_fields]+[(m['names'][dst],'motionLevel')]
            for move,p in touched:
                j=m['pos'][move,p]
                if F[i,j]==x[j]:continue
                events.append({'index':int(i),'move':move,'property':p,'before':float(F[i,j]),'after':float(x[j]),'cause':'changed cancel relationship lacks retained Pool A witness; remove its edited rule inputs'})
                F[i,j]=x[j];dropped=True
        if not dropped:raise RuntimeError('Unsupported relationship cannot be resolved by removing edited cancel components')
    else:raise RuntimeError('Far relationship trimming did not converge')
    return F,events

# Source: final_design_v13_r1/verify_paper.py
def full_qualification(m,Far,FT,A):
    x=m['stock'];fd=Far-x;ad=A-x;bad=np.zeros(len(Far),int)
    for j,(n,p) in enumerate(m['cells']):
        if p in ('attack.AttackType','attack.DownProp'):
            bad+=(fd[:,j]!=0)&~np.any(Far[:,j,None]==A[None,:,j],axis=1)
        else:
            for s in (-1,1):
                if not np.any(s*ad[:,j]>0):bad+=s*fd[:,j]>0
    G=d.c.graph(m,Far);AG=d.c.graph(m,A);BG=d.c.graph(m,x[None,:])[0]
    bad+=np.sum(((G&~BG)&~np.any(AG&~BG,axis=0))|((~G&BG)&~np.any(~AG&BG,axis=0)),axis=(1,2))
    scoregood=np.zeros(len(Far),bool)
    for t in range(5):
        rows=np.flatnonzero(np.argmax(abs(FT[:,:5]),axis=1)==t)
        cols=[j for j,(_,p) in enumerate(m['cells']) if p in d.c.CORE[d.TRAITS[t]] and m['L'][j,t]!=0]
        scores=d.c.core_score(m,Far,t);bound=max(d.c.core_score(m,A,t))
        outside=np.zeros(len(Far),bool)
        for j in cols:
            for s in (-1,1):
                vals=s*ad[:,j];maximum=np.max(vals[vals>0]) if np.any(vals>0) else np.inf
                outside|=s*fd[:,j]>=maximum+1
        scoregood[rows]=(scores[rows]>bound+1e-9)&outside[rows]
    return (bad==0)&scoregood,{'unsupported':bad,'extrapolates':scoregood}

# Source: full_design_v20_paper/model.py
def construct(m,T,noise,F,uniforms,*,operators=True):
    T=np.asarray(T);N=len(T);x=m['stock'];S=m['scales'];L=m['L']*m['eligible']
    gains=np.where(T>=0,F[:,:,1],F[:,:,0]) if F.ndim==3 else np.where(T>=0,F[:,1],F[:,0])
    contributions=T[:,None,:]*gains[:,None,:]*L[None,:,:];signal=contributions.sum(axis=2)*3*S
    residual=np.minimum(.25*S,.25*abs(signal));proposed=signal+noise*residual
    plus=np.maximum(0,np.minimum(np.floor(3*S),np.floor(m['hi']-x)));minus=np.maximum(0,np.minimum(np.floor(3*S),np.floor(x-m['lo'])))
    bounded=np.clip(proposed,-minus,plus);rounded=np.sign(bounded)*np.floor(abs(bounded)+.5)
    forced=(signal!=0)&(rounded==0);one=np.sign(signal)
    room=np.where(one>0,plus,minus)>=1
    rounded=np.where(forced&room,one,rounded)
    support=np.array([[(-1 in a),(1 in a)] for a in m['supports']]);allowed=np.where(rounded>0,support[:,1],support[:,0])
    Y=x+np.where(allowed,rounded,0)
    rejected_support=(rounded!=0)&~allowed
    invariant=np.zeros_like(forced);exclusion=np.zeros_like(forced)
    def restore(mask,cols):
        for j in cols:invariant[:,j]|=mask&(Y[:,j]!=x[j]);Y[mask,j]=x[j]
    def invariants():
        for n in m['names']:
            r=m['table'][n];pos=m['pos'];f,s,a=[pos[n,p] for p in ('frameNumber','attack.StartUp','attack.Active')]
            bad=(r['attack.Active']>0)&(Y[:,s]>=Y[:,f]);restore(bad,[f,s])
            if not d.c.v1.is_projectile(r):restore((Y[:,a]!=x[a])&(Y[:,a]>Y[:,f]-Y[:,s]),[a])
            else:
                px,py=[pos[n,p] for p in ('attack.speedX','attack.speedY')]
                restore(((Y[:,px].astype(np.int64)+Y[:,py].astype(np.int64))&0xffffffff)==0,[px,py])
            for prefix in ('','attack.'):
                for low,high in (('hitAreaLeft','hitAreaRight'),('hitAreaUp','hitAreaDown')):
                    a,b=pos[n,prefix+low],pos[n,prefix+high];restore(Y[:,a]>=Y[:,b],[a,b])
    invariants()
    op_attempt=np.zeros((N,len(m['names']),4),bool);prob=np.zeros_like(op_attempt,float)
    if operators:
        for ni,n in enumerate(m['names']):
            r=m['table'][n];pos=m['pos']
            if not d.c.group('strike',n,r):continue
            for k,(p,t) in enumerate(OPS.items()):
                j=pos[n,p];prob[:,ni,k]=np.clip((abs(T[:,t])-.1)/.4,0,1)
                take=uniforms[:,ni,k]<prob[:,ni,k];target=Y[:,j].copy()
                if p=='attack.DownProp':target=(T[:,t]>0).astype(int)
                elif p=='attack.AttackType':
                    if r[p] not in (1,2,3):continue
                    take&=T[:,t]>0;target[:]={1:2,2:3,3:2}[r[p]]
                elif p=='cancelAbleFrame':take&=T[:,t]<0;target=Y[:,pos[n,'frameNumber']]
                else:
                    take&=T[:,t]>0;levels=Y[:,[pos[a,'motionLevel'] for a in m['names']]]
                    target=np.min(np.where(levels>Y[:,j,None],levels,99),axis=1);take&=target<99
                direction=np.sign(target-x[j]);ok=np.where(direction>0,support[j,1],support[j,0]);take&=ok&(target!=x[j])
                op_attempt[:,ni,k]=take;Y[:,j]=np.where(take,target,Y[:,j])
        for _ in range(3):
            G=d.c.graph(m,Y);drop=np.zeros_like(forced)
            for ni,n in enumerate(m['names']):
                for p in ('motionLevel','cancelAbleMotionLevel','cancelAbleFrame'):
                    j=m['pos'][n,p];changed=Y[:,j]!=x[j]
                    if not changed.any():continue
                    Z=Y.copy();Z[:,j]=x[j];H=d.c.graph(m,Z)
                    touched=np.any(G[:,:,ni]!=H[:,:,ni],axis=1) if p=='motionLevel' else np.any(G[:,ni,:]!=H[:,ni,:],axis=1)
                    if p=='cancelAbleFrame':touched|=np.any(G[:,ni,:]|H[:,ni,:],axis=1)&changed
                    drop[:,j]=changed&~touched
            if not drop.any():break
            Y=np.where(drop,x,Y)
    for j,(n,p) in enumerate(m['cells']):
        delta=Y[:,j]-x[j];bad=np.zeros(N,bool)
        if p=='frameNumber':
            for sign in (-1,1):
                if (m['root'],n,sign) in d.NOOPS:bad|=sign*delta>0
        elif p=='attack.GiveGuardRecov':bad=(delta!=0)&(abs(delta)<2)
        exclusion[:,j]|=bad;Y[bad,j]=x[j]
    for n in m['names']:
        f,s,a=[m['pos'][n,p] for p in ('frameNumber','attack.StartUp','attack.Active')]
        bad=(Y[:,s]>=Y[:,f])|((not d.c.v1.is_projectile(m['table'][n]))&(Y[:,a]>Y[:,f]-Y[:,s]));restore(bad,[f,s,a])
    return Y,{'signal':signal,'minimum_step_attempted':forced,'minimum_step_retained':forced&(Y!=x),
              'minimum_step_no_headroom':forced&~room,'minimum_step_unsupported':forced&rejected_support,
              'minimum_step_invariant':forced&invariant,'minimum_step_excluded':forced&exclusion,
              'operator_selected':op_attempt,'operator_probability':prob}

def features(m,Y):return base_feature(m,Y)*descriptor_multiplier(m,weights(m))
@functools.lru_cache(maxsize=1)
def models():
 obj=pickle.loads((ASSETS/'model.pkl').read_bytes());return obj['natural'],obj['generation'],[],obj['direction_audit']
v1=types.SimpleNamespace(is_projectile=is_projectile,HOT=ASSETS,feature=base_feature)
c=types.SimpleNamespace(v1=v1,CORE=CORE,core_score=core_score,graph=graph,group=group,edits=edits)
d=types.SimpleNamespace(c=c,NOOPS=NOOPS,TRAITS=TRAITS)
bank=types.SimpleNamespace(trim_far=trim_far,full_qualification=full_qualification)
d.prior=types.SimpleNamespace(old=types.SimpleNamespace(bank=bank))
old=types.SimpleNamespace(bank=bank)

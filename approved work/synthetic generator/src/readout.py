"""Seed/label/pool-blind conservative interval readout for the full V20 model."""
import numpy as np
import model as m
from settings import ranges
from readout_bounds import plus_inverse,minus_inverse,propagate,raw_to_z,z_to_raw,SAFE_ZERO

def constraints(model,Y,stock_reverted=None):
    N=len(Y);x=model['stock'];S=model['scales'];L=model['L'][:,:5]*model['eligible'][:,:5]
    omit=np.zeros_like(Y,bool) if stock_reverted is None else np.asarray(stock_reverted,bool)
    if omit.shape!=Y.shape or np.any(omit&(Y!=x)):raise ValueError('Only recorded exact-stock reverts may be omitted')
    groups={};idx=[]
    for j,c in enumerate(L):
        if not np.any(c):continue
        key=tuple(c)
        if key not in groups:groups[key]=len(groups)
        idx.append((j,groups[key]))
    C=np.array(list(groups));A=np.full((N,len(C)),-np.inf);B=np.full_like(A,np.inf)
    cp=np.maximum(0,np.minimum(np.floor(3*S),np.floor(model['hi']-x)));cn=np.maximum(0,np.minimum(np.floor(3*S),np.floor(x-model['lo'])))
    for j,k in idx:
        p=model['cells'][j][1];delta=Y[:,j]-x[j];ab=abs(delta);nz=delta!=0
        low=plus_inverse(np.maximum(0,ab-.5),S[j]);low=np.where(ab==1,0,low)
        high=minus_inverse(ab+.5,S[j]);cap=np.where(delta>0,cp[j],cn[j]);high=np.where(ab>=cap,np.inf,high)
        lo=np.where(delta>0,low,-high);hi=np.where(delta>0,high,-low)
        lo=np.where(nz,lo,-np.inf);hi=np.where(nz,hi,np.inf)
        if p in SAFE_ZERO:
            # A valid nonzero signal cannot stay zero after the minimum step.
            # Guard stun's one-frame exclusion remains an explicit exception.
            extent=float(minus_inverse(1.5,S[j])) if p=='attack.GiveGuardRecov' else 0.
            minimum=2 if p=='attack.GiveGuardRecov' else 1
            if 1 in model['supports'][j] and cp[j]>=minimum:hi=np.where(~nz,extent,hi)
            if -1 in model['supports'][j] and cn[j]>=minimum:lo=np.where(~nz,-extent,lo)
        A[:,k]=np.maximum(A[:,k],np.where(omit[:,j],-np.inf,lo)/(3*S[j]))
        B[:,k]=np.minimum(B[:,k],np.where(omit[:,j],np.inf,hi)/(3*S[j]))
    return C,A,B

def operator_bounds(model,Y,F,lo,hi):
    for move in model['names']:
        r=model['table'][move]
        if not m.d.c.group('strike',move,r):continue
        for p,t in m.OPS.items():
            j=model['pos'][move,p];changed=Y[:,j]!=model['stock'][j]
            if p=='attack.DownProp':
                positive=changed&(Y[:,j]==1);negative=changed&(Y[:,j]==0)
                lo[positive,t]=np.maximum(lo[positive,t],.1*F[t,1]);hi[negative,t]=np.minimum(hi[negative,t],-.1*F[t,0])
            elif p=='attack.AttackType' and r[p] in (1,2,3):
                take=changed&(Y[:,j]=={1:2,2:3,3:2}[r[p]]);lo[take,t]=np.maximum(lo[take,t],.1*F[t,1])
            elif p=='cancelAbleFrame':hi[changed,t]=np.minimum(hi[changed,t],-.1*F[t,0])
            elif p=='cancelAbleMotionLevel':lo[changed,t]=np.maximum(lo[changed,t],.1*F[t,1])
    return lo,hi

def role_tighten(lo,hi,p,s,sign,near):
    lo=lo.copy();hi=hi.copy();valid=np.ones(len(lo),bool)
    for _ in range(3):
        minimum=[]
        secmax=np.where(sign>0,hi[:,s],-lo[:,s]);secmin=np.where(sign>0,lo[:,s],-hi[:,s])
        for t in range(5):
            if t in (p,s):continue
            weak=not near and any(m.PARTNER.get(role)==t for role in (p,s))
            low,high=ranges()['reserved_partner_background' if weak else 'other_background']
            limit=np.minimum(high,secmax-ranges()['secondary_gap'])
            a=np.maximum(lo[:,t],low);b=np.minimum(hi[:,t],limit);pos=a<=b+2e-10
            c=np.maximum(lo[:,t],-limit);d=np.minimum(hi[:,t],-low);neg=c<=d+2e-10
            valid&=pos|neg
            lo[:,t]=np.where(pos&~neg,a,np.where(neg&~pos,c,np.maximum(lo[:,t],-limit)))
            hi[:,t]=np.where(pos&~neg,b,np.where(neg&~pos,d,np.minimum(hi[:,t],limit)))
            amin=np.where(pos&~neg,a,np.where(neg&~pos,-d,low));minimum.append(amin)
        secmin=np.maximum(secmin,np.max(minimum,axis=0)+ranges()['secondary_gap'])
        if sign>0:lo[:,s]=np.maximum(lo[:,s],secmin)
        else:hi[:,s]=np.minimum(hi[:,s],-secmin)
        valid&=np.all(lo<=hi+2e-10,axis=1)
    return lo,hi,valid

def infer(model,Y,F,stock_reverted=None):
    Y=np.asarray(Y,float);F=np.asarray(F)[:5];N=len(Y)
    C,A,B=constraints(model,Y,stock_reverted);lo=np.tile(-F[:,0],(N,1));hi=np.tile(F[:,1],(N,1))
    lo,hi=operator_bounds(model,Y,F,lo,hi);lo,hi,consistent=propagate(C,A,B,lo,hi)
    rawlo=z_to_raw(lo,F);rawhi=z_to_raw(hi,F)
    count=np.zeros(N,int);primary=np.full(N,-1,int);secondary=np.full(N,-1,int);ps=np.zeros(N,int);ss=np.zeros(N,int)
    lower=np.full((N,5),np.inf);upper=np.full((N,5),-np.inf)
    for p in range(5):
        for s in range(5):
            if p==s:continue
            near=tuple(sorted((p,s))) in m.RESERVED
            for a in (-1,1):
                for b in (-1,1):
                    survives=np.zeros(N,bool)
                    for pmin,pmax in ((tuple(ranges()['primary']),) if near else (tuple(ranges()['primary']),tuple(ranges()['far_primary']))):
                        rl=np.maximum(rawlo,-ranges()['other_background'][1]);rh=np.minimum(rawhi,ranges()['other_background'][1])
                        rl[:,p]=np.maximum(rawlo[:,p],pmin if a>0 else -pmax);rh[:,p]=np.minimum(rawhi[:,p],pmax if a>0 else -pmin)
                        rl[:,s]=np.maximum(rawlo[:,s],ranges()['secondary'][0] if b>0 else -ranges()['secondary'][1]);rh[:,s]=np.minimum(rawhi[:,s],ranges()['secondary'][1] if b>0 else -ranges()['secondary'][0])
                        rl,rh,roleok=role_tighten(rl,rh,p,s,b,near)
                        take=np.flatnonzero(consistent&roleok)
                        if not len(take):continue
                        zl,zh,ok=propagate(C,A[take],B[take],raw_to_z(rl[take],F),raw_to_z(rh[take],F))
                        rlo,rhi,rg=role_tighten(z_to_raw(zl,F),z_to_raw(zh,F),p,s,b,near)
                        valid=take[ok&rg];survives[valid]=True
                        lower[valid]=np.minimum(lower[valid],rlo[ok&rg]);upper[valid]=np.maximum(upper[valid],rhi[ok&rg])
                    count+=survives;primary[survives]=p;secondary[survives]=s;ps[survives]=a;ss[survives]=b
    identified=count==1;primary[~identified]=-1;secondary[~identified]=-1;ps[~identified]=0;ss[~identified]=0
    return {'identified':identified,'primary':primary,'secondary':secondary,'primary_sign':ps,'secondary_sign':ss,'feasible_tuples':count,
            'lower':lower,'upper':upper,'numeric_constraints_consistent':consistent}

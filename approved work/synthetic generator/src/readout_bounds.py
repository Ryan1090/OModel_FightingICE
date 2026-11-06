import numpy as np
SAFE_ZERO={
 'attack.HitDamage','attack.GuardDamage','attack.StartAddEnergy',
 'attack.HitAddEnergy','attack.GuardAddEnergy','attack.GiveEnergy',
 'attack.ImpactX','attack.ImpactY','attack.GiveGuardRecov','speedX','speedY'}
def plus_inverse(x,S):return np.where(x<=1.25*S,x/1.25,x-.25*S)

def minus_inverse(x,S):return np.where(x<=.75*S,x/.75,x+.25*S)

def propagate(C,A,B,lo,hi,sweeps=24):
    lo=lo.copy();hi=hi.copy();feasible=np.ones(len(lo),bool);eps=2e-10
    for iteration in range(sweeps):
        oldlo=lo.copy();oldhi=hi.copy()
        for k,c in enumerate(C):
            pos=np.maximum(c,0);neg=np.minimum(c,0)
            total_lo=lo@pos+hi@neg;total_hi=hi@pos+lo@neg
            feasible&=(A[:,k]<=total_hi+eps)&(B[:,k]>=total_lo-eps)
            for t in np.flatnonzero(c):
                v=c[t];selflo=np.minimum(v*lo[:,t],v*hi[:,t]);selfhi=np.maximum(v*lo[:,t],v*hi[:,t])
                a=(A[:,k]-(total_hi-selfhi))/v;b=(B[:,k]-(total_lo-selflo))/v
                lo[:,t]=np.maximum(lo[:,t],np.minimum(a,b));hi[:,t]=np.minimum(hi[:,t],np.maximum(a,b))
            feasible&=np.all(lo<=hi+eps,axis=1)
            # Empty boxes are discarded, but kept finite for the other rows.
            lo[~feasible]=0;hi[~feasible]=0
        if np.max(abs(lo-oldlo),initial=0)<1e-10 and np.max(abs(hi-oldhi),initial=0)<1e-10:break
    return lo,hi,feasible

def raw_to_z(raw,F):return np.where(raw>=0,raw*F[:,1],raw*F[:,0])

def z_to_raw(z,F):return np.where(z>=0,z/F[:,1],z/F[:,0])

import numpy as np
import model as m
def applicable(model):
    props=set();cells=[]
    for j,(n,p) in enumerate(model['cells']):
        ok=np.any((model['L'][j,:5]!=0)&model['eligible'][j,:5])
        if p in m.OPS:ok=bool(model['supports'][j]) and m.d.c.group('strike',n,model['table'][n])
        if ok:props.add(p);cells.append(j)
    return sorted(props),cells

def diversity(model,Y):
    props,cells=applicable(model);x=model['stock'];types=np.column_stack([np.any(Y[:,[j for j,(_,q) in enumerate(model['cells']) if q==p]]!=x[[j for j,(_,q) in enumerate(model['cells']) if q==p]],axis=1) for p in props])
    return types.mean(axis=1),types,props,cells

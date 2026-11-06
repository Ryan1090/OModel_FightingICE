import numpy as np
import generator as gen
d=gen.design_context
def failing_cells(report):
    failures={};rejected=set()
    for x in report.get('static_issues',[]):
        key=x['move'],x['property'];failures[key]=x.get('reason','static failure');rejected.add(key)
    for group in report.get('groups',[]):
        for x in group.get('results',[]):
            if x.get('status')=='PASSED' or 'cell' not in x:continue
            key=x['cell']['move'],x['cell']['property'];failures[key]=x.get('reason',group.get('reason','unresolved'))
            if x.get('status')=='REJECTED':rejected.add(key)
    return failures,rejected

def invariant_closure(m,y):
    y=np.array(y,copy=True);events=[]
    for name in m['names']:
        f,s,a=[m['pos'][name,p] for p in ('frameNumber','attack.StartUp','attack.Active')]
        if y[s]>=y[f] or (not d.c.v1.is_projectile(m['table'][name]) and y[a]>y[f]-y[s]):
            for j in (f,s,a):
                if y[j]!=m['stock'][j]:events.append({'move':name,'property':m['cells'][j][1],'cause':'revert closure: preserve move invariant'});y[j]=m['stock'][j]
    return y,events

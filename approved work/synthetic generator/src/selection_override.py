import functools
import generator as gen
def role_map(root,primary,secondary):
    n,g=(m[root] for m in gen.models());roles={}
    for j,(move,prop) in enumerate(g['cells']):
        main=[t for t in range(5) if g['eligible'][j,t] and abs(g['L'][j,t])>=.5]
        if prop in gen.model.OPS:main=[gen.model.OPS[prop]]
        roles[move+'|'+prop]='primary' if primary in main else 'secondary' if secondary in main else 'background' if main else 'side effect'
    return roles

def context_for(item):
    return {**item['context'],'selection_roles':role_map(item['root'],item['meta']['primary'],item['meta']['secondary'])}

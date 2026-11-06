import numpy as np
import generator as gen
from repair_rules import failing_cells,invariant_closure
from gmtv.schema import digest
def apply_batch(item,state,report,config,*,final=False,constructor=None,closure=None,trimmer=None):
    root=item['root'];m=gen.models()[0][root];y=np.asarray(state['y']).copy();before=y.copy()
    failures,rejected=failing_cells(report)
    stage='final_reversion' if final else 'repair'
    round_index=state['repair_rounds']+1
    actions=[];events=[];audit=state['audit'];noise=np.asarray(state['noise'])
    proposed=None;redraw_audit=[]
    # One unchanged round seed, shared by all genuine failures in this batch.
    if rejected and not final:
        noise=gen.rng(item['namespace'],root,item['id'],round_index).uniform(-1,1,len(m['cells']))
        proposed,noise,redraw_audit=(constructor or gen.build)(root,item['traits'],item['namespace'],item['id'],config,
            noise=noise,reference=np.asarray(item['reference']) if item.get('reference') is not None else None)
    for key,reason in failures.items():
        j=m['pos'][key];value=float(y[j]);stock=float(m['stock'][j]);kind=None;cause=reason
        if key not in rejected:kind='unobservable selected effect';target=stock
        elif final:kind='remaining non-passing edit after three repair rounds';target=stock
        else:
            token='/'.join(key);state['redraws'][token]=state['redraws'].get(token,0)+1;target=float(proposed[j])
            if target==value:kind='redraw cannot change value';cause=kind;target=stock
            elif target==stock:kind='genuine failure redraw to stock'
        if target!=value:
            if target==stock:
                events.append({'move':key[0],'property':key[1],'value':value,'cause':cause,'assessment_reason':reason,'kind':kind,'stage':stage,'round':round_index})
            actions.append({'move':key[0],'property':key[1],'value_before':value,'value_after':target,'action':kind or 'genuine failure noise redraw','assessment_reason':reason})
            y[j]=target
    # Coupled closure and far support remain exactly the existing safeguards.
    prec=y.copy();y,extra=(closure or invariant_closure)(m,y)
    for e in extra:
        e={**e,'value':float(prec[m['pos'][e['move'],e['property']]]),'stage':stage,'round':round_index};events.append(e)
    if item.get('reference') is not None:
        prec=y.copy();Z,extra=(trimmer or gen.design_context.prior.old.bank.trim_far)(m,y[None,:],np.asarray(item['reference']));y=Z[0]
        for e in extra:events.append({**e,'value':float(prec[m['pos'][e['move'],e['property']]]),'stage':stage,'round':round_index})
    updated={(a['move'],a['property']) for a in actions if a['action']=='genuine failure noise redraw' or a['action']=='genuine failure redraw to stock'}
    newer={(a['move'],a['property']):a for a in redraw_audit}
    audit=[newer.get((a['move'],a['property']),a) if (a['move'],a['property']) in updated else a for a in audit]
    state.update(y=y.tolist(),noise=np.asarray(noise).tolist(),audit=audit)
    state['reverts'].extend(events)
    if final:state['final_reversion_done']=True
    else:state['repair_rounds']+=1
    record={'stage':stage,'round':round_index,'fully_assessed_failures':len(failures),'genuine_failures':len(rejected),
      'actions':actions,'reverts':events,'input_vector_sha256':digest(before.tolist()),'output_vector_sha256':digest(y.tolist()),
      'changed':not np.array_equal(before,y),'no_evidence_cells_never_inferred_as_failures':True}
    state['batches'].append(record)
    return record

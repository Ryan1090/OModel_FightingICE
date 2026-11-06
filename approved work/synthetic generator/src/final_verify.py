"""No gameplay: final commitments, distances, readout and aggregate C verification."""
import collections,gzip,json
from pathlib import Path
import numpy as np
import common as c
gen=c.local_module('generator_production');policy=c.local_module('policy');safe_remove=c.local_module('sealed_store').safe_remove
from gmtv.schema import sha,digest,read
from gmtv.storage import load_commit,atomic

def verify(store,state,accepted,config):
    import importlib.util
    spec=importlib.util.spec_from_file_location('v28_verify_worker',c.HERE/'worker.py');w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)
    c.verify_release(config);natural,generation=gen.models();errors=collections.Counter();raw_hashes={};seen=set();fixtures=0;validated=0;readout=collections.Counter()
    public_ab=[];core_values=collections.defaultdict(list);core_rms=collections.defaultdict(list)
    def check(path,expected=None):
        nonlocal fixtures
        path=Path(path);key=str(path)
        if expected and sha(path)!=expected:raise RuntimeError('Evidence hash mismatch')
        if key in seen:return
        seen.add(key)
        if not (path.name.endswith('.json') or path.name.endswith('.json.gz')):return
        obj=json.loads(gzip.decompress(path.read_bytes()) if path.suffix=='.gz' else path.read_text(encoding='utf-8'))
        if isinstance(obj,dict) and {'checksum','binding','payload'}.issubset(obj):
            expected=obj.pop('checksum')
            if digest(obj)!=expected:raise RuntimeError('Commit checksum mismatch')
            fixtures+=1
            for p,h in obj.get('files',{}).items():
                if p in raw_hashes and raw_hashes[p]!=h:raise RuntimeError('Contradictory hash')
                raw_hashes[p]=h;check(p,h)
    for row in accepted:
        item=store.get('job:'+row['id']);is_c=row['pool'].startswith('C_');root=row['root'];m=natural[root];g=generation[root]
        work,folder,home=w.paths(item,item['runtime_slot'])
        try:
            if is_c:
                if work.exists():raise RuntimeError('Unexpected unsealed C workspace at final verification')
                w.provision_home(home)
                if not store.restore('workspace:'+item['id'],work):raise RuntimeError('Missing private C archive')
            binding=c.item_binding(config,item);proof=load_commit(folder/'COMMIT.json',binding);s=load_commit(folder/'STATE.json',binding)
            if proof is None or s is None or proof['final_sha256']!=row['final_sha256']:raise RuntimeError('Candidate binding failed')
            if s.get('migration'):
                original=c.HOT/'characters'/row['id']/'STATE.json'
                check(original,s['migration']['source_state_sha256'])
            if s.get('engine_startup_recovery'):
                original=Path(s['engine_startup_recovery']['source_state_path'])
                if not original.resolve().is_relative_to(c.HOT.resolve()):raise RuntimeError('Recovery proof outside catalogue')
                check(original,s['engine_startup_recovery']['source_state_sha256'])
            check(folder/'COMMIT.json');check(folder/'STATE.json')
            table=read(row['final_path'],root);y=np.asarray([table[n][p] for n,p in m['cells']])
            if not np.array_equal(y,row['final_vector']):raise RuntimeError('CSV/vector mismatch')
            p=gen.assess_profile(root,y,row['traits'],row['meta'],s['initial_primary_score'],c.item_config(config,item),item['reference'],gen.reversion_keys(s['audit'],s['reverts']))
            if not p['passed'] or not row['screen_passed']:raise RuntimeError('Profile/screen failed')
            readout[row['pool']]+=p['profile_coherent'];validated+=1
            for attempt in row['attempts']:
                ledger=Path(attempt['report'])/'LEDGER.json'
                if ledger.exists():
                    check(ledger)
                    for record in json.loads(ledger.read_text())['records']:check(record['raw_path'])
            T=np.asarray(row['traits']);primary=row['meta']['primary'];secondary=row['meta']['secondary']
            if not np.all(np.abs(T[:5])>0) or abs(T[secondary])+1e-12<max(abs(T[t]) for t in range(5) if t not in (primary,secondary))+config['ranges']['secondary_gap']:raise RuntimeError('Trait range/gap failure')
            if row['pool']!='C_near' and any((abs(T[a])>=config['ranges']['primary'][0] and abs(T[b])>=config['ranges']['secondary'][0]) or (abs(T[b])>=config['ranges']['primary'][0] and abs(T[a])>=config['ranges']['secondary'][0]) for a,b in ((0,1),(2,3))):raise RuntimeError('Reserved-pair strength failure')
            cols=[j for j,(_,prop) in enumerate(g['cells']) if prop in gen.design_context.c.CORE[gen.model.TRAITS[primary]] and g['L'][j,primary]!=0]
            vals=((y-g['stock'])/g['scales'])[cols];group=(row['pool'],gen.model.TRAITS[primary])
            core_values[group].extend(abs(vals).tolist());core_rms[group].append(float(np.sqrt(np.mean(vals**2))))
            if not is_c:public_ab.append({'id':row['id'],'root':root,'pool':row['pool'],'motion_csv':str(row['final_path']),'file_sha256':sha(row['final_path']),'profile':p})
        except Exception:
            errors['candidate/evidence/profile integrity']+=1;store.put('final_verification_error:'+row['id'],{'root':root,'pool':row['pool']})
        finally:
            if is_c and work.exists():safe_remove(work,c.HOT)
    distances=[];b_flags=[];diversity=[];far_ok=0
    for root,m in natural.items():
        rows=[r for r in accepted if r['root']==root];X=gen.model.features(m,np.asarray([r['final_vector'] for r in rows]))
        for pool in c.POOLS:
            ids=[i for i,r in enumerate(rows) if r['pool']==pool];nearest=[];ab=[];stock=[]
            for i in ids:
                own=[float(np.linalg.norm(X[i]-X[j])) for j in ids if j!=i];nearest.append(min(own) if own else 0);stock.append(float(np.linalg.norm(X[i])))
                if stock[-1]+1e-12<config['floors']['stock'] or (own and nearest[-1]+1e-12<config['floors']['within']):errors['final distance floor']+=1
                others=[float(np.linalg.norm(X[i]-X[j])) for j,r in enumerate(rows) if j!=i and r['pool'] in ('A','B')]
                if pool.startswith('C_'):
                    value=min(others);ab.append(value);floor=config['floors']['far_AB' if pool=='C_far' else 'iid_near_AB']
                    if value+1e-12<floor:errors['held-out distance floor']+=1
                    if pool=='C_far':far_ok+=rows[i]['profile']['far_qualified'] is True
                elif pool=='B':
                    value=min(float(np.linalg.norm(X[i]-X[j])) for j,r in enumerate(rows) if r['pool']=='A');ab.append(value)
                    if value<config['floors']['within']:b_flags.append({'id':rows[i]['id'],'root':root,'nearest_A':value,'within_pool_reference_floor':config['floors']['within']})
            distances.append({'root':root,'pool':pool,'from_stock':c.summary_numbers(stock),'nearest_own_pool':c.summary_numbers(nearest),'nearest_A_or_B' if pool.startswith('C_') else 'nearest_A_if_B':c.summary_numbers(ab)})
        for i in range(len(rows)):
            if any(np.linalg.norm(X[i]-X[j])<1e-12 for j in range(i)):errors['duplicate across pools']+=1
        A=[r['final_vector'] for r in rows if r['pool']=='A']
        if len(A)==c.QUOTAS['A']:diversity.append(policy.diversity(root,A))
        else:errors['missing final A panel']+=1
        for pool in c.POOLS:
            rr=[r for r in rows if r['pool']==pool];actual=collections.Counter(tuple(r['stratum']) for r in rr)
            if any(actual[s]!=c.stratum_target(pool) for s in c.strata(pool)) or len(rr)!=c.QUOTAS[pool]:errors['quota/stratum accounting']+=1
    result={'integrity_passed':not errors,'errors':dict(errors),'validated_characters':validated,'verified_commit_envelopes':fixtures,'referenced_files':len(raw_hashes),
      'quotas_per_root':c.QUOTAS,'B_to_A_floor_enforced':False,'B_closer_to_A_than_within_pool_floor':b_flags,
      'distance_distributions':distances,'C_far_support_extrapolation_passed':int(far_ok),'readout_identified_per_pool':dict(readout),
      'reserved_strength_invariant_passed':not errors,'final_A_diversity':diversity,
      'all_final_A_diversity_gates_passed':all(r['coverage_passed'] and r['numeric_frequency_passed'] and r['main_spread']['passed'] for r in diversity),
      'realised_primary_changes':[{ 'pool':p,'trait':t,'absolute_primary_core_cell_generation_S':c.summary_numbers(core_values[p,t]),'character_core_RMS_generation_S':c.summary_numbers(core_rms[p,t])} for p in c.POOLS for t in gen.model.TRAITS],
      'distribution_scope':'Actual final table primary-core offsets divided by generation S, including restored zeros. Core fields can have co-contributors; not isolated causal or behavioural effects.',
      'split_frozen':False,'regenerated_for_diversity':False}
    atomic(c.HOT/'A_B_FINAL_CHARACTERS.json',public_ab)
    return result

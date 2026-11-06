"""No-engine integration and exact arithmetic comparison of the promoted package."""
import ast,asyncio,collections,copy,hashlib,importlib.util,json,os,pickle,subprocess,sys,tempfile,types,uuid
from pathlib import Path
PACKAGE=Path(__file__).resolve().parent
sys.path.insert(0,str(PACKAGE/'python_lib'))
sys.path.insert(0,str(PACKAGE/'src'))
import numpy as np
from app import run_configuration,activate,restore_worker
if __name__=='__mp_main__':restore_worker()

def body(source,name):
    node=next(n for n in ast.parse(source).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name==name)
    return ast.dump(ast.Module(body=node.body,type_ignores=[]),include_attributes=False)

def main():
    work=PACKAGE/'verification/work'/uuid.uuid4().hex;work.mkdir(parents=True)
    checks=[]
    def check(name,fn):
        fn();checks.append(name);print('PASS '+name,flush=True)
    def equal(a,b):
        if isinstance(a,np.ndarray) or isinstance(b,np.ndarray):assert np.array_equal(a,b)
        elif isinstance(a,dict):
            assert a.keys()==b.keys(),(a.keys(),b.keys())
            for key in a:equal(a[key],b[key])
        elif isinstance(a,(list,tuple)):
            assert len(a)==len(b)
            for x,y in zip(a,b):equal(x,y)
        else:assert a==b,(a,b)
    config=run_configuration(PACKAGE/'config.json',str(work/'output'))
    reference=pickle.loads((PACKAGE/'verification/reference.pkl').read_bytes())
    config['production_namespace']=reference['namespace'];config.pop('configuration_sha256');config['configuration_sha256']=hashlib.sha256(json.dumps(config,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    frozen=work/'RUN_CONFIG.json';frozen.write_text(json.dumps(config));os.environ['SG_RUN_CONFIG']=str(frozen)
    c,runner=activate(config);g=c.original;policy=c.local_module('policy');admission=c.local_module('admission_r4')
    check('default schedule exactly equals 126-slot reference per root',lambda:equal(g.schedule(),reference['schedule']))
    def samples():
        for row in reference['samples']:
            z=row['meta'];T,meta=g.sample(row['root'],z['primary'],z['secondary'],z['sign'],z['secondary_sign'],z['pool'],row['id'],c.NAMESPACE)
            equal(T,row['T']);equal(meta,z)
    check('630 seeded trait samples exactly match validated sampling',samples)
    def arithmetic():
        for row in reference['cases']:
            y,noise,audit=g.build(row['root'],row['T'],c.NAMESPACE,row['id'],config,reference=row.get('refs'))
            equal(y,row['y']);equal(noise,row['noise']);equal(audit,row['audit'])
            equal(g.model.features(g.models()[0][row['root']],y[None,:]),row['features'])
            if 'scores' in row:equal([float(g.design_context.c.core_score(g.models()[0][row['root']],y[None,:],t)[0]) for t in range(5)],row['scores'])
            if 'profile' in row:
                score=g.design_context.c.core_score(g.models()[0][row['root']],y[None,:],row['meta']['primary'])[0]
                equal(g.assess_profile(row['root'],y,row['T'],row['meta'],score,config,None,g.reversion_keys(audit)),row['profile'])
            if 'qualification' in row:equal(g.model.old.bank.full_qualification(g.models()[0][row['root']],y[None,:],row['T'][None,:],np.array(row['refs'])),row['qualification'])
    check('55 complete tables, noise, per-cell audits, metrics, readout and far trimming exactly match',arithmetic)
    def sources():
        src=PACKAGE/'src'
        for file,key,names in [('resolution_selection.py','selector',['play_eligible','select_resolution','resolution_summary','coverage_resolution']),('repair_batch.py','repair',['apply_batch']),('reach_witness.py','witness',['envelope','geometry'])]:
            for name in names:assert body((src/file).read_text(),name)==body(reference['sources'][key],name),(file,name)
        assert body((src/'screen_v8.py').read_text(),'execute_batch')==body(reference['sources']['execute_batch'],'execute_batch')
        old=reference['sources']['screen'].replace('budget_seconds=min(300,budget_seconds)','budget_seconds=min(1800,budget_seconds)').replace("'complete_loop_cap':300,'target':200","'infrastructure_safety_cap':1800,'wall_clock_admission_limit':None")
        assert body((src/'screen_v8.py').read_text(),'screen')==body(old,'screen_selection300')
    check('selector, batch mechanics, screen traversal and reach witness have identical scientific function bodies',sources)
    def configuration():
        import settings
        template=json.loads((PACKAGE/'config.json').read_text());changed=copy.deepcopy(template)
        changed['quotas_per_root']={'A':20,'B':10,'C_iid':10,'C_near':32,'C_far':10}
        settings.validate(changed)
        original=dict(config['quotas_per_root']);config['quotas_per_root']=changed['quotas_per_root']
        schedule=g.schedule();counts=collections.Counter(z['pool'] for z in schedule);assert dict(counts)==changed['quotas_per_root']
        for pool,n in changed['quotas_per_root'].items():
            by=collections.Counter(c.actual_stratum(z,pool) for z in schedule if z['pool']==pool)
            assert all(k==n//len(c.strata(pool)) for k in by.values())
        config['quotas_per_root']=original
        for change in ({'A':61},{'C_near':17}):
            bad=copy.deepcopy(template);bad['quotas_per_root'].update(change)
            try:settings.validate(bad)
            except ValueError:pass
            else:raise AssertionError('Unbalanced quotas accepted')
        saved=copy.deepcopy(config['ranges']);config['ranges'].update(primary=[.4,.55],far_primary=[.7,1.],secondary=[.22,.32],other_background=[.14,.24],reserved_partner_background=[.11,.16],secondary_gap=.06)
        for row in reference['samples'][:126]:
            z=row['meta'];T,_=g.sample(row['root'],z['primary'],z['secondary'],z['sign'],z['secondary_sign'],z['pool'],row['id'],c.NAMESPACE)
            assert .7<=abs(T[z['primary']])<=1 if z['pool']=='C_far' else .4<=abs(T[z['primary']])<=.55
            assert abs(T[z['secondary']])>=max(abs(T[t]) for t in range(5) if t not in (z['primary'],z['secondary']))+.06-1e-12
        config['ranges']=saved
    check('nondefault quotas/ranges, balanced strata and invalid-settings refusal',configuration)
    def batches():
        row=reference['cases'][0];m=g.models()[0][row['root']];keys=[k for k in m['cells'] if row['y'][m['pos'][k]]!=m['stock'][m['pos'][k]]][:3]
        state={'y':row['y'].tolist(),'noise':row['noise'].tolist(),'audit':row['audit'],'repair_rounds':0,'redraws':{},'reverts':[],'batches':[]}
        report={'groups':[{'results':[{'cell':dict(move=key[0],property=key[1]),'status':'REJECTED' if i<2 else 'UNRESOLVED','reason':'software fixture'} for i,key in enumerate(keys)]}]}
        item={'id':row['id'],'root':row['root'],'traits':row['T'].tolist(),'namespace':c.NAMESPACE,'meta':row['meta']}
        def constructor(*a,**k):return row['y'].copy(),row['noise'],row['audit']
        record=__import__('repair_batch').apply_batch(item,state,report,config,constructor=constructor)
        assert record['fully_assessed_failures']==3 and len(record['actions'])==3
        assert [r['kind'] for r in state['reverts']].count('redraw cannot change value')==2
        assert [r['kind'] for r in state['reverts']].count('unobservable selected effect')==1
        assert admission.failing_cells({'groups':[{'status':'UNRESOLVED','results':[]}]})==({},set())
    check('joint repair, identical redraw skip, immediate unresolved reversion and absent evidence',batches)
    def admission_loop():
        row=reference['cases'][0];m=g.models()[0][row['root']]
        item={'id':'software-loop','root':row['root'],'pool':'A','traits':row['T'].tolist(),'namespace':c.NAMESPACE,'meta':row['meta'],'initial_vector':row['y'].tolist(),'initial_noise':row['noise'].tolist(),'initial_audit':row['audit'],'admission_references':{'A':[],'B':[]},'reference':None,'context':{},'execution_revision':'R4'}
        home=work/'loop-home';folder=c.HOT/'loop';cc=c.item_config(config,item);calls=[]
        api=c.local_module('runtime_api');old_validate=api.validate;old_context=api.context_for;old_batch=admission.apply_batch;old_assess=g.assess_profile
        def validate(*a,**kw):
            calls.append(1);return {'verdict':'SCREEN_INCOMPLETE','screen_passed':False,'groups':[{'results':[{'cell':{'move':'STAND_A','property':'attack.HitDamage'},'status':'UNRESOLVED','reason':'software fixture'}]}],'reason':'unobservable software fixture','output':str(work/'fake-screen')}
        def batch(item,state,report,config,final=False,**kw):
            if final:state['final_reversion_done']=True
            else:state['repair_rounds']+=1
            r={'changed':True,'stage':'final_reversion' if final else 'repair'};state['batches'].append(r);return r
        api.validate=validate;api.context_for=lambda item:{};admission.apply_batch=batch;g.assess_profile=lambda *a,**kw:{'passed':True}
        try:
            result=admission.run_job(item,home,folder,cc,work/'no-pause')
            assert len(calls)==5 and result['state']=='assessed' and not result['admitted']
            repeated=admission.run_job(item,home,folder,cc,work/'no-pause');assert len(calls)==5 and repeated['reused_candidate_commit']
        finally:api.validate=old_validate;api.context_for=old_context;admission.apply_batch=old_batch;g.assess_profile=old_assess
    check('actual admission adapter max five screens and completed-commit reuse without repeat screening',admission_loop)
    def checkpoint():
        rows=[]
        for root in config['roots']:
            rows.extend({'root':root,'pool':'A'} for _ in range(10))
        assert policy.checkpoint_ready('first_50_A',rows,config['roots'])
        assert not policy.checkpoint_ready('first_50_A',rows[:-1],config['roots'])
        far=[{'root':root,'pool':'C_far'} for root in config['roots'] for _ in range(2)]
        assert policy.checkpoint_ready('first_10_far',far,config['roots'])
        assert not policy.checkpoint_ready('first_10_far',far[:-1],config['roots'])
    check('balanced first-50-A and first-ten-far checkpoint trigger boundaries',checkpoint)
    def integrity():
        from gmtv.storage import commit,load_commit
        path=work/'fixture.json';commit(path,'binding',{'value':1});assert load_commit(path,'binding')=={'value':1}
        x=json.loads(path.read_text());x['payload']['value']=2;path.write_text(json.dumps(x));assert load_commit(path,'binding') is None
        for target in (PACKAGE/'outside.csv',work/'outside.csv'):
            try:c.authorise_output(target,c.NAMESPACE,config)
            except RuntimeError:pass
            else:raise AssertionError('Escaped output guard')
    check('hash-bound commits reject corruption and writes outside run',integrity)
    def private_archive():
        Store=c.local_module('sealed_store').Store;hot=work/'private-test';store=Store(hot,'software-test')
        store.put('job:secret',{'id':'private-test-marker'});assert store.get('job:secret')['id']=='private-test-marker'
        assert b'private-test-marker' not in store.path.read_bytes()
        store.finalise()
        try:Store(hot,'software-test')
        except RuntimeError:pass
        else:raise AssertionError('Sealed archive reopened')
    check('Windows encrypted archive, no plaintext C export and sealed-reopen refusal',private_archive)
    def shared_engine():
        api=c.local_module('runtime_api')
        expected=PACKAGE.parent/'engine/observation_enabled_v1/FightingICE.observation-enabled.jar'
        assert api.runtime_source('FightingICE.jar')==expected
        assert not (PACKAGE/'assets/runtime/FightingICE.jar').exists()
        manifest=json.loads((PACKAGE/'assets/runtime_manifest.json').read_text())
        row=next(r for r in manifest['files'] if r['path']=='FightingICE.jar')
        assert c.sha(expected)==row['sha256']
        release=json.loads(c.RELEASE.read_text())
        assert release['shared_engine']['sha256']==row['sha256']
        assert (PACKAGE/release['shared_engine']['relative_path']).resolve()==expected.resolve()
    check('one shared approved engine, exact frozen bytes, no bundled engine duplicate',shared_engine)
    def shared_engine_guards():
        api=c.local_module('runtime_api');saved=c.BASE
        fixture=work/'relocated approved work';package=fixture/'renamed generator';package.mkdir(parents=True)
        engine=fixture/'engine/observation_enabled_v1/FightingICE.observation-enabled.jar';engine.parent.mkdir(parents=True)
        try:
            c.BASE=package
            # A stale local copy must never conceal a missing approved engine.
            stale=package/'assets/runtime/FightingICE.jar';stale.parent.mkdir(parents=True);stale.write_bytes(b'stale')
            try:api.runtime_source('FightingICE.jar')
            except RuntimeError as e:assert 'missing' in str(e)
            else:raise AssertionError('Missing shared engine accepted')
            engine.write_bytes(b'corrupt')
            try:api.runtime_source('FightingICE.jar')
            except RuntimeError as e:assert 'checksum mismatch' in str(e)
            else:raise AssertionError('Corrupt shared engine accepted')
            engine.unlink();os.link(saved.parent/'engine/observation_enabled_v1/FightingICE.observation-enabled.jar',engine)
            assert api.runtime_source('FightingICE.jar')==engine
            try:api.runtime_source('../escape.jar')
            except ValueError:pass
            else:raise AssertionError('Runtime path traversal accepted')
        finally:c.BASE=saved
    check('relative shared-engine relocation, missing/corrupt engine refusal and no duplicate fallback',shared_engine_guards)
    def provision():
        api=c.local_module('runtime_api');a=c.HOT/'provision-test-a';b=c.HOT/'provision-test-b'
        api.provision(a);api.provision(b)
        mirror=c.HOT/'runtime_assets/FightingICE.jar'
        assert (a/'runtime/FightingICE.jar').stat().st_ino==mirror.stat().st_ino
        assert (b/'runtime/FightingICE.jar').stat().st_ino==mirror.stat().st_ino
        assert (a/'runtime/data/characters/ZEN/Motion.csv').stat().st_ino!=(b/'runtime/data/characters/ZEN/Motion.csv').stat().st_ino
        assert (a/'stock_reference/ZEN/Motion.csv').read_bytes()==(PACKAGE/'assets/stock_reference/ZEN/Motion.csv').read_bytes()
        api.directory_link(a/'runtime/data/characters/SOFTWARE_TEST_GRAPHICS',a/'runtime/data/characters/ZEN')
        assert (a/'runtime/data/characters/SOFTWARE_TEST_GRAPHICS').is_junction()
    check('verified run-local assets, immutable hard links, isolated mutable tables and owned graphics junction',provision)
    def paused_resume():
        row=reference['cases'][0];item={'id':'software-interruption','root':row['root'],'pool':'A','traits':row['T'].tolist(),'namespace':c.NAMESPACE,'meta':row['meta'],'initial_vector':row['y'].tolist(),'initial_noise':row['noise'].tolist(),'initial_audit':row['audit'],'admission_references':{'A':[],'B':[]},'reference':None,'context':{},'execution_revision':'R4','slot_key':'ZEN/0','stratum':[row['meta']['primary'],row['meta']['sign']]}
        cc=c.item_config(config,item);pause=work/'test-pause';folder=c.HOT/'interrupted';api=c.local_module('runtime_api');old=api.validate;old_context=api.context_for;old_profile=g.assess_profile;hashes=[]
        def validate(path,*a,**kw):
            hashes.append(hashlib.sha256(Path(path).read_bytes()).hexdigest())
            if len(hashes)==1:pause.write_text('{}')
            return {'verdict':'SCREEN_PASSED','screen_passed':True,'groups':[],'output':str(work/'software-screen')}
        api.validate=validate;api.context_for=lambda item:{};g.assess_profile=lambda *a,**kw:{'passed':True}
        try:
            first=admission.run_job(item,work/'home',folder,cc,pause);assert first['state']=='paused'
            pause.unlink();second=admission.run_job(item,work/'home',folder,cc,pause);assert second['admitted'] and len(hashes)==2 and hashes[0]==hashes[1]
            from gmtv.storage import load_commit
            assert load_commit(folder/'COMMIT.json',c.item_binding(config,item)) is not None
            state={'decisions':{},'accepted_slots':{}};saved=policy.distance_reasons;policy.distance_reasons=lambda *args:[]
            try:
                integrated=runner.integrate(state,item,second,[],config);assert integrated and runner.integrate(state,item,second,[],config) is False
                assert len(state['accepted_slots'])==1 and len(state['decisions'])==1
            finally:policy.distance_reasons=saved
        finally:api.validate=old;api.context_for=old_context;g.assess_profile=old_profile
    check('interrupted admission resumes identical bytes and coordinator integrates its commit exactly once',paused_resume)
    def spawning():
        import multiprocessing as mp
        tasks=mp.Queue();output=mp.Queue();tasks.put(None)
        p=mp.Process(target=runner.worker_entry,args=(0,tasks,output));p.start();p.join(30)
        if p.is_alive():p.terminate();p.join();raise AssertionError('Worker bootstrap stalled')
        assert p.exitcode==0,p.exitcode
    check('real Windows-spawn worker boots final runtime and exits without gameplay',spawning)
    def dependencies():
        spec=importlib.util.find_spec('pilot_v3');assert spec is None,'Historical helper leaked into approved runtime'
        forbidden=['synthetic_generator_trait_review_2026_10_31','general_move_table_validator_2026_10_28']
        for module in list(sys.modules.values()):
            p=getattr(module,'__file__',None)
            if p:assert not any('/'+x+'/' in str(p).replace('\\','/') for x in forbidden),p
    check('runtime imports are independent of historical research folders',dependencies)
    retention_path=PACKAGE/'verification/test_retention.py'
    spec=importlib.util.spec_from_file_location('_generator_retention_controls',retention_path)
    controls=importlib.util.module_from_spec(spec);spec.loader.exec_module(controls)
    checks.extend(controls.run_checks(work))
    report={'passed':True,'checks':checks,'check_count':len(checks),'seeded_samples':630,'exact_constructed_tables':55,'gameplay_calls':0,'new_catalogue_generation':False,'sealed_historical_archives_opened':0,'scope':'Software equivalence/integration. Existing live validation provenance is retained; no new live re-screen claimed.'}
    out=PACKAGE/'verification/SOFTWARE_CHECKS.json';out.parent.mkdir(exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
if __name__=='__main__':main()

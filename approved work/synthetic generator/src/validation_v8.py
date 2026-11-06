"""Public two-argument bounded screening interface."""
import argparse,json,os,time
from pathlib import Path
import screen_v8 as s
from gmtv.fingerprint import instrument
from gmtv.storage import Lock,load_commit

def validate(candidate_motion_csv,base_character,*,home=None,budget_seconds=150,context=None):
    budget_seconds=min(1800,budget_seconds)
    started=time.perf_counter();root=str(base_character).upper();path=Path(candidate_motion_csv)
    try:
        if root not in s.ROOTS:raise ValueError('Unknown stock root')
        checksum=s.sha(path)
        if home is None:home=os.environ.get('GMTV_HOME')
        if home is None:raise ValueError('A run-local runtime must be provided')
        home=Path(home)
        if not (home/'runtime/FightingICE.jar').exists():raise ValueError('Private runtime not prepared: '+str(home))
        if context is None:
            import pickle
            cache=home.parents[1]/'MODEL_CACHE.pkl'
            if not cache.exists():raise ValueError('Aggregate stock usage context missing; provide a prepared V8 home or context')
            data=pickle.loads(cache.read_bytes());m=data['models'][root]
            context={'usage':{n:float(data['usage'].get((root,n),0)) for n in m['names']}}
        code={'screen_sha256':s.sha(Path(s.__file__)),'policy':s.digest(s.POLICY),'context':s.digest(context or {}),'instrument':instrument()['instrument_sha256'],
            'api_sha256':s.sha(Path(__file__)),'selection_sha256':s.sha(Path(__file__).with_name('selection_v8.py')),'execution_v14':s.sha(Path(__file__).with_name('execution_v14.py')),'dependencies':s.sha(Path(__file__).with_name('dependencies.py')),'early_probe':s.sha(Path(__file__).with_name('early_probe.py')),'probe_retry':s.sha(Path(__file__).with_name('probe_retry.py')),
            'stock':s.sha(home/'stock_reference'/root/'Motion.csv'),'zen':s.sha(home/'stock_reference/ZEN/Motion.csv')}
        code['batch_overlay_sha256']=V27_SELECTION_SHA
        output=home/'screens'/root/checksum/s.digest(code)
        with Lock(home/'VALIDATOR.lock'):
            old=load_commit(output/'SCREEN_COMMIT.json',s.screen_binding(checksum,context))
            if old is not None:return {**old,'original_execution_seconds':old['seconds'],'seconds':time.perf_counter()-started,'cached_screen_commit':True,'output':str(output),'screen_source_sha256':code['screen_sha256']}
            remaining=budget_seconds-(time.perf_counter()-started)
            if remaining<1:return {'verdict':'SCREEN_INCOMPLETE','screen_passed':False,'valid':False,'reason':'Budget spent before gameplay','seconds':time.perf_counter()-started}
            result=s.screen(path,root,home,output,remaining,context=context)
        return {**result,'seconds':time.perf_counter()-started,'screen_source_sha256':code['screen_sha256'],'output':str(output)}
    except OSError as error:
        return {'verdict':'INFRASTRUCTURE_FAILURE','screen_passed':False,'valid':False,'reason':str(error),'seconds':time.perf_counter()-started}
    except (ValueError,TypeError) as error:
        return {'verdict':'SCREEN_REJECTED','screen_passed':False,'valid':False,'reason':str(error),'seconds':time.perf_counter()-started}

V27_SELECTION_SHA='7d69e89144d5101b9d6dfc1668d3541caf8a5fb6c2d2ee4f9b40055c4a98448f'

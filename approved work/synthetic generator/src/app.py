"""Public single-process launcher and configuration freeze."""
import argparse,datetime,hashlib,json,os,subprocess,sys
from pathlib import Path
import settings
PACKAGE=settings.PACKAGE

def run_configuration(path,output=None):
    path=Path(path).resolve();user=settings.validate(json.loads(path.read_text(encoding='utf-8')))
    folder=Path(os.path.expandvars(output or user['output_directory'])).expanduser()
    if not folder.is_absolute():folder=path.parent/folder
    folder=folder.resolve()
    if not path.is_relative_to(PACKAGE) or not folder.is_relative_to(PACKAGE):raise ValueError('Keep configuration and output inside the synthetic generator folder')
    if folder==PACKAGE or PACKAGE.is_relative_to(folder) or folder.is_relative_to(PACKAGE/'src') or folder.is_relative_to(PACKAGE/'assets'):
        raise ValueError('Output must be separate from release sources/assets')
    frozen=json.loads((PACKAGE/'assets/frozen_design.json').read_text())
    release=json.loads((PACKAGE/'RELEASE.json').read_text())
    result={**frozen,**user,'roots':list(settings.ROOTS),'authorised_hot':str(folder),'production_write_enabled':True,
            'retain_evidence':user.get('retain_evidence',True),
            'production_namespace':'synthetic-generator-v1:'+user['run_id'],'diagnostic_namespace':'diagnostic-only',
            'runtime_reference_vectors':{},'production_max_draws_per_stratum':user['stops']['max_draws_per_slot'],
            'pool_acceptance_check_minimum_completed':user['stops']['minimum_completed_per_pool'],
            'acceptance_check_minimum_completed':user['stops']['minimum_completed_forecast'],
            'execution_policy_sha256':settings.checksum({'release':release['checksum'],'screens':5,'repair_rounds':3,'per_probe_seconds':[20,40],'identical_probe_retries':1,'safety_seconds':1800}),
            'release_checksum':release['checksum'],'configuration_source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'screen_hard_cap_seconds':1800,'screen_target_seconds':200,'wall_clock_admission_limit':None,
            'infrastructure_safety_cap_seconds':1800,'same_input_timeout_retry_limit':0,
            'repair':'Three joint repair rounds, final joint reversion, at most five logical screens; unobservable and identical-redraw reverts in the same batch.'}
    result.pop('configuration_sha256',None)
    result['configuration_sha256']=settings.checksum(result)
    return result

def activate(config):
    if sys.version_info[:2]!=(3,12):raise RuntimeError('This frozen release requires Python 3.12')
    settings._config=config
    import common as c
    c.verify_release()
    import runtime_api
    runtime_api.install()
    runner=c.local_module('catalogue')
    import gmtv.status
    runner.best_effort_status=gmtv.status.best_effort_status
    return c,runner

def restore_worker():
    """Register worker target before Windows spawn unpickles it."""
    if os.environ.get('SG_RUN_CONFIG'):
        activate(settings.current())

def main(argv=None):
    parser=argparse.ArgumentParser(description='Frozen synthetic FightingICE generator. Run once; pause/resume safely.')
    parser.add_argument('--action',choices=('Run','Resume','Pause','Status','Check'),default='Run')
    parser.add_argument('--config',type=Path,default=PACKAGE/'config.json')
    parser.add_argument('--output',help='Override output folder (use the identical folder again on Resume)')
    parser.add_argument('--workers',type=int,help='Concurrency override; does not alter character seeds')
    parser.add_argument('--background',action='store_true',help='Launch a hidden dedicated coordinator and return')
    a=parser.parse_args(argv);config=run_configuration(a.config,a.output);hot=Path(config['authorised_hot'])
    if a.action=='Status':
        p=hot/'status.json'
        print(p.read_text(encoding='utf-8') if p.exists() else json.dumps({'state':'not_started','output':str(hot)}));return 0
    if a.action=='Pause':
        if not (hot/'RUN_CONFIG.json').exists():raise RuntimeError('No run exists at this output folder')
        from gmtv.storage import atomic
        atomic(hot/'PAUSE_REQUESTED',{'reason':'User pause'});print('Pause requested; committed work is retained.');return 0
    if a.action=='Check':
        c,runner=activate(config)
        if not __import__('shutil').which('java') or not __import__('shutil').which('javac'):raise RuntimeError('Java and javac must be on PATH')
        import importlib.metadata as md
        expected=json.loads((PACKAGE/'provenance/ENVIRONMENT.json').read_text())['packages']
        for name,version in expected.items():
            if md.version(name)!=version:raise RuntimeError('Pinned dependency differs: '+name)
        for record in json.loads((PACKAGE/'assets/runtime_manifest.json').read_text())['files']:
            if c.sha(__import__('runtime_api').runtime_source(record['path']))!=record['sha256']:raise RuntimeError('Engine asset mismatch: '+record['path'])
        schedule=c.original.schedule()
        if len(schedule)*len(config['roots'])!=c.TOTAL:raise RuntimeError('Configured schedule count mismatch')
        print(json.dumps({'passed':True,'total':c.TOTAL,'quotas_per_root':c.QUOTAS,'output':str(hot),'retain_evidence':config['retain_evidence'],'gameplay_calls':0,'candidate_writes':0}));return 0
    if os.name!='nt':raise RuntimeError('This release requires Windows DPAPI and junction support')
    if a.workers is not None and not 1<=a.workers<=64:raise ValueError('workers must be 1..64')
    workers=a.workers or config['workers']
    hot.mkdir(parents=True,exist_ok=True)
    frozen_path=hot/'RUN_CONFIG.json'
    from gmtv.storage import atomic,Lock
    with Lock(hot/'LAUNCH.lock'):
        if frozen_path.exists():
            prior=json.loads(frozen_path.read_text())
            if prior!=config:raise RuntimeError('Run configuration changed. Restore its exact config or select a new output/run_id.')
            if (hot/'PRODUCTION_COMPLETED.json').exists():
                print(json.dumps({'state':'complete_review_required','message':'Already completed; no archive reopened, no workers started','output':str(hot)}));return 0
            if a.action=='Run':raise RuntimeError('This run already exists. Use Resume.')
        else:
            if a.action=='Resume':raise RuntimeError('No committed run to resume. Use Run.')
            foreign=[p for p in hot.iterdir() if p.name!='LAUNCH.lock']
            if foreign:raise RuntimeError('New output folder must be empty')
            atomic(frozen_path,config)
            atomic(hot/'RELEASE_BINDING.json',{'release_checksum':config['release_checksum'],'configuration_sha256':config['configuration_sha256'],'split_frozen':False})
        index=PACKAGE/'generated characters'/('RUN_'+config['run_id']+'.json')
        record={'run_id':config['run_id'],'output_directory':hot.relative_to(PACKAGE).as_posix(),'status_file':(hot/'status.json').relative_to(PACKAGE).as_posix(),'configuration_sha256':config['configuration_sha256'],'release_checksum':config['release_checksum'],'target':5*sum(config['quotas_per_root'].values()),'C_records':'aggregate only; encrypted archive at output','final_dataset_membership_decided':False}
        if index.exists() and json.loads(index.read_text())!=record:raise RuntimeError('Run ID already indexes a different catalogue; choose a new run_id')
        atomic(index,record)
        os.environ['SG_RUN_CONFIG']=str(frozen_path)
        if a.background:
            # Subprocess owns a hidden process group; no visible terminal.
            cmd=[sys.executable,'-u',str(PACKAGE/'generator.py'),'--action','Resume','--config',str(a.config.resolve()),'--output',str(hot),'--workers',str(workers)]
            with (hot/'coordinator.stdout.log').open('ab') as stdout,(hot/'coordinator.stderr.log').open('ab') as stderr:
                process=subprocess.Popen(cmd,cwd=str(PACKAGE),stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW|subprocess.CREATE_NEW_PROCESS_GROUP)
            atomic(hot/'LAUNCH.json',{'pid':process.pid,'command':cmd,'started_Perth':datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()})
            print(json.dumps({'pid':process.pid,'output':str(hot),'workers':workers}));return 0
    c,runner=activate(config)
    with Lock(hot/'CAMPAIGN.lock'):
        (hot/'PAUSE_REQUESTED').unlink(missing_ok=True)
        reason=runner.run(workers)
    print(json.dumps({'stop_reason':reason,'output':str(hot),'split_frozen':False}));return 0


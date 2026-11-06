"""One infrastructure retry for an identical timed-out fixture, never a verdict."""
from pathlib import Path
from execution_v14 import ScreenBudgetExceeded
from gmtv.schema import digest,sha
from gmtv.storage import commit,load_commit

class ProbeRetryMixin:
    def retry_identity(self,spec,role):
        return {'spec':spec,'role':role,'motion_sha256':dict(self.hashes),'controller_sha256':self.controller_hash,'horizon_policy_sha256':sha(__import__('gmtv.fast',fromlist=['fixed_horizon']).__file__),
            'stock_zen_sha256':sha(self.runtime/'data/characters/ZEN/Motion.csv')}

    def retry_ledger(self):
        binding=digest({'input':dict(self.hashes),'controller':self.controller_hash,'retry_source':sha(__file__)})
        path=self.output/'PROBE_TIMEOUT_RETRIES.json'
        value=load_commit(path,binding)
        if value is None:
            if path.exists():raise RuntimeError('Probe retry ledger failed integrity validation')
            value={'timeouts':{},'events':[],'completed_after_retry':[]}
        return path,binding,value

    async def execute(self,spec,role):
        identity=self.retry_identity(spec,role);key=digest(identity)
        path,binding,ledger=self.retry_ledger()
        count=ledger['timeouts'].get(key,0)
        if count>=2:raise ScreenBudgetExceeded('Identical probe timed out twice; remains incomplete; no third attempt')
        recovered=key in ledger.get('completed_after_retry',[])
        while True:
            self.check_budget()
            if count and not recovered: self.probe_timeout_retries=getattr(self,'probe_timeout_retries',0)+1
            try:
                record=await super().execute(spec,role)
                if digest(self.retry_identity(spec,role))!=key:raise RuntimeError('Probe retry identity changed')
                if count and not recovered:
                    if record.get('load_verified') and not record.get('infrastructure_failure'):ledger['completed_after_retry'].append(key)
                    ledger['events'].append({'fixture_identity':identity,'timeout_count':count,'outcome':'probe_completed_after_retry','fixture_id':record.get('fixture_id')})
                    commit(path,binding,ledger)
                return record
            except ScreenBudgetExceeded as error:
                if not str(error).startswith('Per-probe wall limit reached'):raise
                if digest(self.retry_identity(spec,role))!=key:raise RuntimeError('Timed-out probe identity changed') from error
                count+=1;self.probe_timeouts=getattr(self,'probe_timeouts',0)+1
                ledger['timeouts'][key]=count
                ledger['events'].append({'fixture_identity':identity,'timeout_count':count,'outcome':'incomplete_timeout',
                    'engine_log':str(self.log) if self.log else None,'reason':str(error)})
                commit(path,binding,ledger)
                # A fresh engine guarantees reset state; the spec, role, table
                # bytes, input phases, horizon function and controller stay fixed.
                await self.shutdown()
                if self.paused():raise InterruptedError('Paused before identical infrastructure retry')
                if count>=2:raise ScreenBudgetExceeded('Identical probe timed out twice; remains incomplete; no third attempt') from error
                self.check_budget()

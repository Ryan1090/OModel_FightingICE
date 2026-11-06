import common as c
"""Reviewable forecast sampling proposal. Not installed by this module."""
def calculate(state,elapsed,accepted,completed,workers,signature,bootstrap=None):
    window=state.get('stable_forecast_window')
    if window is None or window['workers']!=workers or window['signature']!=signature:
        initial=bootstrap or {'active_seconds':elapsed,'accepted':accepted,'completed':completed}
        window={'workers':workers,'signature':signature,'active_start':initial['active_seconds'],'accepted_start':initial['accepted'],'completed_start':initial['completed']}
        state['stable_forecast_window']=window
    active=max(0,elapsed-window['active_start']);added=accepted-window['accepted_start'];decisions=completed-window['completed_start']
    qualified=active>=c.load_config()['stops']['forecast_minimum_seconds'] and decisions>=c.load_config()['stops']['forecast_minimum_decisions']
    total=elapsed+active/added*(c.TOTAL-accepted) if added>0 else None
    return {'projected_total_seconds':total,'projected_remaining_seconds':max(0,total-elapsed) if total is not None else None,
        'forecast_qualified':qualified,'forecast_unbounded':qualified and added<=0,
        'forecast_basis':{'workers':workers,'active_seconds':active,'admissions':added,'completed_decisions':decisions,'minimum_active_seconds':c.load_config()['stops']['forecast_minimum_seconds'],'minimum_completed_decisions':c.load_config()['stops']['forecast_minimum_decisions'],'retained_across_same_worker_restarts':True}}

def stop(summary,config):
    policy=config['stops'];limit=policy['projection_limit_seconds']
    for pool,row in summary['pools'].items():
        threshold=policy['pool_minimum_acceptance'][pool]
        if threshold is not None and row['completed']>=policy['minimum_completed_per_pool'] and row['acceptance']<threshold:return 'Pool acceptance below configured threshold: '+pool
    if summary['elapsed_seconds']>limit:return 'Projection stop: elapsed active time exceeds limit'
    if summary['completed']>=policy['minimum_completed_forecast'] and summary['forecast_qualified'] and (summary['forecast_unbounded'] or summary['projected_total_seconds'] is not None and summary['projected_total_seconds']>limit):return 'Projected completion exceeds configured limit'
    return None

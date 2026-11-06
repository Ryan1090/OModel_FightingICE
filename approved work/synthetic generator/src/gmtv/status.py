"""One visible status, optionally carrying an enclosing validator evaluation."""
import json
import os
import time
from pathlib import Path
from .storage import atomic


def best_effort_status(path,payload):
    """Display failures must not discard or abort durable scientific commits."""
    try:atomic(path,payload);return True
    except OSError as error:
        try:
            log=Path(path).parent/'STATUS_WRITE_FAILURES.jsonl'
            with log.open('a',encoding='utf-8') as stream:
                stream.write(json.dumps({'path':str(path),'error':repr(error),'pid':os.getpid(),
                    'epoch':time.time(),'payload':payload,'effect':'display update skipped; durable evidence writes remain mandatory'})+'\n')
        except OSError:pass
        return False


def publish(hot,payload,local=None):
    if local:best_effort_status(local,payload)
    context=os.environ.get('GMTV_COHORT_CONTEXT');destination=os.environ.get('GMTV_COHORT_STATUS')
    if context:
        cohort=json.loads(Path(context).read_text())
        payload={**payload,'candidate_state':payload['state'],'candidate_progress':payload.get('progress'),
            'state':'running','activity':'single validator evaluation','evaluation':cohort,
            'progress':f"{cohort['completed']}/{cohort['total']} candidate inputs"}
    best_effort_status(Path(hot)/'status.json',payload)
    if destination:best_effort_status(destination,payload)

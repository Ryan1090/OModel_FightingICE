"""A detached entry point must never leave a running status after an error."""
import os
import sys
import time
import traceback
from pathlib import Path
from .storage import atomic


def guarded(main,default_run):
    try:return main()
    except BaseException as error:
        if isinstance(error,SystemExit) and error.code in (None,0):return
        try:
            args=sys.argv
            hot=Path(args[args.index('--hot')+1])
            run=args[args.index('--run')+1] if '--run' in args else default_run
            output=hot/run;output.mkdir(parents=True,exist_ok=True)
            atomic(output/'status.json',{'state':'technical_failure','error':repr(error),'pid':os.getpid(),
                'updated_epoch':time.time(),'not_final_evaluation':True,
                'meaning':'no scientific verdict inferred; committed evidence preserved'})
            (output/('failure.'+str(time.time_ns())+'.log')).write_text(traceback.format_exc(),encoding='utf-8')
        finally:raise

"""Run, resume, pause, inspect or software-check the frozen generator."""
import os,sys
from pathlib import Path
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
sys.path.insert(0,str(Path(__file__).resolve().parent/'python_lib'))
sys.path.insert(0,str(Path(__file__).resolve().parent/'src'))
from app import main,restore_worker
if __name__=='__mp_main__':restore_worker()
if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as error:
        print(type(error).__name__+': '+str(error),file=sys.stderr)
        raise SystemExit(1)

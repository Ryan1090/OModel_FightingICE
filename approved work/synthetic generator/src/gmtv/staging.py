"""Preserve name-selected stock bookkeeping without modifying the engine."""
import contextlib
import os
from pathlib import Path
from .storage import atomic
from .schema import sha


@contextlib.contextmanager
def canonical(runtime,root,identity,candidate,output):
    runtime=Path(runtime);output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    if root not in {'GARNET','LUD','NEZ'} or identity==root:
        yield identity;return
    target=runtime/'data/characters'/root/'Motion.csv'
    backup=output/'canonical_stock_motion_preserved.csv'
    if backup.exists():
        original=backup.read_bytes()
        if target.read_bytes() not in (original,Path(candidate).read_bytes()):
            raise RuntimeError('unrecognised runtime Motion contents; refusing to overwrite')
    else:
        original=target.read_bytes();backup.write_bytes(original)
    data=Path(candidate).read_bytes()
    temporary=target.with_name('Motion.gmtv-staging.tmp')
    journal={'root':root,'logical_diagnostic_identity':identity,'loaded_identity':root,
        'stock_sha256':sha(backup),'candidate_sha256':sha(candidate),'reason':'preserve exact-name-selected stock style bookkeeping',
        'engine_unchanged':True,'only_disposable_runtime_motion_staged':True}
    atomic(output/'STAGING.json',{**journal,'state':'staging'})
    temporary.write_bytes(data);os.replace(temporary,target)
    if sha(target)!=sha(candidate):raise RuntimeError('canonical staging mismatch')
    try:yield root
    finally:
        temporary.write_bytes(original);os.replace(temporary,target)
        if sha(target)!=sha(backup):raise RuntimeError('canonical stock restore mismatch')
        atomic(output/'STAGING.json',{**journal,'state':'stock_restored'})

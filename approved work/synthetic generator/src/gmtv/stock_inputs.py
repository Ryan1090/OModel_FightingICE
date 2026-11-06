"""Own immutable stock references, separate from disposable runtime staging."""
from pathlib import Path
import json
from .schema import ROOTS,sha,read


def references(hot):
    hot=Path(hot);manifest=json.loads((hot/'ASSET_MANIFEST.json').read_text());result={}
    for root in ROOTS:
        for filename in ('Motion.csv','gSetting.txt'):
            runtime=hot/'runtime/data/characters'/root/filename
            asset=next(x for x in manifest['files'] if Path(x['destination'])==runtime)
            if sha(runtime)!=asset['sha256']:raise RuntimeError('runtime stock was not restored: '+str(runtime))
            target=hot/'stock_reference'/root/filename
            target.parent.mkdir(parents=True,exist_ok=True)
            if not target.exists():target.write_bytes(runtime.read_bytes())
            if sha(target)!=asset['sha256']:raise RuntimeError('immutable stock reference mismatch: '+str(target))
        result[root]={'table':read(hot/'stock_reference'/root/'Motion.csv',root),
            'motion_sha256':sha(hot/'stock_reference'/root/'Motion.csv'),
            'width':int((hot/'stock_reference'/root/'gSetting.txt').read_text().split(',')[0])}
    return result

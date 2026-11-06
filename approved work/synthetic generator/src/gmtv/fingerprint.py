"""Bind probe caches to the installed controller implementation as well as ours."""
import importlib.metadata
import platform
from functools import lru_cache
from pathlib import Path
from .schema import digest,sha
from .engine import ENGINE_SHA


@lru_cache(maxsize=1)
def environment():
    sdk=importlib.metadata.distribution('pyftg')
    files={str(p).replace('\\','/'):sha(sdk.locate_file(p)) for p in sdk.files
        if str(p).endswith('.py') and str(p).replace('\\','/').startswith('pyftg/')}
    result={'python':platform.python_version(),'pyftg_version':sdk.version,'pyftg_source_files':files,
        'protobuf_version':importlib.metadata.version('protobuf')}
    return {**result,'sha256':digest(result)}


def instrument():
    source={p.name:sha(p) for p in sorted(Path(__file__).parent.glob('*.py'))}
    source['engine_evidence/CommandOracle.java']=sha(Path(__file__).resolve().parents[1]/'engine_evidence/CommandOracle.java')
    source_sha=digest(source);env=environment()
    return {'source_sha256':source_sha,'environment':env,'engine_sha256':ENGINE_SHA,
        'instrument_sha256':digest({'source_sha256':source_sha,'environment_sha256':env['sha256'],'engine_sha256':ENGINE_SHA})}

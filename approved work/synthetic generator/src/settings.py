"""Validated run settings, shared by sampling, inference and accounting."""
import copy,hashlib,json,os
from pathlib import Path
PACKAGE=Path(__file__).resolve().parents[1]
POOLS=('A','B','C_iid','C_near','C_far')
ROOTS=('ZEN','GARNET','LUD','KFM','NEZ')
_config=None
def checksum(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def validate(x):
 if x.get('schema_version')!=1:raise ValueError('Unsupported configuration schema')
 if type(x.get('retain_evidence',True)) is not bool:raise ValueError('retain_evidence must be true or false')
 if not isinstance(x.get('run_id'),str) or not x['run_id'] or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in x['run_id']):raise ValueError('run_id must use letters, digits, underscore or hyphen')
 if set(x['quotas_per_root'])!=set(POOLS):raise ValueError('All five pools are required')
 for p,n in x['quotas_per_root'].items():
  unit=16 if p=='C_near' else 10
  if type(n) is not int or n<=0 or n%unit:raise ValueError(p+' quota must be a positive multiple of '+str(unit)+' to preserve complete strata')
 if type(x['workers']) is not int or not 1<=x['workers']<=64:raise ValueError('workers must be 1..64')
 r=x['ranges'];keys={'primary','far_primary','secondary','other_background','reserved_partner_background','secondary_gap'}
 if set(r)!=keys:raise ValueError('Unexpected range keys')
 for k in keys-{'secondary_gap'}:
  v=r[k]
  if not isinstance(v,list) or len(v)!=2 or not all(type(a) in (int,float) for a in v) or not 0<v[0]<v[1]<=1:raise ValueError('Invalid magnitude range: '+k)
 gap=r['secondary_gap']
 if not isinstance(gap,(int,float)) or not 0<gap<1:raise ValueError('secondary_gap must be positive')
 if r['other_background'][1]+gap>r['secondary'][1]+1e-12:raise ValueError('Background range leaves no secondary headroom')
 if r['secondary'][1]+gap>r['primary'][0]+1e-12:raise ValueError('Primary range must remain separated from secondary')
 if r['reserved_partner_background'][1]>=r['secondary'][0]:raise ValueError('Reserved weak partner must stay below strong-secondary threshold')
 if r['far_primary'][0]<=r['primary'][1]:raise ValueError('Far primary range must exceed training primary range')
 if r['reserved_partner_background'][1]>r['other_background'][1]:raise ValueError('Reserved background exceeds ordinary background domain')
 s=x['stops']
 if s['projection_limit_seconds']<=0 or type(s['max_draws_per_slot']) is not int or s['max_draws_per_slot']<1:raise ValueError('Invalid stop limits')
 if set(s['pool_minimum_acceptance'])!=set(POOLS):raise ValueError('Missing acceptance threshold')
 for v in s['pool_minimum_acceptance'].values():
  if v is not None and (not isinstance(v,(int,float)) or not 0<=v<=1):raise ValueError('Invalid acceptance threshold')
 for k in ('minimum_completed_per_pool','minimum_completed_forecast','forecast_minimum_decisions'):
  if type(s[k]) is not int or s[k]<1:raise ValueError('Invalid stop sample size')
 if s['forecast_minimum_seconds']<=0:raise ValueError('Invalid forecast duration')
 return x
def current():
 global _config
 if _config is None:
  path=os.environ.get('SG_RUN_CONFIG')
  if not path:raise RuntimeError('Use generator.py with a configuration file')
  doc=json.loads(Path(path).read_text(encoding='utf-8'));h=doc.pop('configuration_sha256')
  if checksum(doc)!=h:raise RuntimeError('Run configuration checksum mismatch')
  _config={**doc,'configuration_sha256':h}
 return _config
def ranges():return current()['ranges']

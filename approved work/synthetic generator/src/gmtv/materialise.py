"""Stage one full diagnostic table without duplicating graphics or user data."""
import json
import hashlib
import os
import subprocess
from pathlib import Path
from .schema import sha
from .storage import atomic


def directory_link(target,source):
    target=Path(target);source=Path(source)
    if target.exists():
        if target.resolve()!=source.resolve():raise RuntimeError('unexpected existing graphics path '+str(target))
        return
    def literal(path):return "'"+str(path).replace("'","''")+"'"
    command='New-Item -ItemType Junction -Path '+literal(target)+' -Target '+literal(source)+' -ErrorAction Stop | Out-Null'
    result=subprocess.run(['powershell','-NoProfile','-NonInteractive','-Command',command],capture_output=True,text=True,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),timeout=30)
    if result.returncode:raise RuntimeError('graphics junction failed: '+result.stderr)


def stage(hot,candidate,root,input_sha):
    hot=Path(hot);runtime=hot/'runtime';stock=runtime/'data/characters'/root
    identity=root+'__GMTV_'+input_sha[:20];folder=runtime/'data/characters'/identity;folder.mkdir(parents=True,exist_ok=True)
    motion=folder/'Motion.csv'
    data=Path(candidate).read_bytes()
    if hashlib.sha256(data).hexdigest()!=input_sha or sha(candidate)!=input_sha:raise RuntimeError('input changed while staging')
    if motion.exists() and motion.read_bytes()!=data:raise RuntimeError('diagnostic identity collision; preserve evidence')
    if not motion.exists():motion.write_bytes(data)
    if sha(motion)!=input_sha:raise RuntimeError('staged Motion bytes do not match the submitted input')
    setting=folder/'gSetting.txt';source=stock/'gSetting.txt'
    if setting.exists() and setting.read_bytes()!=source.read_bytes():raise RuntimeError('diagnostic setting differs')
    if not setting.exists():setting.write_bytes(source.read_bytes())
    directory_link(folder/'graphics',stock/'graphics')
    atomic(hot/'diagnostics'/(root+'_'+input_sha+'.json'),{'identity':identity,'root':root,'motion_sha256':input_sha,
        'motion_path':str(motion),'permanently_pool_ineligible':True,'seed':'not generated; user input bytes',
        'graphics':'read-only shared stock assets; no duplicate graphics tree'})
    return identity

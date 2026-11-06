"""Conservative completion signal; every measured action must finish first."""
from gmtv.probe import Probe

def terminal_sample(sample,move,seen_source):
    me,op=sample['me'],sample['op']
    return bool(seen_source and me['action']!=move and me['action'] in ('STAND','CROUCH') and me['control']
        and op['control'] and op['state']!='AIR' and me['state']!='AIR'
        and not sample['projectiles'] and me['attack'].get('empty_flag',True) and op['attack'].get('empty_flag',True)
        and me['speed_x']==me['speed_y']==op['speed_x']==op['speed_y']==0)

def completion_frame(trace,move,issue_frame=-1):
    seen=False;stable=0
    for sample in trace:
        seen|=sample['frame']>issue_frame and sample['me']['action']==move
        stable=stable+1 if terminal_sample(sample,move,seen) else 0
        if stable>=12:return sample['frame']
    return None

class EarlyProbe(Probe):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.seen_source=False;self.stable=0
    def get_non_delay_frame_data(self,fd):
        old=self.previous_frame;super().get_non_delay_frame_data(fd)
        if not self.target or old==self.previous_frame or not self.trace or self.spec.get('followup') or self.spec.get('incoming_action'):return
        sample=self.trace[-1];self.seen_source|=sample['me']['action']==self.spec['move'] and self.issued and sample['frame']>self.started
        self.stable=self.stable+1 if terminal_sample(sample,self.spec['move'],self.seen_source) else 0
        if self.stable>=12:self.coordinator['observations_complete']=sample['frame']

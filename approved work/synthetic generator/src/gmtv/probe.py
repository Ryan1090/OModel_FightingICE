"""Data-constructed physical probes. No per-move recipe or prior evidence imports."""
from pyftg.aiinterface.ai_interface import AIInterface
from pyftg.aiinterface.command_center import CommandCenter
from pyftg.models.key import Key
import time
from .rules import COMMANDS


def character(c):
    return {'action':c.action.name,'state':c.state.name,'x':int(c.x),'y':int(c.y),
        'left':c.left,'right':c.right,'top':c.top,'bottom':c.bottom,'energy':c.energy,'hp':c.hp,
        'speed_x':c.speed_x,'speed_y':c.speed_y,'remaining':c.remaining_frame,
        'control':bool(c.control),'hit_confirm':bool(c.hit_confirm),'front':bool(c.front),
        'attack':c.attack_data.to_dict()}


class Probe(AIInterface):
    def __init__(self,spec,table,coordinator,sink,target=True):
        self.spec=spec;self.table=table;self.coordinator=coordinator;self.sink=sink;self.target=target
        self.cc=CommandCenter();self.fd=None;self.key=Key();self.trace=[];self.started=None
        self.ready_count=0;self.issued=False;self.followup_issued=False;self.request=None
        self.jump_at=None;self.previous_frame=None;self.inputs=[];self.preparation=[]
        self.first_frame_wall=None;self.last_frame_wall=None;self.issue_wall=None
    def name(self):return 'GMTV_TARGET' if self.target else 'GMTV_ZEN'
    def is_blind(self):return False
    def initialize(self,game_data,player_number):self.player=player_number
    def get_information(self,frame_data,is_control):pass
    def get_non_delay_frame_data(self,fd):
        self.fd=fd
        if fd.empty_flag:return
        now=time.perf_counter()
        if self.first_frame_wall is None:self.first_frame_wall=now
        self.last_frame_wall=now
        self.cc.set_frame_data(fd,self.player)
        if self.target and self.previous_frame!=fd.current_frame_number:
            self.previous_frame=fd.current_frame_number
            self.trace.append({'frame':fd.current_frame_number,'me':character(fd.get_character(self.player)),
                'op':character(fd.get_character(not self.player)),
                'projectiles':[p.to_dict() for p in fd.projectile_data]})
    def get_screen_data(self,*args):pass
    def get_audio_data(self,*args):pass
    def input(self):
        if self.fd is not None and not self.fd.empty_flag:
            c=self.fd.get_character(self.player)
            entry={'frame':self.fd.current_frame_number,'state':c.state.name,'front':bool(c.front),
                'keys':{k:bool(getattr(self.key,k)) for k in ('A','B','C','U','D','L','R')}}
            if self.target:self.inputs.append(entry)
            else:self.coordinator.setdefault('opponent_inputs',[]).append(entry)
        return self.key
    def game_end(self):pass
    def close(self):pass
    def command(self,action):
        if action in {'STAND','AIR'}:
            self.key=Key();return
        if not self.cc.get_skill_flag():self.cc.create_keys(COMMANDS[action])
        if self.cc.get_skill_flag():self.key=self.cc.get_skill_key()
    def processing(self):
        self.key=Key()
        if self.fd is None or self.fd.empty_flag:return
        c=self.fd.get_character(self.player);frame=self.fd.current_frame_number
        if self.cc.get_skill_flag():self.key=self.cc.get_skill_key();return
        prep=self.spec.get('energy_setup')
        if prep and not self.coordinator.get('energy_settled'):
            target=self.fd.get_character(self.player if self.target else not self.player)
            if self.target and target.energy>=prep['required_energy'] and 'energy_reached' not in self.coordinator:
                self.coordinator['energy_reached']=frame
                self.preparation.append({'frame':frame,'event':'energy_requirement_attained','energy':target.energy})
            reached=self.coordinator.get('energy_reached')
            if reached is not None:
                if frame-reached>=prep['settle_frames'] and target.control and target.speed_x==0:
                    self.coordinator['energy_settled']=frame
                return
            if frame>=prep['budget_frames']:
                self.coordinator['energy_setup_failure']='physical energy setup budget exhausted'
                return
            if self.target:
                self.key.L=c.front;self.key.R=not c.front
            elif c.control:
                other=self.fd.get_character(not self.player)
                row=self.spec['zen_rows'][prep['opponent_action']]
                # Compare actual body edges to stock attack reach relative to
                # the attacker's body. Never teleport or alter Motion/energy.
                centre=(c.left+c.right)/2;opcentre=(other.left+other.right)/2
                own=self.spec['zen_rows']['STAND']
                reach=row['attack.hitAreaRight']-(own['hitAreaLeft']+own['hitAreaRight'])/2
                if abs(centre-opcentre)<=reach-12:
                    if c.speed_x==0:self.command(prep['opponent_action'])
                else:
                    self.key.R=opcentre>centre;self.key.L=opcentre<centre
            return
        # Position in raw engine coordinates. Targets are computed from stock
        # body-relative geometry once and reused unchanged on the candidate.
        wanted=self.spec['target_x'] if self.target else self.spec['opponent_x']
        current_row=(self.table if self.target else self.spec['zen_rows'])[c.action.name]
        raw_x=c.left-(current_row['hitAreaLeft'] if c.front else c.graphic_size_x-current_row['hitAreaRight'])
        ready=self.coordinator.get('ready')
        if ready is None:
            error=wanted-raw_x
            # Friction is applied after movement. Brake before the anchor;
            # repeatedly back-stepping after overshoot creates an oscillation.
            speed=int(c.speed_x);stopping=abs(speed)*(abs(speed)+1)/2
            projected=error-(stopping if speed>0 else -stopping)
            tolerance=self.spec.get('placement_tolerance',6)
            wall_blocked=self.target and self.spec.get('rear_wall_anchor') and c.speed_x==0 and (
                c.left<=0 and error<0 or c.right>=960 and error>0)
            if not wall_blocked and abs(error)>tolerance and abs(projected)>3 and error*projected>0 and c.control:
                moving_forward=(error>0)==bool(c.front)
                if moving_forward:self.key.R=error>0;self.key.L=error<0
                else:self.command('BACK_STEP')
                self.ready_count=0
            elif c.speed_x==0 and (abs(error)<=tolerance or wall_blocked):self.ready_count+=1
            else:self.ready_count=0
            self.coordinator['target_ready' if self.target else 'opponent_ready']=self.ready_count>=4
            if self.coordinator.get('target_ready') and self.coordinator.get('opponent_ready'):
                # Engine GameSetting.INPUT_LIMIT=30. Remove positioning key
                # history before interpreting a walk/dash/special command.
                self.coordinator['ready']=frame+self.spec.get('input_history_settle_frames',35)
            return
        if frame<ready:return
        if not self.target:
            incoming=self.spec.get('incoming_action')
            if incoming:
                if self.coordinator.get('incoming_issued'):return
                if incoming.startswith('AIR'):
                    if self.jump_at is None and frame>=ready+self.spec.get('incoming_jump_delay',0) and c.control:
                        self.command('JUMP');self.jump_at=frame;return
                    if self.jump_at is None or frame-self.jump_at<self.spec['incoming_jump_age']:return
                elif frame<ready+self.spec.get('incoming_delay',0):return
                if c.control:
                    self.command(incoming);self.coordinator['incoming_issued']=frame
                return
            mode=self.spec.get('defence','passive')
            if mode in {'jump','air_guard'} and self.jump_at is None and frame>=ready+self.spec.get('opponent_jump_delay',0) and c.control:
                self.command('JUMP');self.jump_at=frame;return
            # Release guarding as soon as the first guard event has occurred.
            # Held inputs must not prolong the measured guard recovery.
            if 'GUARD_RECOV' in c.action.name:self.coordinator['guard_event']=True
            if not self.coordinator.get('guard_event'):
                if mode=='stand_guard':self.key.L=c.front;self.key.R=not c.front
                if mode=='crouch_guard':
                    self.key.L=c.front;self.key.R=not c.front;self.key.D=True
                # Guarded-contact scenarios continue holding back after the
                # jump lands. The actual contact posture is measured; a late
                # projectile must not hit an accidentally passive defender.
                if mode=='air_guard':self.key.L=c.front;self.key.R=not c.front
            return
        action=self.spec['move'];row=self.table[action]
        if frame<ready+self.spec.get('target_wait_frames',0):return
        airborne=action.startswith('AIR')
        if airborne and self.jump_at is None:
            self.command('JUMP');self.jump_at=frame;return
        if airborne and frame-self.jump_at<self.spec.get('jump_age',6):return
        if not self.issued:
            if c.control:
                self.command(action);self.issued=True;self.started=frame;self.issue_wall=time.perf_counter()
            return
        if self.spec.get('followup') and not self.followup_issued and c.action.name==action:
            elapsed=row['frameNumber']-c.remaining_frame
            at=self.spec['request_elapsed']
            if elapsed>=at:
                self.request={'frame':frame,'pre_input':character(c),'requested':self.spec['followup']}
                self.command(self.spec['followup']);self.followup_issued=True
                self.request['keys']={k:bool(getattr(self.key,k)) for k in ('A','B','C','U','D','L','R')}
                return
        # A neutral command can itself cancel an uncontrolled source when the
        # table permits it. This is left in the trace, never counted as a direct
        # source -> requested-followup transition.
    def round_end(self,result):
        if self.target:self.sink.append({'trace':self.trace,'inputs':self.inputs,'request':self.request,
            'opponent_inputs':self.coordinator.get('opponent_inputs',[]),
            'ready':self.coordinator.get('ready'),'issued':self.issued,'issue_frame':self.started,
            'energy_preparation':self.preparation,'energy_settled_frame':self.coordinator.get('energy_settled'),
            'incoming_issue_frame':self.coordinator.get('incoming_issued'),
            'energy_setup_failure':self.coordinator.get('energy_setup_failure')})


def placement(stock,zen,move,graphic_width,side,distance=None,zen_graphic_width=400):
    row=stock[move];body=stock['STAND'];op=zen['STAND']
    centre=(body['hitAreaLeft']+body['hitAreaRight'])/2
    opcentre=(op['hitAreaLeft']+op['hitAreaRight'])/2
    if distance is None:
        # Deep stock contact, while allowing the bodies to remain disjoint.
        minimum=(body['hitAreaRight']-body['hitAreaLeft']+op['hitAreaRight']-op['hitAreaLeft'])/2+4
        far=row['attack.hitAreaRight']-centre+(op['hitAreaRight']-op['hitAreaLeft'])/2
        distance=max(minimum,(minimum+far)/2)
    front=side=='P1';targetcentre=((960-distance)/2 if front else (960+distance)/2) if distance>300 else (360 if front else 600)
    sign=1 if front else -1
    return {'target_x':round(targetcentre-(centre if front else graphic_width-centre)),
        'opponent_x':round(targetcentre+sign*distance-(zen_graphic_width-opcentre if front else opcentre)),
        'stock_body_centre_distance':distance,'orientation':side}

#!/usr/bin/env python3
"""Run legacy Py4J FightingICE agents on pyftg 2.3 without changing policy code."""

from __future__ import annotations

import argparse
import asyncio
import csv
import importlib
import importlib.util
import inspect
import json
import math
import os
import socket
import struct
import sys
import types
from collections import deque
from pathlib import Path
from types import SimpleNamespace

from pyftg import AIInterface, FrameData, GameData, Key, RoundResult, ScreenData
from pyftg.aiinterface.command_center import CommandCenter
from pyftg.models.attack_data import AttackData
from pyftg.models.character_data import CharacterData
from pyftg.models.enums.action import Action
from pyftg.models.enums.state import State
from pyftg.models.hit_area import HitArea
from pyftg.protoc import message_pb2
from pyftg.socket.aio.gateway import Gateway


ROUND_FRAMES = 3600
MOTION_BY_PLAYER = {}


def install_dependency_aliases() -> None:
    """Restore small public spellings removed from current dependencies."""
    import numpy as np
    if not hasattr(np, "math"):
        np.math = math


class JavaList(list):
    def get(self, index): return self[index]
    def elementAt(self, index): return self[index]
    def size(self): return len(self)


class ArrayDeque(deque):
    def add(self, value): self.append(value); return True


def _ordinal(value): return list(type(value)).index(value)


def install_model_aliases() -> None:
    """Add the historical Java/Py4J spellings to pyftg's equivalent models."""
    for enum_type in (Action, State):
        enum_type.ordinal = _ordinal
        enum_type.equals = lambda self, other: self == other

    aliases = {
        FrameData: {
            "getCharacter": lambda self, player: self.get_character(player),
            "getP1": lambda self: self.get_character(True),
            "getP2": lambda self: self.get_character(False),
            "getEmptyFlag": lambda self: self.empty_flag,
            "getFramesNumber": lambda self: self.current_frame_number,
            "getFrameNumber": lambda self: self.current_frame_number,
            "getRound": lambda self: self.current_round,
            "getRemainingFramesNumber": lambda self: max(0, ROUND_FRAMES - self.current_frame_number),
            # The v4.50 Java/Py4J API returned whole seconds here, rounded upward.
            "getRemainingTime": lambda self: math.ceil(max(0, ROUND_FRAMES - self.current_frame_number) / 60),
            "getDistanceX": lambda self: abs(self.get_character(True).x - self.get_character(False).x),
            "getProjectiles": lambda self: JavaList(self.projectile_data),
            "getAttack": lambda self: JavaList(self.projectile_data),
            "getProjectilesByP1": lambda self: JavaList(self.get_projectiles_by_player(True)),
            "getProjectilesByP2": lambda self: JavaList(self.get_projectiles_by_player(False)),
        },
        CharacterData: {
            "getHp": lambda self: self.hp, "getEnergy": lambda self: self.energy,
            # pyftg's x/y are hit-box centres, whereas the old Java/Py4J getX/getY
            # methods returned the sprite's top-left coordinate.  Recover it from the
            # current hit box and the selected action's static character hit area.
            "getX": _legacy_graphic_x, "getY": _legacy_graphic_y,
            "getCenterX": lambda self: self.x, "getCenterY": lambda self: self.y,
            "getLeft": lambda self: self.left, "getRight": lambda self: self.right,
            "getTop": lambda self: self.top, "getBottom": lambda self: self.bottom,
            "getSpeedX": lambda self: self.speed_x, "getSpeedY": lambda self: self.speed_y,
            "getState": lambda self: self.state, "getAction": lambda self: self.action,
            "getRemainingFrame": lambda self: self.remaining_frame,
            "getHitCount": lambda self: self.hit_count, "isControl": lambda self: self.control,
            "isFront": lambda self: self.front, "isHitConfirm": lambda self: self.hit_confirm,
            "getAttack": lambda self: self.attack_data,
            "getGraphicSizeX": lambda self: self.graphic_size_x,
            "getGraphicSizeY": lambda self: self.graphic_size_y,
            "getGraphicAdjustX": lambda self: self.graphic_adjust_x,
        },
        AttackData: {
            "getCurrentHitArea": lambda self: self.current_hit_area,
            "getSpeedX": lambda self: self.speed_x, "getSpeedY": lambda self: self.speed_y,
            "getStartUp": lambda self: self.start_up, "getActive": lambda self: self.active,
            "getHitDamage": lambda self: self.hit_damage, "getGuardDamage": lambda self: self.guard_damage,
            "getStartAddEnergy": lambda self: self.start_add_energy,
            "getHitAddEnergy": lambda self: self.hit_add_energy,
            "getGuardAddEnergy": lambda self: self.guard_add_energy,
            "getGiveEnergy": lambda self: self.give_energy,
            "getImpactX": lambda self: self.impact_x, "getImpactY": lambda self: self.impact_y,
            "getGiveGuardRecov": lambda self: self.give_guard_recov,
            "isDownProp": lambda self: self.down_prop,
        },
        HitArea: {
            "getLeft": lambda self: self.left, "getRight": lambda self: self.right,
            "getTop": lambda self: self.top, "getBottom": lambda self: self.bottom,
        },
        CommandCenter: {
            "setFrameData": CommandCenter.set_frame_data,
            "commandCall": CommandCenter.command_call,
            "getSkillFlag": CommandCenter.get_skill_flag,
            "getSkillKey": CommandCenter.get_skill_key,
            "skillCancel": CommandCenter.skill_cancel,
            "getDistanceX": lambda self: abs(self.frame_data.get_character(True).x - self.frame_data.get_character(False).x),
        },
    }
    for model, methods in aliases.items():
        for name, method in methods.items():
            if not hasattr(model, name): setattr(model, name, method)


class MotionDataProxy:
    INT_FIELDS = {
        "frameNumber": 1, "speedX": 2, "speedY": 3,
        "characterHitLeft": 4, "characterHitRight": 5,
        "characterHitTop": 6, "characterHitBottom": 7, "attackStartUp": 15,
        "attackActive": 16, "attackHitDamage": 17, "attackGuardDamage": 18,
        "attackStartAddEnergy": 19, "attackHitAddEnergy": 20,
        "attackGuardAddEnergy": 21, "attackGiveEnergy": 22,
        "attackImpactX": 23, "attackImpactY": 24, "attackGiveGuardRecov": 25,
        "attackType": 26, "cancelAbleFrame": 28, "cancelAbleMotionLevel": 29,
        "motionLevel": 30,
    }

    def __init__(self, row: list[str]):
        self.actionName = row[0]
        for name, index in self.INT_FIELDS.items(): setattr(self, name, int(row[index]))
        self.attackDownProp = row[27].strip().upper() == "TRUE"

    def getFrameNumber(self): return self.frameNumber
    def getStartUp(self): return self.attackStartUp
    def getActive(self): return self.attackActive
    def getHitDamage(self): return self.attackHitDamage
    def getGuardDamage(self): return self.attackGuardDamage
    def getStartAddEnergy(self): return self.attackStartAddEnergy
    def getHitAddEnergy(self): return self.attackHitAddEnergy
    def getGuardAddEnergy(self): return self.attackGuardAddEnergy
    def getGiveEnergy(self): return self.attackGiveEnergy
    def getImpactX(self): return self.attackImpactX
    def getImpactY(self): return self.attackImpactY
    def getGiveGuardRecov(self): return self.attackGiveGuardRecov
    def isDownProp(self): return self.attackDownProp


def load_motion_table(path: Path) -> JavaList:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.reader(stream))[1:]
    if len(rows) != len(Action):
        raise ValueError(f"{path}: expected {len(Action)} motion rows, found {len(rows)}")
    return JavaList(MotionDataProxy(row) for row in rows)


def _motion_for(character: CharacterData) -> MotionDataProxy:
    table = MOTION_BY_PLAYER.get(bool(character.player_number))
    if table is None:
        raise RuntimeError("motion table requested before GameData initialization")
    return table[_ordinal(character.action)]


def _legacy_graphic_x(character: CharacterData) -> int:
    motion = _motion_for(character)
    if character.front:
        return character.left - motion.characterHitLeft
    return character.left - character.graphic_size_x + motion.characterHitRight


def _legacy_graphic_y(character: CharacterData) -> int:
    return character.top - _motion_for(character).characterHitTop


class SimulatorProxy:
    def __init__(self, host: str, port: int): self.host, self.port = host, port

    @staticmethod
    def _recv_exact(stream: socket.socket, count: int) -> bytes:
        result = bytearray()
        while len(result) < count:
            block = stream.recv(count - len(result))
            if not block: raise ConnectionError("simulator bridge closed early")
            result.extend(block)
        return bytes(result)

    def simulate(self, frame_data, player, my_actions, opp_actions, frame_limit):
        # All six audited live policies pass None for both action queues. Refuse rather than
        # silently approximating a hypothetical-action request.
        if my_actions is not None or opp_actions is not None:
            raise NotImplementedError("historical action-queue simulation is not bridged")
        payload = struct.pack("<BI", bool(player), int(frame_limit))
        with socket.create_connection((self.host, self.port), timeout=5) as stream:
            stream.sendall(b"\x06" + struct.pack("<I", len(payload)) + payload)
            size = struct.unpack("<I", self._recv_exact(stream, 4))[0]
            response = self._recv_exact(stream, size)
        proto = message_pb2.GrpcFrameData()
        proto.ParseFromString(response)
        return FrameData.from_proto(proto)


class GameDataProxy:
    def __init__(self, source: GameData, motion_root: Path, simulator: SimulatorProxy):
        self.source, self.motion_root, self.simulator = source, motion_root, simulator
        MOTION_BY_PLAYER[True] = load_motion_table(motion_root / source.get_character_name(True) / "Motion.csv")
        MOTION_BY_PLAYER[False] = load_motion_table(motion_root / source.get_character_name(False) / "Motion.csv")
    def getSimulator(self): return self.simulator
    def getCharacterName(self, player): return self.source.get_character_name(player)
    def getAiName(self, player): return self.source.get_ai_name(player)
    def getMotionData(self, player):
        name = self.getCharacterName(player)
        return load_motion_table(self.motion_root / name / "Motion.csv")


def install_fake_py4j() -> None:
    java_gateway = types.ModuleType("py4j.java_gateway")
    java_gateway.get_field = lambda obj, name: getattr(obj, name)
    java_gateway.JavaGateway = object
    java_gateway.GatewayParameters = object
    java_gateway.CallbackServerParameters = object
    package = types.ModuleType("py4j")
    package.__path__ = []
    package.java_gateway = java_gateway
    sys.modules["py4j"] = package
    sys.modules["py4j.java_gateway"] = java_gateway


class FakeGateway:
    def __init__(self):
        self.jvm = SimpleNamespace(
            enumerate=SimpleNamespace(Action=Action, State=State),
            struct=SimpleNamespace(Key=Key, FrameData=FrameData),
            aiinterface=SimpleNamespace(CommandCenter=CommandCenter),
            java=SimpleNamespace(util=SimpleNamespace(ArrayDeque=ArrayDeque)),
        )


def load_class(source: Path, class_name: str, working_directory: Path | None,
               module_name: str | None):
    working_directory = (working_directory or source.parent).resolve()
    os.chdir(working_directory)
    search_directories = ((working_directory,) if module_name else
                          (working_directory, source.parent, *list(source.parents)[:5]))
    for directory in search_directories:
        if str(directory) not in sys.path: sys.path.insert(0, str(directory))
    # The historical launch directory must win over the leaf source directory. Otherwise a
    # file such as SpringAI/SpringAI.py shadows its containing SpringAI package.
    if str(working_directory) in sys.path:
        sys.path.remove(str(working_directory))
    sys.path.insert(0, str(working_directory))
    if module_name:
        module = importlib.import_module(module_name)
        return getattr(module, class_name)
    spec = importlib.util.spec_from_file_location("recovery_py4j_" + source.stem, source)
    if spec is None or spec.loader is None: raise ImportError(source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, class_name)


class Py4JCompatibilityAdapter(AIInterface):
    def __init__(self, delegate, host: str, port: int, motion_root: Path, audit_file: Path | None = None):
        self.delegate, self.host, self.port, self.motion_root = delegate, host, port, motion_root
        self.non_delay = None
        self.audit_file = audit_file
        self.audit_stream = None
        self.callback_index = 0
        if audit_file is not None:
            audit_file.parent.mkdir(parents=True, exist_ok=True)
            self.audit_stream = audit_file.open("w", encoding="utf-8", buffering=1)
    def name(self): return self.delegate.__class__.__name__
    def is_blind(self): return False
    def initialize(self, game_data, player):
        proxy = GameDataProxy(game_data, self.motion_root, SimulatorProxy(self.host, self.port))
        return self.delegate.initialize(proxy, player)
    def get_information(self, frame_data, is_control):
        self.callback_index += 1
        self._audit_input(frame_data, is_control)
        method = self.delegate.getInformation
        if len(inspect.signature(method).parameters) >= 3:
            method(frame_data, is_control, self.non_delay if self.non_delay is not None else frame_data)
        else: method(frame_data, is_control)
    def get_non_delay_frame_data(self, frame_data): self.non_delay = frame_data
    def get_screen_data(self, screen_data):
        method = getattr(self.delegate, "getScreenData", None)
        if method: method(screen_data)
    def get_audio_data(self, audio_data): pass
    def processing(self): return self.delegate.processing()
    def input(self):
        key = self.delegate.input()
        if self.audit_stream is not None:
            self.audit_stream.write(json.dumps({
                "kind": "output", "callback": self.callback_index,
                "A": bool(key.A), "B": bool(key.B), "C": bool(key.C),
                "U": bool(key.U), "R": bool(key.R), "D": bool(key.D), "L": bool(key.L),
            }, separators=(",", ":")) + "\n")
        return key
    def round_end(self, result: RoundResult):
        method = getattr(self.delegate, "roundEnd", None)
        if method: method(result.remaining_hps[0], result.remaining_hps[1], result.elapsed_frame)
    def game_end(self): pass
    def close(self):
        method = getattr(self.delegate, "close", None)
        if method: method()
        if self.audit_stream is not None: self.audit_stream.close()

    def _audit_input(self, frame_data, is_control):
        if self.audit_stream is None: return
        row = {
            "kind": "input", "callback": self.callback_index,
            "frame": frame_data.current_frame_number, "round": frame_data.current_round,
            "empty": frame_data.empty_flag, "is_control": bool(is_control),
            "non_delay_frame": None if self.non_delay is None else self.non_delay.current_frame_number,
            "players": [], "projectiles": len(frame_data.projectile_data),
        }
        for player in (True, False):
            value = frame_data.get_character(player)
            if value is None:
                row["players"].append(None); continue
            row["players"].append({
                "side": "P1" if player else "P2", "player_number": bool(value.player_number),
                "hp": value.getHp(), "energy": value.getEnergy(),
                "x": value.getX(), "y": value.getY(),
                "center_x": value.getCenterX(), "center_y": value.getCenterY(),
                "left": value.getLeft(), "right": value.getRight(),
                "top": value.getTop(), "bottom": value.getBottom(),
                "speed_x": value.getSpeedX(), "speed_y": value.getSpeedY(),
                "front": value.isFront(), "control": value.isControl(),
                "action": value.getAction().name, "action_ordinal": value.getAction().ordinal(),
                "state": value.getState().name, "remaining_frame": value.getRemainingFrame(),
                "hit_count": value.getHitCount(),
            })
        self.audit_stream.write(json.dumps(row, separators=(",", ":")) + "\n")


async def run(args) -> None:
    global ROUND_FRAMES
    ROUND_FRAMES = args.round_frames
    install_fake_py4j(); install_model_aliases(); install_dependency_aliases()
    agent_class = load_class(args.source.resolve(), args.class_name, args.working_directory,
                             args.module_name)
    delegate = agent_class(FakeGateway())
    adapter = Py4JCompatibilityAdapter(delegate, args.host, args.port, args.motion_root.resolve(),
                                       args.audit_file.resolve() if args.audit_file else None)
    gateway = Gateway(host=args.host, port=args.port)
    gateway.register_ai(adapter.name(), adapter)
    agents = [adapter.name(), args.opponent] if args.side == "P1" else [args.opponent, adapter.name()]
    try: await gateway.run_game([args.character, args.character], agents, args.rounds)
    finally: await gateway.close_game()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--class-name", required=True)
    parser.add_argument("--working-directory", type=Path)
    parser.add_argument("--module-name")
    parser.add_argument("--character", default="ZEN")
    parser.add_argument("--side", choices=("P1", "P2"), required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--motion-root", type=Path, required=True)
    parser.add_argument("--round-frames", type=int, default=3600)
    parser.add_argument("--audit-file", type=Path)
    parser.add_argument("--opponent", default="MctsAi23i")
    parser.add_argument("--rounds", type=int, default=1)
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__": main()

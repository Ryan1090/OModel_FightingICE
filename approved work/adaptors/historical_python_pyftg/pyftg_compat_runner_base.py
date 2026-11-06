#!/usr/bin/env python3
"""Load a historical pyftg controller behind a pyftg 2.3 callback/import adapter."""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import inspect
import json
import os
import sys
import types
from pathlib import Path

from pyftg import AIInterface, AudioData, FrameData, GameData, Key, RoundResult, ScreenData
from pyftg.socket.aio.gateway import Gateway


class LegacyAIInterface:
    """Non-abstract base exported under the pyftg 1.x import path."""

    pass


def install_import_aliases() -> None:
    """Expose removed pyftg 1.x module names using 2.3 model classes."""
    import pyftg
    from pyftg.aiinterface.command_center import CommandCenter
    from pyftg.models.attack_data import AttackData
    from pyftg.models.character_data import CharacterData
    from pyftg.models.enums.action import Action
    from pyftg.models.enums.state import State
    from pyftg.models.game_data import GameData as ModelGameData
    from pyftg.models.hit_area import HitArea
    from pyftg.models.key import Key as ModelKey

    old_ai = types.ModuleType("pyftg.ai_interface")
    old_ai.AIInterface = LegacyAIInterface
    sys.modules["pyftg.ai_interface"] = old_ai

    old_struct = types.ModuleType("pyftg.struct")
    old_struct.__path__ = []
    exports = {
        "Action": Action, "State": State, "AttackData": AttackData,
        "CharacterData": CharacterData, "FrameData": FrameData,
        "GameData": ModelGameData, "HitArea": HitArea, "Key": ModelKey,
        "AudioData": AudioData, "ScreenData": ScreenData, "RoundResult": RoundResult,
        "CommandCenter": CommandCenter,
    }
    old_struct.__dict__.update(exports)
    old_struct.__all__ = tuple(exports)
    sys.modules["pyftg.struct"] = old_struct

    enumerate = types.ModuleType("pyftg.struct.enumerate")
    enumerate.Action, enumerate.State = Action, State
    enumerate.__all__ = ("Action", "State")
    sys.modules["pyftg.struct.enumerate"] = enumerate
    attack_data = types.ModuleType("pyftg.struct.attack_data")
    attack_data.AttackData = AttackData
    attack_data.__all__ = ("AttackData",)
    sys.modules["pyftg.struct.attack_data"] = attack_data
    setattr(pyftg, "ai_interface", old_ai)
    setattr(pyftg, "struct", old_struct)

    # PyTorch 2.6 changed torch.load's default to weights_only=True. Competition checkpoints
    # predate that format restriction and contain trusted local model objects.
    try:
        import torch
        original_load = torch.load
        def historical_load(*args, **kwargs):
            kwargs.setdefault("weights_only", False)
            return original_load(*args, **kwargs)
        torch.load = historical_load
    except ImportError:
        pass


def load_class(source: Path, class_name: str):
    install_import_aliases()
    os.chdir(source.parent)
    for directory in (source.parent, *list(source.parents)[:4]):
        value = str(directory)
        if value not in sys.path:
            sys.path.insert(0, value)
    module_name = "recovery_agent_" + "".join(ch if ch.isalnum() else "_" for ch in source.stem)
    spec = importlib.util.spec_from_file_location(module_name, source)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot create module spec for {source}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, class_name)


class PyftgCompatibilityAdapter(AIInterface):
    def __init__(self, delegate, audit_file: Path | None = None):
        self.delegate = delegate
        self.non_delay: FrameData | None = None
        self.audit_stream = None
        self.callback_index = 0
        if audit_file is not None:
            audit_file.parent.mkdir(parents=True, exist_ok=True)
            self.audit_stream = audit_file.open("w", encoding="utf-8", buffering=1)

    def name(self) -> str:
        method = getattr(self.delegate, "name", None)
        return str(method()) if method else self.delegate.__class__.__name__

    def is_blind(self) -> bool:
        method = getattr(self.delegate, "is_blind", None)
        return bool(method()) if method else False

    def initialize(self, game_data: GameData, player_number: bool):
        return self.delegate.initialize(game_data, player_number)

    def get_non_delay_frame_data(self, frame_data: FrameData):
        self.non_delay = frame_data
        method = getattr(self.delegate, "get_non_delay_frame_data", None)
        if method: method(frame_data)

    def get_information(self, frame_data: FrameData, is_control: bool):
        self.callback_index += 1
        self._audit_input(frame_data, is_control)
        method = self.delegate.get_information
        parameter_count = len(inspect.signature(method).parameters)
        if parameter_count >= 3:
            method(frame_data, is_control, self.non_delay if self.non_delay is not None else frame_data)
        else:
            method(frame_data, is_control)

    def get_screen_data(self, screen_data: ScreenData):
        method = getattr(self.delegate, "get_screen_data", None)
        if method: method(screen_data)

    def get_audio_data(self, audio_data: AudioData):
        method = getattr(self.delegate, "get_audio_data", None)
        if method: method(audio_data)

    def processing(self): return self.delegate.processing()
    def input(self) -> Key:
        key = self.delegate.input()
        if self.audit_stream is not None:
            self.audit_stream.write(json.dumps({
                "kind": "output", "callback": self.callback_index,
                "A": bool(key.A), "B": bool(key.B), "C": bool(key.C),
                "U": bool(key.U), "R": bool(key.R), "D": bool(key.D), "L": bool(key.L),
            }, separators=(",", ":")) + "\n")
        return key

    def round_end(self, round_result: RoundResult):
        method = getattr(self.delegate, "round_end", None)
        if method: method(round_result)

    def game_end(self):
        method = getattr(self.delegate, "game_end", None)
        if method: method()

    def close(self):
        method = getattr(self.delegate, "close", None)
        if method: method()
        if self.audit_stream is not None: self.audit_stream.close()

    def _audit_input(self, frame_data: FrameData, is_control: bool) -> None:
        if self.audit_stream is None: return
        row = {
            "kind": "input", "callback": self.callback_index,
            "frame": frame_data.current_frame_number, "round": frame_data.current_round,
            "empty": frame_data.empty_flag, "is_control": bool(is_control),
            "non_delay_frame": None if self.non_delay is None else self.non_delay.current_frame_number,
            "projectiles": len(frame_data.projectile_data), "players": [],
        }
        for player in (True, False):
            value = frame_data.get_character(player)
            if value is None:
                row["players"].append(None); continue
            row["players"].append({
                "side": "P1" if player else "P2", "player_number": bool(value.player_number),
                "hp": value.hp, "energy": value.energy, "x": value.x, "y": value.y,
                "left": value.left, "right": value.right, "top": value.top, "bottom": value.bottom,
                "speed_x": value.speed_x, "speed_y": value.speed_y,
                "front": value.front, "control": value.control,
                "action": value.action.name, "state": value.state.name,
                "remaining_frame": value.remaining_frame, "hit_count": value.hit_count,
            })
        self.audit_stream.write(json.dumps(row, separators=(",", ":")) + "\n")


async def run(args) -> None:
    agent_class = load_class(args.source.resolve(), args.class_name)
    # Some 2.0-era classes inherit today's ABC but omit callbacks that were optional then.
    # The adapter supplies those callbacks, so instantiate the unchanged policy class.
    agent_class.__abstractmethods__ = frozenset()
    delegate = agent_class()
    adapter = PyftgCompatibilityAdapter(delegate, args.audit_file.resolve() if args.audit_file else None)
    name = adapter.name()
    gateway = Gateway(host="127.0.0.1", port=args.port)
    gateway.register_ai(name, adapter)
    agents = [name, args.opponent] if args.side == "P1" else [args.opponent, name]
    await gateway.run_game([args.character, args.character], agents, args.rounds)
    await gateway.close_game()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--class-name", required=True)
    parser.add_argument("--character", required=True)
    parser.add_argument("--side", choices=("P1", "P2"), required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--opponent", default="MctsAi23i")
    parser.add_argument("--audit-file", type=Path)
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()

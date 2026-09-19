"""Clean semantic-action FightingICE agent template for pyftg 2.3.

Search for ``TODO:`` for required learning-agent work and ``EDIT:`` for experiment-specific
configuration. See ``agent_template_learning.py`` for the fully explained version.

Use --input-sync. Memory updates on valid delayed frames; choices occur whenever the input
queue is empty. Ignore current is_control; no estimated legality masks. Finish command entry.
POLICY_CHOICES has 41 commands plus None (WAIT); raw features are 42 x 47, raw feedback is 49 values.
These are prepared features, not learned X-length embeddings. Add the encoder in the model hooks.
The policy and recurrent network remain hooks. The default chooses WAIT.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from pyftg.aiinterface.ai_interface import AIInterface
from pyftg.aiinterface.command_center import CommandCenter
from pyftg.models.audio_data import AudioData
from pyftg.models.enums.action import Action
from pyftg.models.enums.state import State
from pyftg.models.frame_data import FrameData
from pyftg.models.game_data import GameData
from pyftg.models.key import Key
from pyftg.models.round_result import RoundResult
from pyftg.models.screen_data import ScreenData
from pyftg.socket.aio.gateway import Gateway


_COMMAND_ACTION_NAMES = frozenset(
    """
    FORWARD_WALK DASH BACK_STEP CROUCH JUMP FOR_JUMP BACK_JUMP
    STAND_GUARD CROUCH_GUARD AIR_GUARD THROW_A THROW_B
    STAND_A STAND_B CROUCH_A CROUCH_B AIR_A AIR_B AIR_DA AIR_DB
    STAND_FA STAND_FB CROUCH_FA CROUCH_FB AIR_FA AIR_FB AIR_UA AIR_UB
    STAND_D_DF_FA STAND_D_DF_FB STAND_F_D_DFA STAND_F_D_DFB
    STAND_D_DB_BA STAND_D_DB_BB AIR_D_DF_FA AIR_D_DF_FB
    AIR_F_D_DFA AIR_F_D_DFB AIR_D_DB_BA AIR_D_DB_BB STAND_D_DF_FC
    """.split()
)
POLICY_ACTIONS: tuple[Action, ...] = tuple(
    action for action in Action if action.name in _COMMAND_ACTION_NAMES
)
# POLICY_ACTIONS contains engine commands only. POLICY_CHOICES adds WAIT as Python None.
# Output row i and choice_features[i] refer to the same choice; WAIT is always the last row.
POLICY_CHOICES: tuple[Action | None, ...] = (*POLICY_ACTIONS, None)

AIR_ACTIONS = frozenset(
    {
        Action.AIR_GUARD,
        Action.AIR_A,
        Action.AIR_B,
        Action.AIR_DA,
        Action.AIR_DB,
        Action.AIR_FA,
        Action.AIR_FB,
        Action.AIR_UA,
        Action.AIR_UB,
        Action.AIR_D_DF_FA,
        Action.AIR_D_DF_FB,
        Action.AIR_F_D_DFA,
        Action.AIR_F_D_DFB,
        Action.AIR_D_DB_BA,
        Action.AIR_D_DB_BB,
    }
)

# pyftg 2.3 -> FightingICE 7.1 compatibility fixes; leave the installed library unchanged.
# EDIT: recheck against CommandTable.java and live tests when changing versions.
_COMMAND_OVERRIDES = {"AIR_GUARD": "4", "AIR_FA": "6 _ A", "AIR_FB": "6 _ B"}

# EDIT WITH CARE: changing this order changes checkpoint tensor meanings. If selecting or
# transforming features, version the schema and fit normalization on training characters only.
SEMANTIC_FEATURE_NAMES: tuple[str, ...] = (
    "total_frames",
    "character_speed_x",
    "character_speed_y",
    "hurtbox_left",
    "hurtbox_right",
    "hurtbox_top",
    "hurtbox_bottom",
    "attack_box_left",
    "attack_box_right",
    "attack_box_top",
    "attack_box_bottom",
    "attack_speed_x",
    "attack_speed_y",
    "startup",
    "active",
    "hit_damage",
    "guard_damage",
    "start_add_energy",
    "hit_add_energy",
    "guard_add_energy",
    "give_energy",
    "impact_x",
    "impact_y",
    "give_guard_recovery",
    "down_property",
    "cancel_able_frame",
    "cancel_able_motion_level",
    "motion_level",
    "control",
    "landing_flag",
    "projectile",
    "state_stand",
    "state_crouch",
    "state_air",
    "state_down",
    "attack_none",
    "attack_high",
    "attack_middle",
    "attack_low",
    "attack_throw",
    "category_movement",
    "category_defence",
    "category_throw",
    "category_attack",
    "category_special",
    "category_airborne",
)


# The move schema remains 46 columns. Each policy choice adds an is_wait metadata flag.
# WAIT needs a row because it is selectable, but has no move properties: use 46 zeros + 1.
# Before any choice, 47 zeros marks "no previous request". This is not one-hot action identity.
# EDIT WITH CARE: these are raw encoder INPUT columns; the learned embedding size X is separate.
CHOICE_FEATURE_NAMES: tuple[str, ...] = (*SEMANTIC_FEATURE_NAMES, "is_wait")


def _csv_bool(value: str) -> bool:
    if value.upper() not in {"TRUE", "FALSE"}:
        raise ValueError(f"expected TRUE/FALSE in Motion.csv, got {value!r}")
    return value.upper() == "TRUE"


def _categories(action: Action, attack_type: int, state: State) -> frozenset[str]:
    categories: set[str] = set()
    if action in {
        Action.FORWARD_WALK,
        Action.DASH,
        Action.BACK_STEP,
        Action.CROUCH,
        Action.JUMP,
        Action.FOR_JUMP,
        Action.BACK_JUMP,
    }:
        categories.add("movement")
    if action in {Action.STAND_GUARD, Action.CROUCH_GUARD, Action.AIR_GUARD}:
        categories.add("defence")
    if action in {Action.THROW_A, Action.THROW_B}:
        categories.add("throw")
    if attack_type != 0:
        categories.add("attack")
    if "_D_" in action.name or "_F_D_" in action.name:
        categories.add("special")
    if action in AIR_ACTIONS or state is State.AIR:
        categories.add("airborne")
    return frozenset(categories)


@dataclass(frozen=True)
class ActionSpec:
    action: Action
    total_frames: int
    character_speed_x: int
    character_speed_y: int
    hurtbox: tuple[int, int, int, int]
    state: State
    attack_box: tuple[int, int, int, int]
    attack_speed_x: int
    attack_speed_y: int
    startup: int
    active: int
    hit_damage: int
    guard_damage: int
    start_add_energy: int
    hit_add_energy: int
    guard_add_energy: int
    give_energy: int
    impact_x: int
    impact_y: int
    give_guard_recovery: int
    attack_type: int
    down_property: bool
    cancel_able_frame: int
    cancel_able_motion_level: int
    motion_level: int
    control: bool
    landing_flag: bool
    projectile: bool
    categories: frozenset[str]

    @property
    def energy_cost(self) -> int:
        return max(0, -self.start_add_energy)

    @property
    def recovery_proxy(self) -> int:
        return max(0, self.total_frames - self.startup - self.active)

    def semantic_vector(self) -> tuple[float, ...]:
        state_flags = tuple(float(self.state is state) for state in State)
        attack_type_flags = tuple(float(self.attack_type == value) for value in range(5))
        category_flags = tuple(
            float(name in self.categories)
            for name in ("movement", "defence", "throw", "attack", "special", "airborne")
        )
        vector = (
            float(self.total_frames),
            float(self.character_speed_x),
            float(self.character_speed_y),
            *(float(value) for value in self.hurtbox),
            *(float(value) for value in self.attack_box),
            float(self.attack_speed_x),
            float(self.attack_speed_y),
            float(self.startup),
            float(self.active),
            float(self.hit_damage),
            float(self.guard_damage),
            float(self.start_add_energy),
            float(self.hit_add_energy),
            float(self.guard_add_energy),
            float(self.give_energy),
            float(self.impact_x),
            float(self.impact_y),
            float(self.give_guard_recovery),
            float(self.down_property),
            float(self.cancel_able_frame),
            float(self.cancel_able_motion_level),
            float(self.motion_level),
            float(self.control),
            float(self.landing_flag),
            float(self.projectile),
            *state_flags,
            *attack_type_flags,
            *category_flags,
        )
        if len(vector) != len(SEMANTIC_FEATURE_NAMES):
            raise AssertionError("semantic feature schema and vector implementation diverged")
        return vector


class MotionTable:
    def __init__(self, character: str, source: Path, specs: Sequence[ActionSpec]) -> None:
        self.character = character
        self.source = source
        self.specs = tuple(specs)
        self.by_action = {spec.action: spec for spec in specs}

    @classmethod
    def load(cls, motion_root: Path, character: str) -> "MotionTable":
        source = motion_root / character / "Motion.csv"
        if not source.is_file():
            raise FileNotFoundError(
                f"Motion.csv not found for {character!r}: {source}. "
                "Pass --motion-root pointing at the SAME runtime used by Java."
            )
        with source.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.reader(stream))
        if not rows:
            raise ValueError(f"empty Motion.csv: {source}")

        actions = tuple(Action)
        data_rows = rows[1:]
        if len(data_rows) != len(actions):
            raise ValueError(
                f"{source} has {len(data_rows)} rows; pyftg Action has {len(actions)} values"
            )

        specs: list[ActionSpec] = []
        for ordinal, (action, row) in enumerate(zip(actions, data_rows, strict=True)):
            if len(row) < 34:
                raise ValueError(f"{source}:{ordinal + 2} has {len(row)} columns; expected 34")
            if row[0] != action.name or action.to_int() != ordinal:
                raise ValueError(
                    f"ordinal mismatch at {source}:{ordinal + 2}: "
                    f"expected {ordinal}:{action.name}, found {row[0]!r}"
                )
            attack_type = int(row[26])
            state = State[row[8]]
            projectile = int(row[13]) + int(row[14]) != 0
            specs.append(
                ActionSpec(
                    action=action,
                    total_frames=int(row[1]),
                    character_speed_x=int(row[2]),
                    character_speed_y=int(row[3]),
                    hurtbox=tuple(int(value) for value in row[4:8]),
                    state=state,
                    attack_box=tuple(int(value) for value in row[9:13]),
                    attack_speed_x=int(row[13]),
                    attack_speed_y=int(row[14]),
                    startup=int(row[15]),
                    active=int(row[16]),
                    hit_damage=int(row[17]),
                    guard_damage=int(row[18]),
                    start_add_energy=int(row[19]),
                    hit_add_energy=int(row[20]),
                    guard_add_energy=int(row[21]),
                    give_energy=int(row[22]),
                    impact_x=int(row[23]),
                    impact_y=int(row[24]),
                    give_guard_recovery=int(row[25]),
                    attack_type=attack_type,
                    down_property=_csv_bool(row[27]),
                    cancel_able_frame=int(row[28]),
                    cancel_able_motion_level=int(row[29]),
                    motion_level=int(row[30]),
                    control=_csv_bool(row[31]),
                    landing_flag=_csv_bool(row[32]),
                    projectile=projectile,
                    categories=_categories(action, attack_type, state),
                )
            )
        return cls(character, source, specs)

    def policy_specs(self) -> tuple[ActionSpec, ...]:
        return tuple(self.by_action[action] for action in POLICY_ACTIONS)

    def semantic_matrix(self) -> tuple[tuple[float, ...], ...]:
        return tuple(spec.semantic_vector() for spec in self.policy_specs())


@dataclass(frozen=True)
class PolicyFeedback:
    """Raw feedback captured before this callback's possible new choice.

    Order: build feedback -> update memory -> continue queued input OR choose a new command.
    A choice made now is therefore reported on the next valid memory update.
    """

    # 46 raw move features + is_wait. No encoder/model output is stored here.
    last_request_features: tuple[float, ...] = (0.0,) * len(CHOICE_FEATURE_NAMES)
    # Needed because memory updates during automatic multi-input continuation, when choose_action
    # is not called but last_request_features still repeats the most recent choice. True means the
    # choice is newly dispatched; False means those same features are only being remembered.
    new_request: bool = False
    # Local queued input delivery, not whether an engine move is still executing.
    input_sequence_in_progress: bool = False

    def as_raw_vector(self) -> tuple[float, ...]:
        """Return 49 raw values: choice features, new-request flag, input-queue flag."""
        return (
            *self.last_request_features,
            float(self.new_request),
            float(self.input_sequence_in_progress),
        )


class MyAgent(AIInterface):
    """Delayed-observation scaffold; complete command inputs before choosing again."""

    def __init__(
        self,
        motion_root: Path,
        agent_name: str = "MyAgent",
        demo_action: Action | None = None,
    ) -> None:
        self.motion_root = motion_root
        self.agent_name = agent_name
        self.demo_action = demo_action
        self.player = True
        self.max_hp = 400
        self.opponent_max_hp = 400
        self.frame: FrameData | None = None
        self.key = Key()
        self.command_center = CommandCenter()
        self.motion_table: MotionTable | None = None
        self.choice_features: tuple[tuple[float, ...], ...] = ()
        self.frame_count = 0
        self.valid_frame_count = 0
        self.previous_round: int | None = None
        self.previous_self_hp: int | None = None
        self.previous_opponent_hp: int | None = None
        self.last_net_damage_reward = 0.0
        self.last_requested_choice: Action | None = None
        self._last_request_features = (0.0,) * len(CHOICE_FEATURE_NAMES)
        # Carries a dispatch event to the next valid memory update, then resets to False.
        self._new_request = False
        self.policy_feedback = PolicyFeedback()
        # TODO: construct/load the network and replace None with its hidden-state structure.
        self.recurrent_state = None

    def name(self) -> str:
        """Return the socket AI name supplied by the runner."""
        return self.agent_name

    def is_blind(self) -> bool:
        # EDIT: return False only if the experiment is changed to consume ScreenData.
        return True

    def initialize(self, game_data: GameData, player_number: bool) -> int:
        """Receive match metadata, load the selected character, and reset local state."""
        self.player = player_number
        mine = 0 if player_number else 1
        opponent = 1 - mine
        self.max_hp = game_data.max_hps[mine]
        self.opponent_max_hp = game_data.max_hps[opponent]
        character = game_data.character_names[mine]
        self.motion_table = MotionTable.load(self.motion_root, character)
        self.choice_features = tuple(
            (*row, 0.0) for row in self.motion_table.semantic_matrix()
        ) + ((0.0,) * len(SEMANTIC_FEATURE_NAMES) + (1.0,),)
        if len(self.choice_features) != len(POLICY_CHOICES):
            raise AssertionError("one raw feature row is required for every choice, including WAIT")
        # TODO: load a model here if needed; keep the same input/execution contract across Ms.
        self.frame = None
        self.key = Key()
        self.command_center = CommandCenter()
        self.frame_count = 0
        self.valid_frame_count = 0
        self.previous_round = None
        self.previous_self_hp = None
        self.previous_opponent_hp = None
        self.last_net_damage_reward = 0.0
        self.last_requested_choice = None
        self._last_request_features = (0.0,) * len(CHOICE_FEATURE_NAMES)
        self._new_request = False
        self.policy_feedback = PolicyFeedback()
        self.recurrent_state = None
        print(
            f"[initialize] {character} as P{mine + 1}; max_hp={self.max_hp}; "
            f"policy_choices={len(POLICY_CHOICES)}x{len(CHOICE_FEATURE_NAMES)}; "
            f"motion={self.motion_table.source}"
        )
        return 0

    def round_end(self, round_result: RoundResult) -> None:
        """Clear round-local inputs/reward baselines; preserve recurrent match memory."""
        mine = round_result.remaining_hps[0 if self.player else 1]
        theirs = round_result.remaining_hps[1 if self.player else 0]
        print(
            f"[round_end] round {round_result.current_round}: me {mine} / them {theirs} "
            f"after {round_result.elapsed_frame} frames "
            f"({self.valid_frame_count} match-valid callbacks so far)"
        )
        self.previous_round = None
        self.previous_self_hp = None
        self.previous_opponent_hp = None
        self.last_net_damage_reward = 0.0
        self.frame = None
        self.last_requested_choice = None
        self._last_request_features = (0.0,) * len(CHOICE_FEATURE_NAMES)
        self._new_request = False
        self.policy_feedback = PolicyFeedback()
        self.command_center.skill_cancel()
        self.key = Key()
        # DESIGN: preserve recurrent memory across rounds for future opponent adaptation.

    def game_end(self) -> None:
        # TODO: flush trajectories and settle terminal rewards in future training code.
        print("[game_end] match over")

    def close(self) -> None:
        """Receive notification that the pyftg connection is closing."""
        print("[close] connection closed")

    def get_information(self, frame_data: FrameData, is_control: bool) -> None:
        """Store delayed FrameData; deliberately ignore the current is_control argument."""
        self.frame = frame_data

    def get_non_delay_frame_data(self, frame_data: FrameData) -> None:
        """Give current facing to the low-level action translator, but not to the policy."""
        # DESIGN EXCEPTION: current facing lets CommandCenter mirror semantic requests such as
        # FORWARD_WALK and directional specials into the correct physical Left/Right Keys after
        # a side-cross. This shared execution aid preserves the Action/Motion.csv correspondence,
        # but it is privileged current-state assistance and must be disclosed in the methodology.
        # Never read this object or CommandCenter.frame_data in policy/memory/reward code.
        self.command_center.set_frame_data(frame_data, self.player)

    def get_screen_data(self, screen_data: ScreenData) -> None:
        # EDIT: consume this only if is_blind() is changed to False.
        pass

    def get_audio_data(self, audio_data: AudioData) -> None:
        # EDIT: leave unused for the intended non-audio agent.
        pass

    def _update_damage_reward(self, frame: FrameData) -> None:
        """Compute one delayed reward component; this does not perform training."""
        # EDIT: add terminal outcome/coefficients and settle hidden end-of-round damage in
        # trajectory code. This helper alone does not provide the complete learning objective.
        mine = frame.get_character(self.player)
        theirs = frame.get_character(not self.player)
        if mine is None or theirs is None:
            self.last_net_damage_reward = 0.0
            return
        if self.previous_round != frame.current_round:
            self.previous_round = frame.current_round
            self.previous_self_hp = mine.hp
            self.previous_opponent_hp = theirs.hp
            self.last_net_damage_reward = 0.0
            return
        assert self.previous_self_hp is not None
        assert self.previous_opponent_hp is not None
        opponent_damage = max(0, self.previous_opponent_hp - theirs.hp)
        self_damage = max(0, self.previous_self_hp - mine.hp)
        self.last_net_damage_reward = (
            opponent_damage / max(1, self.opponent_max_hp)
            - self_damage / max(1, self.max_hp)
        )
        self.previous_self_hp = mine.hp
        self.previous_opponent_hp = theirs.hp

    def update_recurrent_state(
        self,
        frame: FrameData,
        choice_features: Sequence[Sequence[float]],
        feedback: PolicyFeedback,
    ) -> None:
        """TODO: update memory from this delayed frame and raw request feedback."""
        # TODO: encode frame and map raw choice/request features to the intended X-length embeddings.
        # WAIT may use a separate learned embedding. Define a distinct no-previous-request value.
        # as_raw_vector() is optional raw-data packing, not the final recurrent network input.
        # TODO: fit feature normalization on training data and update self.recurrent_state.
        # TODO: train on sequences, not isolated frames. Recompute learned embeddings if weights change.

    def choose_action(
        self,
        frame: FrameData,
        choice_features: Sequence[Sequence[float]],
        feedback: PolicyFeedback,
    ) -> Action | None:
        """TODO: choose one of POLICY_CHOICES: 41 commands or None for WAIT."""
        # TODO: replace this fallback with reflex rules, then a learned policy when ready.
        # EDIT: --demo-action repeatedly ATTEMPTS that command whenever the queue is empty.
        # It ignores game legality and may fail, hold a button, or produce a different move.
        return self.demo_action

    def processing(self) -> None:
        """Update on valid observations; choose freely when our input queue is empty."""
        self.frame_count += 1
        self.key = Key()
        frame = self.frame
        input_sequence_in_progress = self.command_center.get_skill_flag()
        if frame is not None and not frame.empty_flag:
            self.valid_frame_count += 1
            self._update_damage_reward(frame)
            self.policy_feedback = PolicyFeedback(
                last_request_features=self._last_request_features,
                new_request=self._new_request,
                input_sequence_in_progress=input_sequence_in_progress,
            )
            self.update_recurrent_state(frame, self.choice_features, self.policy_feedback)
            self._new_request = False

        if input_sequence_in_progress:
            self.key = self.command_center.get_skill_key()
            return
        if frame is None or frame.empty_flag:
            return
        if self.motion_table is None:
            raise RuntimeError("initialize() must load the motion table before policy decisions")

        action = self.choose_action(frame, self.choice_features, self.policy_feedback)
        if action is not None and (
            not isinstance(action, Action) or action not in POLICY_ACTIONS
        ):
            raise ValueError(f"policy must return a commandable Action or None (WAIT), got {action!r}")
        index = POLICY_CHOICES.index(action)
        if action is not None:
            self.command_center.command_call(_COMMAND_OVERRIDES.get(action.name, action.name))
            self.key = self.command_center.get_skill_key()
        self.last_requested_choice = action
        self._last_request_features = self.choice_features[index]
        self._new_request = True
        # TODO: trajectory code records a policy choice here. Continuation callbacks still
        # contribute reward/time and memory updates, but are not fresh sampled actions.
        # TODO: account for elapsed frames if training transitions span complete command sequences.

    def input(self) -> Key:
        """Return this callback's seven button states for pyftg to send to Java."""
        return self.key


async def run(args: argparse.Namespace) -> None:
    demo_action = (
        Action[args.demo_action] if args.demo_action not in (None, "WAIT") else None
    )
    agent = MyAgent(args.motion_root, args.name, demo_action)
    gateway = Gateway(host=args.host, port=args.port)
    gateway.register_ai(agent.name(), agent)
    opponent_character = args.opponent_character or args.character
    if args.player == 1:
        characters = [args.character, opponent_character]
        agents = [agent.name(), args.opponent]
    else:
        characters = [opponent_character, args.character]
        agents = [args.opponent, agent.name()]
    try:
        await gateway.run_game(characters, agents, args.games)
    finally:
        await gateway.close_game()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a semantic-action pyftg 2.3 agent.")
    # EDIT: these defaults are conveniences; CLI flags should pin every experimental run.
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=31415)
    # EDIT: use a unique socket name that does not collide with a Java AI jar.
    parser.add_argument("--name", default="MyAgent")
    # EDIT: choose the controlled and evaluation characters for each experiment.
    parser.add_argument("--character", default="ZEN")
    parser.add_argument("--opponent-character", default=None)
    # EDIT: this must match an available AI jar/controller name in the runtime.
    parser.add_argument("--opponent", default="MctsAi23i")
    parser.add_argument("--player", type=int, choices=(1, 2), default=1)
    parser.add_argument("--games", type=int, default=1)
    parser.add_argument(
        "--motion-root",
        type=Path,
        # EDIT: this must be the data/characters directory used by the SAME Java runtime.
        default=Path("runtime/DareFightingICE-7.1/FightingICE7.1/data/characters"),
    )
    parser.add_argument(
        "--demo-action",
        choices=tuple(action.name for action in POLICY_ACTIONS) + ("WAIT",),
        default=None,
    )
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Pass-2 launch wrapper for historical pyftg agents with explicit staging metadata.

The policy source remains unchanged.  ``RECOVERY_WORKING_DIR`` restores the working
directory assumed by a submitted launcher, while ``RECOVERY_CONSTRUCTOR_PROFILE``
restores documented constructor arguments that the generic Pass-1 loader could not know.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import logging
import os
from pathlib import Path

from pyftg.socket.aio.gateway import Gateway


def load_pass1_runner():
    path = Path(__file__).resolve().with_name("pyftg_compat_runner_base.py")
    spec = importlib.util.spec_from_file_location("pass1_pyftg_compat", path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BASE = load_pass1_runner()


def install_pyftg_2_0_model_aliases() -> None:
    """Restore constructors removed between the submitted pyftg API and pyftg 2.3."""
    from pyftg import FrameData

    if not hasattr(FrameData, "get_default_instance"):
        FrameData.get_default_instance = classmethod(lambda cls: cls())


def construct(agent_class, profile: str):
    if profile == "default":
        return agent_class()
    if profile == "benai_competition":
        # These are the same settings used by the submitted trained_ai/test.py launcher.
        return agent_class(
            logger=logging.getLogger("BenAI"),
            encoder="mel",
            path="trained_model",
            rnn=True,
        )
    raise ValueError(f"unknown constructor profile: {profile}")


def normalize_loaded_torch_device_metadata(delegate) -> None:
    """Move stale serialized ``.device`` hints to CPU when this runtime has no CUDA.

    ``map_location='cpu'`` moves tensors but does not rewrite arbitrary device attributes
    stored inside pickled modules.  CAS's submitted checkpoint contains such a nested hint.
    Rewriting only those execution-device hints preserves weights and network operations.
    """
    try:
        import torch
    except ImportError:
        return
    if torch.cuda.is_available():
        return
    for value in vars(delegate).values():
        if not isinstance(value, torch.nn.Module):
            continue
        value.to("cpu")
        for module in value.modules():
            if hasattr(module, "device"):
                module.device = torch.device("cpu")


async def run(args) -> None:
    install_pyftg_2_0_model_aliases()
    agent_class = BASE.load_class(args.source.resolve(), args.class_name)
    agent_class.__abstractmethods__ = frozenset()
    working_dir = os.environ.get("RECOVERY_WORKING_DIR")
    if working_dir:
        os.chdir(Path(working_dir).resolve())
    profile = os.environ.get("RECOVERY_CONSTRUCTOR_PROFILE", "default")
    delegate = construct(agent_class, profile)
    normalize_loaded_torch_device_metadata(delegate)
    adapter = BASE.PyftgCompatibilityAdapter(
        delegate, args.audit_file.resolve() if args.audit_file else None
    )
    name = adapter.name()
    gateway = Gateway(host="127.0.0.1", port=args.port)
    gateway.register_ai(name, adapter)
    agents = [name, args.opponent] if args.side == "P1" else [args.opponent, name]
    try:
        await gateway.run_game([args.character, args.character], agents, args.rounds)
    finally:
        await gateway.close_game()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--class-name", required=True)
    parser.add_argument("--character", required=True)
    parser.add_argument("--side", choices=("P1", "P2"), required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--opponent", default="MctsAi23i")
    parser.add_argument("--audit-file", type=Path)
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()

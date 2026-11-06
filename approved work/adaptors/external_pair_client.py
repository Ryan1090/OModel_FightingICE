#!/usr/bin/env python3
"""Register zero, one, or two external endpoints and run one engine game.

Historical policy construction is delegated to the already-validated recovery
constructor.  This file owns orchestration and trace capture only.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

for extra in os.environ.get("FIXING_LEARNER_SITE", "").split(os.pathsep):
    if extra and extra not in sys.path:
        sys.path.append(extra)


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ROOT = Path(r"D:\fightICE")
CONSTRUCT = load(
    "fixing_phase_construct_candidate",
    ROOT / "ai agent work/tools/adapter_io_audit_2026_09_25/run_step5_python_case_fixed.py",
)
TRACE = load(
    "fixing_phase_trace_agent",
    ROOT / "ai agent work/tools/mixed_interface_learner_harness_2026_10_02/scripts/harness_common.py",
)


def historical_endpoint(spec: dict, port: int):
    args = SimpleNamespace(
        tier=spec["tier"],
        source=Path(spec["source"]),
        class_name=spec["class_name"],
        working_directory=Path(spec["working_directory"]),
        constructor_profile=spec.get("constructor_profile", "default"),
        module_name=spec.get("module_name") or None,
        host="127.0.0.1",
        port=port,
        motion_root=Path(spec["motion_root"]),
    )
    return CONSTRUCT.construct_candidate(args)


def learner_endpoint(spec: dict, sink: list[dict]):
    import torch

    context = {
        "job": spec["job_id"],
        "opponent": spec["opponent"],
        "mode": spec.get("mode", "greedy"),
        "policy_seed": int(spec["policy_seed"]),
    }
    return TRACE.TraceEvaluationAgent(
        Path(spec["motion_root"]), Path(spec["checkpoint"]), torch.device("cpu"), sink, context
    )


async def run(args) -> dict:
    from pyftg.socket.aio.gateway import Gateway

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    sink: list[dict] = []
    gateway = Gateway(host="127.0.0.1", port=args.port)
    names: list[str] = []
    constructed = []
    for index, endpoint in enumerate(plan["endpoints"]):
        if endpoint["kind"] == "internal":
            names.append(endpoint["launch_name"])
            continue
        if endpoint["kind"] == "historical_python":
            agent = historical_endpoint(endpoint, args.port)
        elif endpoint["kind"] == "learner":
            agent = learner_endpoint(endpoint, sink)
        else:
            raise ValueError(f"unknown endpoint kind {endpoint['kind']}")
        name = agent.name()
        if name in names:
            name = f"{name}_FIXSIDE{index+1}"
            original_name = agent.name
            agent.name = lambda n=name, _old=original_name: n
        gateway.register_ai(name, agent)
        constructed.append(agent)
        names.append(name)

    if len(names) != 2:
        raise RuntimeError(f"expected two endpoint names, got {names}")
    try:
        await gateway.run_game(plan["characters"], names, int(plan.get("rounds", 1)))
    finally:
        try:
            await gateway.close_game()
        except Exception:
            pass

    payload = {
        "job_id": plan["job_id"],
        "endpoint_names": names,
        "learner_rounds": sink,
        "plan_sha256": hashlib.sha256(args.plan.read_bytes()).hexdigest(),
    }
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = asyncio.run(run(args))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

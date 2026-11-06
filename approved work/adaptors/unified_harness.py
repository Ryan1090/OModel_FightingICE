#!/usr/bin/env python3
"""Unified FightingICE route-validation harness.

The harness composes already-preserved controller routes without modifying agent
policy code.  It is an engineering validator, not a research-pass runner.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import importlib.util
import json
import os
import shutil
import socket
import stat
import struct
import subprocess
import sys
import time
import traceback
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(r"D:\fightICE")
TASK = ROOT / "ai agent work/tools/project_fixing_phase_2026_10_21"
A5 = ROOT / "ai agent work/tools/stock_competency_A5_extension_2026_10_03/report_bundle/five_character_eligibility_matrix.csv"
SOURCE_POOL = ROOT / "ai agent work/tools/aicontroller_race_blindai_runtime_2026_09_25/results/master/final_usable_opponent_pool.csv"
INVENTORY = ROOT / "ai agent work/audit/agent_inventory.csv"
AGENTS_ROOT = ROOT / "ai agent work/audit/work/agents"
DUAL_ADAPTER = TASK / "harness/dual-legacy-java-v1-adapter.jar"
CLIENT = TASK / "harness/external_pair_client.py"
PROFILES = TASK / "harness/COMPATIBILITY_PROFILES.json"
PY_MANIFEST = ROOT / "ai agent work/tools/adapter_io_audit_2026_09_25/adapters/pyftg_compat_v2/launch_manifest.json"
MAIN_SITE = ROOT / ".venv/Lib/site-packages"
DIRECT = set(range(2, 13)) | set(range(23, 25)) | set(range(27, 56))
STOCK_ASSET_HASHES = {
    "ZEN": {
        "gSetting.txt": "bae5b37d64ddd80c149eeae969903c9a97a0b262ff635263275b3ae31bc2c30a",
        "Motion.csv": "49bfe1dcbb669481b434418f2ba6890688922302f556073ad33f0539bf71c800",
    },
    "GARNET": {
        "gSetting.txt": "9045ff12cb28405502257599e29ec8336f6b6a64645f7aac7fd65dc15a2987c9",
        "Motion.csv": "f825dd81abfd6d273ce7190bf156faea7de609adf75511b8485fcd1b8fa9102e",
    },
    "LUD": {
        "gSetting.txt": "9045ff12cb28405502257599e29ec8336f6b6a64645f7aac7fd65dc15a2987c9",
        "Motion.csv": "6d3136cdefefae2417502ae25ece08ecdac4db74386e232efb31475054400de5",
    },
    "KFM": {
        "gSetting.txt": "ddc2f6c98d60f124aa3112ed33e09148229052aa36be8161344cf3cb01232990",
        "Motion.csv": "aeb524f6070e7f705376c76f67ec13951ca4909781e380107e8345c2432eff65",
    },
    "NEZ": {
        "gSetting.txt": "bae5b37d64ddd80c149eeae969903c9a97a0b262ff635263275b3ae31bc2c30a",
        "Motion.csv": "e9afadf05bb3cb5000d266e09bd75053c32851f7f12d2df05db28dd690014276",
    },
}


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


A_JAVA = load("fix_phase_a_java", ROOT / "ai agent work/tools/stock_competency_A_2026_09_30/scripts/run_java_screen.py")
A_PYTHON = load("fix_phase_a_python", ROOT / "ai agent work/tools/stock_competency_A_2026_09_30/scripts/run_python_screen.py")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def clean_runtime(runtime: Path) -> None:
    # Archived submissions can stage read-only resources (including packed SCM
    # metadata) into aiData.  Normalize permissions before the shared cleaner
    # unlinks them, matching the validated stock-screen lifecycle behavior.
    for relative in ("data/aiData", "data/ai"):
        root = runtime / relative
        if root.exists():
            for item in root.rglob("*"):
                try:
                    os.chmod(item, stat.S_IWRITE | stat.S_IREAD)
                except OSError:
                    pass
    A_PYTHON.BASE.JAVA_AUDIT.clean_stage(runtime)
    for relative in ("log/point", "log/replay", "log/style"):
        directory = runtime / relative
        directory.mkdir(parents=True, exist_ok=True)
        for item in directory.iterdir():
            try:
                os.chmod(item, stat.S_IWRITE | stat.S_IREAD)
            except OSError:
                pass
            shutil.rmtree(item) if item.is_dir() else item.unlink()
    for old in (runtime / "data/ai").glob("ReflectiveAdapterP?.jar"):
        old.unlink()


def replay_metrics(path: Path) -> dict:
    payload = path.read_bytes(); offset = 24; frames = []
    while offset + 40 <= len(payload):
        players = []
        for _ in range(2):
            front, remaining, action, hp, energy, x, y, key = struct.unpack_from(">?bbiiiiB", payload, offset)
            offset += 20
            players.append({"front": front, "remaining": remaining, "action": action & 255, "hp": hp,
                            "energy": energy, "x": x, "y": y, "key": key})
        frames.append(players)
    if not frames:
        raise RuntimeError("empty replay")
    sides = []
    for index in (0, 1):
        seq = [frame[index]["action"] for frame in frames]
        onsets = [{"frame": i, "action": action} for i, action in enumerate(seq) if i == 0 or action != seq[i - 1]]
        sides.append({
            "final_hp": frames[-1][index]["hp"], "final_energy": frames[-1][index]["energy"],
            "action_onsets": onsets, "action_onset_count": len(onsets),
            "distinct_actions": len(set(seq)), "direct_onsets": sum(x["action"] in DIRECT for x in onsets),
            "active_key_frames": sum(frame[index]["key"] != 0 for frame in frames),
        })
    fingerprint = hashlib.sha256(json.dumps({"frames": len(frames), "sides": sides}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {"elapsed_frames": len(frames), "sides": sides, "replay_sha256": hashlib.sha256(payload).hexdigest(),
            "gameplay_fingerprint_sha256": fingerprint}


class UnifiedHarness:
    def __init__(self, args):
        self.args = args
        self.a5 = {(row["agent_id"], row["character"]): row for row in read_csv(A5)}
        self.inventory = {row["agent_id"]: row for row in read_csv(INVENTORY)}
        self.pool = {row["agent_id"]: row for row in read_csv(SOURCE_POOL)}
        self.profiles = json.loads(PROFILES.read_text(encoding="utf-8"))
        self.py_manifest = json.loads(PY_MANIFEST.read_text(encoding="utf-8"))
        self.python_candidates = {}

    def preflight(self) -> dict:
        required = [self.args.engine, DUAL_ADAPTER, CLIENT, A5, SOURCE_POOL, INVENTORY, PROFILES, PY_MANIFEST]
        missing = [str(path) for path in required if not path.is_file()]
        if missing:
            raise FileNotFoundError("missing required assets: " + "; ".join(missing))
        if self.args.engine_sha256 and sha256(self.args.engine) != self.args.engine_sha256:
            raise RuntimeError("engine hash mismatch")
        hashes = {str(path): sha256(path) for path in required}
        for key, value in self.profiles["python_interpreters"].items():
            path = Path(value)
            if not path.is_file():
                raise FileNotFoundError(f"missing Python runtime {key}: {path}")
            hashes[str(path)] = sha256(path)
        if not MAIN_SITE.is_dir():
            raise FileNotFoundError(f"learner site-packages unavailable: {MAIN_SITE}")
        for index in range(self.args.workers):
            runtime = self.args.runtime_root / f"worker_{index}"
            for character, expected_files in STOCK_ASSET_HASHES.items():
                for relative, expected_hash in expected_files.items():
                    asset = runtime / "data/characters" / character / relative
                    if not asset.is_file():
                        raise FileNotFoundError(f"missing stock asset: {asset}")
                    actual_hash = sha256(asset)
                    if actual_hash != expected_hash:
                        raise RuntimeError(f"stock asset hash mismatch: {asset}")
                    hashes[str(asset)] = actual_hash
        return hashes

    def config(self, config_id: str) -> dict[str, str]:
        agent_id, character = config_id.rsplit("::", 1)
        row = self.a5.get((agent_id, character))
        if row is None:
            raise KeyError(f"unknown configuration {config_id}")
        return row

    def python_candidate(self, row: dict[str, str]):
        aid = row["agent_id"]
        if aid not in self.python_candidates:
            self.python_candidates[aid] = A_PYTHON.BASE.discover(self.pool[aid], self.inventory[aid], AGENTS_ROOT, self.py_manifest)
        return self.python_candidates[aid]

    def stage_current_java(self, runtime: Path, row: dict[str, str]) -> tuple[dict, list[str]]:
        launch, evidence = A_PYTHON.BASE.JAVA_AUDIT.stage_agent(self.inventory[row["agent_id"]], AGENTS_ROOT, runtime)
        return {"kind": "internal", "launch_name": launch}, evidence

    def java_primary(self, row: dict[str, str]) -> Path:
        profile = self.profiles["java_profiles"].get(row["agent_id"], {})
        if "primary_override" in profile:
            return Path(profile["primary_override"])
        primary = self.inventory[row["agent_id"]].get("primary_artifact", "")
        if not primary:
            raise RuntimeError(f"no primary Java artifact for {row['agent_id']}")
        return AGENTS_ROOT / primary

    def stage_adapter(self, runtime: Path, row: dict[str, str], side: str, ports: Path) -> tuple[dict, list[str], list[str]]:
        side_key = side.lower(); class_launch = "ReflectiveAdapterP1" if side == "P1" else "ReflectiveAdapterP2"
        primary = self.java_primary(row)
        inventory_row = self.inventory.get(row["agent_id"])
        entry = AGENTS_ROOT / inventory_row["entry_path"] if inventory_row else primary.parent
        class_name, discover_evidence = A_JAVA.BASE.LEGACY.discover_class(primary, row["agent_name"])
        if not class_name:
            raise RuntimeError(f"legacy class discovery failed for {row['agent_id']}: {discover_evidence}")
        combined = ports / f"{side}_{row['agent_id']}.jar"
        A_JAVA.BASE.LEGACY.merge_adapter(DUAL_ADAPTER, primary, combined)
        profile = self.profiles["java_profiles"].get(row["agent_id"], {})
        append = profile.get("append_entry_from_jar")
        if append:
            with zipfile.ZipFile(Path(append["source"])) as source:
                content = source.read(append["entry"])
            with zipfile.ZipFile(combined, "a") as target:
                target.writestr(append["entry"], content)
        destination = runtime / "data/ai" / f"{class_launch}.jar"
        shutil.copy2(combined, destination)
        shutil.copy2(DUAL_ADAPTER, runtime / "lib/000_fixing_phase_dual_adapter.jar")
        resources, copied = A_JAVA.BASE.LEGACY.stage_resources(entry, primary, runtime)
        extra = profile.get("copy_glob_to_ai_data")
        if extra:
            for item in entry.glob(extra):
                shutil.copy2(item, runtime / "data/aiData" / item.name)
                copied.append(f"{item} -> data/aiData/{item.name}")
        dummy = "0" if class_name == "Tomatensimulator" else "-1"
        try:
            old_year = int(row["agent_id"][:4]) <= 2016
        except ValueError:
            old_year = False
        props = [f"-Dlegacy.{side_key}.agent.class={class_name}",
                 f"-Dlegacy.{side_key}.empty.frame.number={dummy}",
                 f"-Dlegacy.{side_key}.remaining.time.unit={'milliseconds' if old_year else 'seconds'}"]
        evidence = [discover_evidence, f"combined_sha256={sha256(combined)}", "resources=" + ";".join(resources)]
        return {"kind": "internal", "launch_name": class_launch}, evidence, props

    def stage_historical_python(self, runtime: Path, case: Path, row: dict[str, str]) -> tuple[dict, list[str]]:
        candidate = self.python_candidate(row)
        staged = case / f"staged_{row['agent_id']}"
        if staged.exists():
            shutil.rmtree(staged)
        shutil.copytree(candidate.entry, staged)
        source = staged / candidate.source_relative; working = staged / candidate.working_relative
        spec = {"kind": "historical_python", "agent_id": row["agent_id"], "tier": candidate.tier,
                "source": str(source), "class_name": candidate.class_name, "working_directory": str(working),
                "constructor_profile": candidate.constructor_profile, "module_name": candidate.module_name,
                "motion_root": str(runtime / "data/characters")}
        return spec, [f"staged_source={source}", f"source_sha256={sha256(source)}"]

    def interpreter(self, endpoint_rows: list[dict[str, str]]) -> Path:
        mapping = self.profiles["python_interpreters"]
        selected = [Path(mapping[row["agent_id"]]) for row in endpoint_rows if row["agent_id"] in mapping]
        unique = {str(path).lower(): path for path in selected}
        if len(unique) > 1:
            raise RuntimeError("two external endpoints require incompatible isolated Python runtimes")
        return next(iter(unique.values())) if unique else Path(mapping["default"])

    def stage_endpoint(self, runtime: Path, case: Path, config_id: str, side: str, ports: Path):
        row = self.config(config_id)
        route = row["interface_type"]
        if route in ("Java:running",):
            endpoint, evidence = self.stage_current_java(runtime, row); return endpoint, evidence, [], row
        if route in ("Java:adapter_java", "Java+Kotlin:adapter_java"):
            endpoint, evidence, props = self.stage_adapter(runtime, row, side, ports); return endpoint, evidence, props, row
        if route.startswith("Python:"):
            endpoint, evidence = self.stage_historical_python(runtime, case, row); return endpoint, evidence, [], row
        raise RuntimeError(f"unsupported route {route}")

    def wait_server(self, process, log: Path, seconds: int) -> None:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"engine exited during startup: {process.returncode}")
            text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
            if A_PYTHON.BASE.JAVA_AUDIT.FAILURE_RE.search(text):
                raise RuntimeError("fatal engine exception during startup")
            if ("gRPC server started" in text or "Server started" in text or "Waiting for connection" in text
                    or "Socket server is started" in text or "Waiting to launch a game" in text):
                return
            time.sleep(0.1)
        raise TimeoutError("engine startup timeout")

    def monitor(self, engine, client, engine_log: Path, timeout: int) -> None:
        deadline = time.monotonic() + timeout
        last_size = -1
        while time.monotonic() < deadline:
            client_code = client.poll(); engine_code = engine.poll()
            if engine_log.exists():
                size = engine_log.stat().st_size
                if size != last_size:
                    last_size = size
                    text = engine_log.read_text(encoding="utf-8", errors="replace")
                    if A_PYTHON.BASE.JAVA_AUDIT.FAILURE_RE.search(text):
                        raise RuntimeError("fatal engine exception")
            if client_code is not None:
                if client_code != 0:
                    raise RuntimeError(f"external coordinator exited {client_code}")
                return
            if engine_code is not None:
                text = engine_log.read_text(encoding="utf-8", errors="replace") if engine_log.exists() else ""
                if engine_code != 0 or "Game over" not in text:
                    raise RuntimeError(f"engine exited before normal game completion: {engine_code}")
                # Normal server shutdown can win the race with the external
                # coordinator's final JSON flush.  Keep the frozen wall clock
                # and wait only for that already-running client to finish.
            time.sleep(0.1)
        raise TimeoutError("job wall timeout")

    def run_job(self, slot: int, job: dict) -> dict:
        started = time.perf_counter(); runtime = self.args.runtime_root / f"worker_{slot}"
        case = self.args.output / "cases" / job["job_id"]; ports = case / "ports"
        case.mkdir(parents=True, exist_ok=True); ports.mkdir(parents=True, exist_ok=True)
        engine = client = engine_handle = out_handle = err_handle = None
        attempt = {"job": job, "status": "FAILED", "failure_category": "", "failure": ""}
        try:
            clean_runtime(runtime)
            if sha256(runtime / "FightingICE.jar") != self.args.engine_sha256:
                raise RuntimeError("runtime engine hash mismatch")
            endpoint_specs = []; java_props = []; evidence = []; rows = []
            for side, key in (("P1", "p1_config"), ("P2", "p2_config")):
                side_number = 1 if side == "P1" else 2
                if job.get(f"p{side_number}_kind") == "learner":
                    endpoint_specs.append(None)
                    rows.append({"agent_id": f"LEARNER_{job.get(f'p{side_number}_checkpoint_id', 'UNKNOWN')}",
                                 "agent_name": "ZEN_LEARNER", "language": "Learner"})
                    continue
                endpoint, ev, props, row = self.stage_endpoint(runtime, case, job[key], side, ports)
                endpoint_specs.append(endpoint); evidence.extend([f"{side}:{x}" for x in ev]); java_props.extend(props); rows.append(row)
            if job.get("p1_kind") == "learner" or job.get("p2_kind") == "learner":
                for index, kind in enumerate((job.get("p1_kind"), job.get("p2_kind"))):
                    if kind != "learner": continue
                    checkpoint = Path(job[f"p{index+1}_checkpoint"])
                    endpoint_specs[index] = {"kind": "learner", "checkpoint": str(checkpoint),
                        "motion_root": str(runtime), "job_id": job["job_id"],
                        "opponent": rows[1-index]["agent_name"], "mode": job.get("mode", "greedy"),
                        "policy_seed": int(job.get("policy_seed", "1"))}
            plan = {"job_id": job["job_id"], "endpoints": endpoint_specs,
                    "characters": [job["p1_character"], job["p2_character"]], "rounds": int(job.get("rounds", 1))}
            plan_path = case / "client_plan.json"; atomic_json(plan_path, plan)
            port = free_port(); engine_log = case / "engine.log"
            mask_sides = job.get("mask_sides", "OFF").strip()
            mask_props = [] if mask_sides in ("", "OFF", "NONE") else [f"-Dfightingice.syntheticNameMaskSides={mask_sides}"]
            command = ["java", "-Xms64m", "-Xmx512m", *java_props, *mask_props,
                "--enable-native-access=ALL-UNNAMED", "-cp",
                "FightingICE.jar;./lib/*;./lib/lwjgl/*;./lib/lwjgl/natives/windows/amd64/*;./lib/grpc/*",
                "Main", "--pyftg-mode", "--lightweight-mode", "--input-sync", "--mute", "--err-log",
                "--limithp", "400", "400", "-r", str(job.get("rounds", 1)), "-f", str(job["frames"]), "--port", str(port)]
            engine_handle = engine_log.open("w", encoding="utf-8")
            engine_started = time.perf_counter()
            engine = subprocess.Popen(command, cwd=runtime, stdout=engine_handle, stderr=subprocess.STDOUT,
                                      creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.wait_server(engine, engine_log, int(job.get("startup_timeout_seconds", 60)))
            startup_seconds = time.perf_counter() - engine_started
            output_json = case / "client_result.json"; client_out = case / "client.stdout.log"; client_err = case / "client.stderr.log"
            python_rows = [row for row in rows if row["language"] == "Python"]
            interpreter = self.interpreter(python_rows)
            env = os.environ.copy(); env["PYTHONPYCACHEPREFIX"] = str((self.args.output / "python-pycache").resolve())
            env["PYTHONNOUSERSITE"] = "1"; env["FIXING_LEARNER_SITE"] = str(MAIN_SITE)
            out_handle = client_out.open("w", encoding="utf-8"); err_handle = client_err.open("w", encoding="utf-8")
            client_started = time.perf_counter()
            client = subprocess.Popen([str(interpreter), str(CLIENT), "--plan", str(plan_path), "--port", str(port),
                                       "--output", str(output_json)], cwd=case, env=env, stdout=out_handle, stderr=err_handle,
                                      creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.monitor(engine, client, engine_log, int(job.get("wall_timeout_seconds", 180 if int(job["frames"]) <= 600 else 420)))
            client_wall_seconds = time.perf_counter() - client_started
            result = json.loads(output_json.read_text(encoding="utf-8"))
            replays = sorted((runtime / "log/replay").glob("*.dat"), key=lambda path: path.stat().st_mtime)
            if not replays:
                raise RuntimeError("missing replay")
            metrics = replay_metrics(replays[-1])
            if metrics["elapsed_frames"] <= 0 or not all(side["action_onset_count"] > 0 for side in metrics["sides"]):
                raise RuntimeError("invalid or empty action trace")
            for round_row in result.get("learner_rounds", []):
                if int(round_row.get("observation_count", 0)) <= 0 or int(round_row.get("nonfinite_observations", 0)) != 0:
                    raise RuntimeError("learner observation invariant failed")
                if int(round_row.get("requested_count", 0)) <= 0 or int(round_row.get("realised_onset_count", 0)) <= 0 or int(round_row.get("opponent_onset_count", 0)) <= 0:
                    raise RuntimeError("learner action/onset invariant failed")
            attempt.update(status="PASSED", evidence=evidence, client=result, metrics=metrics,
                           startup_seconds=startup_seconds, client_wall_seconds=client_wall_seconds,
                           wall_seconds=time.perf_counter() - started)
        except TimeoutError as error:
            attempt.update(failure_category="TIMEOUT", failure=f"{type(error).__name__}: {error}", wall_seconds=time.perf_counter() - started)
        except Exception as error:
            attempt.update(failure_category="IMPLEMENTATION_OR_CONTROLLER", failure=f"{type(error).__name__}: {error}\n{traceback.format_exc()}", wall_seconds=time.perf_counter() - started)
        finally:
            for process in (client, engine):
                if process is not None and process.poll() is None:
                    process.terminate()
                    try: process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill(); process.wait(timeout=5)
            for handle in (out_handle, err_handle, engine_handle):
                if handle is not None: handle.close()
            atomic_json(self.args.output / "jobs" / f"{job['job_id']}.json", attempt)
        return attempt

    def run(self, jobs: list[dict]) -> list[dict]:
        buckets = [[] for _ in range(min(self.args.workers, len(jobs)))]
        for index, job in enumerate(jobs): buckets[index % len(buckets)].append(job)
        results = []
        def worker(slot, bucket):
            values = []
            for job in bucket:
                result = self.run_job(slot, job); values.append(result)
                print(f"[{job['job_id']}] {result['status']}", flush=True)
            return values
        with ThreadPoolExecutor(max_workers=len(buckets)) as executor:
            futures = [executor.submit(worker, slot, bucket) for slot, bucket in enumerate(buckets)]
            for future in as_completed(futures): results.extend(future.result())
        return sorted(results, key=lambda row: row["job"]["job_id"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schedule", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--engine-sha256", required=True)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--job-ids", nargs="*")
    args = parser.parse_args()
    for key in ("schedule", "runtime_root", "output", "engine"):
        setattr(args, key, getattr(args, key).resolve())
    args.output.mkdir(parents=True, exist_ok=True)
    jobs = read_csv(args.schedule)
    if args.job_ids: jobs = [job for job in jobs if job["job_id"] in set(args.job_ids)]
    harness = UnifiedHarness(args); hashes = harness.preflight(); started = time.perf_counter()
    results = harness.run(jobs)
    summary = {"jobs": len(results), "passed": sum(row["status"] == "PASSED" for row in results),
               "failed": sum(row["status"] != "PASSED" for row in results), "wall_seconds": time.perf_counter() - started,
               "engine_sha256": args.engine_sha256, "harness_sha256": sha256(Path(__file__)), "asset_hashes": hashes}
    atomic_json(args.output / "summary.json", summary)
    atomic_json(args.output / "status.json", {"state": "complete" if not summary["failed"] else "failed", **summary})
    print(json.dumps(summary, indent=2))
    raise SystemExit(1 if summary["failed"] else 0)


if __name__ == "__main__":
    main()

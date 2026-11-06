# Historical Python/pyftg adapter

- `pyftg_compat_runner_base.py` restores legacy pyftg imports and callback/model compatibility.
- `pyftg_compat_runner.py` adds the validated launch-context, constructor and execution-device compatibility layer.
- `launch_manifest.json` records the small submission-specific launch contexts justified by archived submission evidence.

These files adapt APIs and runtime context only; they do not rewrite controller decisions, weights or policy source.

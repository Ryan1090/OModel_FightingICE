# Synthetic FightingICE generator — standalone folder

**Version 1.2.0.** Copy or move this entire `synthetic generator` folder wherever
you want to keep it. Its code, stock models, approved engine assets, third-party
Python libraries and configuration travel together. Historical catalogues,
archives and run evidence are kept in untracked research storage, outside this
approved package.
Nothing under `ai agent work`, an old virtual environment, `%LOCALAPPDATA%`, or
another project folder is required to run the generator.

Windows x64, **Python 3.12 x64** and a **Java/JDK** installation with `java` and
`javac` on PATH remain system requirements. All seven required third-party Python
distributions are included in `python_lib`; no pip install or access to the old
repository's `.venv` is needed. Original library licences are included.

## Start here

From PowerShell, in this folder:

```powershell
.\run.ps1 -Action Check
.\run.ps1 -Action Run -Background
.\run.ps1 -Action Status
.\run.ps1 -Action Pause
.\run.ps1 -Action Resume -Workers 8 -Background
```

Check verifies configuration, source, dependencies and engine assets without
gameplay. Run starts the whole process. The launcher also works from another
current directory because it resolves paths from its own folder. Alternatively:

```powershell
py -3.12 -I -S .\generator.py --action Check
py -3.12 -I -S .\generator.py --action Run --background
```

`-I -S` isolates Python from user packages and site configuration; the entry point
loads the bundled libraries itself. No production run was started during this
standalone conversion.

## Folder layout

```text
synthetic generator/
  run.ps1                   PowerShell launcher
  generator.py              Python entry point
  config.json               Editable settings for a new run
  RELEASE.json              Frozen source, asset and library hashes
  src/                      Complete generator and validator implementation
  assets/                   Stock models, tables, engine and runtime assets
  python_lib/               Pinned Python libraries and their dependencies
  verification/             Software checks and reference vectors
  provenance/               Dependency metadata and source lineage
  generated characters/
    catalogue_001/          Default destination for the next run, created on Run
```

The approved package contains the essentials to rerun generation from scratch.
The existing 630-candidate catalogue and its archives remain preserved in
untracked research storage. They are not needed to run this generator. Future
output under `generated characters` is ignored by Git; its documentation remains
tracked.

## Settings and output

Edit [config.json](config.json) before a new run. The default is:

```json
"output_directory": "generated characters/catalogue_001"
```

This path is relative to the configuration file. With the configuration here,
moving this folder to C: makes the output use C: automatically. Configuration
files and output folders stay inside this generator folder; there are no
hard-coded drive letters or external project dependencies. `--config` selects
another configuration kept inside this folder. Its relative output resolves
from that configuration's directory. Run-index paths are relative too.

| Setting | Default | Meaning |
| --- | --- | --- |
| `run_id` | `catalogue_001` | Seed namespace and catalogue identity |
| `workers` | 8 | Concurrency; Resume may override it |
| `retain_evidence` | `false` | Keep detailed evidence permanently when true; otherwise compact it after final verification |
| `quotas_per_root` | A60, B10, C-iid20, C-near16, C-far20 | Per stock, 630 total |
| `ranges` | Validated role/background/far ranges | Shared by sampling and readout |
| `stops` | Final operational policy | Acceptance, qualified forecast, two-day active-time and draw limits |

A/B/C-iid/C-far amounts must be positive multiples of ten; C-near must be a
positive multiple of sixteen. This preserves all trait/sign and reserved-pair
strata. Range validation preserves role separation and the secondary gap.

A run freezes effective settings in `RUN_CONFIG.json`. Resume requires those
same settings and output location. A new configuration needs a new run ID and
empty output folder. Move the generator before starting a run: interrupted
evidence in an already-started run retains absolute commitment paths, so moving
an unfinished run requires a separate evidence migration.

Changed quotas/ranges are new experimental configurations and do not inherit
the default paper packing/equalisation results. The same checks still run; some
configurations may not fill. Loadings, factors, scales, operators, no-op rules,
minimum step, tolerances, floors and diversity gates are fixed release assets.

## Optional evidence retention

```json
"retain_evidence": false
```

- **False (default):** after the complete final verification passes, keep accepted
  tables, traits/profile summaries, configuration, hashes, checkpoints and compact
  run statistics. Remove detailed gameplay traces, per-probe evidence, rejected
  candidate workspaces, runtime caches and the large working archive. Public A/B
  tables live under `catalogue/A` and `catalogue/B`; C final tables and their compact
  metadata remain in a small encrypted archive, without gameplay logs/traces.
- **True:** keep the original full evidence archive and working output, allowing
  later raw-trace audits.

Both settings perform the same screening, repair, admission and final verification.
This setting controls long-term retention, not whether validation runs. The final
summary explicitly records when raw evidence was checked and then removed.

Working evidence is temporary but still necessary during generation: it supports
resuming an interrupted screen, reusing compatible probes, and the final integrity
scan. Temporary disk usage can therefore still reach several gigabytes. Failed or
paused runs keep it so Resume can continue. Cleanup itself is transactional and
resumable; a failed export never silently removes the original working evidence.

Completed characters can be kept and reused without raw evidence. Their table
bytes, identity/configuration and compact acceptance/hash records remain. A table
alone cannot tell the runner which probes of an unfinished screen have completed.
The completed marker prevents an already-finished run from generating it again.

Choose retention before Run. As with other frozen settings, it cannot be changed
midway through an existing run.

## Workflow and output

One Run performs generation, screening, batched repairs, quota filling,
checkpoints, final verification and archive creation in order
**A → B → C-iid → C-near → C-far**. It uses the frozen V24 numerical design,
V27 selector, V26 batched loop and validated V41 moving-horizontal-reach fallback.

There are at most three joint repair rounds and five logical screens. Probe
limits stay 20/40 seconds with one identical-probe retry. The 30-minute safety
epoch is infrastructure recovery, not elapsed-time character rejection.
Scientific writes retain their durable saves and integrity checks.

Balanced checkpoints report at ten accepted A per stock and two accepted C-far
per stock, bounded by configured amounts, then continue. Status contains
pool/stratum progress, reverts, live work, forecast and minute CPU/memory/disk
counters. The default C-far acceptance-rate stop is disabled; other pools retain
50% after ten completed decisions. Admission criteria never loosen automatically.

| Run output | Contents |
| --- | --- |
| `status.json` | Live aggregate progress and resource counters |
| `RUN_CONFIG.json`, `RELEASE_BINDING.json` | Frozen settings and software binding |
| `characters/` | A/B candidates, final tables and evidence |
| `catalogue/` | Compact accepted A/B tables and relative-path index when retention is off |
| `A_B_FINAL_CHARACTERS.json` | Accepted A/B table index |
| `workers/`, `runtime_assets/` | Owned runtime and immutable engine assets |
| `checkpoints/` | Balanced A/far checkpoint snapshots |
| `PRE_FREEZE_VERIFICATION.json` | Final integrity, quotas, profiles, distances, far criteria, distributions and diversity |
| `SEALED_POOL_C.sqlite`, `SEALED_POOL_C.FINAL.json` | Encrypted C archive and checksum |
| `CATALOGUE.json`, `EVIDENCE_RETENTION.json` | Compact-output hashes and retention outcome when retention is off |
| `FINAL.json`, `PRODUCTION_COMPLETED.json` | Completion and review markers |

C per-character records remain encrypted; public C reports contain aggregates.
Temporary private workspaces are captured and removed. A completed archive is
sealed once; ordinary Status/Resume does not reopen it. Windows DPAPI remains
bound to the originating account/profile. Moving drives on the same account
does not change those archive bytes.

## Verification and release

`RELEASE.json` binds source, models, assets and bundled Python libraries.
`config.json` remains an editable template. Original source locations recorded in
lineage metadata are historical identifiers, not runtime dependencies. Raw run
archives and historical report copies are excluded from this package.

Repeat the integrated software controls without gameplay:

```powershell
py -3.12 -I -S .\verify.py
```

Fixtures are written under `verification/work` inside this folder. Checks cover
630 seeded profiles, 55 complete tables, original selector/repair/witness bodies,
corruption refusal, resume, provisioning, worker spawning and archive controls.
The standalone layout is also tested from an unrelated working directory with
bare Python and site packages disabled. No new gameplay equivalence cohort or
production catalogue is claimed.

Additional storage controls cover both retention choices, exact final-table
exports, C privacy, corrupt export refusal, interrupted compaction/sealing and
completed-character reuse without the working archive.

The existing 630 are **candidate characters**. Competency filtering, weighted
sampling and final dataset membership remain undecided. Freezing this generator
does not freeze that eventual split.

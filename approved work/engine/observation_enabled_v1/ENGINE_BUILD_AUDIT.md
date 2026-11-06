# Engine-build audit

Record version: `ENGINE-BUILD-AUDIT-V1`  
Status: static audit complete; prospective equivalence execution completed but inconclusive

## Builds used

| Passes | Engine SHA-256 | Located artifact |
|---|---|---|
| B | `bcab2deb9e8a59ea1358287ae519c69eab64bca9432cb023de6307c23e57919b` | `stock_competency_A_2026_09_30/work/full_java_workers/worker_0/FightingICE.jar` |
| B5 | `86dc1bd920bf073f140f420a9d7487e0f208687470b47f57828c9ea2d4d91270` | `C:/Users/Ryanm/AppData/Local/fightICE_hot/stock_competency_A5_extension_2026_10_03_v2/runtimes/worker_0/FightingICE.jar` |
| D5, E, 2A, 2B | `0b1defaff286e892481f27572b2d951c3da1ab60ce04928e4a6453510a8b5635` | `synthetic_functional_D5_2026_10_04/work/FightingICE.d5.audit.jar` |

The B hash is recorded in `stock_competency_B_2026_09_30/report_bundle/LAUNCH_CONTRACT.json` line 31. D5 and E independently freeze the audited build in `D_FREEZE.json` lines 17-19 and `E_FREEZE.json` lines 18-20. Passes 2A/2B record the same audited-engine hash.

## Bytecode-level differences

A complete ZIP-entry SHA-256 comparison found exactly these differences:

- B to B5:
  - `fighting/CommandAcceptanceLogger.class` was added;
  - `fighting/Fighting.class` changed.
- B5 to D5/E/2A/2B:
  - only `aiinterface/AIController.class` changed.

`javap` inspection shows that B5's `Fighting.processingCommands` takes an added player index and invokes `CommandAcceptanceLogger.log(...)` with frame, side, character, requested action, and acceptance. The logger is observational file output. B's `Fighting` also contains a private `baseCharacterName` helper that is absent in B5, so the B-to-B5 difference is not safely describable as logger-only until gameplay equivalence is tested. Existing style-tracker fields and per-frame style updates exist in both builds.

The source corresponding to the audited AIController is preserved as `synthetic_functional_D5_2026_10_04/contract/AIController.java`, SHA-256 `40bc2b61240974d4d9ac4cd0fc8c8d981a9ea394662af658a85671ac37714e78`. Compared with the earlier name-mask source, SHA-256 `d8637c5b4ec09274f08d4d7a0643d7707f540982601d3174f06d7e34c3574791`, it adds audit emission and dynamic mechanic extraction. The masking decision already exists in B and B5 bytecode; D5 adds audit observability rather than introducing the mask itself.

## Expected implications

- Name masking changes only the selected historical controller's `GameData` view. The engine retains the true synthetic identity and actual MotionData.
- D5 audit additions should affect log observability, not action selection, timing, physics, HP, or termination.
- B5 command-acceptance logging should be observational, but B's additional `Fighting` helper means behavioural equality must be demonstrated, not assumed.
- Engine instrumentation can change wall time or I/O even when gameplay is identical; throughput is therefore reported separately from gameplay equivalence.

## Prospective gameplay-test result

All three builds completed their unchanged 120-cell schedules: B 120/120, B5 120/120, and D5/E/2A/2B 120/120, with no execution failure. This establishes route compatibility for the sampled cells, but the frozen equivalence rule did **not** pass:

- exact gameplay fingerprints across builds: 0/120;
- exact stock-name mask/no-mask null pairs: 0/180; and
- repeated statistical build comparisons passing the frozen bounds: 1/36.

The null failures show that the selected controller pairings were not deterministic under these independent launches. Final HP and onset-count differences were also too variable for the prospectively frozen bounds. Consequently, this result neither establishes build equivalence nor establishes a semantic build difference: the comparison method cannot separate ordinary controller/run variation from a build effect in this cohort.

Changing the reference controllers, seeding method, repetitions, pairing model or equivalence bounds would change the prospective evaluation protocol. None is changed automatically. `ENGINE_EQUIVALENCE_RESULT.json`, SHA-256 `f8b4c5e40655ff294adc4ae65b69a4dd9f9bce755cf1d4b5aacf3bd743a6ea77`, preserves the complete result.

## Standard-build proposal

No standard build is proposed for adoption from this failed gate. The D5/E/2A/2B build remains the practical validation build because it is the latest audited build and uniquely supplies the required information-boundary audit, but that is continuity of existing engineering use—not an equivalence finding. A revised controlled comparison and user approval are required before designating it as the universal future build.

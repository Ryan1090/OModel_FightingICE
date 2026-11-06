# Consolidated implementation fixes

Record version: `FIXING-PHASE-IMPLEMENTATION-FIXES-V1`  
Date: 2026-10-23  
Scope: engineering restoration only; no historical policy, eligibility, information-access, dataset, model, split, threshold or research-protocol change

## Final frozen stack

| Artifact | SHA-256 |
|---|---|
| `harness/unified_harness.py` | `340239ee6d8e0002b34ef8780c129e2be4262e2aed1cca07e57dddd09951773e` |
| `harness/dual-legacy-java-v1-adapter.jar` | `6dcaa9747b0fc733b6d33178bacd9bde0369dc1bc60ab62e1b2d08705ee1a5b5` |
| `harness/external_pair_client.py` | `4f0dd11d4835fd061c80f40fe622f38ba7693da0dbb7ea3140a94cfe1015ce4d` |
| `harness/src/SideReflectiveAdapter.java` | `ab98c3a083e89f66adc413a888f98518085fda82e5938a7b82e7b7d01984201e` |
| `harness/src/structs/FrameData.java` | `8469d2e5d9f4884a4541ae0e8c9d0ce831aecb7055bb2e67889a4f754874da80` |
| `scripts/build_dual_adapter.ps1` | `0e1badda818275c53fad9f4555c7e4cf36aafeb26e023db477eff7e436d06fd3` |

## Fixes

| Fix | Defect | Minimal correction | Verification |
|---|---|---|---|
| Engine readiness | The readiness gate omitted the audited engine's actual `Socket server is started` and `Waiting to launch a game` messages. | Recognize those existing messages without changing the 60-second gate. | Unchanged launch control passed. |
| Normal exit race | A normal zero-code engine exit after `Game over` could precede the external coordinator's final result flush. | Permit only that already-normal state to await the coordinator within the unchanged wall ceiling; all abnormal exits still fail fast. | Unchanged lifecycle control passed. |
| Py4J constructor context | The coordinator omitted the preserved Py4J bridge's host, port and Motion-root inputs. | Propagate the allocated loopback endpoint and staged stock Motion root. | Adapter/Py4J and Py4J/Py4J controls passed. |
| Throughput observability | Job records lacked comparable startup and client durations. | Record monotonic durations around existing calls. | Fields populated across final controls and full-horizon runs. |
| Learner Motion root | The learner received `runtime/data/characters` even though it appends that suffix itself. | Pass the runtime root to learner endpoints only; keep the distinct historical Py4J contract unchanged. | Full-horizon regression passed 36/36. |
| KFM stock staging | The validation template and workers omitted stock KFM assets. | Stage audited v7.1 KFM assets and hash-check `gSetting.txt` and `Motion.csv` for all five stock characters. | All 486 affected KFM rows passed after clean replacement. |
| HAL metadata delegation | HAL has a frozen primary override but no inventory row; staging dereferenced inventory first. | Use the explicit override JAR's parent when that inventory row is absent. | All 30 HAL rows passed. |
| Side-scoped legacy translation | The adapter emitted per-side compatibility settings while inherited `FrameData` read obsolete global settings. | Give each translated `FrameData` its frozen empty-frame marker and remaining-time unit. | All 24 former Tomatensimulator failures and mixed API-generation controls passed. |
| Read-only cleanup | HAL staging copied a read-only packed Git object and cleanup failed before launch. | Normalize permissions in staged `data/ai` and `data/aiData` before the existing cleanup. | All eight positive controls passed; no cleanup failures in the final rerun. |

## Final integration result

The final hash-frozen rerun completed 1,674/1,674 jobs: the complete 72-cell ordered route matrix, 1,566 learner rows affected by the shared repairs, and all 36 full-horizon learner regressions. Replacement rows supersede earlier attempts only by original job ID. Failed and intermediate attempts remain provenance and are absent from the final ledgers.

The complete learner-population ledger contains 2,718 cells. It passed 2,700 and failed 18. The failures are exactly the three ZoneAI configurations on ZEN, GARNET and LUD across all three checkpoints and both orientations. Each failure originates in preserved `ZoneAI.processing` through a non-positive `Random.nextInt` bound. Altering that controller would change historical policy behaviour and was not authorized.

The original per-fix files and freeze records remain byte-preserved under `results/provenance/implementation_fixes/`.

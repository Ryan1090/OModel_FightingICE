# Adapter provenance

## Source snapshots

- Legacy Java v3 base: `ai agent work/tools/adapter_io_audit_2026_09_25/adapters/legacy_java_v3/`
- Historical Python/Py4J: `ai agent work/tools/adapter_io_audit_2026_09_25/adapters/py4j_compat_v2/`
- Historical Python/pyftg: `ai agent work/tools/adapter_io_audit_2026_09_25/adapters/pyftg_compat_v2/`
- Final side-scoped Java wrapper and shared orchestration: `ai agent work/tools/project_fixing_phase_2026_10_21/harness/`
- Dual-adapter build recipe: `ai agent work/tools/project_fixing_phase_2026_10_21/scripts/build_dual_adapter.ps1`
- Verification record: `ai agent work/tools/project_fixing_phase_2026_10_21/report_bundle/IMPLEMENTATION_FIXES_CONSOLIDATED.md` and `FINAL_SUMMARY.json`

The obsolete `legacy-java-v2-adapter.jar`, build products, Python bytecode caches and raw run outputs were intentionally not admitted.

## Admission decision

The researcher explicitly approved the adapter methods for admission on 2026-10-23. Codex checked the final completed fixing-pass evidence, copied the selected source/runtime bytes without modification, and verified their destination hashes against the source hashes.

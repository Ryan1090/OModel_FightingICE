# Approved work

This directory is the curated authority area for dissertation-critical artifacts.

## Admission rule

Artifacts are added only after the relevant work has completed and both the researcher and Codex have explicitly accepted them. Admission copies the frozen bytes; it does not delete or rewrite the original evidence. Every admitted artifact must retain provenance and SHA-256 verification.

Any subsequent engine change must be reported to the researcher, including its purpose, byte/source diff, verification result and scientific implications. Codex must obtain explicit approval before adding the changed engine to `approved work`. An approved engine version is immutable: a changed build must be admitted under a new versioned directory and must never overwrite an existing approved version.

## Approved as of 2026-10-23

- `adaptors/`: the three approved compatibility methods plus the final shared orchestration files used to validate them.
- `engine/observation_enabled_v1/`: the approved observation-enabled FightingICE engine, its changed source file and its provenance/equivalence records.

At that initial admission, `synthetic generator/` and `verification passes/` were empty.

## Added 2026-11-05

- [`synthetic generator/`](<synthetic generator/README.md>): user-approved consolidation of the validated numerical generator, final selector, batched repair loop, moving-reach witness and engineering controls. One runnable process, configurable pool amounts/ranges, shared approved engine and owned stock/runtime assets, bundled third-party Python libraries and folder-relative outputs. No `ai agent work` or old virtual-environment dependency. Current release 1.2.1 uses the sibling `engine/observation_enabled_v1` JAR instead of bundling a duplicate. Move both folders together. Optional evidence retention is off by default, preserving temporary resume/verification data until successful final verification, then retaining final characters and compact records. Preceding source/packaging metadata is preserved under `ai agent work`.
- [`synthetic generator/generated characters/`](<synthetic generator/generated characters/README.md>): Git-ignored output folder for fresh runs. Previous catalogues, archives and raw evidence remain in untracked research storage; approved work contains the essentials to rerun generation from scratch. Final competency filtering and dataset membership remain undecided.

## Important migration note

This is currently an authoritative artifact collection, not yet a standalone replacement for all of `ai agent work`. The frozen shared harness and compatibility profiles deliberately retain paths to historical agents, assets and evidence outside this directory. Do not delete `ai agent work` until a separately approved dependency-closure and portable-path migration has been completed and revalidated.

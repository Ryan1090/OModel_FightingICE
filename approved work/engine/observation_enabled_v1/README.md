# Observation-enabled FightingICE engine v1

Approval date: 2026-10-23  
Runtime artifact: `FightingICE.observation-enabled.jar`  
SHA-256: `0b1defaff286e892481f27572b2d951c3da1ab60ce04928e4a6453510a8b5635`

## Purpose

This is the audited engine used by D5, E, 2A and 2B. Relative to the preceding B5 build, its only changed ZIP entry was `aiinterface/AIController.class`. The preserved `AIController.java` adds audit emission and dynamic mechanics extraction needed to expose observations; the existing name-masking decision was not introduced by this edit.

## Contents

- the executable JAR;
- the exact changed Java source;
- the D5 runtime manifest and freeze record;
- the implementation-fix note;
- the later engine-build audit and prospective equivalence result.

## Scientific boundary

Approval here means this observation-enabled build is the authoritative instrumented engine artifact. It does **not** claim universal gameplay equivalence with the older B or B5 engine builds. The preserved prospective comparison was inconclusive because the selected controls were nondeterministic; it established neither equivalence nor a semantic difference. Any designation as a universal standard build still requires a separately approved equivalence method.

See `SHA256SUMS.txt` for the authoritative byte inventory.

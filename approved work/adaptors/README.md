# Approved adapter methods

Approval date: 2026-10-23  
Status: approved, copied byte-for-byte and SHA-256 verified

The three subdirectories are the three dedicated adapter methods:

1. `legacy_java_reflection/` — reflection/structure translation for legacy Java controllers. It also serves Java-plus-Kotlin submissions; that route is not a distinct adapter implementation.
2. `historical_python_py4j/` — compatibility translation for historical Python controllers written against the Java/Py4J API.
3. `historical_python_pyftg/` — compatibility translation for historical Python controllers written against older pyftg APIs.

The files at this directory's root are shared orchestration rather than a fourth adapter method:

- `unified_harness.py` composes all validated route pairings;
- `external_pair_client.py` coordinates two external controller endpoints;
- `COMPATIBILITY_PROFILES.json` records validated runtime/dependency restoration profiles without changing agent policy;
- `IMPLEMENTATION_FIXES_CONSOLIDATED.md` and `FINAL_SUMMARY.json` preserve the final engineering verification record.

## Verification boundary

The final shared stack passed the 72/72 ordered route-pair gate and 36/36 full-horizon learner controls. The subsequent population gate supported 450/453 configurations. The remaining three ZoneAI learner configurations were deliberately left unresolved because fixing them would require changing preserved controller behaviour; they are not adapter implementation failures.

These are the exact verified bytes. `unified_harness.py` and `COMPATIBILITY_PROFILES.json` still contain historical absolute paths, so relocation is a future migration task requiring its own validation.

See `SHA256SUMS.txt` for the authoritative byte inventory.

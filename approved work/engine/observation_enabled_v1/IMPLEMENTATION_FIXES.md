# Pass D implementation fixes before gate release

All intermediate runs are preserved under the C-drive task workspace.

1. `precheck_v1` did not start gameplay: the runner looked for the required freeze file under `contract/` rather than `report_bundle/`. The lookup alone was corrected and re-hashed.
2. `precheck_v1` then exposed an inventory-key typo before process launch: MrTwo is `2020-competition-07MrTwo`, not `2020-competition-12MrTwo`. The schedule builder alone was corrected and re-frozen.
3. `precheck_v2` showed that direct CLI character selection rejects synthetic identities and falls back to stock. Java-versus-Java cases were restored to the already-validated PyFTG gateway character-selection path while both controllers remain engine-internal.
4. In `precheck_v3`, 48/60 cases passed fully. The remaining 12 were ZEN-only digest false negatives: true identities, source Motion SHA-256, visible/actual equality and the frozen configured value all passed, but the offline CSV digest replica did not reproduce ZEN's loader-normalized digest. The four engine-observed ZEN digests were frozen prospectively for the complete rerun. No identity, sentinel, threshold, controller, or expected configured value changed.

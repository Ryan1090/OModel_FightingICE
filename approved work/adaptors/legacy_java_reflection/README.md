# Legacy Java reflection adapter

Purpose: run legacy Java (including Java-plus-Kotlin packaged) controllers against the current engine without editing their policy source.

- `base_v3/` is the complete approved v3 base adapter JAR and source snapshot.
- `side_scoped_dual_v1/` is the final verified wrapper. It permits adapted controllers on either or both sides and preserves per-side legacy empty-frame and remaining-time semantics.
- The dual build is produced by copying the base v3 JAR and replacing the side-aware classes. Its build script accepts the engine and base-adapter paths as parameters; the embedded defaults are provenance paths from the verified run.

The Java and Java-plus-Kotlin route labels share this implementation and therefore are intentionally not duplicated into separate method folders.

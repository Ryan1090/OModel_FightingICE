# Current layout ? 1.2.1 shared approved engine

The user explicitly replaced the earlier whole-folder standalone requirement
with a shared-engine layout. The generator resolves the unchanged engine at
`../engine/observation_enabled_v1/FightingICE.observation-enabled.jar` and
verifies its approved SHA-256 before staging it. The duplicate generator JAR
has been removed. Move both sibling folders together; no drive letter is fixed.
All other libraries/models/runtime assets and folder-relative output handling
remain as before. Scientific rules and engine bytes are unchanged.

The preceding layout history below describes the superseded packaging.

# Standalone layout revision — 1.1.0

Distribution cleanup: the user subsequently specified that approved work should
contain rerun essentials only. The copied completed catalogue, sealed archive and
historical report copies described below were moved back to untracked research
storage. They are not part of the distributed generator; the standalone runtime,
relative future-output paths, dependencies and scientific rules are unchanged.

The user clarified that the whole `synthetic generator` folder must operate
independently when moved with the repository, leaving research scratch/history
on D:. This supersedes the earlier external SSD-output/junction layout.

Changes are packaging and path handling only:

- The entry point, configuration, sources, assets and verification are at this
  folder's root, without historical version-launcher chains.
- Third-party Python libraries and required transitive dependencies are bundled
  under `python_lib`, with metadata, licences, exact versions and file hashes.
  Python 3.12 x64 and Java/JDK remain installed system runtimes, found by normal
  executable discovery rather than hard-coded repository paths.
- Default output is `generated characters/catalogue_001`, resolved relative to
  the local configuration. Configuration/output are restricted to this folder.
- The external historical-path guard and external runtime-home defaults were
  replaced with local path handling. Existing nonempty-catalogue/write guards
  remain. Run indexes use relative paths.
- The existing final 350 A/B tables are copied into local pool/character folders
  with unchanged CSV bytes. The sealed C archive is copied as an opaque file and
  independently hashed against its existing completion marker. It is not decoded,
  compacted, rewritten or resealed. Original records remain untouched.
- Old absolute path strings inside historical evidence/provenance remain intact
  as historical identifiers. They are not runtime dependencies.

The preceding 1.0.0 approved package is preserved outside this folder in research
history. Construction, ranges, selection, observations, assessments, repair,
floors, quotas and the existing candidate catalogue's membership do not change.
No engine, candidate generation or production restart occurs during conversion.

Portability is verified using bare Python with `-I -S`, both from an unrelated
working directory and under a different standalone folder name. This ensures the
old `.venv`, user site packages and historical project modules cannot supply
missing runtime dependencies. The integrated software controls are repeated.

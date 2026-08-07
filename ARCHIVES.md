# Required archives (not tracked in git)

The upstream binary archives this project runs on are deliberately not committed. They total
roughly 1.9 GB, five of them exceed GitHub's 100 MB per-file limit, and redistribution rights
for the engine assets and for the third-party competition submissions are unresolved.

Exact bytes are pinned by SHA-256 below instead. Restore the archive folders at the repository
root and verify them before use.

## Expected layout

```
7.0 zips/       DareFightingICE-7.0.zip, FightingICE-7.0.zip, FightingICE-7.0.tar.gz, resources-6.3.zip
7.1 zips/       DareFightingICE-7.1.zip, FightingICE-7.1.zip, FightingICE-7.1.tar.gz, resource-7.1.zip
past agents/    twelve per-year competition archives
```

## Minimum set to run the platform

Only two archives are needed. Extract both into a single directory:

```
DareFightingICE-7.1.zip  ->  FightingICE7.1/
resource-7.1.zip         ->  FightingICE7.1/data/
```

The release archive ships no assets, and the engine loads them from the working directory
(`./data/...`) rather than from the jar — so the jar's embedded copy of `data/` is never read
and the resource pack is mandatory.

`resource-7.1.zip` matters twice over: it supplies those assets, and it is the source of the
`Motion.csv` files a Python agent must read locally, because pyftg does not deliver
`MotionData` over the protocol. Pin any action-property encoder to this archive's hash — if
the file the encoder reads drifts from the file the engine reads, the action properties
silently describe a different game.

`resources-6.3.zip` is the pre-rebalance resource pack, needed only for experiments that
restore the earlier energy economy.

## Verifying

```powershell
Get-ChildItem '7.0 zips','7.1 zips','past agents' -File |
  ForEach-Object { '{0}  {1}' -f (Get-FileHash $_.FullName -Algorithm SHA256).Hash, $_.Name }
```

## Engine archives

| Archive | Size | SHA-256 |
|---|---:|---|
| `DareFightingICE-7.0.zip` | 19.0 MB | `D14CE73530B190686ABE787416F178FE03400B8C48B328497A57A4978A8E2E9A` |
| `FightingICE-7.0.tar.gz` | 24.5 MB | `95FA6C049C93E1C7E223B1325466E42F56A0E6A4BC85B2B692D648FE703397A9` |
| `FightingICE-7.0.zip` | 24.6 MB | `B468D9AB72EF8492E39DAC9CEE4DD7AB5604F4276A2BE00E6BA738D599C37479` |
| `resources-6.3.zip` | 80.0 MB | `CC04F64518A8C7F7F09508DEF8A5673930B8D0EFFA877F643BCD583FD4E57F06` |
| `DareFightingICE-7.1.zip` | 118.4 MB | `510752A69A097B767677D3911B1407D6A08A721DAD4FAF2CB5B7A19B988F1C62` |
| `FightingICE-7.1.tar.gz` | 39.8 MB | `84DC053EF87822C7CA97D6E5EB4FCFBCD6C84F3037BC2D7FCD9DAC800C0C5524` |
| `FightingICE-7.1.zip` | 39.9 MB | `158C3480B469A79823573016E7975DD119BB22A34AAC047DCF95CFF0CA341932` |
| `resource-7.1.zip` | 89.8 MB | `386FD713F901DB00583054528CCFBCE315953C157DC16231C4367416D86DCE53` |

The `.tar.gz` files are byte-equivalent in content to their `.zip` counterparts — the same
source distribution in a different container.

No commit ID, git metadata, `Implementation-Version`, or build revision is embedded in any of
these packages. The citable identity is therefore **release package name plus the hash above**,
not a commit. Jar entries are timestamped 2026-04-18 and source entries 2026-04-16; those are
provenance evidence, not identifiers.

## Competition archives

| Archive | Size | SHA-256 |
|---|---:|---|
| `2014AIs.zip` | 1.8 MB | `D41627010AFC9EAD8D7C18B5A173BDB4017520F90A8CD9B6A68FB97D23D7788C` |
| `2015Competition.zip` | 29.1 MB | `5E81FC8553866787CB3E4843298AADCCD15D5EC3E8F89D603FA9C3B0E700CA13` |
| `2016Competition.zip` | 55.5 MB | `9EEC78B76F3FDF9CF564BDD5D79C75C0E49C774F25E13F2D17AA853CF8101886` |
| `2017Competition.zip` | 46.8 MB | `4B2ADDF45385FD37B3F9774993F427EF59B175907C41257EF0DCE62BAF1FD116` |
| `2018Competition.zip` | 48.3 MB | `EA57FAF449F68682C9D7C3C3C0E2ECF8C5D8FBCCA1F385846771680C7670BD54` |
| `2019Competition.zip` | 179.6 MB | `DADC9C1A83351479571790564233C8262DFBC7895089C0B17A26297A16743B1E` |
| `2020Competition.zip` | 268.3 MB | `BE3A5F3E45AA7CA756B92387578EDFE48DA31B0EEFFDCE0A641EB49E766836F8` |
| `updated_2021Competition.zip` | 249.0 MB | `18F161DFEE6C6B2DDE8EBEAD484198D4062295FAA6628BF3A0F09EED63E83A7A` |
| `2022AI.zip` | 5.4 MB | `DD15B4D8597DB72E1A240F199B1337FA8C3B18CD044D49D601FE88844A80688C` |
| `2023AI.zip` | 29.4 MB | `B8A90DEF60BFD72EC467EDA6BC89814637C76B1119F988F61AE28B78DF7EE38D` |
| `2024AI.zip` | 163.5 MB | `2A62B6C563EC881452D1EBF097C914BEAA5B8A16957C6E37888E72D8E24BD92C` |
| `2025AI.zip` | 9.3 MB | `EB9057806DD73854DA143769CF80EBF088F55743BA0F145D4D01B0BBF1F6B0D1` |

## Sources

Engine releases and resource packs come from the FightingICE release page:
<https://github.com/TeamFightingICE/FightingICE/releases>

One exact URL is recorded in the shipped 7.0 and 7.1 source READMEs, and the other release
assets follow the same pattern:

```
https://github.com/TeamFightingICE/FightingICE/releases/download/v6.3/resources-6.3.zip
```

Per-year competition-track documentation is under
<https://github.com/TeamFightingICE/FightingICE/tree/master/DareFightingICE>.

**TODO:** record the exact download URL for each of the twelve `past agents/` archives. They
came from the competition archives rather than the engine release page, and the specific URLs
were not captured. The hashes above pin the bytes, but a reader still needs a retrieval path.

param(
    [string]$EngineJar = 'D:\fightICE\ai agent work\tools\synthetic_functional_D5_2026_10_04\work\FightingICE.d5.audit.jar',
    [string]$LegacyAdapter = 'D:\fightICE\ai agent work\tools\adapter_io_audit_2026_09_25\adapters\legacy_java_v3\legacy-java-v3-adapter.jar'
)

$ErrorActionPreference = 'Stop'
$task = Split-Path -Parent $PSScriptRoot
$source = Join-Path $task 'harness\src'
$build = Join-Path $task 'harness\build'
$output = Join-Path $task 'harness\dual-legacy-java-v1-adapter.jar'

New-Item -ItemType Directory -Force -Path (Join-Path $build 'structs') | Out-Null
Get-ChildItem -LiteralPath $build -Recurse -File -Filter '*.class' -ErrorAction SilentlyContinue | Remove-Item -Force

$sources = @(
    (Join-Path $source 'SideReflectiveAdapter.java'),
    (Join-Path $source 'ReflectiveAdapterP1.java'),
    (Join-Path $source 'ReflectiveAdapterP2.java'),
    (Join-Path $source 'structs\FrameData.java')
)

& javac -encoding UTF-8 -cp "$EngineJar;$LegacyAdapter" -d $build @sources
if ($LASTEXITCODE -ne 0) { throw "javac failed with exit code $LASTEXITCODE" }

Copy-Item -LiteralPath $LegacyAdapter -Destination $output -Force
& jar uf $output -C $build 'SideReflectiveAdapter.class' -C $build 'ReflectiveAdapterP1.class' -C $build 'ReflectiveAdapterP2.class' -C $build 'structs\FrameData.class'
if ($LASTEXITCODE -ne 0) { throw "jar update failed with exit code $LASTEXITCODE" }

$hash = (Get-FileHash -LiteralPath $output -Algorithm SHA256).Hash.ToLowerInvariant()
[pscustomobject]@{
    output = $output
    sha256 = $hash
    bytes = (Get-Item -LiteralPath $output).Length
    engine_sha256 = (Get-FileHash -LiteralPath $EngineJar -Algorithm SHA256).Hash.ToLowerInvariant()
    base_adapter_sha256 = (Get-FileHash -LiteralPath $LegacyAdapter -Algorithm SHA256).Hash.ToLowerInvariant()
} | ConvertTo-Json

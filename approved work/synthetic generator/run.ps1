param(
    [ValidateSet('Run','Resume','Pause','Status','Check')]
    [string]$Action = 'Run',
    [string]$Config = 'config.json',
    [int]$Workers = 0,
    [switch]$Background
)
$ErrorActionPreference = 'Stop'
$scriptPath = Join-Path $PSScriptRoot 'generator.py'
$configPath = if ([System.IO.Path]::IsPathRooted($Config)) { $Config } else { Join-Path $PSScriptRoot $Config }
$arguments = @('-I', '-S', $scriptPath, '--action', $Action, '--config', $configPath)
if ($Workers -gt 0) { $arguments += @('--workers', [string]$Workers) }
if ($Background) { $arguments += '--background' }
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3.12 @arguments
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python @arguments
} else {
    throw 'Install Python 3.12 x64. All third-party Python libraries are already included in python_lib.'
}
exit $LASTEXITCODE

# Atajos de desarrollo de Senda (Windows PowerShell 5.1+ / PowerShell 7). Ver tools/README.md.
#   .\tools\dev.ps1 build | validate [-Json] | check | test | package | all
#   .\tools\dev.ps1 install-dev -Target "C:\...\_forever_\Interface\AddOns"
#   (install-dev copia los cuatro addons: Senda, Senda_Nav, Senda_Nav_EK y Senda_Nav_Kalimdor)
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('build', 'check', 'validate', 'test', 'package', 'all', 'install-dev', 'help')]
    [string]$Command = 'help',
    [string]$Target,
    [switch]$Json,
    [switch]$Strict,
    [switch]$AllowAnyDir
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Py = if ($env:PYTHON) { $env:PYTHON } elseif (Get-Command python -ErrorAction SilentlyContinue) { 'python' } else { 'py' }

function Invoke-Py([string[]]$PyArgs) {
    & $Py @PyArgs
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

switch ($Command) {
    'build'    { Invoke-Py @("$Root\tools\build.py") }
    'check'    { Invoke-Py @("$Root\tools\build.py", '--check') }
    'validate' {
        $a = @("$Root\tools\validate.py")
        if ($Json) { $a += '--json' }
        if ($Strict) { $a += '--strict' }
        Invoke-Py $a
    }
    'test'     { Invoke-Py @('-m', 'unittest', 'discover', '-s', "$Root\tests", '-p', 'test_*.py') }
    'package'  { Invoke-Py @("$Root\tools\package.py") }
    'all' {
        Invoke-Py @("$Root\tools\validate.py")
        Invoke-Py @("$Root\tools\build.py")
        Invoke-Py @("$Root\tools\package.py")
    }
    'install-dev' {
        # Sin ruta por defecto: -Target es obligatorio y package.py lo vuelve a comprobar. Copia Senda,
        # Senda_Nav, Senda_Nav_EK y Senda_Nav_Kalimdor (los de navegación los carga Senda bajo demanda).
        if (-not $Target) {
            [Console]::Error.WriteLine('install-dev: falta -Target <ruta a Interface\AddOns>. No hay ruta por defecto.')
            exit 2
        }
        $a = @("$Root\tools\package.py", '--install-dev', '--target', $Target)
        if ($AllowAnyDir) { $a += '--allow-any-dir' }
        Invoke-Py $a
    }
    default {
        Get-Content $PSCommandPath -TotalCount 4| ForEach-Object { $_ -replace '^# ?', '' }
    }
}

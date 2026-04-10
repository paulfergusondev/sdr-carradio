param(
    [switch]$BuildLocked
)

$ErrorActionPreference = 'Stop'

function Enter-BuildMutex {
    param(
        [string]$Name,
        [int]$TimeoutSeconds = 900
    )

    $mutex = New-Object System.Threading.Mutex($false, $Name)
    $acquired = $false
    try {
        try {
            $acquired = $mutex.WaitOne([TimeSpan]::FromSeconds($TimeoutSeconds))
        }
        catch [System.Threading.AbandonedMutexException] {
            $acquired = $true
        }

        if (-not $acquired) {
            throw "Timed out waiting for the PyRadio SDR build lock. Another build is probably still running."
        }

        return $mutex
    }
    catch {
        $mutex.Dispose()
        throw
    }
}

function Exit-BuildMutex {
    param($Mutex)

    if ($null -eq $Mutex) {
        return
    }

    try {
        $Mutex.ReleaseMutex()
    }
    catch {
    }
    finally {
        $Mutex.Dispose()
    }
}

$buildMutex = $null
if (-not $BuildLocked) {
    $buildMutex = Enter-BuildMutex -Name 'Global\PyRadioSDRBuild'
}

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$specFile = Join-Path $projectRoot 'pyradio_sdr.spec'
$legacyExe = Join-Path $projectRoot 'dist\PyRadioSDR.exe'

if (-not (Test-Path $python)) {
    throw "Virtual environment Python was not found at $python"
}

if (-not (Test-Path $specFile)) {
    throw "PyInstaller spec was not found at $specFile"
}

Push-Location $projectRoot
try {
    if (Test-Path $legacyExe) {
        Remove-Item -Path $legacyExe -Force
    }
    & $python -m pip install -r requirements-build.txt
    & $python -m PyInstaller --noconfirm --clean $specFile
    Write-Host "Portable build created at dist\PyRadioSDR\PyRadioSDR.exe"
}
finally {
    Pop-Location
    Exit-BuildMutex $buildMutex
}
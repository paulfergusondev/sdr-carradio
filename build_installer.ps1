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
$portableBuildScript = Join-Path $projectRoot 'build_portable.ps1'
$installerScript = Join-Path $projectRoot 'installer\PyRadioSDR.iss'
$iexpressInstallScript = Join-Path $projectRoot 'installer\install_pyradio_sdr.ps1'

if (-not (Test-Path $portableBuildScript)) {
    throw "Portable build script was not found at $portableBuildScript"
}

if (-not (Test-Path $installerScript)) {
    throw "Installer script was not found at $installerScript"
}

if (-not (Test-Path $iexpressInstallScript)) {
    throw "IExpress install script was not found at $iexpressInstallScript"
}

& $portableBuildScript -BuildLocked

$compilerCandidates = @()
$pathCompiler = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if ($pathCompiler) {
    $compilerCandidates += $pathCompiler.Source
}
$compilerCandidates += @(
    "$env:ProgramFiles(x86)\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
)

$compiler = $compilerCandidates |
    Where-Object { $_ -and (Test-Path $_) } |
    Select-Object -First 1

if (-not $compiler) {
    $iexpress = Get-Command iexpress.exe -ErrorAction SilentlyContinue
    if (-not $iexpress) {
        throw "Neither Inno Setup nor IExpress was found. Install Inno Setup or enable IExpress and rerun build_installer.ps1."
    }

    $distDir = Join-Path $projectRoot 'dist'
    $distAppDir = Join-Path $distDir 'PyRadioSDR'
    $installerOutputDir = Join-Path $distDir 'installer'
    $stagingDir = Join-Path $installerOutputDir 'staging'
    $sedPath = Join-Path $installerOutputDir 'PyRadioSDR_IExpress.sed'
    $targetExe = Join-Path $installerOutputDir 'PyRadioSDRSetup.exe'
    $portableArchive = Join-Path $stagingDir 'PyRadioSDR-portable.zip'

    if (-not (Test-Path (Join-Path $distAppDir 'PyRadioSDR.exe'))) {
        throw "Portable app directory was not found at $distAppDir"
    }

    New-Item -ItemType Directory -Force -Path $installerOutputDir | Out-Null
    New-Item -ItemType Directory -Force -Path $stagingDir | Out-Null
    Remove-Item -Path (Join-Path $stagingDir '*') -Recurse -Force -ErrorAction SilentlyContinue

    Compress-Archive -Path (Join-Path $distAppDir '*') -DestinationPath $portableArchive -Force
    Copy-Item $iexpressInstallScript (Join-Path $stagingDir 'install_pyradio_sdr.ps1') -Force

    $sedContent = @"
[Version]
Class=IEXPRESS
SEDVersion=3

[Options]
PackagePurpose=InstallApp
ShowInstallProgramWindow=1
HideExtractAnimation=1
UseLongFileName=1
InsideCompressed=1
CAB_FixedSize=0
CompressionType=MSZIP
RebootMode=N
InstallPrompt=
DisplayLicense=
FinishMessage=PyRadio SDR installation is complete.
TargetName=$targetExe
FriendlyName=PyRadio SDR Setup
AppLaunched=powershell.exe -NoProfile -ExecutionPolicy Bypass -File install_pyradio_sdr.ps1
PostInstallCmd=<None>
AdminQuietInstCmd=powershell.exe -NoProfile -ExecutionPolicy Bypass -File install_pyradio_sdr.ps1
UserQuietInstCmd=powershell.exe -NoProfile -ExecutionPolicy Bypass -File install_pyradio_sdr.ps1
SourceFiles=SourceFiles

[Strings]
FILE0="PyRadioSDR-portable.zip"
FILE1="install_pyradio_sdr.ps1"

[SourceFiles]
SourceFiles0=$stagingDir

[SourceFiles0]
%FILE0%=
%FILE1%=
"@

    Set-Content -Path $sedPath -Value $sedContent -Encoding ASCII
    & $iexpress.Source /N /Q $sedPath
    Write-Host "Installer build created at $targetExe"
    exit 0
}

Push-Location $projectRoot
try {
    & $compiler $installerScript
    Write-Host "Installer build created under dist\installer"
}
finally {
    Pop-Location
    Exit-BuildMutex $buildMutex
}
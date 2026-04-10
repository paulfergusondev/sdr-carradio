$ErrorActionPreference = 'Stop'

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-IsAdministrator)) {
    $arguments = @(
        '-NoProfile'
        '-ExecutionPolicy'
        'Bypass'
        '-File'
        ('"{0}"' -f $PSCommandPath)
    ) -join ' '
    Start-Process -FilePath 'powershell.exe' -ArgumentList $arguments -Verb RunAs -Wait
    exit $LASTEXITCODE
}

$appName = 'PyRadio SDR'
$exeName = 'PyRadioSDR.exe'
$sourceExe = Join-Path $PSScriptRoot $exeName
$sourceDir = Join-Path $PSScriptRoot 'PyRadioSDR'
$sourceArchive = Join-Path $PSScriptRoot 'PyRadioSDR-portable.zip'
$installDir = Join-Path ${env:ProgramFiles} $appName
$installedExe = Join-Path $installDir $exeName
$programsDir = [Environment]::GetFolderPath('Programs')
$desktopDir = [Environment]::GetFolderPath('DesktopDirectory')
$startMenuDir = Join-Path $programsDir $appName
$desktopShortcut = Join-Path $desktopDir "$appName.lnk"
$startMenuShortcut = Join-Path $startMenuDir "$appName.lnk"

if (-not (Test-Path $sourceExe) -and -not (Test-Path $sourceDir) -and -not (Test-Path $sourceArchive)) {
    throw "Packaged application was not found at $PSScriptRoot"
}

New-Item -ItemType Directory -Force -Path $installDir | Out-Null
New-Item -ItemType Directory -Force -Path $startMenuDir | Out-Null

Get-ChildItem -Path $installDir -Force -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

if (Test-Path $sourceArchive) {
    Expand-Archive -Path $sourceArchive -DestinationPath $installDir -Force
}
elseif (Test-Path $sourceDir) {
    Copy-Item -Path (Join-Path $sourceDir '*') -Destination $installDir -Recurse -Force
}
else {
    Copy-Item -Path $sourceExe -Destination $installedExe -Force
}

if (-not (Test-Path $installedExe)) {
    throw "Installed application executable was not created at $installedExe"
}

$shell = New-Object -ComObject WScript.Shell
foreach ($shortcutPath in @($desktopShortcut, $startMenuShortcut)) {
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $installedExe
    $shortcut.WorkingDirectory = $installDir
    $shortcut.IconLocation = "$installedExe,0"
    $shortcut.Save()
}

Write-Host "Installed $appName to $installDir"
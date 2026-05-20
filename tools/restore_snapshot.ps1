param(
    [string]$SnapshotId = ""
)

$ErrorActionPreference = "Stop"

function Test-RobocopyResult {
    param([int]$Code)
    if ($Code -ge 8) {
        throw "Robocopy failed with exit code $Code"
    }
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$backupRoot = Join-Path $projectRoot "backups\snapshots"
if (-not (Test-Path -LiteralPath $backupRoot)) {
    throw "Backup directory not found: $backupRoot"
}

if ([string]::IsNullOrWhiteSpace($SnapshotId)) {
    $latestFile = Join-Path $projectRoot "backups\LATEST_SNAPSHOT.txt"
    if (Test-Path -LiteralPath $latestFile) {
        $SnapshotId = (Get-Content -LiteralPath $latestFile -Raw).Trim()
    }
}

if ([string]::IsNullOrWhiteSpace($SnapshotId)) {
    $last = Get-ChildItem -LiteralPath $backupRoot -Directory |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($null -eq $last) {
        throw "No snapshot found under $backupRoot"
    }
    $SnapshotId = $last.Name
}

$snapshotPath = Join-Path $backupRoot $SnapshotId
if (-not (Test-Path -LiteralPath $snapshotPath)) {
    throw "Snapshot not found: $snapshotPath"
}

# Safety backup of core files before restore.
$safetyRoot = Join-Path $projectRoot "backups\pre_restore"
if (-not (Test-Path -LiteralPath $safetyRoot)) {
    New-Item -ItemType Directory -Path $safetyRoot | Out-Null
}
$safetyId = "pre_restore_{0}" -f (Get-Date -Format "yyyyMMdd_HHmmss")
$safetyPath = Join-Path $safetyRoot $safetyId
New-Item -ItemType Directory -Path $safetyPath | Out-Null

$coreFiles = @("app.py", "otc_gui.db")
foreach ($name in $coreFiles) {
    $src = Join-Path $projectRoot $name
    if (Test-Path -LiteralPath $src) {
        Copy-Item -LiteralPath $src -Destination (Join-Path $safetyPath $name) -Force
    }
}

$robocopyArgs = @(
    $snapshotPath,
    $projectRoot,
    "/E", "/R:1", "/W:1",
    "/NFL", "/NDL", "/NJH", "/NJS", "/NP",
    "/XD",
    (Join-Path $projectRoot "backups")
)

& robocopy @robocopyArgs | Out-Null
Test-RobocopyResult -Code $LASTEXITCODE

Write-Output ("Restored snapshot: {0}" -f $SnapshotId)
Write-Output ("Snapshot path: {0}" -f $snapshotPath)
Write-Output ("Safety backup: {0}" -f $safetyPath)

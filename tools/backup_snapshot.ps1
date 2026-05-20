param(
    [string]$Tag = "manual",
    [switch]$IncludeTransient
)

$ErrorActionPreference = "Stop"

function Test-RobocopyResult {
    param([int]$Code)
    # Robocopy exit code:
    # 0-7 success (including "extra files", "copied", etc.)
    # >=8 failure
    if ($Code -ge 8) {
        throw "Robocopy failed with exit code $Code"
    }
}

function Get-SafeHash {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        return ""
    }
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$backupRoot = Join-Path $projectRoot "backups\snapshots"
if (-not (Test-Path -LiteralPath $backupRoot)) {
    New-Item -ItemType Directory -Path $backupRoot | Out-Null
}

$safeTag = [Regex]::Replace(([string]$Tag).Trim(), "[^a-zA-Z0-9._-]", "_")
if ([string]::IsNullOrWhiteSpace($safeTag)) {
    $safeTag = "manual"
}

$snapshotId = "{0}_{1}" -f (Get-Date -Format "yyyyMMdd_HHmmss"), $safeTag
$snapshotPath = Join-Path $backupRoot $snapshotId
New-Item -ItemType Directory -Path $snapshotPath | Out-Null

$excludeDirs = @(
    (Join-Path $projectRoot "backups"),
    (Join-Path $projectRoot ".git"),
    (Join-Path $projectRoot "__pycache__")
)
if (-not $IncludeTransient) {
    $excludeDirs += (Join-Path $projectRoot "_report_images_tmp")
    $excludeDirs += (Join-Path $projectRoot "tools\__pycache__")
}

$robocopyArgs = @(
    $projectRoot,
    $snapshotPath,
    "/E", "/R:1", "/W:1",
    "/NFL", "/NDL", "/NJH", "/NJS", "/NP",
    "/XD"
) + $excludeDirs + @(
    "/XF", "*.pyc"
)

& robocopy @robocopyArgs | Out-Null
Test-RobocopyResult -Code $LASTEXITCODE

$manifest = [ordered]@{
    snapshot_id = $snapshotId
    created_at = (Get-Date).ToString("s")
    source_root = $projectRoot
    snapshot_path = $snapshotPath
    include_transient = [bool]$IncludeTransient
    entry_files = [ordered]@{
        app_py = [ordered]@{
            exists = (Test-Path -LiteralPath (Join-Path $snapshotPath "app.py"))
            sha256 = Get-SafeHash -Path (Join-Path $snapshotPath "app.py")
        }
        db = [ordered]@{
            exists = (Test-Path -LiteralPath (Join-Path $snapshotPath "otc_gui.db"))
            sha256 = Get-SafeHash -Path (Join-Path $snapshotPath "otc_gui.db")
        }
    }
}

$manifestPath = Join-Path $snapshotPath "manifest.json"
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

$latestFile = Join-Path $projectRoot "backups\LATEST_SNAPSHOT.txt"
Set-Content -LiteralPath $latestFile -Value $snapshotId -Encoding ASCII

Write-Output ("Snapshot created: {0}" -f $snapshotId)
Write-Output ("Path: {0}" -f $snapshotPath)
Write-Output ("Manifest: {0}" -f $manifestPath)

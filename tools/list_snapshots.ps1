$projectRoot = Split-Path -Parent $PSScriptRoot
$backupRoot = Join-Path $projectRoot "backups\snapshots"

if (-not (Test-Path -LiteralPath $backupRoot)) {
    Write-Output "No snapshots directory found: $backupRoot"
    exit 0
}

$rows = Get-ChildItem -LiteralPath $backupRoot -Directory |
    Sort-Object LastWriteTime -Descending |
    Select-Object Name, LastWriteTime

if ($null -eq $rows -or $rows.Count -eq 0) {
    Write-Output "No snapshots found."
    exit 0
}

$rows | Format-Table -AutoSize

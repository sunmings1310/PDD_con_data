param(
  [string]$TargetRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
)
$ErrorActionPreference = 'Stop'
foreach ($name in @('backlog.md','roadmap.md','milestone.md')) {
  Copy-Item -LiteralPath (Join-Path $PSScriptRoot ("ORIGINAL_" + $name)) -Destination (Join-Path $TargetRoot ("docs\" + $name)) -Force
}
Write-Output 'ROLLBACK_RESULT=restored docs/backlog.md, docs/roadmap.md, docs/milestone.md'

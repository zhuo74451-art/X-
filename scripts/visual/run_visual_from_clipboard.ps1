param()

$root = Resolve-Path (Join-Path $PSScriptRoot "..\\..")
Set-Location $root

$text = Get-Clipboard -Raw
if (-not $text) {
  Write-Host "clipboard is empty"
  exit 2
}

$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$inboxDir = "data/visual_inbox"
if (-not (Test-Path $inboxDir)) {
  New-Item -ItemType Directory -Path $inboxDir | Out-Null
}

$path = Join-Path $inboxDir ($ts + "_clipboard_input.txt")
Set-Content -Path $path -Value $text -Encoding UTF8

python scripts/visual/visual_prompt_pipeline.py --input-file $path --input-type auto
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$latestPath = "out/visual_pipeline/latest_run.json"
if (-not (Test-Path $latestPath)) {
  Write-Host "missing latest_run.json"
  exit 2
}

$latest = Get-Content $latestPath -Raw | ConvertFrom-Json
$runDir = $latest.run_dir
if (-not $runDir) {
  Write-Host "latest_run.json missing run_dir"
  exit 2
}

python scripts/visual/check_visual_pipeline_outputs.py --run-dir $runDir
if ($LASTEXITCODE -ne 0) {
  $latest.check_status = "FAIL"
  ($latest | ConvertTo-Json -Depth 10) | Set-Content $latestPath -Encoding UTF8
  exit $LASTEXITCODE
}

$latest.check_status = "PASS"
($latest | ConvertTo-Json -Depth 10) | Set-Content $latestPath -Encoding UTF8

Write-Host "VISUAL_PIPELINE_CLIPBOARD_PASS"
Write-Host ("run_dir: " + $latest.run_dir)
Write-Host ("selected_route: " + $latest.selected_route)
Write-Host ("ready_prompt: " + $latest.ready_to_generate_prompt)
Write-Host ("audit_report: " + $latest.audit_report)
Write-Host ("operator_review: " + $latest.operator_review)

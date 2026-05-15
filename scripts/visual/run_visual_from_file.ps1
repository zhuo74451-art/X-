param(
  [Parameter(Mandatory = $true)]
  [string]$inputFile,
  [Parameter(Mandatory = $false)]
  [string]$routeOrAuto,
  [Parameter(Mandatory = $false)]
  [string]$overrideFile
)

$root = Resolve-Path (Join-Path $PSScriptRoot "..\\..")
Set-Location $root

$argsList = @("--input-file", $inputFile, "--input-type", "auto")
if ($routeOrAuto -and $routeOrAuto -ne "auto") {
  $argsList += @("--route", $routeOrAuto)
}
if ($overrideFile) {
  $argsList += @("--override-file", $overrideFile)
}

python scripts/visual/visual_prompt_pipeline.py @argsList
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

Write-Host "VISUAL_PIPELINE_FILE_PASS"
Write-Host ("run_dir: " + $latest.run_dir)
Write-Host ("selected_route: " + $latest.selected_route)
Write-Host ("ready_prompt: " + $latest.ready_to_generate_prompt)
Write-Host ("audit_report: " + $latest.audit_report)
Write-Host ("operator_review: " + $latest.operator_review)

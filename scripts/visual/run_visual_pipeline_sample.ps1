param(
  [Parameter(Mandatory = $true)]
  [ValidateSet("musk","whale")]
  [string]$sample
)

$root = Resolve-Path (Join-Path $PSScriptRoot "..\\..")
Set-Location $root

if ($sample -eq "musk") {
  $inputFile = "data/samples/visual_input_musk_openai_beijing_post.txt"
} else {
  $inputFile = "data/samples/visual_input_daily_whale_digest_post.txt"
}

python scripts/visual/visual_prompt_pipeline.py --input-file $inputFile --input-type post
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

Write-Host "VISUAL_PIPELINE_SAMPLE_PASS"
Write-Host ($sample + " PASS")
Write-Host ("run_dir: " + $latest.run_dir)
Write-Host ("selected_route: " + $latest.selected_route)
Write-Host ("ready_prompt: " + $latest.ready_to_generate_prompt)
Write-Host ("audit_report: " + $latest.audit_report)
Write-Host ("operator_review: " + $latest.operator_review)

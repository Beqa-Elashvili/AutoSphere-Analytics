# Wrapper that Windows Task Scheduler runs (docs/automated-reporting.md).
# Runs the scheduled job from the repository root with the project's virtual environment,
# appends all output to logs\scheduled_YYYY-MM-DD.log and passes the exit code back to
# Task Scheduler ("Last Run Result": 0 = success, 1 = pipeline failed, 2 = report failed, 3 = already running).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"
$log = Join-Path $root ("logs\scheduled_{0:yyyy-MM-dd}.log" -f (Get-Date))
New-Item -ItemType Directory -Force (Split-Path $log) | Out-Null

"=== $(Get-Date -Format s) scheduled run started ===" | Out-File -Append -Encoding utf8 $log
& $python scripts\scheduled_run.py *>> $log
$code = $LASTEXITCODE
"=== $(Get-Date -Format s) finished with exit code $code ===" | Out-File -Append -Encoding utf8 $log
exit $code

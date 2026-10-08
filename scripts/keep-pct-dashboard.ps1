$ErrorActionPreference = "Stop"
$pctRoot = Split-Path -Parent $PSScriptRoot
$pctPython = Join-Path $pctRoot ".venv\Scripts\python.exe"
$pctLogs = Join-Path $pctRoot "logs"
New-Item -ItemType Directory -Force -Path $pctLogs | Out-Null

while ($true) {
    $listener = Get-NetTCPConnection -State Listen -LocalPort 8010 -ErrorAction SilentlyContinue
    if ($listener) {
        Start-Sleep -Seconds 10
        continue
    }
    $pctProcess = Start-Process -FilePath $pctPython -ArgumentList @("main.py", "dashboard") -WorkingDirectory $pctRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $pctLogs "pct-dashboard-out.log") -RedirectStandardError (Join-Path $pctLogs "pct-dashboard-error.log") -PassThru
    $pctProcess.WaitForExit()
    Add-Content -LiteralPath (Join-Path $pctLogs "pct-dashboard-keeper.log") -Value "$(Get-Date -Format o) dashboard exited with code $($pctProcess.ExitCode); retrying in 10 seconds"
    Start-Sleep -Seconds 10
}

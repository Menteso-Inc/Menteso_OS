param(
    [Parameter(Mandatory = $true)][string]$OllamaExecutable,
    [Parameter(Mandatory = $true)][string]$ModelsPath,
    [string]$LogsPath = (Join-Path $env:ProgramData 'Menteso\ollama'),
    [switch]$ValidateOnly
)
$ErrorActionPreference = 'Stop'
$pctOllamaExe = (Resolve-Path -LiteralPath $OllamaExecutable).ProviderPath
$pctOllamaModels = (Resolve-Path -LiteralPath $ModelsPath).ProviderPath
if (-not (Test-Path -LiteralPath $pctOllamaExe -PathType Leaf) -or
    -not (Test-Path -LiteralPath $pctOllamaModels -PathType Container)) {
    throw 'Ollama executable or local model directory is unavailable.'
}
# Run independently of an interactive desktop login. No public listener/cloud use.
$env:OLLAMA_HOST = '127.0.0.1:11434'
$env:OLLAMA_MODELS = $pctOllamaModels
$env:OLLAMA_NO_CLOUD = '1'
$env:OLLAMA_NUM_PARALLEL = '1'
$env:OLLAMA_MAX_LOADED_MODELS = '1'
$env:OLLAMA_MAX_QUEUE = '8'
if ($ValidateOnly) {
    [pscustomobject]@{ ExecutableExists = $true; ModelsExist = $true; Bind = $env:OLLAMA_HOST } | ConvertTo-Json
    exit 0
}
New-Item -ItemType Directory -Path $LogsPath -Force | Out-Null
while ($true) {
    $pctOllamaListener = Get-NetTCPConnection -State Listen -LocalPort 11434 -ErrorAction SilentlyContinue
    if ($pctOllamaListener) {
        # An existing user-owned Ollama may already be serving. Never kill it.
        Start-Sleep -Seconds 10
        continue
    }
    $pctOllamaStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $pctOllamaProcess = Start-Process -FilePath $pctOllamaExe -ArgumentList @('serve') -WindowStyle Hidden -PassThru `
        -WorkingDirectory (Split-Path -Parent $pctOllamaExe) `
        -RedirectStandardOutput (Join-Path $LogsPath "$pctOllamaStamp-out.log") `
        -RedirectStandardError (Join-Path $LogsPath "$pctOllamaStamp-error.log")
    $pctOllamaProcess.WaitForExit()
    Add-Content -LiteralPath (Join-Path $LogsPath 'keeper.log') -Value "$(Get-Date -Format o) Ollama exited; retrying in 10 seconds"
    Start-Sleep -Seconds 10
}

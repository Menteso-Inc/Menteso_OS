param(
    [switch]$SkipPull,
    [switch]$ForceReset
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$SeoAgentDir = Join-Path $ProjectRoot "agents\patentzoom_seo_agent"
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$DeployLogDir = Join-Path $ProjectRoot "logs"
$DeployLogFile = Join-Path $DeployLogDir "deployments.jsonl"

function Write-DeployEvent {
    param(
        [string]$Status,
        [string]$Step,
        [string]$Message = ""
    )

    if (-not (Test-Path -LiteralPath $DeployLogDir)) {
        New-Item -ItemType Directory -Path $DeployLogDir | Out-Null
    }

    $commit = ""
    try {
        $commit = (git rev-parse --short HEAD 2>$null).Trim()
    } catch {
        $commit = ""
    }

    $event = [ordered]@{
        timestamp = (Get-Date).ToUniversalTime().ToString("o")
        status = $Status
        step = $Step
        message = $Message
        commit = $commit
    }
    Add-Content -LiteralPath $DeployLogFile -Value ($event | ConvertTo-Json -Compress)
}

function Test-Pm2App {
    param([string]$Name)
    try {
        $output = (cmd /c pm2 describe $Name 2>&1) -join "`n"
        return ($LASTEXITCODE -eq 0 -and $output -match [regex]::Escape($Name) -and $output -notmatch "doesn't exist")
    } catch {
        return $false
    }
}

Set-Location $ProjectRoot
Write-DeployEvent -Status "running" -Step "start" -Message "Deployment started"

try {
    if (-not (Test-Path -LiteralPath ".env")) {
        throw ".env is missing. Create it on the server before deploying."
    }

    if (-not (Test-Path -LiteralPath $PythonExe)) {
        throw "Python virtualenv is missing at $PythonExe"
    }

    if (-not $SkipPull) {
        Write-DeployEvent -Status "running" -Step "git" -Message "Updating main from origin"
        git fetch origin main
        if ($ForceReset) {
            git reset --hard origin/main
        } else {
            git checkout main
            git pull --ff-only origin main
        }
    }

    Write-DeployEvent -Status "running" -Step "python" -Message "Installing and compiling Python dependencies"
    & $PythonExe -m pip install -r requirements.txt
    & $PythonExe -m compileall main.py server.py shared agents\pct_agent agents\patentzoom_seo_agent\agent.py agents\patentzoom_seo_agent\tests.py

    Write-DeployEvent -Status "running" -Step "seo-agent" -Message "Installing, building, and testing SEO agent"
    Set-Location $SeoAgentDir
    npm ci
    npm run build
    npm test

    Write-DeployEvent -Status "running" -Step "pm2" -Message "Reloading dashboard and preserving tunnel process"
    Set-Location $ProjectRoot
    if (Test-Pm2App -Name "menteso-os") {
        pm2 restart menteso-os --update-env
    } else {
        pm2 start ecosystem.config.js --only menteso-os --update-env
    }
    if (-not (Test-Pm2App -Name "menteso-os-public-quick")) {
        pm2 start ecosystem.config.js --only menteso-os-public-quick --update-env
    }
    pm2 save

    Write-DeployEvent -Status "running" -Step "health-check" -Message "Checking dashboard API"
    $port = if ($env:DASHBOARD_PORT) { $env:DASHBOARD_PORT } else { "3002" }
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:$port/api/agents" -UseBasicParsing -TimeoutSec 20
    if ($response.StatusCode -ne 200) {
        throw "Dashboard health check returned HTTP $($response.StatusCode)"
    }
    Write-DeployEvent -Status "success" -Step "complete" -Message "Deployment complete"
} catch {
    Set-Location $ProjectRoot
    Write-DeployEvent -Status "failure" -Step "failed" -Message $_.Exception.Message
    try {
        pm2 logs menteso-os --lines 80 --nostream
    } catch {
        # Keep the original deployment failure as the thrown error.
    }
    throw
}

Write-Output "Deployment complete."

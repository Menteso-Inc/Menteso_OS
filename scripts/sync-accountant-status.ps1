$ErrorActionPreference = "Stop"
$targetDirectory = "C:\sites\Menteso_OS\data\accountant_agent"
$targetFile = Join-Path $targetDirectory "status.json"
$temporaryFile = Join-Path $targetDirectory "status.json.tmp"

New-Item -ItemType Directory -Path $targetDirectory -Force | Out-Null
ssh menteso-os-aws "sudo cat /home/menteso_os/data/accountant_agent/status.json" |
    Set-Content -LiteralPath $temporaryFile -Encoding utf8
if ($LASTEXITCODE -ne 0) {
    Remove-Item -LiteralPath $temporaryFile -Force -ErrorAction SilentlyContinue
    exit $LASTEXITCODE
}
Move-Item -LiteralPath $temporaryFile -Destination $targetFile -Force

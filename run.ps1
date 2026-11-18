# Atalho para Windows: roda o mirror com push.
# Uso: .\run.ps1            (commita e faz push)
#      .\run.ps1 -DryRun    (só simula)
param([switch]$DryRun)

Set-Location -Path $PSScriptRoot
$python = if (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }

if ($DryRun) { & $python mirror.py --dry-run }
else         { & $python mirror.py --push }
exit $LASTEXITCODE

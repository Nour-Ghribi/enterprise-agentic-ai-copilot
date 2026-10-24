param([switch]$PullModel, [string]$Model='qwen3:1.7b')
$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
$ollamaCommand=Get-Command ollama -ErrorAction SilentlyContinue
$ollamaPath=if ($ollamaCommand) {$ollamaCommand.Source} else {Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'}
if (-not (Test-Path -LiteralPath $ollamaPath)) {
    throw 'Ollama is not installed. Install from https://ollama.com/download/windows then run this script again. No success has been simulated.'
}
$env:OLLAMA_HOST='127.0.0.1:11434'
$env:OLLAMA_NO_CLOUD='1'
$env:OLLAMA_MODELS=Join-Path $projectRoot 'data\ollama-models'
New-Item -ItemType Directory -Path $env:OLLAMA_MODELS -Force | Out-Null
try {Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 2 | Out-Null}
catch {
    Start-Process -FilePath $ollamaPath -ArgumentList 'serve' -WindowStyle Hidden -WorkingDirectory $projectRoot | Out-Null
    $ready=$false
    for ($attempt=0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Milliseconds 300
        try {Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 1 | Out-Null; $ready=$true; break} catch {}
    }
    if (-not $ready) {throw 'Ollama server did not start. No model inference was executed.'}
}
if ($PullModel) {
    if ($Model -match 'cloud|https?://') {throw 'Only a local model tag is permitted.'}
    & $ollamaPath pull $Model
    if ($LASTEXITCODE -ne 0) {throw 'Model download failed; local validation remains pending.'}
}
Write-Output 'Local server reached. Run python -m copilot.local_check to verify actual inference and tool calling.'

param(
    [switch]$Cloud
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$VenvPath = Join-Path $ProjectRoot ".venv"
$PythonPath = $null

if (Get-Command py -ErrorAction SilentlyContinue) {
    $PythonPath = "py"
    $PythonArgs = @("-3.11")
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $PythonPath = "python"
    $PythonArgs = @()
} else {
    throw "Python 3.11 or newer is required. Install it from https://www.python.org/downloads/windows/"
}

if (-not (Test-Path -LiteralPath (Join-Path $VenvPath "Scripts\python.exe"))) {
    & $PythonPath @PythonArgs -m venv $VenvPath
    if ($LASTEXITCODE -ne 0) { throw "Could not create the Python virtual environment." }
}

$VenvPython = Join-Path $VenvPath "Scripts\python.exe"
& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Could not upgrade pip." }

$Extras = if ($Cloud) { ".[local,azure,gemini]" } else { ".[local]" }
& $VenvPython -m pip install -e $Extras
if ($LASTEXITCODE -ne 0) { throw "Application dependency installation failed." }

$Frontend = Join-Path $ProjectRoot "web\dist\index.html"
if (-not (Test-Path -LiteralPath $Frontend)) {
    throw "The prebuilt web interface is missing. Use the Windows release ZIP or run 'pnpm build' in web/."
}

Write-Host ""
Write-Host "Arabic Schoolbook OCR installed successfully." -ForegroundColor Green
Write-Host "Run start_windows.bat to open the local application."
Write-Host "Local mode requires no API key and sends no document data to the cloud."

param(
    [string]$Version = "0.1.0-alpha"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$DistRoot = Join-Path $ProjectRoot "dist"
$ReleaseName = "ArabicSchoolbookOCR-v$Version-windows"
$Stage = Join-Path $DistRoot $ReleaseName
$ZipPath = Join-Path $DistRoot "$ReleaseName.zip"

New-Item -ItemType Directory -Path $DistRoot -Force | Out-Null
$ResolvedDist = (Resolve-Path -LiteralPath $DistRoot).Path
$StageFull = [System.IO.Path]::GetFullPath($Stage)
if (-not $StageFull.StartsWith($ResolvedDist + [System.IO.Path]::DirectorySeparatorChar)) {
    throw "Refusing to prepare a release outside the repository dist directory."
}
if (Test-Path -LiteralPath $StageFull) {
    Remove-Item -LiteralPath $StageFull -Recurse -Force
}
if (Test-Path -LiteralPath $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}
New-Item -ItemType Directory -Path $StageFull -Force | Out-Null

$RootFiles = @(
    ".env.example", "ACCURACY_REPORT.json", "ACCURACY_REPORT.md",
    "AI_SMOKE_TEST_STATUS.md", "CHANGELOG.md", "DATA_LICENSES.md",
    "FORMATTING_AUDIT_SUMMARY.md", "INSTALL_WINDOWS.md",
    "KNOWN_LIMITATIONS.md", "LICENSE", "MODEL_SUPPORT.md", "PRIVACY.md", "README.md",
    "SECURITY.md", "THIRD_PARTY_NOTICES.md", "install_windows.ps1", "start_windows.bat",
    "pyproject.toml", "UNRESOLVED_BLOCK_ANALYSIS.md"
)
foreach ($File in $RootFiles) {
    Copy-Item -LiteralPath (Join-Path $ProjectRoot $File) -Destination $StageFull
}

foreach ($Directory in @("docs", "src", "scripts", "examples\demo", "web\dist")) {
    $Source = Join-Path $ProjectRoot $Directory
    if (-not (Test-Path -LiteralPath $Source)) { throw "Required release directory missing: $Directory" }
    $Destination = Join-Path $StageFull $Directory
    New-Item -ItemType Directory -Path (Split-Path -Parent $Destination) -Force | Out-Null
    Copy-Item -LiteralPath $Source -Destination $Destination -Recurse
}

$Forbidden = Get-ChildItem -LiteralPath $StageFull -Recurse -Force | Where-Object {
    $_.FullName -match "(?:\\|/)(?:jobs|private_data|ground_truth|\.env|\.git)(?:\\|/|$)"
}
if ($Forbidden) {
    throw "Private or secret path entered the release staging directory."
}

Compress-Archive -LiteralPath $StageFull -DestinationPath $ZipPath -CompressionLevel Optimal
$Hash = (Get-FileHash -LiteralPath $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
"$Hash  $ReleaseName.zip" | Set-Content -LiteralPath (Join-Path $DistRoot "SHA256SUMS.txt") -Encoding ascii
Write-Output $ZipPath

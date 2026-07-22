param(
    [Parameter(Mandatory = $true)]
    [string[]] $InputPath,

    [Parameter(Mandatory = $true)]
    [string] $OutputPath,

    [string] $LanguageTag = "ar-SA"
)

$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Storage.FileAccessMode, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics.Imaging, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrResult, Windows.Foundation, ContentType = WindowsRuntime]

function Wait-WinRtResult {
    param(
        [Parameter(Mandatory = $true)] $Operation,
        [Parameter(Mandatory = $true)] [Type] $ResultType
    )

    $asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() |
        Where-Object {
            $_.Name -eq "AsTask" -and
            $_.IsGenericMethod -and
            $_.GetParameters().Count -eq 1
        } |
        Select-Object -First 1

    $task = $asTask.MakeGenericMethod($ResultType).Invoke($null, @($Operation))
    $task.Wait()
    return $task.Result
}

$language = [Windows.Globalization.Language]::new($LanguageTag)
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($language)
if ($null -eq $engine) {
    throw "No installed Windows OCR engine supports language '$LanguageTag'."
}

$records = foreach ($path in $InputPath) {
    $resolved = (Resolve-Path -LiteralPath $path).Path
    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $stream = $null
    $bitmap = $null

    try {
        $file = Wait-WinRtResult `
            ([Windows.Storage.StorageFile]::GetFileFromPathAsync($resolved)) `
            ([Windows.Storage.StorageFile])
        $stream = Wait-WinRtResult `
            ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) `
            ([Windows.Storage.Streams.IRandomAccessStream])
        $decoder = Wait-WinRtResult `
            ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) `
            ([Windows.Graphics.Imaging.BitmapDecoder])
        $bitmap = Wait-WinRtResult `
            ($decoder.GetSoftwareBitmapAsync()) `
            ([Windows.Graphics.Imaging.SoftwareBitmap])
        $result = Wait-WinRtResult `
            ($engine.RecognizeAsync($bitmap)) `
            ([Windows.Media.Ocr.OcrResult])
        $stopwatch.Stop()

        $lines = foreach ($line in $result.Lines) {
            [ordered]@{
                text = $line.Text
                words = @($line.Words | ForEach-Object {
                    [ordered]@{
                        text = $_.Text
                        bounding_rect = @(
                            $_.BoundingRect.X,
                            $_.BoundingRect.Y,
                            $_.BoundingRect.Width,
                            $_.BoundingRect.Height
                        )
                    }
                })
            }
        }

        [ordered]@{
            input_path = $resolved
            language_tag = $LanguageTag
            image_width = [int] $decoder.PixelWidth
            image_height = [int] $decoder.PixelHeight
            elapsed_seconds = [Math]::Round($stopwatch.Elapsed.TotalSeconds, 4)
            line_count = @($lines).Count
            text = $result.Text
            lines = @($lines)
        }
    }
    finally {
        if ($null -ne $bitmap) { $bitmap.Dispose() }
        if ($null -ne $stream) { $stream.Dispose() }
    }
}

$parent = Split-Path -Parent $OutputPath
if ($parent) {
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
}

[ordered]@{
    engine = "Windows.Media.Ocr"
    generated_at = (Get-Date).ToUniversalTime().ToString("o")
    records = @($records)
} |
    ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath $OutputPath -Encoding UTF8

Write-Output $OutputPath

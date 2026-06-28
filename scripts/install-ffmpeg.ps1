$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$tools = Join-Path $root "tools"
$zip = Join-Path $tools "ffmpeg-release-essentials.zip"
$downloadDir = Join-Path $tools "ffmpeg-download"
$target = Join-Path $tools "ffmpeg"
$url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

New-Item -ItemType Directory -Force $tools | Out-Null

Write-Host "Downloading FFmpeg essentials..."
Invoke-WebRequest $url -OutFile $zip -TimeoutSec 300

if (Test-Path $downloadDir) {
    Remove-Item $downloadDir -Recurse -Force
}
Expand-Archive $zip -DestinationPath $downloadDir -Force

$bin = Get-ChildItem $downloadDir -Recurse -Directory -Filter bin | Select-Object -First 1
if (-not $bin) {
    throw "FFmpeg bin directory was not found in the downloaded archive."
}

if (Test-Path $target) {
    Remove-Item $target -Recurse -Force
}
New-Item -ItemType Directory -Force $target | Out-Null
Copy-Item $bin.FullName (Join-Path $target "bin") -Recurse

Remove-Item $zip -Force
Remove-Item $downloadDir -Recurse -Force

& (Join-Path $target "bin\ffmpeg.exe") -version | Select-Object -First 1
& (Join-Path $target "bin\ffprobe.exe") -version | Select-Object -First 1

Write-Host "FFmpeg installed to $target\bin"

# Install the official pinned Windows CUDA runtime without modifying system PATH.
$ErrorActionPreference = 'Stop'
if (-not [Environment]::Is64BitOperatingSystem) { throw '64-bit Windows is required' }
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$runtimeRoot = Join-Path $projectRoot '.tools/colmap'
$archivePath = Join-Path $projectRoot '.tools/downloads/colmap-4.2.1-windows-cuda.zip'
$expectedHash = 'e9c5cbd84c2ea986d2e970a2473fc2d2e6b34a2cdcf5d3df2765c319a63af881'
New-Item -ItemType Directory -Force (Split-Path $archivePath) | Out-Null
if (-not (Test-Path -LiteralPath $archivePath)) {
    Invoke-WebRequest 'https://github.com/colmap/colmap/releases/download/4.2.1/colmap-x64-windows-cuda.zip' -OutFile $archivePath
}
if ((Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedHash) {
    throw 'COLMAP archive checksum mismatch; inspect the download before retrying'
}
Expand-Archive -LiteralPath $archivePath -DestinationPath $runtimeRoot -Force
$nativeColmap = Join-Path $runtimeRoot 'bin/colmap.exe'
& $nativeColmap -h
if ($LASTEXITCODE -ne 0) { throw 'COLMAP could not start; check runtime requirements' }
Write-Host "Installed official COLMAP 4.2.1 CUDA runtime at $nativeColmap"
Write-Host 'Run Holo from the project folder, or set COLMAP_EXECUTABLE to this path.'
Write-Host 'A usable NVIDIA CUDA device is also required; /api/health checks both.'

<# 
.SYNOPSIS
    Start Odysseus with ChromaDB dependency management
.DESCRIPTION
    Launches ChromaDB if not running, then starts Odysseus on port 7000
.EXAMPLE
    .\start_odysseus.ps1
#>

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $scriptDir

Write-Host "=========================================="
Write-Host "Starting Odysseus stack..."
Write-Host "=========================================="

# Check if virtual environment exists
$venvActivate = Join-Path $scriptDir "venv\Scripts\Activate.ps1"
if (-not (Test-Path $venvActivate)) {
    Write-Error "ERROR: Virtual environment not found at .\venv"
    Write-Host "Run setup.py first or create venv manually"
    Read-Host "Press Enter to exit"
    exit 1
}

# Activate venv
& $venvActivate

# Check if ChromaDB is already running
try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:8100/api/v2/heartbeat" -Method GET -TimeoutSec 2 -ErrorAction Stop
    if ($response.StatusCode -eq 200) {
        Write-Host "[ok] ChromaDB already running on port 8100"
    }
} catch {
    Write-Host "[start] Launching ChromaDB on port 8100..."
    $chromaProcess = Start-Process -FilePath "cmd.exe" -ArgumentList "/c chroma run --host 127.0.0.1 --port 8100 --path .\data\chroma" -WindowStyle Hidden -PassThru
    
    # Wait for ChromaDB to be healthy
    Write-Host "[wait] Waiting for ChromaDB to be ready..."
    $ready = $false
    for ($i = 1; $i -le 30; $i++) {
        try {
            $response = Invoke-WebRequest -Uri "http://127.0.0.1:8100/api/v2/heartbeat" -Method GET -TimeoutSec 2 -ErrorAction Stop
            if ($response.StatusCode -eq 200) {
                Write-Host "[ok] ChromaDB is ready"
                $ready = $true
                break
            }
        } catch {
            # Not ready yet
        }
        Start-Sleep -Seconds 1
    }
    if (-not $ready) {
        Write-Warning "ChromaDB startup timed out, continuing anyway..."
    }
}

# Start Odysseus
Write-Host "[start] Launching Odysseus on http://127.0.0.1:7000"
Write-Host "=========================================="
python -m uvicorn app:app --host 127.0.0.1 --port 7000
# Service Monitoring and Health Check Script for Caluu+
# This script monitors Django service and Cloudflare Tunnel, restarts if needed

$serviceName = "CaluuPlusDjango"
$healthCheckUrl = "http://localhost:8000/api/health"
$logFile = "C:\Users\Administrator\Documents\KODIN SOFTWARES\caluuplus\logs\monitor.log"

function Write-Log {
    param([string]$message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logEntry = "[$timestamp] $message"
    Add-Content -Path $logFile -Value $logEntry
    Write-Host $logEntry
}

Write-Log "=== Service Monitor Started ==="

# Check Django Service
Write-Log "Checking Django service status..."
$djangoService = Get-Service -Name $serviceName -ErrorAction SilentlyContinue

if (-not $djangoService) {
    Write-Log "ERROR: Django service '$serviceName' not found"
    exit 1
}

if ($djangoService.Status -ne "Running") {
    Write-Log "WARNING: Django service is not running (Status: $($djangoService.Status))"
    Write-Log "Attempting to start service..."
    Start-Service -Name $serviceName
    Start-Sleep -Seconds 10
    $djangoService.Refresh()
    
    if ($djangoService.Status -eq "Running") {
        Write-Log "SUCCESS: Django service started successfully"
    } else {
        Write-Log "ERROR: Failed to start Django service"
        exit 1
    }
} else {
    Write-Log "Django service is running"
}

# Health Check
Write-Log "Performing health check on $healthCheckUrl..."
try {
    $response = Invoke-WebRequest -Uri $healthCheckUrl -UseBasicParsing -TimeoutSec 10
    if ($response.StatusCode -eq 200) {
        Write-Log "SUCCESS: Health check passed (Status: $($response.StatusCode))"
    } else {
        Write-Log "WARNING: Health check returned status $($response.StatusCode)"
    }
} catch {
    Write-Log "WARNING: Health check failed: $_"
    Write-Log "Attempting to restart Django service..."
    Restart-Service -Name $serviceName -Force
    Start-Sleep -Seconds 15
    Write-Log "Django service restarted"
}

# Check Cloudflare Tunnel process
Write-Log "Checking Cloudflare Tunnel process..."
$cloudflaredProcess = Get-Process -Name "cloudflared" -ErrorAction SilentlyContinue

if (-not $cloudflaredProcess) {
    Write-Log "WARNING: Cloudflare Tunnel is not running"
    Write-Log "To start Cloudflare Tunnel, run: .\cloudflared.exe tunnel run --config config.yml caluuplus-backend"
} else {
    Write-Log "Cloudflare Tunnel is running (PID: $($cloudflaredProcess.Id))"
}

# Check disk space
Write-Log "Checking disk space..."
$systemDrive = Get-PSDrive C
$freeSpaceGB = [math]::Round($systemDrive.Free / 1GB, 2)
Write-Log "Free disk space: $freeSpaceGB GB"

if ($freeSpaceGB -lt 5) {
    Write-Log "WARNING: Low disk space (less than 5 GB)"
}

# Check memory usage
Write-Log "Checking memory usage..."
$os = Get-CimInstance Win32_OperatingSystem
$totalMemory = [math]::Round($os.TotalVisibleMemorySize / 1MB, 2)
$freeMemory = [math]::Round($os.FreePhysicalMemory / 1MB, 2)
$usedMemory = $totalMemory - $freeMemory
$memoryUsagePercent = [math]::Round(($usedMemory / $totalMemory) * 100, 2)

Write-Log "Memory usage: $usedMemory GB / $totalMemory GB ($memoryUsagePercent%)"

if ($memoryUsagePercent -gt 90) {
    Write-Log "WARNING: High memory usage (over 90%)"
}

Write-Log "=== Service Monitor Completed ==="

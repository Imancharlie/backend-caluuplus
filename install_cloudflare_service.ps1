# Install Cloudflare Tunnel as Windows Service using NSSM
# This script will install cloudflared as a Windows service for automatic startup

# Define variables
$serviceName = "CaluuPlusCloudflare"
$serviceDisplayName = "Caluu+ Cloudflare Tunnel"
$projectPath = "C:\Users\Administrator\Documents\KODIN SOFTWARES\caluuplus"
$cloudflaredExe = "$projectPath\cloudflared.exe"
$configFile = "$projectPath\config.yml"
$tunnelName = "caluuplus-backend"
$nssmPath = "$projectPath\nssm.exe"

# Check if cloudflared.exe exists
if (-not (Test-Path $cloudflaredExe)) {
    Write-Host "ERROR: cloudflared.exe not found at $cloudflaredExe" -ForegroundColor Red
    exit 1
}

# Check if config.yml exists
if (-not (Test-Path $configFile)) {
    Write-Host "ERROR: config.yml not found at $configFile" -ForegroundColor Red
    Write-Host "Please run setup_cloudflare_tunnel.ps1 first" -ForegroundColor Yellow
    exit 1
}

# Download NSSM if not exists
if (-not (Test-Path $nssmPath)) {
    Write-Host "Downloading NSSM..."
    $nssmUrl = "https://nssm.cc/release/nssm-2.24.zip"
    $nssmZip = "$projectPath\nssm.zip"
    Invoke-WebRequest -Uri $nssmUrl -OutFile $nssmZip
    
    Write-Host "Extracting NSSM..."
    Expand-Archive -Path $nssmZip -DestinationPath "$projectPath\nssm_temp" -Force
    Copy-Item "$projectPath\nssm_temp\nssm-2.24\win64\nssm.exe" -Destination $projectPath
    Remove-Item -Path "$projectPath\nssm_temp" -Recurse -Force
    Remove-Item -Path $nssmZip -Force
    Write-Host "NSSM downloaded and extracted."
}

# Check if service already exists
$existingService = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
if ($existingService) {
    Write-Host "Service $serviceName already exists. Removing it..."
    & $nssmPath stop $serviceName
    & $nssmPath remove $serviceName confirm
}

# Install the service
Write-Host "Installing Windows Service: $serviceName"
& $nssmPath install $serviceName $cloudflaredExe "tunnel" "run" "--config" $configFile $tunnelName

# Configure service
& $nssmPath set $serviceName AppDirectory $projectPath
& $nssmPath set $serviceName DisplayName $serviceDisplayName
& $nssmPath set $serviceName Description "Caluu+ Cloudflare Tunnel for caluu.mipt.co.tz"
& $nssmPath set $serviceName Start SERVICE_AUTO_START

# Configure service recovery (restart on failure)
& $nssmPath set $serviceName AppRestartDelay 60000
& $nssmPath set $serviceName AppThrottle 1500
& $nssmPath set $serviceName AppExit Default Restart
& $nssmPath set $serviceName AppRestartDelay 60000

# Set service to run as Network Service
& $nssmPath set $serviceName ObjectName "NT AUTHORITY\NetworkService"

Write-Host "Service installed successfully!" -ForegroundColor Green
Write-Host "To start the service, run: nssm start $serviceName"
Write-Host "To stop the service, run: nssm stop $serviceName"
Write-Host "To remove the service, run: nssm remove $serviceName confirm"

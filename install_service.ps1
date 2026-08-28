# Install Django as Windows Service using NSSM
# This script will download NSSM and install the Django service

# Define variables
$serviceName = "CaluuPlusDjango"
$serviceDisplayName = "Caluu+ Django Backend"
$projectPath = "C:\Users\Administrator\Documents\KODIN SOFTWARES\caluuplus"
$pythonExe = "$projectPath\.venv\Scripts\python.exe"
$scriptPath = "$projectPath\run_production.py"
$nssmPath = "$projectPath\nssm.exe"

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
& $nssmPath install $serviceName $pythonExe $scriptPath

# Configure service
& $nssmPath set $serviceName AppDirectory $projectPath
& $nssmPath set $serviceName DisplayName $serviceDisplayName
& $nssmPath set $serviceName Description "Caluu+ Django Backend Production Server"
& $nssmPath set $serviceName Start SERVICE_AUTO_START
& $nssmPath set $serviceName AppEnvironmentExtra "DJANGO_SETTINGS_MODULE=academic_backend.production"

# Configure service recovery (restart on failure)
& $nssmPath set $serviceName AppRestartDelay 60000
& $nssmPath set $serviceName AppThrottle 1500
& $nssmPath set $serviceName AppExit Default Restart
& $nssmPath set $serviceName AppRestartDelay 60000

# Set service to run as Network Service (or create a dedicated service account)
& $nssmPath set $serviceName ObjectName "NT AUTHORITY\NetworkService"

Write-Host "Service installed successfully!"
Write-Host "To start the service, run: nssm start $serviceName"
Write-Host "To stop the service, run: nssm stop $serviceName"
Write-Host "To remove the service, run: nssm remove $serviceName confirm"

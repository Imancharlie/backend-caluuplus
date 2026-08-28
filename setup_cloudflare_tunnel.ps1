# Cloudflare Tunnel Setup Script for Caluu+
# This script helps configure cloudflared to expose Django backend to caluu.mipt.co.tz

Write-Host "=== Cloudflare Tunnel Setup for Caluu+ ===" -ForegroundColor Cyan
Write-Host ""

# Check if cloudflared.exe exists
if (-not (Test-Path ".\cloudflared.exe")) {
    Write-Host "ERROR: cloudflared.exe not found in current directory" -ForegroundColor Red
    exit 1
}

Write-Host "Step 1: Login to Cloudflare" -ForegroundColor Yellow
Write-Host "This will open a browser window for authentication"
Write-Host ""

# Login to Cloudflare
.\cloudflared.exe tunnel login

Write-Host ""
Write-Host "Step 2: Create Tunnel" -ForegroundColor Yellow
$tunnelName = "caluuplus-backend"
.\cloudflared.exe tunnel create $tunnelName

Write-Host ""
Write-Host "Step 3: Configure Tunnel" -ForegroundColor Yellow
Write-Host "Creating config file..."

$configContent = @"
tunnel: $tunnelName
credentials-file: $tunnelName.json

ingress:
  - hostname: caluu.mipt.co.tz
    service: http://localhost:8000
  - service: http_status:404
"@

Set-Content -Path "config.yml" -Value $configContent

Write-Host ""
Write-Host "Step 4: Route DNS" -ForegroundColor Yellow
Write-Host "You need to manually route the DNS in Cloudflare dashboard:"
Write-Host "1. Go to https://dash.cloudflare.com"
Write-Host "2. Select your domain: mipt.co.tz"
Write-Host "3. Go to SSL/TLS > Edge Certificates"
Write-Host "4. Ensure 'Always Use HTTPS' is ON"
Write-Host "5. Go to Zero Trust > Networks > Tunnels"
Write-Host "6. Select the tunnel: $tunnelName"
Write-Host "7. Click 'Public Hostname'"
Write-Host "8. Add hostname: caluu.mipt.co.tz"
Write-Host "9. Service: http://localhost:8000"
Write-Host ""

Write-Host "Step 5: Test Tunnel" -ForegroundColor Yellow
Write-Host "Run the following command to test the tunnel:"
Write-Host ".\cloudflared.exe tunnel run --config config.yml $tunnelName"
Write-Host ""

Write-Host "=== Setup Complete ===" -ForegroundColor Green
Write-Host "Next steps:"
Write-Host "1. Configure DNS in Cloudflare dashboard as shown above"
Write-Host "2. Test the tunnel with the command above"
Write-Host "3. Install as Windows Service for automatic startup"

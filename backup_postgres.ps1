# PostgreSQL Backup Script for Caluu+
# This script creates automated backups of the PostgreSQL database

# Configuration
$backupDir = "C:\Users\Administrator\Documents\KODIN SOFTWARES\caluuplus\db_backups"
$dbName = "caluuplus"
$dbUser = "caluuplus_user"
$dbHost = "localhost"
$dbPort = "5432"
$retentionDays = 30  # Keep backups for 30 days

# Create backup directory if it doesn't exist
if (-not (Test-Path $backupDir)) {
    New-Item -ItemType Directory -Path $backupDir -Force
    Write-Host "Created backup directory: $backupDir"
}

# Generate backup filename with timestamp
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupFile = "$backupDir\caluuplus_backup_$timestamp.sql"

Write-Host "=== PostgreSQL Backup Started ===" -ForegroundColor Cyan
Write-Host "Timestamp: $timestamp"
Write-Host "Backup file: $backupFile"
Write-Host ""

# Check if pg_dump is available
$pgDumpPath = "C:\Program Files\PostgreSQL\16\bin\pg_dump.exe"
if (-not (Test-Path $pgDumpPath)) {
    # Try PostgreSQL 17
    $pgDumpPath = "C:\Program Files\PostgreSQL\17\bin\pg_dump.exe"
    if (-not (Test-Path $pgDumpPath)) {
        Write-Host "ERROR: pg_dump.exe not found. Please install PostgreSQL 16 or 17" -ForegroundColor Red
        exit 1
    }
}

# Get database password from .env file
$envFile = "C:\Users\Administrator\Documents\KODIN SOFTWARES\caluuplus\.env"
if (Test-Path $envFile) {
    $envContent = Get-Content $envFile
    $dbPassword = ($envContent | Select-String "DB_PASSWORD=").ToString().Split('=')[1]
    $env:PGPASSWORD = $dbPassword
} else {
    Write-Host "WARNING: .env file not found. You may be prompted for password." -ForegroundColor Yellow
}

# Run pg_dump
Write-Host "Creating backup..." -ForegroundColor Yellow
try {
    & $pgDumpPath -h $dbHost -p $dbPort -U $dbUser -d $dbName -F c -f $backupFile -v
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Backup completed successfully!" -ForegroundColor Green
        Write-Host "Backup size: $((Get-Item $backupFile).Length / 1MB) MB"
    } else {
        Write-Host "ERROR: Backup failed with exit code $LASTEXITCODE" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "ERROR: Backup failed: $_" -ForegroundColor Red
    exit 1
}

# Clean up old backups
Write-Host ""
Write-Host "Cleaning up old backups (older than $retentionDays days)..." -ForegroundColor Yellow
$cutoffDate = (Get-Date).AddDays(-$retentionDays)
$oldBackups = Get-ChildItem -Path $backupDir -Filter "caluuplus_backup_*.sql" | Where-Object { $_.LastWriteTime -lt $cutoffDate }

if ($oldBackups.Count -gt 0) {
    foreach ($backup in $oldBackups) {
        Remove-Item $backup.FullName -Force
        Write-Host "Deleted old backup: $($backup.Name)"
    }
    Write-Host "Deleted $($oldBackups.Count) old backup(s)" -ForegroundColor Green
} else {
    Write-Host "No old backups to clean up" -ForegroundColor Gray
}

# Clear password from environment
$env:PGPASSWORD = $null

Write-Host ""
Write-Host "=== Backup Summary ===" -ForegroundColor Cyan
Write-Host "Total backups in directory: $((Get-ChildItem -Path $backupDir -Filter "caluuplus_backup_*.sql").Count)"
Write-Host "Latest backup: $backupFile"
Write-Host "Backup completed at: $(Get-Date)"

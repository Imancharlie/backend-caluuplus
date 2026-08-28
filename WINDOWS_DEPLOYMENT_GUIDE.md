# Caluu+ Windows Production Deployment Guide

This guide covers deploying the Django backend on Windows with PostgreSQL, Waitress, Cloudflare Tunnel, and automatic startup.

## Architecture Overview

```
Frontend
    |
    |
https://caluu.mipt.co.tz
    |
Cloudflare Tunnel
    |
Windows Desktop
    |
Waitress (WSGI Server)
    |
Django Backend
    |
PostgreSQL Database
```

## Prerequisites

- Windows 10/11 with 16GB RAM
- Python 3.12+ (currently using 3.14.6)
- PostgreSQL 16 or 17
- Cloudflare account with domain mipt.co.tz
- Administrator privileges

## Step 1: Install PostgreSQL

### Download and Install
1. Download PostgreSQL 16 from: https://www.postgresql.org/download/windows/
2. Run installer with these settings:
   - Port: 5432
   - Password: Choose a strong password
   - Components: PostgreSQL Server, pgAdmin 4, Command Line Tools

### Create Database
```powershell
# Open PostgreSQL command prompt
psql -U postgres -h localhost

# Run these SQL commands:
CREATE DATABASE caluuplus;
CREATE USER caluuplus_user WITH PASSWORD 'your_strong_password';
GRANT ALL PRIVILEGES ON DATABASE caluuplus TO caluuplus_user;
ALTER DATABASE caluuplus OWNER TO caluuplus_user;
\q
```

## Step 2: Configure Environment

### Update .env File
Edit `.env` file with your actual values:
```env
SECRET_KEY=your-secret-key-here
DEBUG=False
ALLOWED_HOSTS=caluu.mipt.co.tz,localhost

DB_NAME=caluuplus
DB_USER=caluuplus_user
DB_PASSWORD=your-postgres-password-here
DB_HOST=localhost
DB_PORT=5432
```

### Install Dependencies
```powershell
cd "C:\Users\Administrator\Documents\KODIN SOFTWARES\caluuplus"
.venv\Scripts\activate
pip install -r requirements.txt
```

## Step 3: Database Migration

### Migrate SQLite to PostgreSQL (Optional)
If you have existing SQLite data:
```powershell
.venv\Scripts\activate
pip install django-db-converter
python manage.py migrate --settings=academic_backend.production
```

### Fresh Installation
```powershell
.venv\Scripts\activate
python manage.py migrate --settings=academic_backend.production
python manage.py collectstatic --settings=academic_backend.production
```

## Step 4: Test Django Server

### Manual Test
```powershell
.venv\Scripts\activate
python run_production.py
```

Test at: http://localhost:8000

Press Ctrl+C to stop.

## Step 5: Install Django as Windows Service

### Install Service
```powershell
.\install_service.ps1
```

This will:
- Download NSSM (Non-Sucking Service Manager)
- Install Django as Windows Service "CaluuPlusDjango"
- Configure automatic startup
- Configure auto-restart on failure

### Manage Service
```powershell
# Start service
nssm start CaluuPlusDjango

# Stop service
nssm stop CaluuPlusDjango

# Check status
nssm status CaluuPlusDjango

# View logs
nssm edit CaluuPlusDjango
```

## Step 6: Configure Cloudflare Tunnel

### Setup Tunnel
```powershell
.\setup_cloudflare_tunnel.ps1
```

This will:
- Login to Cloudflare (opens browser)
- Create tunnel "caluuplus-backend"
- Generate config.yml file

### Configure DNS in Cloudflare Dashboard
1. Go to https://dash.cloudflare.com
2. Select domain: mipt.co.tz
3. Go to Zero Trust > Networks > Tunnels
4. Select tunnel: caluuplus-backend
5. Click "Public Hostname"
6. Add hostname: caluu.mipt.co.tz
7. Service: http://localhost:8000

### Test Tunnel
```powershell
.\cloudflared.exe tunnel run --config config.yml caluuplus-backend
```

Test at: https://caluu.mipt.co.tz

Press Ctrl+C to stop.

## Step 7: Install Cloudflare Tunnel as Windows Service

### Install Service
```powershell
.\install_cloudflare_service.ps1
```

This will:
- Install cloudflared as Windows Service "CaluuPlusCloudflare"
- Configure automatic startup
- Configure auto-restart on failure

### Manage Service
```powershell
# Start service
nssm start CaluuPlusCloudflare

# Stop service
nssm stop CaluuPlusCloudflare

# Check status
nssm status CaluuPlusCloudflare
```

## Step 8: Configure Automated Backups

### Manual Backup Test
```powershell
.\backup_postgres.ps1
```

### Schedule Automated Backups
1. Open Task Scheduler
2. Create Basic Task
3. Name: "Caluu+ PostgreSQL Backup"
4. Trigger: Daily at 2:00 AM
5. Action: Start a program
   - Program: `powershell.exe`
   - Arguments: `-ExecutionPolicy Bypass -File "C:\Users\Administrator\Documents\KODIN SOFTWARES\caluuplus\backup_postgres.ps1"`
6. Finish

## Step 9: Configure Monitoring

### Manual Health Check
```powershell
.\monitor_service.ps1
```

### Schedule Automated Monitoring
1. Open Task Scheduler
2. Create Basic Task
3. Name: "Caluu+ Service Monitor"
4. Trigger: Every 5 minutes
5. Action: Start a program
   - Program: `powershell.exe`
   - Arguments: `-ExecutionPolicy Bypass -File "C:\Users\Administrator\Documents\KODIN SOFTWARES\caluuplus\monitor_service.ps1"`
6. Finish

## Step 10: Verify Deployment

### Check Services
```powershell
Get-Service CaluuPlusDjango
Get-Service CaluuPlusCloudflare
```

Both should show "Running" status.

### Test API Endpoints
```powershell
# Test health endpoint
curl http://localhost:8000/api/

# Test public endpoint
curl https://caluu.mipt.co.tz/api/
```

### Check Logs
```powershell
# Django logs
Get-Content logs\django.log -Tail 50

# Monitor logs
Get-Content logs\monitor.log -Tail 50
```

## File Structure

```
caluuplus/
├── .venv/                          # Virtual environment
├── .env                            # Production secrets
├── .env.example                    # Example secrets
├── academic_backend/
│   ├── settings.py                 # Development settings
│   ├── production.py               # Production settings
│   └── wsgi.py                     # WSGI application
├── api/                            # API application
├── chatbot/                        # Chatbot application
├── logs/                           # Log files
├── media/                          # User uploads
├── staticfiles/                    # Collected static files
├── db_backups/                     # PostgreSQL backups
├── cloudflared.exe                 # Cloudflare Tunnel binary
├── config.yml                      # Cloudflare Tunnel config
├── run_production.py               # Waitress startup script
├── install_service.ps1             # Django service installer
├── install_cloudflare_service.ps1  # Cloudflare service installer
├── setup_cloudflare_tunnel.ps1     # Cloudflare tunnel setup
├── backup_postgres.ps1             # PostgreSQL backup script
├── monitor_service.ps1             # Service monitoring script
└── requirements.txt                # Python dependencies
```

## Troubleshooting

### Django Service Won't Start
```powershell
# Check service status
nssm status CaluuPlusDjango

# View service logs
nssm edit CaluuPlusDjango

# Check Django logs
Get-Content logs\django.log -Tail 100

# Test manually
.venv\Scripts\activate
python run_production.py
```

### Cloudflare Tunnel Won't Start
```powershell
# Check service status
nssm status CaluuPlusCloudflare

# Test manually
.\cloudflared.exe tunnel run --config config.yml caluuplus-backend

# Check Cloudflare dashboard for tunnel status
```

### Database Connection Issues
```powershell
# Test PostgreSQL connection
psql -U caluuplus_user -h localhost -d caluuplus

# Check .env file for correct credentials
Get-Content .env

# Restart PostgreSQL service
Get-Service postgresql* | Restart-Service
```

### Port Already in Use
```powershell
# Check what's using port 8000
netstat -ano | findstr :8000

# Kill process if needed
taskkill /PID <PID> /F
```

## Security Recommendations

1. **Change SECRET_KEY**: Generate a new random secret key
2. **Strong Database Password**: Use a strong PostgreSQL password
3. **Firewall**: Configure Windows Firewall to allow only necessary ports
4. **Updates**: Keep PostgreSQL, Python, and dependencies updated
5. **Backups**: Verify backups are running and test restore procedure
6. **SSL**: Cloudflare provides SSL/TLS termination
7. **Environment Variables**: Never commit .env file to version control

## Performance Tuning

### Waitress Configuration
Edit `run_production.py` to adjust:
- `threads`: Number of worker threads (default: 8)
- `connection_limit`: Max concurrent connections (default: 1000)
- `backlog`: Connection backlog (default: 2048)

### PostgreSQL Configuration
Edit `postgresql.conf`:
- `shared_buffers`: 4GB (for 16GB RAM)
- `effective_cache_size`: 12GB
- `maintenance_work_mem`: 1GB
- `checkpoint_completion_target`: 0.9
- `wal_buffers`: 16MB
- `default_statistics_target`: 100

## Maintenance

### Regular Tasks
- **Daily**: Automated backups run at 2:00 AM
- **Every 5 minutes**: Service monitoring runs
- **Weekly**: Check disk space and logs
- **Monthly**: Review backup retention and test restore

### Update Procedure
```powershell
# Stop services
nssm stop CaluuPlusDjango
nssm stop CaluuPlusCloudflare

# Update code
git pull

# Update dependencies
.venv\Scripts\activate
pip install -r requirements.txt

# Run migrations
python manage.py migrate --settings=academic_backend.production

# Collect static files
python manage.py collectstatic --settings=academic_backend.production

# Start services
nssm start CaluuPlusDjango
nssm start CaluuPlusCloudflare
```

## Support

For issues or questions:
- Check logs in `logs/` directory
- Review troubleshooting section
- Check Cloudflare dashboard for tunnel status
- Verify PostgreSQL service is running

## Architecture Benefits

- **24/7 Availability**: Windows Services auto-start on boot
- **Auto-restart**: Services restart automatically on crashes
- **SSL/TLS**: Cloudflare provides free SSL certificates
- **DDoS Protection**: Cloudflare mitigates DDoS attacks
- **Global CDN**: Cloudflare CDN for faster content delivery
- **Monitoring**: Automated health checks and alerts
- **Backups**: Automated daily PostgreSQL backups
- **Scalability**: Waitress handles concurrent connections efficiently

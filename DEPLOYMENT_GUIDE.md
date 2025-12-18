# Deployment Guide for Caluu+ VPS

## VPS Details
- **IP Address:** 209.74.79.228
- **Username:** root
- **Project Path:** /var/www/caluuplus

## Step 1: Upload Files from Local Machine

Run these commands from your local machine (in the project directory):

```bash
# Make script executable
chmod +x deploy_commands.sh

# Run deployment script
./deploy_commands.sh
```

Or run commands individually:

```bash
# Authentication files
scp api/authentication.py root@209.74.79.228:/var/www/caluuplus/api/
scp api/views.py root@209.74.79.228:/var/www/caluuplus/api/
scp api/serializers.py root@209.74.79.228:/var/www/caluuplus/api/
scp academic_backend/settings.py root@209.74.79.228:/var/www/caluuplus/academic_backend/

# Requirements and URLs
scp requirements.txt root@209.74.79.228:/var/www/caluuplus/
scp api/urls.py root@209.74.79.228:/var/www/caluuplus/api/
```

## Step 2: SSH into VPS and Run Migrations

```bash
# SSH into VPS
ssh root@209.74.79.228

# Navigate to project
cd /var/www/caluuplus

# Run migrations
python manage.py makemigrations
python manage.py migrate

# Install/update requirements (if new packages added)
pip install -r requirements.txt

# Restart Django service (choose the one that applies)
sudo systemctl restart gunicorn
# OR
sudo systemctl restart uwsgi
# OR
sudo supervisorctl restart caluuplus
```

## Step 3: Verify Deployment

```bash
# Check service status
sudo systemctl status gunicorn
# OR
sudo systemctl status uwsgi
# OR
sudo supervisorctl status caluuplus

# Check Django logs
tail -f /var/log/gunicorn/error.log
# OR check your Django log location
```

## Quick Deployment (All-in-One)

If you want to upload files and run migrations in one go:

```bash
# From local machine
./deploy_commands.sh

# Then SSH and run
ssh root@209.74.79.228 'cd /var/www/caluuplus && python manage.py makemigrations && python manage.py migrate && pip install -r requirements.txt && sudo systemctl restart gunicorn'
```

## Files Changed Today

### Authentication
- `api/authentication.py` (NEW)
- `api/views.py`
- `api/serializers.py`
- `academic_backend/settings.py`
- `api/urls.py`

### Chatbot (Already uploaded)
- `chatbot/views.py`
- `chatbot/enhanced_service.py`
- `chatbot/vector_service.py`
- `chatbot/models.py`
- `chatbot/admin.py`
- `chatbot/urls.py`
- `chatbot/__init__.py`

### Opportunities (Already uploaded)
- `resources_opps/views.py`
- `resources_opps/models.py`
- `resources_opps/serializers.py`

### Other
- `requirements.txt`

## Troubleshooting

### Permission Denied
```bash
# Fix file permissions on VPS
sudo chown -R www-data:www-data /var/www/caluuplus
sudo chmod -R 755 /var/www/caluuplus
```

### Service Won't Start
```bash
# Check logs
sudo journalctl -u gunicorn -n 50
# OR
sudo tail -f /var/log/gunicorn/error.log
```

### Migration Errors
```bash
# Check for migration conflicts
python manage.py showmigrations

# If needed, fake migrations (use with caution)
# python manage.py migrate --fake
```




#!/bin/bash
# Complete deployment script - Run migrations and restart service on VPS
# Run this AFTER uploading files with deploy_commands.sh
# Usage: ssh root@209.74.79.228 'bash -s' < deploy_vps.sh

cd /var/www/caluuplus

echo "🔄 Running migrations..."
python manage.py makemigrations
python manage.py migrate

echo "📦 Installing/updating requirements..."
pip install -r requirements.txt --quiet

echo "🔄 Restarting Django service..."
# Try different service names - uncomment the one that applies
sudo systemctl restart gunicorn 2>/dev/null || \
sudo systemctl restart uwsgi 2>/dev/null || \
sudo supervisorctl restart caluuplus 2>/dev/null || \
echo "⚠️  Please restart your Django service manually"

echo "✅ Deployment complete!"
echo "📊 Check service status:"
sudo systemctl status gunicorn 2>/dev/null || \
sudo systemctl status uwsgi 2>/dev/null || \
sudo supervisorctl status caluuplus 2>/dev/null || \
echo "⚠️  Service status check failed - verify manually"




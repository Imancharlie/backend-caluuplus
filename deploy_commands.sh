#!/bin/bash
# Deployment commands for Caluu+ VPS
# Project path: /var/www/caluuplus
# Username: root
# VPS IP: 209.74.79.228

VPS_IP="209.74.79.228"
VPS_USER="root"
PROJECT_PATH="/var/www/caluuplus"

echo "🚀 Starting deployment to VPS..."

# Authentication files
echo "📤 Uploading authentication files..."
scp api/authentication.py ${VPS_USER}@${VPS_IP}:${PROJECT_PATH}/api/
scp api/views.py ${VPS_USER}@${VPS_IP}:${PROJECT_PATH}/api/
scp api/serializers.py ${VPS_USER}@${VPS_IP}:${PROJECT_PATH}/api/
scp academic_backend/settings.py ${VPS_USER}@${VPS_IP}:${PROJECT_PATH}/academic_backend/

# Requirements and URLs
echo "📤 Uploading requirements and URL config..."
scp requirements.txt ${VPS_USER}@${VPS_IP}:${PROJECT_PATH}/
scp api/urls.py ${VPS_USER}@${VPS_IP}:${PROJECT_PATH}/api/

echo "✅ File upload complete!"
echo ""
echo "📋 Next steps - SSH into VPS and run:"
echo "   ssh ${VPS_USER}@${VPS_IP}"
echo "   cd ${PROJECT_PATH}"
echo "   python manage.py makemigrations"
echo "   python manage.py migrate"
echo "   pip install -r requirements.txt  # if new packages added"
echo "   sudo systemctl restart gunicorn  # or your service name"
echo ""
echo "   # Alternative restart commands:"
echo "   # sudo supervisorctl restart caluuplus"
echo "   # sudo systemctl restart uwsgi"


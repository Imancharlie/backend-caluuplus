"""
Production startup script for Django with Waitress server
Run this script to start the Django backend in production mode
"""

import os
import sys
from waitress import serve
from django.core.wsgi import get_wsgi_application

# Set Django settings module to production
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'academic_backend.production')

# Get the WSGI application
application = get_wsgi_application()

if __name__ == '__main__':
    print("Starting Django production server with Waitress...")
    print("Settings: academic_backend.production")
    print("Listening on: http://0.0.0.0:8000")

    serve(
        application,
        host='0.0.0.0',
        port=8000,
        threads=8,
        connection_limit=1000,
        backlog=2048,
        channel_timeout=120,
    )
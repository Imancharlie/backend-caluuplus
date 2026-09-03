"""Test the /api/students/data/ endpoint."""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'academic_backend.settings')
django.setup()

from django.test import RequestFactory
from django.contrib.auth import get_user_model
from api.views import student_data

User = get_user_model()

# Get a test user
user = User.objects.first()
if not user:
    print("No users found")
    exit(1)

print(f"Testing with user: {user.email}")

# Create a request
factory = RequestFactory()
request = factory.get('/api/students/data/')
request.user = user

# Call the view
try:
    response = student_data(request)
    print(f"Response status: {response.status_code}")
    print(f"Response data: {response.data}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

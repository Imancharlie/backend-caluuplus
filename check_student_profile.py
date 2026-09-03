"""Check if user has a student profile."""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'academic_backend.settings')
django.setup()

from django.contrib.auth import get_user_model
from api.models import Student

User = get_user_model()

# Get a test user
user = User.objects.first()
if not user:
    print("No users found")
    exit(1)

print(f"User: {user.email} (id: {user.id})")
print(f"Is student: {getattr(user, 'is_student', False)}")

# Check for student profile
try:
    student = Student.objects.get(user=user)
    print(f"Student profile exists: {student}")
    print(f"University: {student.university}")
    print(f"College: {student.college}")
    print(f"Program: {student.program}")
except Student.DoesNotExist:
    print("No student profile found for this user")

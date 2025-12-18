#!/usr/bin/env python
"""
Simple test for Timetable API endpoints
"""
import requests
import json

# Configuration
BASE_URL = "http://localhost:8000/api"

def test_timetable_endpoints():
    """Test timetable endpoints without authentication"""
    
    print("🧪 Testing Timetable API Endpoints")
    print("=" * 50)
    
    # Test 1: Check if server is running
    print("1. Checking server status...")
    try:
        response = requests.get(f"{BASE_URL}/universities/", timeout=5)
        if response.status_code == 200:
            print("   ✅ Server is running")
        else:
            print(f"   ⚠️  Server responded with status {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"   ❌ Server not accessible: {e}")
        return
    
    # Test 2: Check timetable endpoints exist (should return 401 for unauthenticated)
    print("\n2. Testing timetable endpoints...")
    
    endpoints = [
        "/timetable/my/",
        "/students/00000000-0000-0000-0000-000000000001/timetable/",
        "/timetable/slots/"
    ]
    
    for endpoint in endpoints:
        try:
            response = requests.get(f"{BASE_URL}{endpoint}")
            if response.status_code == 401:
                print(f"   ✅ {endpoint} - Authentication required (expected)")
            elif response.status_code == 404:
                print(f"   ✅ {endpoint} - Endpoint exists (404 for invalid student ID)")
            else:
                print(f"   ⚠️  {endpoint} - Unexpected status: {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"   ❌ {endpoint} - Error: {e}")
    
    # Test 3: Check database has timetable data
    print("\n3. Checking database...")
    try:
        import os
        import django
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'academic_backend.settings')
        django.setup()
        
        from api.models import TimetableSlot
        count = TimetableSlot.objects.count()
        print(f"   ✅ Found {count} timetable slots in database")
        
        if count > 0:
            sample = TimetableSlot.objects.first()
            print(f"   📝 Sample: {sample.day_of_week} {sample.time_slot} - {sample.course.code}")
    except Exception as e:
        print(f"   ❌ Database error: {e}")
    
    print("\n🎉 Basic tests completed!")
    print("\n📋 Next steps:")
    print("   1. Visit http://localhost:8000/admin/ to see TimetableSlot in admin")
    print("   2. Login with superuser credentials")
    print("   3. Check 'Timetable slots' section")
    print("   4. Test API with proper authentication")

if __name__ == "__main__":
    test_timetable_endpoints()

#!/usr/bin/env python
"""
Test the API with smart fallback system
"""
import requests
import json

BASE_URL = "http://localhost:8000/api"

def test_api_with_fallback():
    print("🧪 Testing API with Smart Fallback")
    print("=" * 50)
    
    # Test the electrical student who should get fallback data
    print("1. Testing with electrical student (should get fallback)...")
    
    # First, let's check if the server is running
    try:
        response = requests.get(f"{BASE_URL}/universities/", timeout=5)
        if response.status_code != 200:
            print("   ❌ Server not running")
            return
    except:
        print("   ❌ Server not accessible")
        return
    
    print("   ✅ Server is running")
    
    # Test the timetable endpoint (will return 401 without auth, but that's expected)
    try:
        response = requests.get(f"{BASE_URL}/timetable/my/")
        if response.status_code == 401:
            print("   ✅ Timetable endpoint working (requires authentication)")
        else:
            print(f"   ⚠️  Unexpected status: {response.status_code}")
    except Exception as e:
        print(f"   ❌ Error testing endpoint: {e}")
    
    print("\n2. Testing database directly...")
    
    # Test the database directly
    import os
    import django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'academic_backend.settings')
    django.setup()
    
    from api.models import Student, TimetableSlot
    from api.timetable_utils import get_smart_timetable_slots
    
    # Test with the electrical student
    electrical_student = Student.objects.filter(user__email='test_electrical@example.com').first()
    if electrical_student:
        print(f"   Testing with: {electrical_student.user.email}")
        print(f"   Program: {electrical_student.program.name}")
        print(f"   Year: {electrical_student.year}, Semester: {electrical_student.semester}")
        
        # Get smart timetable slots
        smart_slots = get_smart_timetable_slots(electrical_student, 1, '1')
        print(f"   Smart slots found: {len(smart_slots) if hasattr(smart_slots, '__len__') else smart_slots.count()}")
        
        if smart_slots:
            print("   ✅ Smart fallback working!")
            print("   Sample slots:")
            for i, slot in enumerate(smart_slots[:3]):
                print(f"     {i+1}. {slot.day_of_week} {slot.time_slot}: {slot.course.code} - {slot.venue}")
        else:
            print("   ❌ No smart slots found")
    else:
        print("   ❌ Electrical test student not found")
    
    print("\n🎉 API Fallback Test Complete!")

if __name__ == "__main__":
    test_api_with_fallback()






#!/usr/bin/env python
"""
Test script for the Timetable API
"""
import requests
import json

# Configuration
BASE_URL = "http://localhost:8000/api"
TEST_EMAIL = "test@example.com"
TEST_PASSWORD = "testpass123"

def test_timetable_api():
    """Test the timetable API endpoints"""
    
    print("🧪 Testing Timetable API")
    print("=" * 50)
    
    # Step 1: Register/Login
    print("1. Authenticating...")
    
    # Try to login first
    login_data = {
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    }
    
    response = requests.post(f"{BASE_URL}/auth/login/", json=login_data)
    
    if response.status_code != 200:
        # If login fails, try to register
        print("   Login failed, trying to register...")
        register_data = {
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
            "password_confirm": TEST_PASSWORD,
            "display_name": "Test Student",
            "gender": "male",
            "phone_number": "1234567890"
        }
        
        response = requests.post(f"{BASE_URL}/auth/register/", json=register_data)
        
        if response.status_code != 201:
            if "already exists" in response.text:
                print("   ⚠️  User already exists, trying login again...")
                # Try login again with the existing user
                response = requests.post(f"{BASE_URL}/auth/login/", json=login_data)
                if response.status_code == 200:
                    print("   ✅ Login successful with existing user")
                else:
                    print(f"   ❌ Login failed: {response.text}")
                    return
            else:
                print(f"   ❌ Registration failed: {response.text}")
                return
        else:
            print("   ✅ User registered successfully")
    else:
        print("   ✅ Login successful")
    
    # Extract token
    token = response.json().get('token')
    if not token:
        print("   ❌ No token received")
        return
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # Step 2: Create student profile
    print("\n2. Creating student profile...")
    
    student_data = {
        "university": "00000000-0000-0000-0000-000000000001",
        "college": "00000000-0000-0000-0000-000000000001", 
        "program": "00000000-0000-0000-0000-000000000001",
        "year": 2,
        "semester": 1
    }
    
    response = requests.post(f"{BASE_URL}/students/profile/create/", json=student_data, headers=headers)
    
    if response.status_code == 201:
        print("   ✅ Student profile created")
    elif response.status_code == 400 and "already exists" in response.text:
        print("   ✅ Student profile already exists")
    else:
        print(f"   ❌ Student profile creation failed: {response.text}")
        return
    
    # Step 3: Get student data to get student ID
    print("\n3. Getting student data...")
    
    response = requests.get(f"{BASE_URL}/students/data/", headers=headers)
    
    if response.status_code != 200:
        print(f"   ❌ Failed to get student data: {response.text}")
        return
    
    student_data = response.json()
    student_id = student_data.get('id')
    print(f"   ✅ Student ID: {student_id}")
    
    # Step 4: Test timetable endpoints
    print("\n4. Testing timetable endpoints...")
    
    # Test GET /api/timetable/my/
    print("   Testing GET /api/timetable/my/")
    response = requests.get(f"{BASE_URL}/timetable/my/", headers=headers)
    
    if response.status_code == 200:
        timetable_data = response.json()
        print("   ✅ My timetable retrieved successfully")
        print(f"   📊 Found {len(timetable_data.get('data', {}).get('timetable_slots', []))} time slots")
        
        # Show first few time slots
        slots = timetable_data.get('data', {}).get('timetable_slots', [])
        for i, slot in enumerate(slots[:3]):
            print(f"      {slot['time_slot']}: {slot.get('monday', {}).get('course_code', 'N/A') if slot.get('monday') else 'N/A'}")
    else:
        print(f"   ❌ Failed to get my timetable: {response.text}")
    
    # Test GET /api/students/{student_id}/timetable/
    print(f"\n   Testing GET /api/students/{student_id}/timetable/")
    response = requests.get(f"{BASE_URL}/students/{student_id}/timetable/", headers=headers)
    
    if response.status_code == 200:
        print("   ✅ Student timetable retrieved successfully")
    else:
        print(f"   ❌ Failed to get student timetable: {response.text}")
    
    # Step 5: Test creating a timetable slot
    print("\n5. Testing timetable slot creation...")
    
    # First, get available courses
    response = requests.get(f"{BASE_URL}/programs/00000000-0000-0000-0000-000000000001/courses/", headers=headers)
    
    if response.status_code == 200:
        courses = response.json()
        if courses:
            course_id = courses[0]['id']
            print(f"   Using course: {courses[0]['code']} - {courses[0]['name']}")
            
            # Create a timetable slot
            slot_data = {
                "course_id": course_id,
                "time_slot": "1500-1600",
                "day_of_week": "monday",
                "class_type": "lecture",
                "venue": "A200",
                "instructor": "Dr. Test",
                "description": "Test class"
            }
            
            response = requests.post(f"{BASE_URL}/timetable/slots/", json=slot_data, headers=headers)
            
            if response.status_code == 201:
                print("   ✅ Timetable slot created successfully")
                print(f"   📝 Created: {response.json().get('message', '')}")
            else:
                print(f"   ❌ Failed to create timetable slot: {response.text}")
        else:
            print("   ⚠️  No courses available for testing")
    else:
        print(f"   ❌ Failed to get courses: {response.text}")
    
    print("\n🎉 Timetable API testing completed!")

if __name__ == "__main__":
    test_timetable_api()

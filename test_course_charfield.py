#!/usr/bin/env python3
"""
Test script to verify course field works as CharField
"""

import requests
import json

# Configuration
BASE_URL = "http://localhost:8000/api"
AUTH_TOKEN = "YOUR_TOKEN_HERE"  # Replace with your actual token

def test_course_formats():
    """Test various course field formats"""
    print("🧪 Testing Course Field as CharField")
    print("=" * 50)
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {AUTH_TOKEN}"
    }
    
    test_cases = [
        {
            "name": "Course Code",
            "data": {
                "course": "CS101",
                "time_slot": "0900-1000",
                "day_of_week": "monday",
                "semester": 1,
                "academic_year": "2024"
            }
        },
        {
            "name": "Course Name",
            "data": {
                "course": "Introduction to Programming",
                "time_slot": "1000-1100",
                "day_of_week": "tuesday",
                "semester": 1,
                "academic_year": "2024"
            }
        },
        {
            "name": "Course UUID (non-existent)",
            "data": {
                "course": "1cdc63a6-0e7d-4239-9b1d-ca6490188f80",
                "time_slot": "1100-1200",
                "day_of_week": "wednesday",
                "semester": 1,
                "academic_year": "2024"
            }
        },
        {
            "name": "Custom Course Identifier",
            "data": {
                "course": "MATH-201",
                "time_slot": "1200-1300",
                "day_of_week": "thursday",
                "semester": 1,
                "academic_year": "2024"
            }
        }
    ]
    
    created_slots = []
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{i}. Testing: {test_case['name']}")
        print(f"   Course: '{test_case['data']['course']}'")
        
        response = requests.post(
            f"{BASE_URL}/timetable-slots/",
            json=test_case['data'],
            headers=headers
        )
        
        if response.status_code in [200, 201]:
            slot_data = response.json()
            print("   ✅ SUCCESS!")
            print(f"   📝 Created slot ID: {slot_data.get('id')}")
            print(f"   📝 Course: {slot_data.get('course')}")
            print(f"   📝 Course Code: {slot_data.get('course_code')}")
            print(f"   📝 Course Name: {slot_data.get('course_name')}")
            created_slots.append(slot_data.get('id'))
        else:
            print("   ❌ FAILED!")
            print(f"   📝 Status: {response.status_code}")
            print(f"   📝 Error: {response.text}")
    
    # Clean up created slots
    print(f"\n🧹 Cleaning up {len(created_slots)} created slots...")
    for slot_id in created_slots:
        if slot_id:
            delete_response = requests.delete(
                f"{BASE_URL}/timetable-slots/{slot_id}/",
                headers=headers
            )
            if delete_response.status_code == 204:
                print(f"   ✅ Deleted slot {slot_id}")
            else:
                print(f"   ❌ Failed to delete slot {slot_id}")

def test_validation_endpoint():
    """Test the validation endpoint with new course format"""
    print("\n🔍 Testing validation endpoint...")
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {AUTH_TOKEN}"
    }
    
    test_data = {
        "course": "CS101",
        "time_slot": "0900-1000",
        "day_of_week": "monday",
        "semester": 1,
        "academic_year": "2024"
    }
    
    response = requests.post(
        f"{BASE_URL}/timetable-slots/debug-validation/",
        json=test_data,
        headers=headers
    )
    
    print(f"Validation Status: {response.status_code}")
    if response.status_code == 200:
        print("✅ Validation passed")
    else:
        print("❌ Validation failed")
        print(f"Error: {response.text}")

if __name__ == "__main__":
    if AUTH_TOKEN == "YOUR_TOKEN_HERE":
        print("❌ Please update AUTH_TOKEN in the script with your actual token")
        exit(1)
    
    test_course_formats()
    test_validation_endpoint()
    
    print("\n" + "=" * 50)
    print("✅ All tests completed!")








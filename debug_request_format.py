#!/usr/bin/env python3
"""
Debug script to test the exact request format for timetable slots
"""

import requests
import json

# Configuration
BASE_URL = "http://localhost:8000/api"
AUTH_TOKEN = "YOUR_TOKEN_HERE"  # Replace with your actual token

def test_request_format():
    """Test the exact request format"""
    print("🔍 Testing Timetable Slot Request Format")
    print("=" * 50)
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {AUTH_TOKEN}"
    }
    
    # Test 1: Minimal required data
    print("\n1️⃣ Testing minimal required data:")
    minimal_data = {
        "course": "550e8400-e29b-41d4-a716-446655440002",  # Replace with actual course UUID
        "time_slot": "0900-1000",
        "day_of_week": "monday",
        "semester": 1,
        "academic_year": "2024"
    }
    
    print("Request data:", json.dumps(minimal_data, indent=2))
    
    response = requests.post(
        f"{BASE_URL}/timetable-slots/",
        json=minimal_data,
        headers=headers
    )
    
    print(f"Status: {response.status_code}")
    if response.status_code in [200, 201]:
        print("✅ SUCCESS!")
        print("Response:", json.dumps(response.json(), indent=2))
    else:
        print("❌ FAILED!")
        print("Error:", response.text)
        try:
            error_data = response.json()
            print("Error details:", json.dumps(error_data, indent=2))
        except:
            pass
    
    # Test 2: Complete data
    print("\n2️⃣ Testing complete data:")
    complete_data = {
        "course": "550e8400-e29b-41d4-a716-446655440002",  # Replace with actual course UUID
        "time_slot": "1000-1100",
        "day_of_week": "tuesday",
        "class_type": "lecture",
        "venue": "Room 101",
        "instructor": "Dr. Smith",
        "description": "Introduction to Programming",
        "semester": 1,
        "academic_year": "2024"
    }
    
    print("Request data:", json.dumps(complete_data, indent=2))
    
    response = requests.post(
        f"{BASE_URL}/timetable-slots/",
        json=complete_data,
        headers=headers
    )
    
    print(f"Status: {response.status_code}")
    if response.status_code in [200, 201]:
        print("✅ SUCCESS!")
        print("Response:", json.dumps(response.json(), indent=2))
    else:
        print("❌ FAILED!")
        print("Error:", response.text)
        try:
            error_data = response.json()
            print("Error details:", json.dumps(error_data, indent=2))
        except:
            pass

def test_validation_endpoint():
    """Test the debug validation endpoint"""
    print("\n3️⃣ Testing validation endpoint:")
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {AUTH_TOKEN}"
    }
    
    test_data = {
        "course": "550e8400-e29b-41d4-a716-446655440002",
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
    print("Validation Response:", json.dumps(response.json(), indent=2))

def show_common_errors():
    """Show common error patterns"""
    print("\n4️⃣ Common Error Patterns:")
    print("=" * 30)
    
    common_errors = [
        {
            "error": "Invalid course UUID format",
            "wrong": '"course": "123"',
            "correct": '"course": "550e8400-e29b-41d4-a716-446655440002"'
        },
        {
            "error": "Invalid time slot format",
            "wrong": '"time_slot": "9:00-10:00"',
            "correct": '"time_slot": "0900-1000"'
        },
        {
            "error": "Invalid day of week",
            "wrong": '"day_of_week": "Monday"',
            "correct": '"day_of_week": "monday"'
        },
        {
            "error": "Invalid semester type",
            "wrong": '"semester": "1"',
            "correct": '"semester": 1'
        },
        {
            "error": "Invalid academic year type",
            "wrong": '"academic_year": 2024',
            "correct": '"academic_year": "2024"'
        }
    ]
    
    for i, error in enumerate(common_errors, 1):
        print(f"\n{i}. {error['error']}:")
        print(f"   ❌ Wrong: {error['wrong']}")
        print(f"   ✅ Correct: {error['correct']}")

if __name__ == "__main__":
    if AUTH_TOKEN == "YOUR_TOKEN_HERE":
        print("❌ Please update AUTH_TOKEN in the script with your actual token")
        print("You can get a token by logging in via the API")
        exit(1)
    
    test_request_format()
    test_validation_endpoint()
    show_common_errors()
    
    print("\n" + "=" * 50)
    print("✅ Debug tests completed!")








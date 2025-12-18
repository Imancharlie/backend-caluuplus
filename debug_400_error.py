#!/usr/bin/env python3
"""
Debug script to identify the exact cause of 400 errors
"""

import requests
import json

# Configuration
BASE_URL = "http://localhost:8000/api"
AUTH_TOKEN = "YOUR_TOKEN_HERE"  # Replace with your actual token

def test_debug_endpoints():
    """Test the debug endpoints to see what's happening"""
    print("🔍 Debugging 400 Error")
    print("=" * 50)
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {AUTH_TOKEN}"
    }
    
    # Test data that might be causing the issue
    test_data = {
        "course": "CS101",
        "time_slot": "0900-1000",
        "day_of_week": "monday",
        "semester": 1,
        "academic_year": "2024"
    }
    
    print("1️⃣ Testing debug-request endpoint:")
    print("Sending data:", json.dumps(test_data, indent=2))
    
    response = requests.post(
        f"{BASE_URL}/timetable-slots/debug-request/",
        json=test_data,
        headers=headers
    )
    
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        print("✅ Request data received successfully")
        print("Response:", json.dumps(response.json(), indent=2))
    else:
        print("❌ Request failed")
        print("Error:", response.text)
    
    print("\n2️⃣ Testing debug-validation endpoint:")
    
    response = requests.post(
        f"{BASE_URL}/timetable-slots/debug-validation/",
        json=test_data,
        headers=headers
    )
    
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        print("✅ Validation passed")
        print("Response:", json.dumps(response.json(), indent=2))
    else:
        print("❌ Validation failed")
        print("Error:", response.text)
    
    print("\n3️⃣ Testing actual create endpoint:")
    
    response = requests.post(
        f"{BASE_URL}/timetable-slots/",
        json=test_data,
        headers=headers
    )
    
    print(f"Status: {response.status_code}")
    if response.status_code in [200, 201]:
        print("✅ Create successful")
        print("Response:", json.dumps(response.json(), indent=2))
    else:
        print("❌ Create failed")
        print("Error:", response.text)
        try:
            error_data = response.json()
            print("Error details:", json.dumps(error_data, indent=2))
        except:
            pass

def test_different_data_formats():
    """Test different data formats to identify the issue"""
    print("\n4️⃣ Testing different data formats:")
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {AUTH_TOKEN}"
    }
    
    test_cases = [
        {
            "name": "Minimal data",
            "data": {
                "course": "CS101",
                "time_slot": "0900-1000",
                "day_of_week": "monday",
                "semester": 1,
                "academic_year": "2024"
            }
        },
        {
            "name": "With optional fields",
            "data": {
                "course": "CS101",
                "time_slot": "1000-1100",
                "day_of_week": "tuesday",
                "class_type": "lecture",
                "venue": "Room 101",
                "instructor": "Dr. Smith",
                "description": "Test class",
                "semester": 1,
                "academic_year": "2024"
            }
        },
        {
            "name": "String semester (wrong type)",
            "data": {
                "course": "CS101",
                "time_slot": "1100-1200",
                "day_of_week": "wednesday",
                "semester": "1",  # String instead of integer
                "academic_year": "2024"
            }
        },
        {
            "name": "Integer academic_year (wrong type)",
            "data": {
                "course": "CS101",
                "time_slot": "1200-1300",
                "day_of_week": "thursday",
                "semester": 1,
                "academic_year": 2024  # Integer instead of string
            }
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{i}. {test_case['name']}:")
        print("Data:", json.dumps(test_case['data'], indent=2))
        
        response = requests.post(
            f"{BASE_URL}/timetable-slots/debug-validation/",
            json=test_case['data'],
            headers=headers
        )
        
        if response.status_code == 200:
            print("✅ Validation passed")
        else:
            print("❌ Validation failed")
            try:
                error_data = response.json()
                print("Errors:", json.dumps(error_data.get('errors', {}), indent=2))
            except:
                print("Error:", response.text)

def test_common_issues():
    """Test common issues that cause 400 errors"""
    print("\n5️⃣ Testing common issues:")
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {AUTH_TOKEN}"
    }
    
    common_issues = [
        {
            "name": "Missing required field",
            "data": {
                "course": "CS101",
                "time_slot": "0900-1000",
                "day_of_week": "monday",
                # Missing semester and academic_year
            }
        },
        {
            "name": "Invalid time format",
            "data": {
                "course": "CS101",
                "time_slot": "9:00-10:00",  # Wrong format
                "day_of_week": "monday",
                "semester": 1,
                "academic_year": "2024"
            }
        },
        {
            "name": "Invalid day format",
            "data": {
                "course": "CS101",
                "time_slot": "0900-1000",
                "day_of_week": "Monday",  # Wrong case
                "semester": 1,
                "academic_year": "2024"
            }
        },
        {
            "name": "Empty course",
            "data": {
                "course": "",  # Empty course
                "time_slot": "0900-1000",
                "day_of_week": "monday",
                "semester": 1,
                "academic_year": "2024"
            }
        }
    ]
    
    for i, issue in enumerate(common_issues, 1):
        print(f"\n{i}. {issue['name']}:")
        print("Data:", json.dumps(issue['data'], indent=2))
        
        response = requests.post(
            f"{BASE_URL}/timetable-slots/debug-validation/",
            json=issue['data'],
            headers=headers
        )
        
        if response.status_code == 200:
            print("✅ Validation passed (unexpected)")
        else:
            print("❌ Validation failed (expected)")
            try:
                error_data = response.json()
                print("Errors:", json.dumps(error_data.get('errors', {}), indent=2))
            except:
                print("Error:", response.text)

if __name__ == "__main__":
    if AUTH_TOKEN == "YOUR_TOKEN_HERE":
        print("❌ Please update AUTH_TOKEN in the script with your actual token")
        exit(1)
    
    test_debug_endpoints()
    test_different_data_formats()
    test_common_issues()
    
    print("\n" + "=" * 50)
    print("✅ Debug tests completed!")
    print("\nTo debug your specific request:")
    print("1. Send your exact data to /api/timetable-slots/debug-request/")
    print("2. Check the response to see what's being received")
    print("3. Send the same data to /api/timetable-slots/debug-validation/")
    print("4. Check the validation errors")








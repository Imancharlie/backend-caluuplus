#!/usr/bin/env python3
"""
Debug script to test timetable slot update functionality
This script will help identify the exact cause of the 500 error
"""

import requests
import json

# Configuration
BASE_URL = "http://localhost:8000/api"
AUTH_TOKEN = "YOUR_TOKEN_HERE"  # Replace with actual token

def test_debug_validation():
    """Test the debug validation endpoint"""
    print("🔍 Testing debug validation endpoint...")
    
    # Test data that might be causing the issue
    test_data = {
        "course": "550e8400-e29b-41d4-a716-446655440002",  # Replace with actual course ID
        "time_slot": "0900-1000",
        "day_of_week": "monday",
        "class_type": "lecture",
        "venue": "Room 101",
        "instructor": "Dr. Smith",
        "description": "Test class",
        "semester": 1,
        "academic_year": "2024"
    }
    
    headers = {
        "Authorization": f"Bearer {AUTH_TOKEN}",
        "Content-Type": "application/json"
    }
    
    response = requests.post(
        f"{BASE_URL}/timetable-slots/debug-validation/",
        json=test_data,
        headers=headers
    )
    
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text}")
    
    if response.status_code == 200:
        data = response.json()
        print("✅ Validation passed")
        print(f"Validated data: {json.dumps(data, indent=2)}")
    else:
        print("❌ Validation failed")
        try:
            error_data = response.json()
            print(f"Error details: {json.dumps(error_data, indent=2)}")
        except:
            print(f"Raw error: {response.text}")

def test_create_and_update():
    """Test creating a slot and then updating it"""
    print("\n🧪 Testing create and update flow...")
    
    headers = {
        "Authorization": f"Bearer {AUTH_TOKEN}",
        "Content-Type": "application/json"
    }
    
    # First, create a slot
    create_data = {
        "course": "550e8400-e29b-41d4-a716-446655440002",  # Replace with actual course ID
        "time_slot": "0900-1000",
        "day_of_week": "monday",
        "class_type": "lecture",
        "venue": "Room 101",
        "instructor": "Dr. Smith",
        "description": "Test class",
        "semester": 1,
        "academic_year": "2024"
    }
    
    print("Creating timetable slot...")
    create_response = requests.post(
        f"{BASE_URL}/timetable-slots/",
        json=create_data,
        headers=headers
    )
    
    print(f"Create Status: {create_response.status_code}")
    if create_response.status_code not in [200, 201]:
        print(f"Create Error: {create_response.text}")
        return
    
    slot_data = create_response.json()
    slot_id = slot_data.get('id')
    print(f"Created slot with ID: {slot_id}")
    
    # Now try to update it
    update_data = {
        "venue": "Room 202",
        "instructor": "Dr. Johnson"
    }
    
    print("Updating timetable slot...")
    update_response = requests.patch(
        f"{BASE_URL}/timetable-slots/{slot_id}/",
        json=update_data,
        headers=headers
    )
    
    print(f"Update Status: {update_response.status_code}")
    if update_response.status_code == 200:
        print("✅ Update successful")
        print(f"Updated data: {update_response.text}")
    else:
        print("❌ Update failed")
        print(f"Error: {update_response.text}")
        
        # Try to get more details about the error
        try:
            error_data = update_response.json()
            print(f"Error details: {json.dumps(error_data, indent=2)}")
        except:
            print(f"Raw error: {update_response.text}")

def test_different_time_formats():
    """Test different time slot formats to identify the issue"""
    print("\n🕐 Testing different time slot formats...")
    
    headers = {
        "Authorization": f"Bearer {AUTH_TOKEN}",
        "Content-Type": "application/json"
    }
    
    time_formats = [
        "0900-1000",  # Standard format
        "9:00-10:00",  # With colons
        "09:00-10:00",  # With colons and leading zero
        "9-10",  # Short format
        "09-10",  # Short format with leading zero
        "900-1000",  # Without leading zero
        "9:00-10:00 AM",  # With AM/PM
    ]
    
    for time_format in time_formats:
        print(f"\nTesting time format: '{time_format}'")
        
        test_data = {
            "course": "550e8400-e29b-41d4-a716-446655440002",
            "time_slot": time_format,
            "day_of_week": "monday",
            "class_type": "lecture",
            "venue": "Room 101",
            "instructor": "Dr. Smith",
            "description": "Test class",
            "semester": 1,
            "academic_year": "2024"
        }
        
        response = requests.post(
            f"{BASE_URL}/timetable-slots/debug-validation/",
            json=test_data,
            headers=headers
        )
        
        if response.status_code == 200:
            print(f"  ✅ Valid: {time_format}")
        else:
            print(f"  ❌ Invalid: {time_format}")
            try:
                error_data = response.json()
                print(f"    Error: {error_data.get('errors', {}).get('time_slot', ['Unknown error'])}")
            except:
                print(f"    Error: {response.text}")

if __name__ == "__main__":
    print("🚀 Starting Timetable Debug Tests")
    print("=" * 50)
    
    if AUTH_TOKEN == "YOUR_TOKEN_HERE":
        print("❌ Please update AUTH_TOKEN in the script with your actual token")
        print("You can get a token by logging in via the API")
        exit(1)
    
    test_debug_validation()
    test_create_and_update()
    test_different_time_formats()
    
    print("\n" + "=" * 50)
    print("✅ Debug tests completed!")








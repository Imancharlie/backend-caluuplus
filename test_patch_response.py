#!/usr/bin/env python3
"""
Test script to verify PATCH response format for timetable slots
"""
import requests
import json

# Configuration
BASE_URL = "http://localhost:8000"
API_BASE = f"{BASE_URL}/api"

def test_patch_response():
    """Test PATCH response format"""
    
    # You'll need to replace these with actual values
    auth_token = "YOUR_AUTH_TOKEN_HERE"
    slot_id = "1cdc63a6-0e7d-4239-9b1d-ca6490188f80"  # Replace with actual slot ID
    
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }
    
    # Test data for PATCH
    patch_data = {
        "course": "CS101",
        "time_slot": "0900-1000",
        "day_of_week": "monday",
        "class_type": "lecture",
        "venue": "Room 101",
        "instructor": "Dr. Smith",
        "description": "Updated lecture",
        "semester": 1,
        "academic_year": "2024"
    }
    
    print("Testing PATCH response format...")
    print(f"URL: {API_BASE}/timetable-slots/{slot_id}/")
    print(f"Data: {json.dumps(patch_data, indent=2)}")
    print()
    
    try:
        response = requests.patch(
            f"{API_BASE}/timetable-slots/{slot_id}/",
            headers=headers,
            json=patch_data
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        print()
        
        if response.status_code == 200:
            response_data = response.json()
            print("✅ PATCH Response (200):")
            print(json.dumps(response_data, indent=2))
            
            # Check if response has expected format
            if 'success' in response_data and 'slot' in response_data:
                print("\n✅ Response format is correct!")
                print(f"Success: {response_data['success']}")
                print(f"Message: {response_data['message']}")
                print(f"Slot ID: {response_data['slot'].get('id')}")
                print(f"Course: {response_data['slot'].get('course')}")
                print(f"Time Slot: {response_data['slot'].get('time_slot')}")
                print(f"Day: {response_data['slot'].get('day_of_week')}")
            else:
                print("\n❌ Response format is unexpected!")
                print("Expected: {success, message, slot}")
                print(f"Got: {list(response_data.keys())}")
                
        else:
            print(f"❌ PATCH failed with status {response.status_code}")
            print("Response:")
            print(response.text)
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Request failed: {e}")
    except json.JSONDecodeError as e:
        print(f"❌ JSON decode failed: {e}")
        print("Raw response:")
        print(response.text)

if __name__ == "__main__":
    print("Timetable Slot PATCH Response Test")
    print("=" * 40)
    print()
    print("Before running this test:")
    print("1. Start your Django server: python manage.py runserver")
    print("2. Replace YOUR_AUTH_TOKEN_HERE with a valid JWT token")
    print("3. Replace the slot_id with an actual timetable slot ID")
    print("4. Run: python test_patch_response.py")
    print()
    test_patch_response()







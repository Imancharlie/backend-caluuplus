#!/usr/bin/env python3
"""
Test script to verify instructor field is completely optional
"""

import requests
import json

# Configuration
BASE_URL = "http://localhost:8000/api"
AUTH_TOKEN = "YOUR_TOKEN_HERE"  # Replace with actual token

def test_instructor_optional():
    """Test that instructor field works with various values"""
    print("🧪 Testing instructor field optionality...")
    
    headers = {
        "Authorization": f"Bearer {AUTH_TOKEN}",
        "Content-Type": "application/json"
    }
    
    test_cases = [
        {
            "name": "No instructor field",
            "data": {
                "course": "550e8400-e29b-41d4-a716-446655440002",
                "time_slot": "0900-1000",
                "day_of_week": "monday",
                "class_type": "lecture",
                "venue": "Room 101",
                "description": "Test class",
                "semester": 1,
                "academic_year": "2024"
            }
        },
        {
            "name": "Empty instructor string",
            "data": {
                "course": "550e8400-e29b-41d4-a716-446655440002",
                "time_slot": "1000-1100",
                "day_of_week": "tuesday",
                "class_type": "lecture",
                "venue": "Room 102",
                "instructor": "",
                "description": "Test class",
                "semester": 1,
                "academic_year": "2024"
            }
        },
        {
            "name": "Whitespace only instructor",
            "data": {
                "course": "550e8400-e29b-41d4-a716-446655440002",
                "time_slot": "1100-1200",
                "day_of_week": "wednesday",
                "class_type": "lecture",
                "venue": "Room 103",
                "instructor": "   ",
                "description": "Test class",
                "semester": 1,
                "academic_year": "2024"
            }
        },
        {
            "name": "Null instructor",
            "data": {
                "course": "550e8400-e29b-41d4-a716-446655440002",
                "time_slot": "1200-1300",
                "day_of_week": "thursday",
                "class_type": "lecture",
                "venue": "Room 104",
                "instructor": None,
                "description": "Test class",
                "semester": 1,
                "academic_year": "2024"
            }
        },
        {
            "name": "Valid instructor",
            "data": {
                "course": "550e8400-e29b-41d4-a716-446655440002",
                "time_slot": "1300-1400",
                "day_of_week": "friday",
                "class_type": "lecture",
                "venue": "Room 105",
                "instructor": "Dr. Smith",
                "description": "Test class",
                "semester": 1,
                "academic_year": "2024"
            }
        }
    ]
    
    for i, test_case in enumerate(test_cases):
        print(f"\n{i+1}. Testing: {test_case['name']}")
        
        # Test validation first
        validation_response = requests.post(
            f"{BASE_URL}/timetable-slots/debug-validation/",
            json=test_case['data'],
            headers=headers
        )
        
        if validation_response.status_code == 200:
            print(f"  ✅ Validation passed")
            
            # Try to create the slot
            create_response = requests.post(
                f"{BASE_URL}/timetable-slots/",
                json=test_case['data'],
                headers=headers
            )
            
            if create_response.status_code in [200, 201]:
                slot_data = create_response.json()
                instructor_value = slot_data.get('instructor')
                instructor_name = slot_data.get('instructor_name')
                
                print(f"  ✅ Creation successful")
                print(f"  📝 Instructor field: '{instructor_value}'")
                print(f"  📝 Instructor name: '{instructor_name}'")
                
                # Clean up - delete the created slot
                slot_id = slot_data.get('id')
                if slot_id:
                    delete_response = requests.delete(
                        f"{BASE_URL}/timetable-slots/{slot_id}/",
                        headers=headers
                    )
                    if delete_response.status_code == 204:
                        print(f"  🗑️  Cleaned up slot")
                    else:
                        print(f"  ⚠️  Failed to clean up slot")
            else:
                print(f"  ❌ Creation failed: {create_response.status_code}")
                print(f"  📝 Error: {create_response.text}")
        else:
            print(f"  ❌ Validation failed: {validation_response.status_code}")
            try:
                error_data = validation_response.json()
                print(f"  📝 Error: {error_data.get('errors', {})}")
            except:
                print(f"  📝 Error: {validation_response.text}")

def test_minimal_data():
    """Test with absolutely minimal data"""
    print("\n🧪 Testing with minimal required data...")
    
    headers = {
        "Authorization": f"Bearer {AUTH_TOKEN}",
        "Content-Type": "application/json"
    }
    
    minimal_data = {
        "course": "550e8400-e29b-41d4-a716-446655440002",
        "time_slot": "1400-1500",
        "day_of_week": "monday",
        "semester": 1,
        "academic_year": "2024"
    }
    
    print("Minimal data:", json.dumps(minimal_data, indent=2))
    
    response = requests.post(
        f"{BASE_URL}/timetable-slots/",
        json=minimal_data,
        headers=headers
    )
    
    if response.status_code in [200, 201]:
        slot_data = response.json()
        print("✅ Minimal data creation successful")
        print(f"📝 Created slot: {json.dumps(slot_data, indent=2)}")
        
        # Clean up
        slot_id = slot_data.get('id')
        if slot_id:
            delete_response = requests.delete(
                f"{BASE_URL}/timetable-slots/{slot_id}/",
                headers=headers
            )
            if delete_response.status_code == 204:
                print("🗑️  Cleaned up slot")
    else:
        print(f"❌ Minimal data creation failed: {response.status_code}")
        print(f"📝 Error: {response.text}")

if __name__ == "__main__":
    print("🚀 Testing Instructor Field Optionality")
    print("=" * 50)
    
    if AUTH_TOKEN == "YOUR_TOKEN_HERE":
        print("❌ Please update AUTH_TOKEN in the script with your actual token")
        exit(1)
    
    test_instructor_optional()
    test_minimal_data()
    
    print("\n" + "=" * 50)
    print("✅ All tests completed!")








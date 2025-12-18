#!/usr/bin/env python3
"""
Test script for timetable slot PATCH method with flexible course handling
Tests updating timetable slots with temporary course IDs
"""

import requests
import json

# Base URL
BASE_URL = "http://127.0.0.1:8000"

def test_timetable_patch():
    """Test timetable slot PATCH with temporary course IDs"""
    
    print("Testing Timetable Slot PATCH with Flexible Course Handling")
    print("=" * 70)
    
    # First, create a timetable slot
    print("Step 1: Creating initial timetable slot...")
    initial_data = {
        "course": "temp-1759580697450",  # This should exist in StudentCourse
        "day_of_week": "monday",
        "time_slot": "0800-1000",
        "venue": "Room 101",
        "instructor": "Dr. Smith"
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/timetable-slots/",
            json=initial_data,
            headers={'Content-Type': 'application/json'}
        )
        
        if response.status_code == 201:
            slot_data = response.json()
            slot_id = slot_data['id']
            print(f"SUCCESS: Created slot: {slot_id}")
            print(f"   Course: {slot_data['course_name']} ({slot_data['course_code']})")
        else:
            print(f"FAILED: Failed to create initial slot: {response.status_code}")
            print(f"Response: {response.text}")
            return
    except Exception as e:
        print(f"ERROR: Exception creating slot: {str(e)}")
        return
    
    # Test different PATCH scenarios
    test_cases = [
        {
            "name": "Change to another temp course ID",
            "patch_data": {
                "course": "temp-1759583438603"  # Different temp ID
            },
            "expected_name": "Nens",
            "expected_code": "Sjjs"
        },
        {
            "name": "Change to EE132 course",
            "patch_data": {
                "course": "temp-1759583987855"  # EE132 course
            },
            "expected_name": "electronics",
            "expected_code": "EE132"
        },
        {
            "name": "Change to custom course with code and name",
            "patch_data": {
                "course": "custom-course-123",
                "course_name": "Custom Advanced Course",
                "course_code": "CAC101"
            },
            "expected_name": "Custom Advanced Course",
            "expected_code": "CAC101"
        },
        {
            "name": "Change time and venue only (no course change)",
            "patch_data": {
                "time_slot": "1000-1200",
                "venue": "Room 201",
                "instructor": "Dr. Johnson"
            },
            "expected_name": "Custom Advanced Course",  # Should remain the same
            "expected_code": "CAC101"
        }
    ]
    
    # Test each PATCH scenario
    for i, test_case in enumerate(test_cases, 1):
        print(f"\nStep {i+1}: {test_case['name']}")
        print("-" * 50)
        
        try:
            response = requests.patch(
                f"{BASE_URL}/api/timetable-slots/{slot_id}/",
                json=test_case['patch_data'],
                headers={'Content-Type': 'application/json'}
            )
            
            print(f"Status Code: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print("SUCCESS: PATCH SUCCESS!")
                print(f"Updated Slot ID: {data.get('id')}")
                print(f"Course Name: {data.get('course_name')}")
                print(f"Course Code: {data.get('course_code')}")
                print(f"Time: {data.get('time_slot')}")
                print(f"Venue: {data.get('venue')}")
                print(f"Instructor: {data.get('instructor')}")
                
                # Check if the course name and code match expected values
                if (data.get('course_name') == test_case['expected_name'] and 
                    data.get('course_code') == test_case['expected_code']):
                    print("SUCCESS: Course data matches expected values!")
                else:
                    print(f"WARNING: Course data mismatch:")
                    print(f"   Expected: {test_case['expected_name']} ({test_case['expected_code']})")
                    print(f"   Got: {data.get('course_name')} ({data.get('course_code')})")
            else:
                print("FAILED: PATCH FAILED!")
                try:
                    error_data = response.json()
                    print(f"Error: {error_data.get('error', 'Unknown error')}")
                    if 'received_data' in error_data:
                        print(f"Received Data: {error_data['received_data']}")
                except:
                    print(f"Response: {response.text}")
                    
        except Exception as e:
            print(f"ERROR: EXCEPTION: {str(e)}")
    
    # Final verification - get the slot to see final state
    print(f"\nFinal Step: Verifying final slot state")
    print("-" * 50)
    
    try:
        response = requests.get(f"{BASE_URL}/api/timetable-slots/{slot_id}/")
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("SUCCESS: FINAL STATE:")
            print(f"   Course: {data.get('course_name')} ({data.get('course_code')})")
            print(f"   Time: {data.get('time_slot')} on {data.get('day_of_week')}")
            print(f"   Venue: {data.get('venue')}")
            print(f"   Instructor: {data.get('instructor')}")
        else:
            print("FAILED: Failed to get final state")
            print(f"Response: {response.text}")
    except Exception as e:
        print(f"ERROR: EXCEPTION: {str(e)}")
    
    print("\n" + "=" * 70)
    print("PATCH Testing Complete!")

if __name__ == "__main__":
    test_timetable_patch()

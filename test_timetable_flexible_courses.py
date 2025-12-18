#!/usr/bin/env python3
"""
Test script for flexible timetable course handling
Tests various scenarios for course creation
"""

import requests
import json
import uuid

# Base URL
BASE_URL = "http://127.0.0.1:8000"

def test_timetable_slot_creation():
    """Test timetable slot creation with different course scenarios"""
    
    print("🧪 Testing Flexible Timetable Course Creation")
    print("=" * 50)
    
    # Test scenarios
    test_cases = [
        {
            "name": "Temporary Course ID (Frontend Issue)",
            "data": {
                "course": "temp-1759580697450",
                "course_name": "Custom Course",
                "day_of_week": "monday",
                "time_slot": "0800-1000",
                "venue": "Room 101",
                "instructor": "Dr. Smith"
            }
        },
        {
            "name": "Course Code Only",
            "data": {
                "course_code": "CS101",
                "course_name": "Introduction to Computer Science",
                "day_of_week": "tuesday",
                "time_slot": "1000-1200",
                "venue": "Room 102",
                "instructor": "Dr. Johnson"
            }
        },
        {
            "name": "Course Name Only",
            "data": {
                "course_name": "Advanced Mathematics",
                "day_of_week": "wednesday",
                "time_slot": "1400-1600",
                "venue": "Room 103",
                "instructor": "Dr. Brown"
            }
        },
        {
            "name": "Invalid UUID Format",
            "data": {
                "course": "invalid-uuid-format",
                "course_name": "Physics Lab",
                "day_of_week": "thursday",
                "time_slot": "1600-1800",
                "venue": "Lab 1",
                "instructor": "Dr. Wilson"
            }
        }
    ]
    
    # Test each scenario
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n📋 Test Case {i}: {test_case['name']}")
        print("-" * 30)
        
        try:
            # Make the request
            response = requests.post(
                f"{BASE_URL}/api/timetable-slots/",
                json=test_case['data'],
                headers={'Content-Type': 'application/json'}
            )
            
            print(f"Status Code: {response.status_code}")
            
            if response.status_code == 201:
                data = response.json()
                print("✅ SUCCESS!")
                print(f"Created Slot ID: {data.get('id')}")
                print(f"Course: {data.get('course')}")
                print(f"Course Name: {data.get('course_name')}")
                print(f"Course Code: {data.get('course_code')}")
                print(f"Time: {data.get('time_slot')} on {data.get('day_of_week')}")
                print(f"Venue: {data.get('venue')}")
                print(f"Instructor: {data.get('instructor')}")
            else:
                print("❌ FAILED!")
                try:
                    error_data = response.json()
                    print(f"Error: {error_data.get('error', 'Unknown error')}")
                    if 'received_data' in error_data:
                        print(f"Received Data: {error_data['received_data']}")
                except:
                    print(f"Response: {response.text}")
                    
        except requests.exceptions.ConnectionError:
            print("❌ CONNECTION ERROR: Server not running")
            print("Please start the server with: python manage.py runserver")
            break
        except Exception as e:
            print(f"❌ EXCEPTION: {str(e)}")
    
    print("\n" + "=" * 50)
    print("🏁 Testing Complete!")

def test_bulk_creation():
    """Test bulk timetable slot creation"""
    
    print("\n🧪 Testing Bulk Timetable Slot Creation")
    print("=" * 50)
    
    bulk_data = {
        "slots": [
            {
                "course": "temp-bulk-1",
                "course_name": "Bulk Course 1",
                "day_of_week": "monday",
                "time_slot": "0800-1000",
                "venue": "Room 201"
            },
            {
                "course_code": "BULK101",
                "course_name": "Bulk Course 2",
                "day_of_week": "tuesday",
                "time_slot": "1000-1200",
                "venue": "Room 202"
            },
            {
                "course_name": "Bulk Course 3",
                "day_of_week": "wednesday",
                "time_slot": "1400-1600",
                "venue": "Room 203"
            }
        ]
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/timetable-slots/bulk-create/",
            json=bulk_data,
            headers={'Content-Type': 'application/json'}
        )
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 201:
            data = response.json()
            print("✅ BULK CREATION SUCCESS!")
            print(f"Created {len(data.get('created_slots', []))} slots")
            
            for i, slot in enumerate(data.get('created_slots', []), 1):
                print(f"  Slot {i}: {slot.get('course_name')} - {slot.get('time_slot')}")
        else:
            print("❌ BULK CREATION FAILED!")
            try:
                error_data = response.json()
                print(f"Error: {error_data.get('error', 'Unknown error')}")
                if 'errors' in error_data:
                    print("Errors:")
                    for error in error_data['errors']:
                        print(f"  - {error}")
            except:
                print(f"Response: {response.text}")
                
    except requests.exceptions.ConnectionError:
        print("❌ CONNECTION ERROR: Server not running")
    except Exception as e:
        print(f"❌ EXCEPTION: {str(e)}")

if __name__ == "__main__":
    test_timetable_slot_creation()
    test_bulk_creation()




















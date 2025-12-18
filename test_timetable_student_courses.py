#!/usr/bin/env python3
"""
Test script for timetable slots using StudentCourse data
Tests that timetable slots correctly read from StudentCourse JSON
"""

import requests
import json

# Base URL
BASE_URL = "http://127.0.0.1:8000"

def test_timetable_with_student_courses():
    """Test timetable slot creation and retrieval with StudentCourse data"""
    
    print("🧪 Testing Timetable with StudentCourse Integration")
    print("=" * 60)
    
    # Test data that matches the StudentCourse format
    test_cases = [
        {
            "name": "Course from StudentCourse (temp ID)",
            "data": {
                "course": "temp-1759580697450",  # This should exist in StudentCourse
                "day_of_week": "monday",
                "time_slot": "0800-1000",
                "venue": "Room 101",
                "instructor": "Dr. Smith"
            },
            "expected_name": "qrwr",  # From your StudentCourse data
            "expected_code": "qrqr"
        },
        {
            "name": "Course from StudentCourse (another temp ID)",
            "data": {
                "course": "temp-1759583438603",  # This should exist in StudentCourse
                "day_of_week": "tuesday",
                "time_slot": "1000-1200",
                "venue": "Room 102",
                "instructor": "Dr. Johnson"
            },
            "expected_name": "Nens",  # From your StudentCourse data
            "expected_code": "Sjjs"
        },
        {
            "name": "Course from StudentCourse (EE132)",
            "data": {
                "course": "temp-1759583987855",  # This should exist in StudentCourse
                "day_of_week": "wednesday",
                "time_slot": "1400-1600",
                "venue": "Room 103",
                "instructor": "Dr. Brown"
            },
            "expected_name": "electronics",  # From your StudentCourse data
            "expected_code": "EE132"
        }
    ]
    
    created_slots = []
    
    # Test each scenario
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n📋 Test Case {i}: {test_case['name']}")
        print("-" * 40)
        
        try:
            # Create timetable slot
            print("Creating timetable slot...")
            response = requests.post(
                f"{BASE_URL}/api/timetable-slots/",
                json=test_case['data'],
                headers={'Content-Type': 'application/json'}
            )
            
            print(f"Status Code: {response.status_code}")
            
            if response.status_code == 201:
                data = response.json()
                print("✅ CREATION SUCCESS!")
                print(f"Created Slot ID: {data.get('id')}")
                print(f"Course Name: {data.get('course_name')}")
                print(f"Course Code: {data.get('course_code')}")
                
                # Check if the course name and code match expected values
                if (data.get('course_name') == test_case['expected_name'] and 
                    data.get('course_code') == test_case['expected_code']):
                    print("✅ Course data matches StudentCourse!")
                else:
                    print(f"⚠️  Course data mismatch:")
                    print(f"   Expected: {test_case['expected_name']} ({test_case['expected_code']})")
                    print(f"   Got: {data.get('course_name')} ({data.get('course_code')})")
                
                created_slots.append(data.get('id'))
            else:
                print("❌ CREATION FAILED!")
                try:
                    error_data = response.json()
                    print(f"Error: {error_data.get('error', 'Unknown error')}")
                except:
                    print(f"Response: {response.text}")
                    
        except requests.exceptions.ConnectionError:
            print("❌ CONNECTION ERROR: Server not running")
            print("Please start the server with: python manage.py runserver")
            break
        except Exception as e:
            print(f"❌ EXCEPTION: {str(e)}")
    
    # Test retrieval
    if created_slots:
        print(f"\n📋 Testing Timetable Retrieval")
        print("-" * 40)
        
        try:
            response = requests.get(f"{BASE_URL}/api/timetable-slots/")
            print(f"Status Code: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print("✅ RETRIEVAL SUCCESS!")
                print(f"Found {len(data)} timetable slots")
                
                for slot in data:
                    print(f"  - {slot.get('course_name')} ({slot.get('course_code')}) - {slot.get('time_slot')} {slot.get('day_of_week')}")
            else:
                print("❌ RETRIEVAL FAILED!")
                print(f"Response: {response.text}")
                
        except Exception as e:
            print(f"❌ EXCEPTION: {str(e)}")
    
    print("\n" + "=" * 60)
    print("🏁 Testing Complete!")

if __name__ == "__main__":
    test_timetable_with_student_courses()




















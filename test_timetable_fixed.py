#!/usr/bin/env python
"""
Test the fixed timetable API
"""
import requests
import json

BASE_URL = "http://localhost:8000/api"

def test_timetable_api():
    print("🧪 Testing Fixed Timetable API")
    print("=" * 50)
    
    # Test the debug endpoint first
    print("1. Testing debug endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/timetable/debug/")
        if response.status_code == 200:
            data = response.json()
            print("   ✅ Debug endpoint working")
            print(f"   📊 Student: {data['student_info']['email']}")
            print(f"   📊 Current semester slots: {data['timetable_stats']['current_semester_slots']}")
            if data['sample_slots']:
                print(f"   📝 Sample slot: {data['sample_slots'][0]['day']} {data['sample_slots'][0]['time']}")
        else:
            print(f"   ❌ Debug endpoint failed: {response.status_code}")
    except Exception as e:
        print(f"   ❌ Debug endpoint error: {e}")
    
    # Test the main timetable endpoint
    print("\n2. Testing main timetable endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/timetable/my/")
        if response.status_code == 200:
            data = response.json()
            print("   ✅ Main timetable endpoint working")
            print(f"   📊 Success: {data['success']}")
            print(f"   📊 Time slots: {len(data['data']['timetable_slots'])}")
            
            # Check if any slots have actual class data
            slots_with_classes = 0
            for slot in data['data']['timetable_slots']:
                for day in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday']:
                    if slot[day] is not None:
                        slots_with_classes += 1
                        print(f"   📝 Found class: {day} {slot['time_slot']} - {slot[day]['course_code']}")
                        break
            
            print(f"   📊 Slots with classes: {slots_with_classes}")
            
            if 'debug' in data:
                print(f"   🔍 Debug info: {data['debug']['total_slots_in_db']} slots in DB")
        else:
            print(f"   ❌ Main timetable endpoint failed: {response.status_code}")
            print(f"   📝 Response: {response.text[:200]}")
    except Exception as e:
        print(f"   ❌ Main timetable endpoint error: {e}")

if __name__ == "__main__":
    test_timetable_api()






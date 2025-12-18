#!/usr/bin/env python3
"""
Test script for Timetable Slot CRUD operations
This script tests all the CRUD endpoints for timetable slots
"""

import requests
import json
import sys

# Configuration
BASE_URL = "http://localhost:8000/api"
AUTH_TOKEN = None

def get_auth_headers():
    """Get authentication headers"""
    if not AUTH_TOKEN:
        return {}
    return {"Authorization": f"Bearer {AUTH_TOKEN}"}

def test_login():
    """Test login and get auth token"""
    global AUTH_TOKEN
    
    login_data = {
        "email": "test@example.com",  # Replace with actual test user
        "password": "testpassword123"
    }
    
    response = requests.post(f"{BASE_URL}/auth/login/", json=login_data)
    
    if response.status_code == 200:
        data = response.json()
        AUTH_TOKEN = data.get('token')
        print("✅ Login successful")
        return True
    else:
        print(f"❌ Login failed: {response.status_code} - {response.text}")
        return False

def test_create_timetable_slot():
    """Test creating a timetable slot"""
    print("\n🧪 Testing CREATE timetable slot...")
    
    slot_data = {
        "course": "550e8400-e29b-41d4-a716-446655440000",  # Replace with actual course ID
        "time_slot": "0900-1000",
        "day_of_week": "monday",
        "class_type": "lecture",
        "venue": "Room 101",
        "instructor": "Dr. Smith",
        "description": "Introduction to Programming",
        "semester": 1,
        "academic_year": "2024"
    }
    
    response = requests.post(
        f"{BASE_URL}/timetable-slots/",
        json=slot_data,
        headers=get_auth_headers()
    )
    
    if response.status_code == 201:
        data = response.json()
        print("✅ Timetable slot created successfully")
        print(f"   Slot ID: {data.get('id')}")
        return data.get('id')
    else:
        print(f"❌ Create failed: {response.status_code} - {response.text}")
        return None

def test_list_timetable_slots():
    """Test listing timetable slots"""
    print("\n🧪 Testing LIST timetable slots...")
    
    response = requests.get(
        f"{BASE_URL}/timetable-slots/",
        headers=get_auth_headers()
    )
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Retrieved {len(data)} timetable slots")
        return data
    else:
        print(f"❌ List failed: {response.status_code} - {response.text}")
        return []

def test_get_timetable_slot(slot_id):
    """Test getting a specific timetable slot"""
    print(f"\n🧪 Testing GET timetable slot {slot_id}...")
    
    response = requests.get(
        f"{BASE_URL}/timetable-slots/{slot_id}/",
        headers=get_auth_headers()
    )
    
    if response.status_code == 200:
        data = response.json()
        print("✅ Timetable slot retrieved successfully")
        print(f"   Course: {data.get('course_code')} - {data.get('course_name')}")
        print(f"   Time: {data.get('time_slot')} on {data.get('day_of_week')}")
        return data
    else:
        print(f"❌ Get failed: {response.status_code} - {response.text}")
        return None

def test_update_timetable_slot(slot_id):
    """Test updating a timetable slot"""
    print(f"\n🧪 Testing UPDATE timetable slot {slot_id}...")
    
    update_data = {
        "venue": "Room 202",
        "instructor": "Dr. Johnson",
        "description": "Updated: Advanced Programming"
    }
    
    response = requests.patch(
        f"{BASE_URL}/timetable-slots/{slot_id}/",
        json=update_data,
        headers=get_auth_headers()
    )
    
    if response.status_code == 200:
        data = response.json()
        print("✅ Timetable slot updated successfully")
        print(f"   New venue: {data.get('venue')}")
        print(f"   New instructor: {data.get('instructor')}")
        return data
    else:
        print(f"❌ Update failed: {response.status_code} - {response.text}")
        return None

def test_bulk_create_timetable_slots():
    """Test bulk creating timetable slots"""
    print("\n🧪 Testing BULK CREATE timetable slots...")
    
    slots_data = {
        "slots": [
            {
                "course": "550e8400-e29b-41d4-a716-446655440000",  # Replace with actual course ID
                "time_slot": "1000-1100",
                "day_of_week": "tuesday",
                "class_type": "tutorial",
                "venue": "Lab 1",
                "instructor": "Dr. Brown",
                "description": "Programming Tutorial",
                "semester": 1,
                "academic_year": "2024"
            },
            {
                "course": "550e8400-e29b-41d4-a716-446655440000",  # Replace with actual course ID
                "time_slot": "1100-1200",
                "day_of_week": "wednesday",
                "class_type": "practical",
                "venue": "Lab 2",
                "instructor": "Dr. Wilson",
                "description": "Programming Practical",
                "semester": 1,
                "academic_year": "2024"
            }
        ]
    }
    
    response = requests.post(
        f"{BASE_URL}/timetable-slots/bulk-create/",
        json=slots_data,
        headers=get_auth_headers()
    )
    
    if response.status_code == 201:
        data = response.json()
        print(f"✅ Bulk create successful: {data.get('success_count')} slots created")
        return data.get('created_slots', [])
    else:
        print(f"❌ Bulk create failed: {response.status_code} - {response.text}")
        return []

def test_filter_by_semester():
    """Test filtering timetable slots by semester"""
    print("\n🧪 Testing FILTER by semester...")
    
    response = requests.get(
        f"{BASE_URL}/timetable-slots/semester/1/year/2024/",
        headers=get_auth_headers()
    )
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Filtered by semester: {data.get('total_slots')} slots found")
        return data.get('slots', [])
    else:
        print(f"❌ Filter by semester failed: {response.status_code} - {response.text}")
        return []

def test_filter_by_day():
    """Test filtering timetable slots by day"""
    print("\n🧪 Testing FILTER by day...")
    
    response = requests.get(
        f"{BASE_URL}/timetable-slots/day/monday/",
        headers=get_auth_headers()
    )
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Filtered by day: {data.get('total_slots')} slots found for Monday")
        return data.get('slots', [])
    else:
        print(f"❌ Filter by day failed: {response.status_code} - {response.text}")
        return []

def test_delete_timetable_slot(slot_id):
    """Test deleting a timetable slot"""
    print(f"\n🧪 Testing DELETE timetable slot {slot_id}...")
    
    response = requests.delete(
        f"{BASE_URL}/timetable-slots/{slot_id}/",
        headers=get_auth_headers()
    )
    
    if response.status_code == 204:
        print("✅ Timetable slot deleted successfully")
        return True
    else:
        print(f"❌ Delete failed: {response.status_code} - {response.text}")
        return False

def test_bulk_delete_timetable_slots(slot_ids):
    """Test bulk deleting timetable slots"""
    print(f"\n🧪 Testing BULK DELETE {len(slot_ids)} timetable slots...")
    
    delete_data = {
        "slot_ids": slot_ids
    }
    
    response = requests.delete(
        f"{BASE_URL}/timetable-slots/bulk-delete/",
        json=delete_data,
        headers=get_auth_headers()
    )
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Bulk delete successful: {data.get('deleted_count')} slots deleted")
        return True
    else:
        print(f"❌ Bulk delete failed: {response.status_code} - {response.text}")
        return False

def main():
    """Run all tests"""
    print("🚀 Starting Timetable Slot CRUD Tests")
    print("=" * 50)
    
    # Test login first
    if not test_login():
        print("❌ Cannot proceed without authentication")
        sys.exit(1)
    
    # Test CRUD operations
    created_slot_id = test_create_timetable_slot()
    
    if created_slot_id:
        test_get_timetable_slot(created_slot_id)
        test_update_timetable_slot(created_slot_id)
    
    # Test listing
    all_slots = test_list_timetable_slots()
    
    # Test bulk operations
    bulk_created_slots = test_bulk_create_timetable_slots()
    
    # Test filtering
    test_filter_by_semester()
    test_filter_by_day()
    
    # Test deletion
    if created_slot_id:
        test_delete_timetable_slot(created_slot_id)
    
    # Test bulk deletion
    if bulk_created_slots:
        slot_ids = [slot['id'] for slot in bulk_created_slots]
        test_bulk_delete_timetable_slots(slot_ids)
    
    print("\n" + "=" * 50)
    print("✅ All tests completed!")

if __name__ == "__main__":
    main()








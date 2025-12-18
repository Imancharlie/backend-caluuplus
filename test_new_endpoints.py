#!/usr/bin/env python
"""
Test script for the new endpoints: university creation, college creation, and password change
"""
import requests
import json

# Base URL
BASE_URL = "http://localhost:8000/api"

def test_endpoints():
    print("Testing New Endpoints")
    print("=" * 50)
    
    # Test data
    test_user = {
        "email": "test@example.com",
        "password": "testpassword123",
        "password_confirm": "testpassword123",
        "display_name": "Test User",
        "gender": "male",
        "phone_number": "1234567890"
    }
    
    # Step 1: Register a test user
    print("1. Registering test user...")
    register_response = requests.post(f"{BASE_URL}/auth/register/", json=test_user)
    if register_response.status_code == 201:
        print("   [OK] User registered successfully")
        token = register_response.json()['token']
        headers = {"Authorization": f"Bearer {token}"}
    else:
        print(f"   [ERROR] Registration failed: {register_response.status_code}")
        print(f"   Response: {register_response.text}")
        return
    
    # Step 2: Test University Creation
    print("\n2. Testing University Creation...")
    university_data = {
        "name": "Test University",
        "country": "Test Country"
    }
    
    uni_response = requests.post(f"{BASE_URL}/admin/universities/", json=university_data, headers=headers)
    if uni_response.status_code == 201:
        print("   [OK] University created successfully")
        uni_data = uni_response.json()['data']
        university_id = uni_data['id']
        print(f"   University ID: {university_id}")
    else:
        print(f"   [ERROR] University creation failed: {uni_response.status_code}")
        print(f"   Response: {uni_response.text}")
        return
    
    # Step 3: Test College Creation
    print("\n3. Testing College Creation...")
    college_data = {
        "name": "Test College",
        "university": university_id
    }
    
    college_response = requests.post(f"{BASE_URL}/admin/colleges/", json=college_data, headers=headers)
    if college_response.status_code == 201:
        print("   [OK] College created successfully")
        college_data = college_response.json()['data']
        print(f"   College ID: {college_data['id']}")
    else:
        print(f"   [ERROR] College creation failed: {college_response.status_code}")
        print(f"   Response: {college_response.text}")
    
    # Step 4: Test Password Change
    print("\n4. Testing Password Change...")
    password_data = {
        "old_password": "testpassword123",
        "new_password": "newpassword123",
        "new_password_confirm": "newpassword123"
    }
    
    password_response = requests.post(f"{BASE_URL}/auth/change-password/", json=password_data, headers=headers)
    if password_response.status_code == 200:
        print("   [OK] Password changed successfully")
    else:
        print(f"   [ERROR] Password change failed: {password_response.status_code}")
        print(f"   Response: {password_response.text}")
    
    # Step 5: Test Login with New Password
    print("\n5. Testing Login with New Password...")
    login_data = {
        "email": "test@example.com",
        "password": "newpassword123"
    }
    
    login_response = requests.post(f"{BASE_URL}/auth/login/", json=login_data)
    if login_response.status_code == 200:
        print("   [OK] Login with new password successful")
    else:
        print(f"   [ERROR] Login with new password failed: {login_response.status_code}")
        print(f"   Response: {login_response.text}")
    
    print("\n" + "=" * 50)
    print("All Tests Completed!")

if __name__ == "__main__":
    test_endpoints()

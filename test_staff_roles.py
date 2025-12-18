#!/usr/bin/env python
"""
Test the staff/me/roles endpoint
"""
import os
import sys
import django
import requests

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'academic_backend.settings')
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
django.setup()

def test_staff_roles_endpoint():
    """Test the staff roles endpoint"""
    print("🧪 Testing staff/me/roles endpoint")
    print("=" * 40)

    # Test the endpoint directly without authentication first
    base_url = "http://localhost:8000/api"
    endpoint = f"{base_url}/staff/me/roles/"

    try:
        response = requests.get(endpoint, timeout=5)
        print(f"Status Code: {response.status_code}")

        if response.status_code == 401:
            print("✅ Endpoint exists and requires authentication (expected)")
            print("Response:", response.text[:200] + "..." if len(response.text) > 200 else response.text)
        elif response.status_code == 200:
            print("✅ Endpoint working without authentication")
            print("Response:", response.text)
        else:
            print(f"⚠️  Unexpected status: {response.status_code}")
            print("Response:", response.text)

    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to server - is it running?")
    except Exception as e:
        print(f"❌ Error: {e}")

    # Test with Django test client (internal)
    print("\n🔧 Testing with Django test client...")
    from django.test import Client
    from django.contrib.auth.models import User

    client = Client()

    # Create a test user
    try:
        test_user = User.objects.create_user(
            username='test@example.com',
            email='test@example.com',
            password='testpass123',
            display_name='Test User'
        )

        # Login the user
        login_response = client.post('/api/auth/login/', {
            'email': 'test@example.com',
            'password': 'testpass123'
        })

        if login_response.status_code == 200:
            print("✅ User login successful")

            # Get the token
            login_data = login_response.json()
            token = login_data.get('token')

            if token:
                # Test the staff roles endpoint
                response = client.get('/api/staff/me/roles/',
                    HTTP_AUTHORIZATION=f'Bearer {token}')

                print(f"Staff roles status: {response.status_code}")
                if response.status_code == 200:
                    print("✅ Staff roles endpoint working!")
                    print("Response:", response.content.decode()[:300])
                else:
                    print(f"❌ Error: {response.content.decode()}")
            else:
                print("❌ No token received")
        else:
            print(f"❌ Login failed: {login_response.status_code}")

        # Cleanup
        test_user.delete()

    except Exception as e:
        print(f"❌ Test error: {e}")

if __name__ == "__main__":
    test_staff_roles_endpoint()














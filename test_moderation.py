"""Quick smoke test for the open-submit + moderation model."""
import os, sys, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "academic_backend.settings")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from caluu_map.models import Campus, Building, Venue, ModeratedModel

User = get_user_model()

# Setup
superuser = User.objects.filter(is_superuser=True).first()
if not superuser:
    superuser = User.objects.create_superuser("testsuper", "super@test.com", "pass1234")
    print(f"Created superuser: {superuser.username}")

normal_user = User.objects.filter(is_superuser=False).first()
if not normal_user:
    normal_user = User.objects.create_user("testnormal", "normal@test.com", "pass1234")
    print(f"Created normal user: {normal_user.username}")

campus = Campus.objects.first()
if not campus:
    print("ERROR: No campuses in DB. Create one first.")
    sys.exit(1)

print(f"\nUsing campus: {campus.name} (id={campus.id})")

# --- Test 1: Anonymous GET returns only approved ---
print("\n=== Test 1: Anonymous GET buildings ===")
anon = APIClient()
resp = anon.get("/api/map/buildings/", {"campus": campus.id})
print(f"  Status: {resp.status_code}")
print(f"  Count: {resp.data.get('count', len(resp.data))}")

# --- Test 2: Normal user creates building (should be pending) ---
print("\n=== Test 2: Normal user creates building ===")
user_client = APIClient()
# simulate auth - get token
from rest_framework_simplejwt.tokens import RefreshToken
refresh = RefreshToken.for_user(normal_user)
user_client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}")

resp = user_client.post("/api/map/buildings/", {
    "campus": str(campus.id),
    "name": "Test Building Pending",
    "latitude": 14.5995,
    "longitude": 120.9842,
}, format="json")
print(f"  Status: {resp.status_code}")
if resp.status_code in (200, 201):
    building_id = resp.data["id"]
    print(f"  Created building: {building_id}")
    print(f"  Status field: {resp.data.get('status')}")
    print(f"  Created by: {resp.data.get('created_by')}")
else:
    print(f"  Response: {resp.data}")
    building_id = None

# --- Test 3: Author sees their own pending building ---
print("\n=== Test 3: Author sees own pending building ===")
resp = user_client.get("/api/map/buildings/", {"campus": campus.id})
print(f"  Status: {resp.status_code}")
results = resp.data.get("results", resp.data)
if isinstance(results, list):
    own = [b for b in results if b.get("id") == building_id]
    print(f"  Author can see own pending: {len(own) > 0}")
    if own:
        print(f"  Status of own building: {own[0].get('status')}")

# --- Test 4: Anonymous cannot see pending ---
print("\n=== Test 4: Anonymous cannot see pending ===")
resp = anon.get("/api/map/buildings/", {"campus": campus.id})
results = resp.data.get("results", resp.data)
if isinstance(results, list):
    found = [b for b in results if b.get("id") == building_id]
    print(f"  Anonymous sees pending: {len(found) > 0} (should be False)")

# --- Test 5: Superuser approves building ---
print("\n=== Test 5: Superuser approves building ===")
if building_id:
    super_client = APIClient()
    refresh = RefreshToken.for_user(superuser)
    super_client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}")
    resp = super_client.post(f"/api/map/buildings/{building_id}/approve/")
    print(f"  Status: {resp.status_code}")
    print(f"  New status: {resp.data.get('status')}")
    print(f"  Reviewed by: {resp.data.get('reviewed_by')}")

# --- Test 6: Now anonymous can see it ---
print("\n=== Test 6: Anonymous sees approved building ===")
resp = anon.get("/api/map/buildings/", {"campus": campus.id})
results = resp.data.get("results", resp.data)
if isinstance(results, list):
    found = [b for b in results if b.get("id") == building_id]
    print(f"  Anonymous sees approved: {len(found) > 0}")

# --- Test 7: Create venue (normal user) ---
print("\n=== Test 7: Normal user creates venue ===")
building = Building.objects.filter(campus=campus, is_active=True).first()
if not building:
    building = Building.objects.filter(campus=campus).first()
if building:
    resp = user_client.post("/api/map/venues/", {
        "campus": str(campus.id),
        "building": str(building.id),
        "name": "Room A4",
        "number": "A4",
        "venue_type": "classroom",
        "floor": "1",
        "latitude": 14.5995,
        "longitude": 120.9842,
    }, format="json")
    print(f"  Status: {resp.status_code}")
    if resp.status_code in (200, 201):
        venue_id = resp.data["id"]
        print(f"  Created venue: {venue_id}")
        print(f"  Status field: {resp.data.get('status')}")
        
        # Approve venue
        resp = super_client.post(f"/api/map/venues/{venue_id}/approve/")
        print(f"  Approve status: {resp.status_code}")
        print(f"  Venue approved: {resp.data.get('status')}")
    else:
        print(f"  Response: {resp.data}")
else:
    print("  No buildings available to attach venue to")

# --- Test 8: Deny access for non-author/non-approver ---
print("\n=== Test 8: Non-author cannot edit ===")
other_user = User.objects.create_user("otheruser", "other@test.com", "pass1234")
other_client = APIClient()
refresh = RefreshToken.for_user(other_user)
other_client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}")
if building_id:
    resp = other_client.patch(f"/api/map/buildings/{building_id}/", {"name": "Hacked"}, format="json")
    print(f"  Status: {resp.status_code} (should be 403)")

# Cleanup
if building_id:
    Building.objects.filter(pk=building_id).delete()
print("\nDone!")

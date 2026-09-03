"""Approve and activate all map data so it's visible via the API."""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'academic_backend.settings')
django.setup()

from caluu_map.models import Campus, Building, Place, Venue

# Get the campus
campus = Campus.objects.first()
if not campus:
    print("No campus found")
    exit(1)

print(f"Approving data for campus: {campus.name}")

# Approve and activate buildings
buildings = Building.objects.filter(campus=campus)
print(f"\nProcessing {buildings.count()} buildings...")
buildings.update(is_active=True, status="approved")
print(f"  Approved and activated all buildings")

# Approve and activate places
places = Place.objects.filter(campus=campus)
print(f"\nProcessing {places.count()} places...")
places.update(is_active=True, status="approved")
print(f"  Approved and activated all places")

# Approve and activate venues
venues = Venue.objects.filter(campus=campus)
print(f"\nProcessing {venues.count()} venues...")
venues.update(is_active=True, status="approved")
print(f"  Approved and activated all venues")

print("\nDone! All map data is now active and approved.")

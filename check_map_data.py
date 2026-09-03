"""Check map data in database to debug why frontend shows no data."""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'academic_backend.settings')
django.setup()

from caluu_map.models import Campus, Building, Place, Venue

# Get campuses
campuses = Campus.objects.all()
print(f"Total campuses: {campuses.count()}")

for campus in campuses:
    print(f"\n--- Campus: {campus.name} (id: {campus.id}) ---")
    print(f"  is_active: {campus.is_active}")
    
    # Check buildings
    buildings = Building.objects.filter(campus=campus)
    print(f"  Total buildings: {buildings.count()}")
    buildings_active_approved = buildings.filter(is_active=True, status="approved")
    print(f"  Active & approved buildings: {buildings_active_approved.count()}")
    
    for b in buildings_active_approved[:5]:
        print(f"    - {b.name} (status: {b.status}, is_active: {b.is_active})")
    
    # Check places
    places = Place.objects.filter(campus=campus)
    print(f"  Total places: {places.count()}")
    places_active_approved = places.filter(is_active=True, status="approved")
    print(f"  Active & approved places: {places_active_approved.count()}")
    
    for p in places_active_approved[:5]:
        print(f"    - {p.name} (status: {p.status}, is_active: {p.is_active})")
    
    # Check venues
    venues = Venue.objects.filter(campus=campus)
    print(f"  Total venues: {venues.count()}")
    venues_active_approved = venues.filter(is_active=True, status="approved")
    print(f"  Active & approved venues: {venues_active_approved.count()}")
    
    for v in venues_active_approved[:5]:
        print(f"    - {v.name} (status: {v.status}, is_active: {v.is_active})")

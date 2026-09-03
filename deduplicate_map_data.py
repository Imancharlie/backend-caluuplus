"""Remove duplicate buildings and places from the database."""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'academic_backend.settings')
django.setup()

from caluu_map.models import Campus, Building, Place
from django.db.models import Count, Min

campus = Campus.objects.first()
if not campus:
    print("No campus found")
    exit(1)

print(f"Deduplicating data for campus: {campus.name}\n")

# Deduplicate buildings
print("--- Deduplicating buildings ---")
# Find buildings with same name, lat, lng
building_groups = Building.objects.filter(campus=campus).values('name', 'latitude', 'longitude').annotate(
    count=Count('id'),
    min_id=Min('id')
).filter(count__gt=1)

buildings_deleted = 0
for group in building_groups:
    # Keep the one with min_id, delete the rest
    to_delete = Building.objects.filter(
        campus=campus,
        name=group['name'],
        latitude=group['latitude'],
        longitude=group['longitude']
    ).exclude(id=group['min_id'])
    
    count = to_delete.count()
    if count > 0:
        to_delete.delete()
        buildings_deleted += count
        print(f"  Deleted {count} duplicates of '{group['name']}'")

print(f"Total buildings deleted: {buildings_deleted}")

# Deduplicate places
print("\n--- Deduplicating places ---")
place_groups = Place.objects.filter(campus=campus).values('name', 'latitude', 'longitude').annotate(
    count=Count('id'),
    min_id=Min('id')
).filter(count__gt=1)

places_deleted = 0
for group in place_groups:
    # Keep the one with min_id, delete the rest
    to_delete = Place.objects.filter(
        campus=campus,
        name=group['name'],
        latitude=group['latitude'],
        longitude=group['longitude']
    ).exclude(id=group['min_id'])
    
    count = to_delete.count()
    if count > 0:
        to_delete.delete()
        places_deleted += count
        print(f"  Deleted {count} duplicates of '{group['name']}'")

print(f"Total places deleted: {places_deleted}")

# Show final counts
print("\n--- Final counts ---")
print(f"Buildings: {Building.objects.filter(campus=campus).count()}")
print(f"Places: {Place.objects.filter(campus=campus).count()}")

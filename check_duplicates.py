"""Check for duplicate buildings/places in the database."""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'academic_backend.settings')
django.setup()

from caluu_map.models import Campus, Building, Place
from django.db.models import Count

campus = Campus.objects.first()
if not campus:
    print("No campus found")
    exit(1)

print(f"Checking for duplicates in campus: {campus.name}\n")

# Check duplicate buildings by name
print("--- Building duplicates by name ---")
building_duplicates = Building.objects.filter(campus=campus).values('name').annotate(
    count=Count('id')
).filter(count__gt=1).order_by('-count')

if building_duplicates.exists():
    print(f"Found {building_duplicates.count()} duplicate building names:")
    for dup in building_duplicates[:20]:
        print(f"  '{dup['name']}' appears {dup['count']} times")
else:
    print("No duplicate building names found")

# Check duplicate places by name
print("\n--- Place duplicates by name ---")
place_duplicates = Place.objects.filter(campus=campus).values('name').annotate(
    count=Count('id')
).filter(count__gt=1).order_by('-count')

if place_duplicates.exists():
    print(f"Found {place_duplicates.count()} duplicate place names:")
    for dup in place_duplicates[:20]:
        print(f"  '{dup['name']}' appears {dup['count']} times")
else:
    print("No duplicate place names found")

# Check duplicate buildings by code (if available)
print("\n--- Building duplicates by code ---")
building_code_duplicates = Building.objects.filter(campus=campus).exclude(code='').values('code').annotate(
    count=Count('id')
).filter(count__gt=1).order_by('-count')

if building_code_duplicates.exists():
    print(f"Found {building_code_duplicates.count()} duplicate building codes:")
    for dup in building_code_duplicates[:20]:
        print(f"  '{dup['code']}' appears {dup['count']} times")
else:
    print("No duplicate building codes found")

# Sample some buildings to see if they look like duplicates
print("\n--- Sample buildings (first 10) ---")
for b in Building.objects.filter(campus=campus)[:10]:
    print(f"  ID: {b.id}, Name: {b.name}, Code: {b.code}, Lat: {b.latitude}, Lng: {b.longitude}")

import os
import sys
import json
import django
from decimal import Decimal

# Force output to flush immediately to PowerShell terminal
sys.stdout.reconfigure(line_buffering=True)

print("\n=======================================================")
print(">>> STEP 1: SCRIPT BEGAN READING SUCCESSFULLY! <<<")
print("=======================================================")

# Initialize Django environment
try:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "academic_backend.settings")
    django.setup()
    print(">>> STEP 2: DJANGO FRAMEWORK PACKAGES INITIALIZED! <<<")
except Exception as e:
    print(f"❌ CRITICAL ERROR: Django failed to initialize settings! Details:\n{e}")
    sys.exit(1)

# Safe imports after setup
try:
    from api.models import University
    from caluu_map.models import Campus, Building, Place
    print(">>> STEP 3: ALL DATABASE MODELS IMPORTED SUCESSFULLY! <<<")
except Exception as e:
    print(f"❌ CRITICAL ERROR: Could not import models! Check folder/app names. Details:\n{e}")
    sys.exit(1)


def get_centroid(geojson_geometry):
    """Safely flattens geometry to calculate a fallback middle point for columns."""
    if not geojson_geometry or "coordinates" not in geojson_geometry:
        return None, None
    
    coords = geojson_geometry.get("coordinates", [])
    
    # Fully bulletproof flat coordinate extractor
    flat_points = []
    def extract_points(item):
        if isinstance(item, list):
            if len(item) == 2 and isinstance(item[0], (int, float)) and isinstance(item[1], (int, float)):
                flat_points.append(item)
            else:
                for sub_item in item:
                    extract_points(sub_item)

    try:
        extract_points(coords)
        if flat_points:
            longitudes = [p[0] for p in flat_points]
            latitudes = [p[1] for p in flat_points]
            avg_lon = sum(longitudes) / len(longitudes)
            avg_lat = sum(latitudes) / len(latitudes)
            return round(Decimal(str(avg_lat)), 6), round(Decimal(str(avg_lon)), 6)
    except Exception as e:
        print(f"⚠️ Centroid parsing warning skipped: {e}")
    return None, None


def run_import():
    print("\n>>> STEP 4: ENTERING THE RUN_IMPORT PIPELINE <<<")
    
    # Diagnostic File Check
    print(f"-> Looking for Buildings File: {os.path.abspath('udsm_buildings.geojson')}")
    print(f"-> Exists? {os.path.exists('udsm_buildings.geojson')}")
    print(f"-> Looking for Paths/POIs File: {os.path.abspath('udsm_paths.geojson')}")
    print(f"-> Exists? {os.path.exists('udsm_paths.geojson')}\n")

    try:
        # Get or create University
        university_obj, created = University.objects.get_or_create(
            name="University of Dar es Salaam",
            defaults={"is_active": True}
        )
        if created:
            print(f"✅ Created new University entry: {university_obj.name}")
        else:
            print(f"ℹ️ Found existing University entry: {university_obj.name}")

        # Get or create Campus
        campus_obj, created = Campus.objects.get_or_create(
            university=university_obj,
            name="Main Campus (Mlimani)",
            defaults={
                "description": "Main campus of the University of Dar es Salaam.",
                "latitude": Decimal("-6.782500"),
                "longitude": Decimal("39.202900"),
                "is_active": True
            }
        )
        if created:
            print(f"✅ Created new Campus: {campus_obj.name}")
        else:
            print(f"ℹ️ Targeting existing Campus: {campus_obj.name}")

    except Exception as e:
        print(f"❌ DATABASE ERROR during core hierarchy configuration:\n{e}")
        return

    # Process Buildings
    buildings_path = "udsm_buildings.geojson"
    if os.path.exists(buildings_path):
        print("\nParsing building datasets...")
        try:
            with open(buildings_path, "r", encoding="utf-8") as f:
                buildings_data = json.load(f)
            
            b_count = 0
            for feature in buildings_data.get("features", []):
                properties = feature.get("properties", {})
                geometry = feature.get("geometry", {})
                
                osm_name = properties.get("name")
                if not osm_name:
                    b_type = properties.get("building", "structure").replace("_", " ").title()
                    osm_name = f"Unnamed {b_type}"
                    
                code = properties.get("code", "")[:20]
                lat, lon = get_centroid(geometry)
                
                Building.objects.create(
                    campus=campus_obj,
                    name=osm_name,
                    code=code,
                    description=f"OSM Building Type: {properties.get('building')}",
                    latitude=lat,
                    longitude=lon,
                    geometry=geometry,
                    is_active=True
                )
                b_count += 1
            print(f"🎉 Successfully inserted {b_count} Buildings into database!")
        except Exception as e:
            print(f"❌ ERROR while writing buildings table: {e}")
    else:
        print(f"❌ Skipped: '{buildings_path}' file not found.")

    # Process Paths / POIs
    pois_path = "udsm_paths.geojson"
    if os.path.exists(pois_path):
        print("\nParsing infrastructure points and spaces...")
        try:
            with open(pois_path, "r", encoding="utf-8") as f:
                pois_data = json.load(f)
                
            p_count = 0
            TYPE_MAPPING = {
                "university": "lecture_hall", "college": "lecture_hall", "library": "library",
                "cafe": "cafeteria", "fast_food": "cafeteria", "restaurant": "cafeteria",
                "atm": "atm", "bank": "atm", "parking": "parking", "clinic": "clinic",
                "hospital": "clinic", "gate": "gate"
            }
            
            for feature in pois_data.get("features", []):
                properties = feature.get("properties", {})
                geometry = feature.get("geometry", {})
                
                osm_name = properties.get("name")
                # If path file has named checkpoints, import them as other/gate places
                if not osm_name:
                    continue 
                    
                osm_amenity = properties.get("amenity", "other")
                place_type = TYPE_MAPPING.get(osm_amenity, "other")
                lat, lon = get_centroid(geometry)
                
                Place.objects.create(
                    campus=campus_obj,
                    name=osm_name,
                    type=place_type,
                    latitude=lat,
                    longitude=lon,
                    description=f"Imported OSM highway feature: {properties.get('highway', 'path')}",
                    is_active=True
                )
                p_count += 1
            print(f"🎉 Successfully inserted {p_count} Places into database!")
        except Exception as e:
            print(f"❌ ERROR while writing places table: {e}")
    else:
        print(f"❌ Skipped: '{pois_path}' file not found.")

    print("\n=======================================================")
    print(">>> SCRIPT EXECUTED ENTIRELY WITH NO UNCAUGHT FATALS <<<")
    print("=======================================================\n")


# FORCED IMMEDIATE EXECUTION (Removes __main__ block bugs in certain PowerShell processes)
run_import()

"""
Geographic utilities for Caluu Map.

Two geometry backends are supported:

* ``geojson`` (default). Works on every Django database -- including the
  SQLite database currently used by the existing Caluu+ project. Geographic
  points are stored as dedicated ``latitude`` / ``longitude`` decimal
  columns (so they stay indexed and queryable everywhere) while geometries
  such as campus boundaries, building footprints and navigation LineStrings
  are stored as GeoJSON documents. GeoJSON is exactly the format consumed by
  MapLibre on the mobile client, so no GIS-specific representation is ever
  shipped to the app.

* ``postgis``. Activated automatically when all of the following are true:

  1. ``settings.CALUU_MAP_POSTGIS`` is ``True``,
  2. Django can import the GeoDjango/GEOS stack,
  3. the connected database is a PostGIS-enabled PostgreSQL database.

  In this mode spatial queries run through real PostGIS functions
  (``ST_DWithin`` / ``ST_DistanceSphere``) against the coordinate columns.

Important: this module never imports ``django.contrib.gis`` at module
import time. That import raises ``ImproperlyConfigured`` when GDAL is not
installed, which would break the whole Caluu+ project. GIS is only probed
lazily inside functions.
"""

import math

from django.conf import settings

# Approximate meters per degree of latitude (WGS84), used for bounding boxes.
M_PER_DEG_LAT = 111320.0


def postgis_available():
    """Return True when the GeoDjango/GEOS stack can be imported safely."""
    try:
        from django.contrib.gis.geos import GEOSGeometry  # noqa: F401

        return True
    except Exception:
        return False


def postgis_enabled():
    """Return True when we must use real PostGIS spatial SQL for queries."""
    return (
        getattr(settings, "CALUU_MAP_USE_POSTGIS", False)
        and postgis_available()
        and _connection_is_postgis()
    )


def _connection_is_postgis():
    try:
        from django.db import connection

        if connection.vendor != "postgresql":
            return False
        with connection.cursor() as cursor:
            cursor.execute("SELECT PostGIS_Version()")
            _, version = cursor.fetchone()
            return bool(version)
    except Exception:
        return False


def valid_latitude(value):
    return value is not None and -90.0 <= value <= 90.0


def valid_longitude(value):
    return value is not None and -180.0 <= value <= 180.0


def build_point(longitude, latitude):
    """Return a GeoJSON Point dict for a location.

    GeoJSON order is always [longitude, latitude].
    """
    lat = float(latitude) if latitude is not None else None
    lng = float(longitude) if longitude is not None else None
    if lat is None or lng is None:
        return None
    return {"type": "Point", "coordinates": [lng, lat]}


def parse_point(location):
    """Parse a GeoJSON Point (or [lng, lat] pair) into (lng, lat)."""
    if location is None:
        return None, None
    if isinstance(location, dict):
        coords = location.get("coordinates")
        if not isinstance(coords, (list, tuple)) or len(coords) != 2:
            return None, None
        return coords[0], coords[1]
    if isinstance(location, (list, tuple)) and len(location) == 2:
        return location[0], location[1]
    return None, None


def haversine_meters(lat1, lng1, lat2, lng2):
    """Great-circle distance in meters between two WGS84 points."""
    if None in (lat1, lng1, lat2, lng2):
        return None
    r = 6371000.0  # Earth radius, meters
    phi1 = math.radians(float(lat1))
    phi2 = math.radians(float(lat2))
    dphi = math.radians(float(lat2) - float(lat1))
    dlmb = math.radians(float(lng2) - float(lng1))
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    )
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def bounding_box(latitude, longitude, radius_m):
    """Approximate (min_lat, max_lat, min_lng, max_lng) for a radius.

    The longitude delta shrinks with latitude using a cosine factor.
    """
    dlat = radius_m / M_PER_DEG_LAT
    if abs(latitude) < 89.9:
        dlng = radius_m / (M_PER_DEG_LAT * math.cos(math.radians(latitude)))
    else:
        dlng = 180.0
    return (
        latitude - dlat,
        latitude + dlat,
        longitude - dlng,
        longitude + dlng,
    )


def nearby_objects(queryset, latitude, longitude, radius_m, limit=None):
    """Return map rows ordered by distance from a point.

    Returns a list of ``(object, distance_m)`` tuples.

    * PostGIS backend: rows are restricted and ordered inside the database
      with ``ST_DWithin`` / ``ST_DistanceSphere`` after a bounding-box
      pre-filter, so the full table is never scanned.
    * Portable backend: an indexed bounding-box query restricts the rows to
      a tiny candidate set and the exact great-circle distance is computed
      over exactly that set. This is the documented fallback for databases
      without PostGIS and still avoids loading "every campus object".
    """
    min_lat, max_lat, min_lng, max_lng = bounding_box(latitude, longitude, radius_m)

    prefiltered = queryset.filter(
        longitude__range=(min_lng, max_lng),
        latitude__range=(min_lat, max_lat),
    )

    if postgis_enabled():
        from django.db.models.expressions import RawSQL

        table = queryset.model._meta.db_table
        distance_sql = RawSQL(
            'ST_DistanceSphere(ST_MakePoint("{t}"."longitude", "{t}"."latitude"), ST_MakePoint(%s, %s))'.format(
                t=table
            ),
            (float(longitude), float(latitude)),
        )
        qs = prefiltered.annotate(distance_m=distance_sql).filter(
            distance_m__lte=float(radius_m)
        )
        if limit:
            qs = qs[:limit]
        return [(obj, obj.distance_m) for obj in qs]

    results = []
    for obj in prefiltered[:300]:
        dist = haversine_meters(latitude, longitude, obj.latitude, obj.longitude)
        if dist <= radius_m:
            results.append((obj, dist))
    results.sort(key=lambda item: item[1])
    if limit:
        results = results[:limit]
    return results
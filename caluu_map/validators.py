"""Validation helpers for Caluu Map models and serializers."""

from django.conf import settings
from django.core.exceptions import ValidationError


def validate_latitude(value):
    if value is None or not (-90 <= value <= 90):
        raise ValidationError("Latitude must be between -90 and 90.")


def validate_longitude(value):
    if value is None or not (-180 <= value <= 180):
        raise ValidationError("Longitude must be between -180 and 180.")


def validate_positive(value):
    if value is None or value <= 0:
        raise ValidationError("Value must be a positive number.")


def ringing_coordinates(coords):
    """Ensure a linear ring is closed (first == last) with >= 4 vertices."""
    if not isinstance(coords, (list, tuple)) or len(coords) < 4:
        return False
    first = coords[0]
    if not isinstance(first, (list, tuple)) or len(first) != 2:
        return False
    if coords[0] != coords[-1]:
        return False
    return True


def validate_geojson_polygon(value):
    """Validate a GeoJSON Polygon geometry (top-level or Feature/FeatureCollection)."""
    if value is None:
        return
    rings = value.get("coordinates") if isinstance(value, dict) else None
    if not isinstance(rings, (list, tuple)) or not rings:
        raise ValidationError("Polygon geometry requires at least one linear ring.")
    for ring in rings:
        if not ringing_coordinates(ring):
            raise ValidationError(
                "Each polygon ring must be closed with at least 4 vertices."
            )


ALLOWED_POLYGON_TYPES = {"Polygon", "MultiPolygon"}


def validate_geometry(value, allowed_types=None, min_points=None):
    """Validate an arbitrary GeoJSON geometry object.

    ``allowed_types`` restricts the allowed GeoJSON geometry types and
    ``min_points`` requires at least that many coordinates in a LineString.
    """
    if value is None:
        return
    if not isinstance(value, dict):
        raise ValidationError("Geometry must be a GeoJSON object.")
    gtype = value.get("type")
    coords = value.get("coordinates")
    if gtype == "Polygon":
        validate_geojson_polygon(value)
    elif gtype == "LineString":
        if not isinstance(coords, (list, tuple)) or len(coords) < (min_points or 2):
            raise ValidationError("LineString geometry needs at least two points.")
        for pt in coords:
            if not isinstance(pt, (list, tuple)) or len(pt) != 2:
                raise ValidationError("LineString vertices must be [lng, lat] pairs.")
    elif gtype == "MultiPolygon":
        if not isinstance(coords, (list, tuple)):
            raise ValidationError("MultiPolygon geometry must be a list of polygons.")
        for poly in coords:
            for ring in poly if isinstance(poly, (list, tuple)) else []:
                if not ringing_coordinates(ring):
                    raise ValidationError(
                        "Each MultiPolygon ring must be closed with >= 4 vertices."
                    )
    else:
        raise ValidationError(f"Unsupported geometry type: {gtype}.")

    if allowed_types and gtype not in allowed_types:
        raise ValidationError(f"Geometry type {gtype} is not allowed here.")


def max_photo_size_mb():
    return int(getattr(settings, "CALUU_MAP_MAX_PHOTO_MB", 10))


def validate_photo_file(value):
    """Validate an uploaded photo: type (MIME-like extension), format and size.

    Uses Pillow to verify the image can actually be decoded and belongs to a
    whitelist of raster formats supported by the mobile MapLibre pipeline.
    """
    if value is None:
        return

    max_bytes = max_photo_size_mb() * 1024 * 1024
    size = getattr(value, "size", None)
    if size is not None and size > max_bytes:
        raise ValidationError(f"Photo exceeds the {max_photo_size_mb()}MB size limit.")

    name = getattr(value, "name", "") or ""
    extension = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    allowed_extensions = {"jpg", "jpeg", "png", "webp", "gif"}
    if extension not in allowed_extensions:
        raise ValidationError(
            f"Unsupported image type '{extension}'. Allowed: {', '.join(sorted(allowed_extensions))}."
        )

    allowed_formats = {"JPEG", "PNG", "WEBP", "GIF"}
    try:
        from PIL import Image

        value.seek(0)
        image = Image.open(value)
        image.verify()
        fmt = (image.format or "").upper()
        if fmt not in allowed_formats:
            raise ValidationError(f"Image format {fmt} is not supported.")
        value.seek(0)
    except Exception as exc:
        if isinstance(exc, ValidationError):
            raise
        raise ValidationError("Uploaded file is not a valid image.") from exc
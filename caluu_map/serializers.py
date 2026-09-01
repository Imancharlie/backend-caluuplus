"""DRF serializers for Caluu Map.

Geographic fields are serialized as GeoJSON so the mobile MapLibre client
never needs to understand Django-GIS internals:

* a point becomes ``{"type": "Point", "coordinates": [lng, lat]}``
* boundaries/footprints/edges are passed through as GeoJSON documents

On write, clients may send either ``latitude``/``longitude`` separately or a
GeoJSON ``location`` object (e.g. ``{"type": "Point", "coordinates": [39.2, -6.79]}``).
"""

from decimal import Decimal, InvalidOperation

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .gis import parse_point
from .models import (
    Building,
    Campus,
    CampusContributor,
    PathEdge,
    PathNode,
    Photo,
    Place,
    ReportCorrection,
    SyncVersion,
    Venue,
)
from .validators import validate_latitude, validate_longitude


def latitude_field():
    return serializers.DecimalField(
        max_digits=9, decimal_places=6, required=False, validators=[validate_latitude]
    )


def longitude_field():
    return serializers.DecimalField(
        max_digits=9, decimal_places=6, required=False, validators=[validate_longitude]
    )


def photo_absolute_url(request, photo):
    if not photo.image:
        return None
    url = photo.image.url
    if request is None:
        return url
    return request.build_absolute_uri(url)


class GeoLocationMixin:
    """Declares GeoJSON Point output plus GeoJSON Point (or lat/lng) input."""

    def get_location(self, obj):
        return obj.location

    def _apply_geojson_location(self, attrs):
        raw = getattr(self, "initial_data", None) or {}
        location = raw.get("location")
        if location is None:
            return attrs
        lng, lat = parse_point(location)
        if lng is None or lat is None:
            raise serializers.ValidationError(
                {"location": "Expected a GeoJSON Point: {'type': 'Point', 'coordinates': [lng, lat]}."}
            )
        try:
            lng = Decimal(lng)
            lat = Decimal(lat)
        except (InvalidOperation, ValueError, TypeError):
            raise serializers.ValidationError(
                {"location": "Coordinates must be valid numbers in [lng, lat] order."}
            )
        validate_latitude(float(lat))
        validate_longitude(float(lng))
        attrs["longitude"] = lng
        attrs["latitude"] = lat
        return attrs


class ModeratedFieldsMixin:
    """Expose moderation fields on user-submitted content serializers."""

    @extend_schema_field(serializers.CharField)
    def get_created_by(self, obj):
        return getattr(obj.created_by, "display_name", None) if obj.created_by else None

    @extend_schema_field(serializers.CharField)
    def get_reviewed_by(self, obj):
        return getattr(obj.reviewed_by, "display_name", None) if obj.reviewed_by else None


def _photo_summary(obj, request, exclude=False):
    if exclude:
        return []
    photos = obj.photos.all() if hasattr(obj, "photos") else []
    return [
        {
            "id": str(photo.id),
            "url": photo_absolute_url(request, photo),
            "caption": photo.caption,
        }
        for photo in photos
        if photo.is_active
    ]


class CampusSerializer(GeoLocationMixin, serializers.ModelSerializer):
    location = serializers.SerializerMethodField()
    latitude = latitude_field()
    longitude = longitude_field()
    university_name = serializers.CharField(source="university.name", read_only=True)
    sync_version = serializers.SerializerMethodField()
    building_count = serializers.SerializerMethodField()
    place_count = serializers.SerializerMethodField()

    class Meta:
        model = Campus
        fields = [
            "id",
            "university",
            "university_name",
            "name",
            "description",
            "location",
            "latitude",
            "longitude",
            "boundary",
            "is_active",
            "sync_version",
            "building_count",
            "place_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    @extend_schema_field(serializers.IntegerField)
    def get_sync_version(self, obj):
        if hasattr(obj, "sync_version"):
            return obj.sync_version.version
        try:
            return SyncVersion.objects.filter(campus=obj).values_list("version", flat=True).first() or 0
        except Exception:
            return 0

    @extend_schema_field(serializers.IntegerField)
    def get_building_count(self, obj):
        return getattr(obj, "building_count", obj.buildings.filter(is_active=True).count())

    @extend_schema_field(serializers.IntegerField)
    def get_place_count(self, obj):
        return getattr(obj, "place_count", obj.places.filter(is_active=True).count())

    def validate(self, attrs):
        return self._apply_geojson_location(attrs)


class BuildingSerializer(GeoLocationMixin, ModeratedFieldsMixin, serializers.ModelSerializer):
    location = serializers.SerializerMethodField()
    latitude = latitude_field()
    longitude = longitude_field()
    campus_name = serializers.CharField(source="campus.name", read_only=True)
    photos = serializers.SerializerMethodField()
    created_by = serializers.SerializerMethodField()
    reviewed_by = serializers.SerializerMethodField()

    class Meta:
        model = Building
        fields = [
            "id",
            "campus",
            "campus_name",
            "name",
            "code",
            "description",
            "location",
            "latitude",
            "longitude",
            "geometry",
            "address",
            "accessibility_information",
            "photos",
            "status",
            "created_by",
            "reviewed_by",
            "reviewed_at",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "status", "created_by", "reviewed_by", "reviewed_at", "created_at", "updated_at"]

    @extend_schema_field(serializers.ListField)
    def get_photos(self, obj):
        return _photo_summary(obj, self.context.get("request"), exclude=self.context.get("exclude_photos", False))

    def validate(self, attrs):
        return self._apply_geojson_location(attrs)


class PlaceSerializer(GeoLocationMixin, ModeratedFieldsMixin, serializers.ModelSerializer):
    location = serializers.SerializerMethodField()
    latitude = latitude_field()
    longitude = longitude_field()
    campus_name = serializers.CharField(source="campus.name", read_only=True)
    building_name = serializers.CharField(source="building.name", read_only=True, default=None)
    photos = serializers.SerializerMethodField()
    created_by = serializers.SerializerMethodField()
    reviewed_by = serializers.SerializerMethodField()

    class Meta:
        model = Place
        fields = [
            "id",
            "campus",
            "campus_name",
            "building",
            "building_name",
            "name",
            "description",
            "type",
            "location",
            "latitude",
            "longitude",
            "floor",
            "room_number",
            "opening_hours",
            "contact_information",
            "photos",
            "status",
            "created_by",
            "reviewed_by",
            "reviewed_at",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "status", "created_by", "reviewed_by", "reviewed_at", "created_at", "updated_at"]

    @extend_schema_field(serializers.ListField)
    def get_photos(self, obj):
        return _photo_summary(obj, self.context.get("request"), exclude=self.context.get("exclude_photos", False))

    def validate(self, attrs):
        attrs = self._apply_geojson_location(attrs)
        campus = attrs.get("campus")
        building = attrs.get("building")
        if campus is not None and building is not None and building.campus_id != campus.id:
            raise serializers.ValidationError(
                {"building": "Building must belong to the same campus as the place."}
            )
        return attrs


class VenueSerializer(GeoLocationMixin, ModeratedFieldsMixin, serializers.ModelSerializer):
    location = serializers.SerializerMethodField()
    latitude = latitude_field()
    longitude = longitude_field()
    campus_name = serializers.CharField(source="campus.name", read_only=True)
    building_name = serializers.CharField(source="building.name", read_only=True, default=None)
    photos = serializers.SerializerMethodField()
    created_by = serializers.SerializerMethodField()
    reviewed_by = serializers.SerializerMethodField()

    class Meta:
        model = Venue
        fields = [
            "id",
            "campus",
            "campus_name",
            "building",
            "building_name",
            "name",
            "number",
            "venue_type",
            "description",
            "floor",
            "location",
            "latitude",
            "longitude",
            "photos",
            "status",
            "created_by",
            "reviewed_by",
            "reviewed_at",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "status", "created_by", "reviewed_by", "reviewed_at", "created_at", "updated_at"]

    @extend_schema_field(serializers.ListField)
    def get_photos(self, obj):
        return _photo_summary(obj, self.context.get("request"), exclude=self.context.get("exclude_photos", False))

    def validate(self, attrs):
        attrs = self._apply_geojson_location(attrs)
        campus = attrs.get("campus")
        building = attrs.get("building")
        if campus is not None and building is not None and building.campus_id != campus.id:
            raise serializers.ValidationError(
                {"building": "Building must belong to the same campus as the venue."}
            )
        return attrs


class PhotoSerializer(ModeratedFieldsMixin, serializers.ModelSerializer):
    url = serializers.SerializerMethodField()
    image = serializers.ImageField(write_only=True, required=True)
    uploaded_by_name = serializers.CharField(source="uploaded_by.display_name", read_only=True, default="")
    created_by = serializers.SerializerMethodField()
    reviewed_by = serializers.SerializerMethodField()

    class Meta:
        model = Photo
        fields = [
            "id",
            "campus",
            "building",
            "place",
            "venue",
            "image",
            "url",
            "caption",
            "uploaded_by",
            "uploaded_by_name",
            "status",
            "created_by",
            "reviewed_by",
            "reviewed_at",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "uploaded_by",
            "created_by",
            "reviewed_by",
            "reviewed_at",
            "created_at",
            "updated_at",
        ]

    @extend_schema_field(serializers.URLField)
    def get_url(self, obj):
        return photo_absolute_url(self.context.get("request"), obj)

    def validate(self, attrs):
        instance = getattr(self, "instance", None)
        building = attrs.get("building", instance.building if instance else None)
        place = attrs.get("place", instance.place if instance else None)
        venue = attrs.get("venue", instance.venue if instance else None)
        campus = attrs.get("campus", instance.campus if instance else None)
        targets = [t for t in (building, place, venue) if t is not None]
        if len(targets) != 1:
            raise serializers.ValidationError(
                {"place": "A photo must be attached to exactly one of a building, place, or venue."}
            )
        if campus is not None:
            target = targets[0]
            if target.campus_id != campus.id:
                raise serializers.ValidationError(
                    {"campus": "The attached building/place/venue must belong to the provided campus."}
                )
        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        if getattr(request, "user", None) and not getattr(request.user, "is_anonymous", True):
            validated_data["uploaded_by"] = request.user
        building = validated_data.get("building")
        place = validated_data.get("place")
        if "campus" not in validated_data:
            validated_data["campus"] = building.campus if building else place.campus
        return super().create(validated_data)


class PathNodeSerializer(GeoLocationMixin, serializers.ModelSerializer):
    location = serializers.SerializerMethodField()
    latitude = latitude_field()
    longitude = longitude_field()
    campus_name = serializers.CharField(source="campus.name", read_only=True, default=None)

    class Meta:
        model = PathNode
        fields = [
            "id",
            "campus",
            "campus_name",
            "location",
            "latitude",
            "longitude",
            "node_type",
            "name",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        return self._apply_geojson_location(attrs)


class PathEdgeSerializer(serializers.ModelSerializer):
    campus_name = serializers.CharField(source="campus.name", read_only=True, default=None)
    start_node_type = serializers.CharField(source="start_node.node_type", read_only=True, default=None)
    end_node_type = serializers.CharField(source="end_node.node_type", read_only=True, default=None)

    class Meta:
        model = PathEdge
        fields = [
            "id",
            "campus",
            "campus_name",
            "start_node",
            "end_node",
            "start_node_type",
            "end_node_type",
            "distance",
            "geometry",
            "bidirectional",
            "accessibility",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        campus = attrs.get("campus")
        start_node = attrs.get("start_node")
        end_node = attrs.get("end_node")
        distance = attrs.get("distance")

        if start_node is not None and end_node is not None:
            if start_node.id == end_node.id:
                raise serializers.ValidationError(
                    {"end_node": "A path edge cannot connect a node to itself."}
                )
            if start_node.campus_id != end_node.campus_id:
                raise serializers.ValidationError(
                    {"end_node": "Both nodes must belong to the same campus."}
                )
            if campus is not None and (start_node.campus_id != campus.id or end_node.campus_id != campus.id):
                raise serializers.ValidationError(
                    {"campus": "Edge campus must match the campus of its nodes."}
                )

        if distance is not None:
            try:
                if Decimal(distance) <= 0:
                    raise serializers.ValidationError({"distance": "Distance must be positive."})
            except (InvalidOperation, ValueError, TypeError):
                raise serializers.ValidationError({"distance": "Distance must be a number."})
        return attrs


class CampusContributorSerializer(serializers.ModelSerializer):
    user_display_name = serializers.CharField(source="user.display_name", read_only=True, default="")
    campus_name = serializers.CharField(source="campus.name", read_only=True, default="")

    class Meta:
        model = CampusContributor
        fields = [
            "id",
            "user",
            "user_display_name",
            "campus",
            "campus_name",
            "role",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class ReportCorrectionSerializer(serializers.ModelSerializer):
    reporter_name = serializers.CharField(source="reporter.display_name", read_only=True, default="")
    campus_name = serializers.CharField(source="campus.name", read_only=True, default="")
    reviewed_by_name = serializers.CharField(source="reviewed_by.display_name", read_only=True, default="")

    class Meta:
        model = ReportCorrection
        fields = [
            "id",
            "reporter",
            "reporter_name",
            "campus",
            "campus_name",
            "target_type",
            "target_id",
            "description",
            "proposed_correction",
            "status",
            "reviewed_by",
            "reviewed_by_name",
            "reviewed_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "reporter", "reviewed_by", "reviewed_at", "created_at", "updated_at"]

    def create(self, validated_data):
        request = self.context["request"]
        if getattr(request, "user", None) and not getattr(request.user, "is_anonymous", True):
            validated_data["reporter"] = request.user
        return super().create(validated_data)


class SyncVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SyncVersion
        fields = ["campus", "version", "updated_at"]
        read_only_fields = fields
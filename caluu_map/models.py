"""Caluu Map models.

Reuses the existing ``api.University`` model as the root parent entity.
University is NOT duplicated -- Campus references it through a ForeignKey.

Geometry note: points are stored as indexed ``latitude``/``longitude``
decimal columns and larger geometries (boundaries, footprints, navigation
routes) as GeoJSON documents. This is portable across databases and is the
exact GeoJSON format MapLibre consumes. When the deployment uses PostGIS and
``CALUU_MAP_USE_POSTGIS = True`` the same columns are queried through real
PostGIS functions (see :mod:`caluu_map.gis`).
"""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from api.models import University

from .validators import (
    validate_geojson_polygon,
    validate_latitude,
    validate_longitude,
    validate_photo_file,
)


class UUIDModel(models.Model):
    """Base model: UUID primary key plus creation/update timestamps."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Campus(UUIDModel):
    """A physical campus belonging to an existing Caluu+ University."""

    university = models.ForeignKey(
        University,
        on_delete=models.CASCADE,
        related_name="campuses",
        help_text="The existing Caluu+ University this campus belongs to.",
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True, validators=[validate_latitude]
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True, validators=[validate_longitude]
    )
    boundary = models.JSONField(
        null=True,
        blank=True,
        validators=[validate_geojson_polygon],
        help_text="GeoJSON Polygon/MultiPolygon describing the campus boundary.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Campuses"
        indexes = [
            models.Index(fields=["university", "latitude", "longitude"], name="campus_point_idx"),
        ]

    def __str__(self):
        return f"{self.name} ({self.university.name})"

    @property
    def location(self):
        from .gis import build_point

        return build_point(self.longitude, self.latitude)


class Building(UUIDModel):
    """A building on a campus."""

    campus = models.ForeignKey(
        Campus, on_delete=models.CASCADE, related_name="buildings"
    )
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=20, blank=True, default="")
    description = models.TextField(blank=True, default="")
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True, validators=[validate_latitude]
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True, validators=[validate_longitude]
    )
    geometry = models.JSONField(
        null=True,
        blank=True,
        help_text="GeoJSON Polygon/MultiPolygon footprint of the building.",
    )
    address = models.CharField(max_length=255, blank=True, default="")
    accessibility_information = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(
                fields=["campus", "latitude", "longitude"], name="building_point_idx"
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["campus", "code"],
                condition=~models.Q(code=""),
                name="uniq_building_code_per_campus",
            ),
        ]

    def __str__(self):
        return f"{self.code}: {self.name}" if self.code else self.name

    @property
    def location(self):
        from .gis import build_point

        return build_point(self.longitude, self.latitude)


class Place(UUIDModel):
    """A destination or useful point within a campus (office, lab, ATM, ...)."""

    PLACE_TYPES = [
        ("office", "Office"),
        ("lecture_hall", "Lecture Hall"),
        ("laboratory", "Laboratory"),
        ("library", "Library"),
        ("cafeteria", "Cafeteria"),
        ("hostel", "Hostel"),
        ("auditorium", "Auditorium"),
        ("atm", "ATM"),
        ("parking", "Parking"),
        ("clinic", "Clinic"),
        ("sports_ground", "Sports Ground"),
        ("gate", "Gate"),
        ("prayer_area", "Prayer Area"),
        ("other", "Other"),
    ]

    campus = models.ForeignKey(
        Campus, on_delete=models.CASCADE, related_name="places"
    )
    building = models.ForeignKey(
        Building,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="places",
        help_text="Optional parent building. May be empty for places not tied to a building.",
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    type = models.CharField(max_length=30, choices=PLACE_TYPES, default="other")
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True, validators=[validate_latitude]
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True, validators=[validate_longitude]
    )
    floor = models.CharField(max_length=50, blank=True, default="")
    room_number = models.CharField(max_length=50, blank=True, default="")
    opening_hours = models.TextField(blank=True, default="")
    contact_information = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["campus", "type"], name="place_type_idx"),
            models.Index(fields=["campus", "latitude", "longitude"], name="place_point_idx"),
        ]

    def __str__(self):
        return self.name

    @property
    def location(self):
        from .gis import build_point

        return build_point(self.longitude, self.latitude)

    def clean(self):
        from django.core.exceptions import ValidationError as DjangoVE

        if (
            self.building_id is not None
            and self.campus_id is not None
            and self.building_id
            and self.building.campus_id != self.campus_id
        ):
            raise DjangoVE({"building": "Building must belong to the same campus as the place."})


class Photo(UUIDModel):
    """A photo attached to exactly one Building OR one Place."""

    campus = models.ForeignKey(
        Campus, on_delete=models.CASCADE, related_name="photos"
    )
    building = models.ForeignKey(
        Building,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="photos",
    )
    place = models.ForeignKey(
        Place,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="photos",
    )
    image = models.ImageField(
        upload_to="map/photos/%Y/%m/",
        validators=[validate_photo_file],
        help_text="Upload an image file (JPEG, PNG, WEBP, GIF).",
    )
    caption = models.CharField(max_length=255, blank=True, default="")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="map_photos",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["campus", "is_active"], name="photo_campus_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(building__isnull=False, place__isnull=True)
                    | models.Q(building__isnull=True, place__isnull=False)
                ),
                name="photo_has_exactly_one_target",
            ),
        ]

    def __str__(self):
        target = self.building_id and f"building:{self.building_id}" or f"place:{self.place_id}"
        return f"Photo {target} ({self.caption or 'no caption'})"


class PathNode(UUIDModel):
    """A navigable point in the campus graph."""

    NODE_TYPES = [
        ("walkway", "Walkway"),
        ("entrance", "Entrance"),
        ("stairs", "Stairs"),
        ("elevator", "Elevator"),
        ("corridor", "Corridor"),
        ("road", "Road"),
        ("landmark", "Landmark"),
    ]

    campus = models.ForeignKey(
        Campus, on_delete=models.CASCADE, related_name="path_nodes"
    )
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True, validators=[validate_latitude]
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True, validators=[validate_longitude]
    )
    node_type = models.CharField(max_length=20, choices=NODE_TYPES, default="walkway")
    name = models.CharField(max_length=200, blank=True, default="")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["campus_id", "name"]
        indexes = [
            models.Index(fields=["campus", "latitude", "longitude"], name="pathnode_point_idx"),
            models.Index(fields=["campus", "node_type"], name="pathnode_type_idx"),
        ]

    def __str__(self):
        return f"{self.name or self.node_type} ({self.campus.name})"

    @property
    def location(self):
        from .gis import build_point

        return build_point(self.longitude, self.latitude)


class PathEdge(UUIDModel):
    """A connection between two PathNodes in the campus navigation graph."""

    campus = models.ForeignKey(
        Campus, on_delete=models.CASCADE, related_name="path_edges"
    )
    start_node = models.ForeignKey(
        PathNode, on_delete=models.CASCADE, related_name="outgoing_edges"
    )
    end_node = models.ForeignKey(
        PathNode, on_delete=models.CASCADE, related_name="incoming_edges"
    )
    distance = models.DecimalField(max_digits=12, decimal_places=3)
    geometry = models.JSONField(
        null=True,
        blank=True,
        help_text="GeoJSON LineString describing the actual route between the two nodes.",
    )
    bidirectional = models.BooleanField(default=True)
    accessibility = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["campus_id", "distance"]
        indexes = [
            models.Index(fields=["campus", "start_node", "end_node"], name="path_edge_pair_idx"),
        ]

    def __str__(self):
        return f"{self.start_node_id} -> {self.end_node_id} ({self.distance}m)"

    def clean(self):
        from decimal import Decimal

        from django.core.exceptions import ValidationError as DjangoVE

        if self.start_node_id and self.end_node_id:
            if self.start_node_id == self.end_node_id:
                raise DjangoVE("A path edge cannot connect a node to itself.")
            if self.start_node.campus_id != self.end_node.campus_id:
                raise DjangoVE("Path edge start and end nodes must belong to the same campus.")
        try:
            distance = None if self.distance is None else Decimal(str(self.distance))
        except Exception:  # noqa: BLE001 - let the field / DB decide malformed values
            distance = None
        if distance is not None and distance <= 0:
            raise DjangoVE("Path edge distance must be positive.")
        if self.start_node_id and self.start_node.campus_id != self.campus_id:
            raise DjangoVE("Edge campus must match the campus of its nodes.")


class CampusContributor(UUIDModel):
    """Controls who can contribute/manage information for a specific campus."""

    ROLES = [
        ("viewer", "Viewer"),
        ("contributor", "Contributor"),
        ("moderator", "Moderator"),
        ("campus_admin", "Campus Admin"),
    ]
    STATUSES = [
        ("pending", "Pending"),
        ("active", "Active"),
        ("suspended", "Suspended"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="map_contributorships",
    )
    campus = models.ForeignKey(
        Campus, on_delete=models.CASCADE, related_name="contributors"
    )
    role = models.CharField(max_length=20, choices=ROLES, default="viewer")
    status = models.CharField(max_length=20, choices=STATUSES, default="pending")

    class Meta:
        ordering = ["campus__name", "user__display_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "campus"], name="uniq_contributor_per_campus"
            ),
        ]

    def __str__(self):
        return f"{self.user.display_name} - {self.role} @ {self.campus.name}"


class ReportCorrection(UUIDModel):
    """A user-submitted report about incorrect or missing campus data."""

    TARGET_TYPES = [
        ("campus", "Campus"),
        ("building", "Building"),
        ("place", "Place"),
        ("photo", "Photo"),
        ("path_node", "Path Node"),
        ("path_edge", "Path Edge"),
        ("other", "Other"),
    ]
    STATUSES = [
        ("pending", "Pending"),
        ("reviewing", "Reviewing"),
        ("accepted", "Accepted"),
        ("rejected", "Rejected"),
    ]

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="map_correction_reports",
    )
    campus = models.ForeignKey(
        Campus, on_delete=models.CASCADE, related_name="correction_reports"
    )
    target_type = models.CharField(max_length=20, choices=TARGET_TYPES)
    target_id = models.CharField(max_length=64, blank=True, default="")
    description = models.TextField(help_text="What is incorrect or missing.")
    proposed_correction = models.JSONField(
        null=True,
        blank=True,
        help_text="Optional structured proposal (fields the user suggests).",
    )
    status = models.CharField(max_length=20, choices=STATUSES, default="pending")
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_corrections",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["campus", "status"], name="report_status_idx"),
        ]

    def __str__(self):
        return f"{self.target_type} report by {self.reporter.display_name}"


class SyncVersion(UUIDModel):
    """Monotonic sync version per campus (the offline synchronization cursor).

    Every mutation to a campus' map data bumps this counter and appends a
    row to :class:`SyncChange`, giving clients a deterministic, version-based
    way to answer "what changed since my last sync?".
    """

    campus = models.OneToOneField(
        Campus,
        on_delete=models.CASCADE,
        related_name="sync_version",
        primary_key=False,
    )
    version = models.BigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.campus.name} @ v{self.version}"

    @classmethod
    def current_for(cls, campus):
        version, _ = cls.objects.get_or_create(campus=campus)
        return version


class SyncChange(UUIDModel):
    """One row per mutation of a campus' map data, tagged with a version."""

    ENTITY_TYPES = [
        ("campus", "Campus"),
        ("building", "Building"),
        ("place", "Place"),
        ("photo", "Photo"),
        ("path_node", "Path Node"),
        ("path_edge", "Path Edge"),
    ]
    ACTIONS = [
        ("created", "Created"),
        ("updated", "Updated"),
        ("deleted", "Deleted"),
    ]

    campus = models.ForeignKey(
        Campus, on_delete=models.CASCADE, related_name="sync_changes"
    )
    version = models.BigIntegerField()
    entity_type = models.CharField(max_length=20, choices=ENTITY_TYPES)
    object_id = models.UUIDField()
    action = models.CharField(max_length=20, choices=ACTIONS, default="updated")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["version"]
        indexes = [
            models.Index(fields=["campus", "version"], name="sync_version_idx"),
        ]

    def __str__(self):
        return f"{self.entity_type}:{self.object_id} {self.action} @v{self.version}"
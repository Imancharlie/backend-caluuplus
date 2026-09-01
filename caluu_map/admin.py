"""Django admin registrations for Caluu Map.

The existing ``UniversityAdmin`` in ``api.admin`` is untouched.
"""

from django.contrib import admin

from .models import (
    Building,
    Campus,
    CampusContributor,
    PathEdge,
    PathNode,
    Photo,
    Place,
    ReportCorrection,
    SyncChange,
    SyncVersion,
    Venue,
)


@admin.register(Campus)
class CampusAdmin(admin.ModelAdmin):
    list_display = ("name", "university", "is_active", "created_at", "updated_at")
    list_filter = ("is_active", "university", "created_at")
    search_fields = ("name", "university__name", "description")
    raw_id_fields = ("university",)
    list_select_related = ("university",)


@admin.register(Building)
class BuildingAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "campus", "is_active", "created_at")
    list_filter = ("is_active", "campus__university", "campus")
    search_fields = ("name", "code", "address", "campus__name")
    list_select_related = ("campus",)


@admin.register(Place)
class PlaceAdmin(admin.ModelAdmin):
    list_display = ("name", "type", "campus", "building", "room_number", "is_active")
    list_filter = ("type", "is_active", "campus")
    search_fields = ("name", "room_number", "campus__name")
    raw_id_fields = ("building",)
    list_select_related = ("campus", "building")


@admin.register(Venue)
class VenueAdmin(admin.ModelAdmin):
    list_display = ("name", "number", "venue_type", "campus", "building", "floor", "is_active")
    list_filter = ("venue_type", "is_active", "campus")
    search_fields = ("name", "number", "venue_type", "campus__name")
    raw_id_fields = ("building",)
    list_select_related = ("campus", "building")


@admin.register(Photo)
class PhotoAdmin(admin.ModelAdmin):
    list_display = ("__str__", "campus", "caption", "uploaded_by", "is_active", "created_at")
    list_filter = ("is_active", "campus", "created_at")
    search_fields = ("caption", "campus__name")
    raw_id_fields = ("building", "place", "venue", "uploaded_by")


@admin.register(PathNode)
class PathNodeAdmin(admin.ModelAdmin):
    list_display = ("name", "node_type", "campus", "is_active")
    list_filter = ("node_type", "is_active", "campus")
    search_fields = ("name", "campus__name")


@admin.register(PathEdge)
class PathEdgeAdmin(admin.ModelAdmin):
    list_display = ("__str__", "campus", "distance", "bidirectional", "is_active")
    list_filter = ("bidirectional", "is_active", "campus")
    raw_id_fields = ("start_node", "end_node")


@admin.register(CampusContributor)
class CampusContributorAdmin(admin.ModelAdmin):
    list_display = ("user", "campus", "role", "status", "created_at")
    list_filter = ("role", "status", "campus")
    search_fields = ("user__display_name", "user__email", "campus__name")
    raw_id_fields = ("user", "campus")


@admin.register(ReportCorrection)
class ReportCorrectionAdmin(admin.ModelAdmin):
    list_display = (
        "__str__",
        "reporter",
        "campus",
        "target_type",
        "status",
        "reviewed_by",
        "created_at",
    )
    list_filter = ("status", "target_type", "campus", "created_at")
    search_fields = ("description", "reporter__display_name", "campus__name")
    raw_id_fields = ("reporter", "campus", "reviewed_by")


@admin.register(SyncVersion)
class SyncVersionAdmin(admin.ModelAdmin):
    list_display = ("campus", "version", "updated_at")
    list_filter = ("campus",)


@admin.register(SyncChange)
class SyncChangeAdmin(admin.ModelAdmin):
    list_display = ("campus", "version", "entity_type", "object_id", "action", "created_at")
    list_filter = ("entity_type", "action", "campus")
    search_fields = ("campus__name", "object_id")
    list_select_related = ("campus",)
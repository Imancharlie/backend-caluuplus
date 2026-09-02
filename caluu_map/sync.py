"""Version-based synchronization engine for Caluu Map.

The offline-first mobile client uses two flows:

* Initial sync: ``GET api/map/campuses/<id>/data/`` returns the complete
  dataset for a campus plus the current ``sync_version`` cursor.
* Incremental sync: ``GET api/map/sync/?campus_id=...&since=...`` returns
  only what changed after ``since``, grouped into created / updated /
  deleted lists. Deactivated rows (``is_active=False``) or rows whose
  ``status`` is not ``approved`` are reported in the ``deleted`` list
  with appropriate action markers, so the SQLite client can mark them
  inactive without losing metadata.

Every write bumps a per-campus monotonic version (see ``signals.py``),
which keeps the response deterministic and free of timestamp-only heuristics.
"""

from collections import defaultdict

from django.db import transaction


def _entity_map():
    from . import models

    return {
        "campus": models.Campus,
        "building": models.Building,
        "place": models.Place,
        "venue": models.Venue,
        "photo": models.Photo,
        "path_node": models.PathNode,
        "path_edge": models.PathEdge,
    }


def empty_changeset():
    return {
        "created": {"buildings": [], "places": [], "venues": [], "path_nodes": [], "path_edges": [], "photos": []},
        "updated": {"buildings": [], "places": [], "venues": [], "path_nodes": [], "path_edges": [], "photos": []},
        "deleted": {"buildings": [], "places": [], "venues": [], "path_nodes": [], "path_edges": [], "photos": []},
    }


def _entity_key(entity_type):
    return {
        "building": "buildings",
        "place": "places",
        "venue": "venues",
        "path_node": "path_nodes",
        "path_edge": "path_edges",
        "photo": "photos",
    }.get(entity_type)


def current_version(campus):
    """Return the latest sync version for a campus (0 when never synced).

    Queries ``SyncVersion`` directly instead of walking the reverse
    one-to-one relation, which caches misses/values on the model instance
    and can therefore report a stale version after a write.
    """
    from .models import SyncVersion

    version = (
        SyncVersion.objects.filter(campus_id=campus.pk)
        .values_list("version", flat=True)
        .first()
    )
    return version if version is not None else 0


def record_change(campus_id, entity_type, object_id, action):
    """Bump the campus version and append a change-log row."""
    from .models import SyncChange, SyncVersion

    with transaction.atomic():
        sv, _ = SyncVersion.objects.select_for_update().get_or_create(campus_id=campus_id)
        next_version = sv.version + 1
        SyncChange.objects.create(
            campus_id=campus_id,
            version=next_version,
            entity_type=entity_type,
            object_id=object_id,
            action=action,
        )
        sv.version = next_version
        sv.save(update_fields=["version", "updated_at"])


def build_initial_dataset(serializer_context):
    """Serialize the complete dataset for a campus.

    Only ``approved`` rows are included in the public dataset. The author
    can see their own pending content via the ViewSet querysets (not via
    this dataset endpoint).
    """
    from . import models
    from .serializers import (
        BuildingSerializer,
        CampusSerializer,
        PathEdgeSerializer,
        PathNodeSerializer,
        PlaceSerializer,
        VenueSerializer,
    )

    campus = serializer_context["campus"]
    request = serializer_context.get("request")

    buildings = models.Building.objects.filter(
        campus=campus, is_active=True, status="approved"
    ).select_related("campus").prefetch_related("photos")
    places = models.Place.objects.filter(
        campus=campus, is_active=True, status="approved"
    ).select_related("campus", "building")
    venues = models.Venue.objects.filter(
        campus=campus, is_active=True, status="approved"
    ).select_related("campus", "building")
    nodes = models.PathNode.objects.filter(campus=campus, is_active=True).select_related(
        "campus"
    )
    edges = models.PathEdge.objects.filter(campus=campus, is_active=True).select_related(
        "campus", "start_node", "end_node"
    )

    return {
        "campus": CampusSerializer(campus, context={"request": request}).data,
        "buildings": BuildingSerializer(
            buildings, many=True, context={"request": request}
        ).data,
        "places": PlaceSerializer(places, many=True, context={"request": request}).data,
        "venues": VenueSerializer(venues, many=True, context={"request": request}).data,
        "path_nodes": PathNodeSerializer(nodes, many=True, context={"request": request}).data,
        "path_edges": PathEdgeSerializer(edges, many=True, context={"request": request}).data,
    }


def changes_since(campus, since):
    """Return the deterministic change set since a previous sync version."""
    from .models import SyncChange

    groups = empty_changeset()
    current = current_version(campus)

    entries = list(
        SyncChange.objects.filter(campus=campus, version__gt=since).order_by("version")
    )
    if not entries:
        return groups, current

    # Group entries per object to look at their most recent action.
    by_object = defaultdict(list)
    for entry in entries:
        by_object[entry.object_id].append(entry)

    models = _entity_map()
    for object_id, entry_list in by_object.items():
        latest = entry_list[-1]
        key = _entity_key(latest.entity_type)
        if key is None:
            continue
        if latest.action == "deleted":
            groups["deleted"][key].append({"id": str(object_id), "action": "deleted"})
            continue

        model = models[latest.entity_type]
        obj = model.objects.filter(pk=object_id).first()
        if obj is None:
            groups["deleted"][key].append({"id": str(object_id), "action": "deleted"})
            continue

        # Non-approved content is invisible to public sync clients.
        status = getattr(obj, "status", None)
        if status is not None and status != "approved":
            payload = _serialize(obj, latest.entity_type)
            action_label = "rejected" if status == "rejected" else "pending"
            groups["deleted"][key].append({"id": str(object_id), "action": action_label, "object": payload})
            continue

        # Report current state so clients always converge on the truth.
        payload = _serialize(obj, latest.entity_type)
        if not getattr(obj, "is_active", True):
            payload["is_active"] = False
            groups["deleted"][key].append({"id": str(object_id), "action": "deactivated", "object": payload})
            continue

        action = "created" if any(e.action == "created" for e in entry_list) else "updated"
        groups[action][key].append(payload)

    return groups, current


def _serialize(obj, entity_type):
    from .serializers import (
        BuildingSerializer,
        CampusSerializer,
        PathEdgeSerializer,
        PathNodeSerializer,
        PhotoSerializer,
        PlaceSerializer,
        VenueSerializer,
    )

    serializer = {
        "campus": CampusSerializer,
        "building": BuildingSerializer,
        "place": PlaceSerializer,
        "venue": VenueSerializer,
        "photo": PhotoSerializer,
        "path_node": PathNodeSerializer,
        "path_edge": PathEdgeSerializer,
    }.get(entity_type)
    if serializer is None:
        return {"id": str(obj.pk)}
    return serializer(obj, context={"exclude_photos": True}).data

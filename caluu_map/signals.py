"""
Sync change-log signals.

Every save/delete of a Caluu Map entity appends a :class:`SyncChange` row and
bumps the campus' :class:`SyncVersion` counter. This is what powers the
version-based incremental synchronization endpoint.

Notes:
* ``post_save`` logs ``created`` for new rows and ``updated`` for saves of
  existing rows.
* ``pre_delete`` logs ``deleted`` (the row is removed afterwards; only its id
  is kept in the log so clients can prune their SQLite copy).
* Deactivation (``is_active = False``) is detected at sync-response time from
  the object's current state, so no extra log action is needed.
* Operations that bypass model signals (``QuerySet.update`` / ``bulk_create``)
  do not change the version -- mutations should go through the API/serializers.
"""

import logging

from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

logger = logging.getLogger(__name__)

_ENTITY_MODELS = {
    "Building": "building",
    "Place": "place",
    "Venue": "venue",
    "Photo": "photo",
    "PathNode": "path_node",
    "PathEdge": "path_edge",
}


def _record(campus, entity_type, object_id, action):
    from .models import Campus, SyncChange, SyncVersion
    from django.db import transaction

    with transaction.atomic():
        sv, _ = SyncVersion.objects.get_or_create(campus_id=campus)
        next_version = sv.version + 1
        SyncChange.objects.create(
            campus_id=campus,
            version=next_version,
            entity_type=entity_type,
            object_id=object_id,
            action=action,
        )
        SyncVersion.objects.filter(pk=sv.pk).update(version=next_version)


def _campus_id_for(sender_name, instance):
    # Campus entities ARE their own campus; everything else carries campus_id.
    if sender_name == "Campus":
        return instance.pk
    return getattr(instance, "campus_id", None)


@receiver(post_save, dispatch_uid="caluu_map_post_save")
def on_map_entity_saved(sender, instance, created, **kwargs):
    entity_type = _ENTITY_MODELS.get(sender.__name__)
    if entity_type is None:
        return
    campus_id = _campus_id_for(sender.__name__, instance)
    if campus_id is None:
        return
    action = "created" if created else "updated"
    _record(campus_id, entity_type, instance.pk, action)


@receiver(pre_delete, dispatch_uid="caluu_map_pre_delete")
def on_map_entity_deleted(sender, instance, **kwargs):
    entity_type = _ENTITY_MODELS.get(sender.__name__)
    if entity_type is None:
        return
    campus_id = _campus_id_for(sender.__name__, instance)
    if campus_id is None:
        return
    _record(campus_id, entity_type, instance.pk, "deleted")
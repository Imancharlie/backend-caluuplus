"""API views for Caluu Map.

Endpoint layout (mounted under ``api/map/``):

* ``campuses/``                      -- list/create campuses (filter: university_id)
* ``campuses/<id>/``                 -- retrieve/update/deactivate a campus
* ``campuses/<id>/data/``            -- full offline dataset + sync version
* ``buildings/`` ``places/``         -- map content CRUD
* ``photos/``                        -- photo upload/list/retrieve
* ``path-nodes/`` ``path-edges/``    -- navigation graph CRUD
* ``campus-contributors/``           -- manage who can contribute per campus
* ``correction-reports/``            -- submit + review correction reports
* ``sync/``                          -- incremental synchronization
* ``search/``                        -- campus-aware search
* ``nearby/``                        -- PostGIS-powered nearby query
"""

import logging
import uuid

from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404

logger = logging.getLogger(__name__)
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import gis, sync
from .filters import (
    BuildingFilter,
    CampusContributorFilter,
    CampusFilter,
    PathEdgeFilter,
    PathNodeFilter,
    PhotoFilter,
    PlaceFilter,
    ReportCorrectionFilter,
    VenueFilter,
)
from .models import (
    Building,
    Campus,
    CampusContributor,
    PathEdge,
    PathNode,
    Photo,
    Place,
    ReportCorrection,
    Venue,
)
from .permissions import (
    ROLE_CAMPUS_ADMIN,
    ROLE_CONTRIBUTOR,
    ROLE_MODERATOR,
    IsAuthenticatedForMapEdit,
    IsSuperUser,
    can_manage_campus,
    is_superuser,
)
from .serializers import (
    BuildingSerializer,
    CampusContributorSerializer,
    CampusSerializer,
    PathEdgeSerializer,
    PathNodeSerializer,
    PhotoSerializer,
    PlaceSerializer,
    ReportCorrectionSerializer,
    VenueSerializer,
)


def _active_campus_or_404(campus_id):
    return get_object_or_404(Campus.objects.filter(is_active=True), pk=campus_id)


def _clean_campus(payload):
    raw = payload.get("campus")
    if not raw:
        return None
    try:
        return get_object_or_404(Campus, pk=str(raw))
    except (ValueError, TypeError):
        return None


class MapContentMixin:
    """Shared behavior for campus-scoped content ViewSets.

    Post-moderation model (the model the user requested):

    * Reads (GET) are public. Public data only exposes ``approved`` rows.
    * *Any authenticated user* may create or edit content -- no campus
      contributor membership is required. New/edited rows are created with
      ``status='pending'`` and are only ever visible to their author until an
      approver confirms them.
    * Approvers (campus_admin / moderator / superuser) can publish content via
      ``POST .../approve/`` (``status -> 'approved'``) or reject it via
      ``POST .../reject/`` (``status -> 'rejected'``).
    """

    write_role = ROLE_CONTRIBUTOR

    def get_permissions(self):
        if self.request and self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [AllowAny()]
        return [IsAuthenticatedForMapEdit()]

    # ----- visibility scoping -------------------------------------------------
    def scoped_queryset(self, base_qs):
        """Restrict reads by moderation status and the requesting user.

        * Anonymous users: approved only.
        * Approvers (campus_admin/moderator/superuser of that campus): all
          statuses so they can moderate on both the list and retrieve views.
        * Everyone else: approved, plus their own rows (pending/rejected) so an
          author always sees and can continue editing what they submitted.
        """
        user = getattr(self.request, "user", None)
        if user is None or getattr(user, "is_anonymous", True):
            return base_qs.filter(status="approved")
        if self._is_approver(self._campus_of_queryset(base_qs)):
            return base_qs
        return base_qs.filter(Q(status="approved") | Q(created_by=user))

    def _campus_of_queryset(self, base_qs):
        """Best-effort campus id referenced by the queryset or request."""
        params = getattr(self.request, "query_params", None) or {}
        campus_id = params.get("campus")
        if campus_id:
            return campus_id
        return None

    def _is_approver(self, campus_id):
        from .permissions import can_moderate

        user = getattr(self.request, "user", None)
        if user is None or getattr(user, "is_anonymous", True):
            return False
        if campus_id is None:
            # Cannot resolve a campus from the request; only superusers get
            # the global mod view.
            from .permissions import is_superuser

            return is_superuser(user)
        try:
            campus = Campus.objects.get(pk=campus_id)
        except (Campus.DoesNotExist, ValueError, TypeError):
            return False
        return can_moderate(user, campus)

    def default_filter_active(self, queryset):
        if getattr(self, "action", None) != "list":
            return queryset
        params = self.request.query_params
        if params.get("is_active") is None and params.get("include_inactive") != "true":
            queryset = queryset.filter(is_active=True)
        return queryset

    # ----- write guards (open submission + moderation) -----------------------
    def guard_create(self, campus):
        if campus is None:
            raise ValidationError({"campus": "A valid campus is required."})
        # Any authenticated user may submit; approval happens later.

    def guard_update(self, obj):
        user = self.request.user
        if getattr(user, "is_anonymous", True):
            raise PermissionDenied("You must be logged in to edit map content.")
        # The author may always keep editing their own row. Approvers may edit
        # any row. All edits revert to pending so nothing changes publicly
        # without approval.
        if not (user == obj.created_by or self._is_approver(obj.campus_id)):
            raise PermissionDenied(
                "You may only edit content you created before it is approved. "
                "Submit a correction report or ask an approver for help."
            )

    def perform_create(self, serializer):
        self._force_pending(serializer, set_author=True)
        super().perform_create(serializer)
        self._consume_map_tokens()

    def perform_update(self, serializer):
        # Editing marks the row pending again (unless an approver edited the
        # approve/reject state directly).
        self._force_pending(serializer, set_author=False)
        super().perform_update(serializer)

    def _force_pending(self, serializer, set_author):
        data = getattr(serializer, "validated_data", {})
        data["status"] = "pending"
        if set_author and not getattr(self.request.user, "is_anonymous", True):
            data["created_by"] = self.request.user

    def _missing_access_message(self, user, campus, min_role):
        """Keep a diagnostic for any remaining permission denials."""
        if user is None or getattr(user, "is_anonymous", True):
            return (
                "Authentication failed: you must be logged in to modify map content. "
                "Check that an Authorization Bearer token is being sent."
            )
        return (
            f"Access denied for user '{getattr(user, 'username', user.pk)}' on campus "
            f"'{getattr(campus, 'name', campus)}'. You can only edit content you "
            f"created (it stays pending until approved), or content you moderate."
        )

    def _debug_guard(self, action, user, campus):
        logger.warning(
            "MAP %s DENIED user=%s campus=%s path=%s",
            action.upper(),
            getattr(user, "username", getattr(user, "pk", None)),
            getattr(campus, "name", getattr(campus, "pk", None)),
            self.request.path,
        )

    def guard_destroy(self, obj):
        if not is_superuser(self.request.user):
            raise PermissionDenied(
                "Hard deletes require a superuser. Use PATCH is_active=false to deactivate."
            )

    def _consume_map_tokens(self):
        """Route map-activity consumption through the central token service.

        Best-effort so a low balance never blocks writing map content.
        """
        try:
            from tokens import services as token_service
            token_service.consume(
                self.request.user,
                "MAP_ACTIVITY",
                reference_key=f"map:{self.request.path}:{uuid.uuid4()}",
                description="Caluu Map activity",
                initiated_by="caluu_map",
            )
        except Exception as e:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).warning(f"Map token consumption skipped: {str(e)}")

    def create(self, request, *args, **kwargs):
        campus = _clean_campus(request.data.dict() if hasattr(request.data, "dict") else request.data)
        self.guard_create(campus)
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        self.guard_update(instance)
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.guard_destroy(instance)
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ModerationMixin:
    """Approve/reject a single content row (campus_admin, moderator, superuser)."""

    moderation_status_field = "status"

    def _resolve_campus(self, obj):
        return obj.campus if hasattr(obj, "campus") else None

    def approval_action(self, status_value):
        obj = self.get_object()
        from .permissions import can_moderate

        campus = self._resolve_campus(obj)
        if campus is None or not can_moderate(self.request.user, campus):
            raise PermissionDenied(
                "Only a campus admin, moderator, or superuser can approve content."
            )
        from django.utils import timezone

        setattr(obj, self.moderation_status_field, status_value)
        obj.reviewed_by = self.request.user
        obj.reviewed_at = timezone.now()
        obj.save()
        # Re-serialize so the caller sees the fresh state.
        serializer = self.get_serializer(obj)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, *args, **kwargs):
        return self.approval_action(ModelHelpers.approved_status())

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, *args, **kwargs):
        return self.approval_action(ModelHelpers.rejected_status())


class ModelHelpers:
    @staticmethod
    def approved_status():
        from .models import ModeratedModel

        return ModeratedModel.STATUS_APPROVED

    @staticmethod
    def rejected_status():
        from .models import ModeratedModel

        return ModeratedModel.STATUS_REJECTED



class CampusViewSet(viewsets.ModelViewSet):
    queryset = Campus.objects.all()
    serializer_class = CampusSerializer
    filterset_class = CampusFilter

    def get_queryset(self):
        qs = (
            Campus.objects.select_related("university")
            .annotate(
                building_count=Count("buildings", filter=Q(buildings__is_active=True)),
                place_count=Count("places", filter=Q(places__is_active=True)),
            )
            .prefetch_related("sync_version")
        )
        if getattr(self, "action", None) in ("list", "retrieve", "data"):
            params = self.request.query_params
            if params.get("is_active") is None and params.get("include_inactive") != "true":
                if self.action in ("retrieve", "data") and self.kwargs.get("pk"):
                    try:
                        target = Campus.objects.get(pk=self.kwargs["pk"])
                    except Campus.DoesNotExist:
                        target = None
                    if target is not None and can_manage_campus(
                        self.request.user, target, ROLE_CAMPUS_ADMIN
                    ):
                        return qs
                qs = qs.filter(is_active=True)
        return qs

    def get_permissions(self):
        if self.request and self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [AllowAny()]
        if self.action in ("create", "destroy"):
            return [IsAuthenticated(), IsSuperUser()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        if not is_superuser(self.request.user):
            raise PermissionDenied("Only superusers can create campuses.")
        serializer.save()

    def perform_update(self, serializer):
        instance = serializer.instance
        if not can_manage_campus(self.request.user, instance, ROLE_CAMPUS_ADMIN):
            raise PermissionDenied("Campus admin or superuser access required.")
        serializer.save()

    def perform_destroy(self, instance):
        raise PermissionDenied(
            "Campuses are deactivated with PATCH is_active=false; hard delete is disabled."
        )

    @extend_schema(
        operation_id="campus_map_data",
        summary="Full offline dataset for a campus (initial synchronization).",
        description=(
            "Returns the complete dataset required to initialize the offline "
            "SQLite store on the mobile client: campus, buildings, places, "
            "navigation graph and the current sync version. Image payloads are "
            "returned as absolute URLs, never file paths."
        ),
        responses={200: OpenApiTypes.OBJECT},
    )
    @action(detail=True, methods=["get"], url_path="data")
    def data(self, request, pk=None):
        campus = self.get_object()
        dataset = sync.build_initial_dataset(
            {"campus": campus, "request": request}
        )
        dataset["sync_version"] = sync.current_version(campus)
        return Response(dataset)


class BuildingViewSet(MapContentMixin, ModerationMixin, viewsets.ModelViewSet):
    queryset = Building.objects.select_related("campus").prefetch_related("photos")
    serializer_class = BuildingSerializer
    filterset_class = BuildingFilter
    search_fields = ("name", "code", "address")

    def get_queryset(self):
        return self.default_filter_active(self.scoped_queryset(super().get_queryset()))


class PlaceViewSet(MapContentMixin, ModerationMixin, viewsets.ModelViewSet):
    queryset = Place.objects.select_related("campus", "building").prefetch_related("photos")
    serializer_class = PlaceSerializer
    filterset_class = PlaceFilter

    def get_queryset(self):
        return self.default_filter_active(self.scoped_queryset(super().get_queryset()))


class VenueViewSet(MapContentMixin, ModerationMixin, viewsets.ModelViewSet):
    queryset = Venue.objects.select_related("campus", "building").prefetch_related("photos")
    serializer_class = VenueSerializer
    filterset_class = VenueFilter
    search_fields = ("name", "number", "floor")

    def get_queryset(self):
        return self.default_filter_active(self.scoped_queryset(super().get_queryset()))

    def create(self, request, *args, **kwargs):
        campus = _clean_campus(request.data.dict() if hasattr(request.data, "dict") else request.data)
        if campus is None:
            building_id = request.data.get("building")
            if building_id:
                building = get_object_or_404(Building, pk=str(building_id))
                campus = building.campus
        self.guard_create(campus)
        return super().create(request, *args, **kwargs)


class PhotoViewSet(MapContentMixin, ModerationMixin, viewsets.ModelViewSet):
    queryset = Photo.objects.select_related("campus", "building", "place", "venue", "uploaded_by")
    serializer_class = PhotoSerializer
    filterset_class = PhotoFilter

    def get_queryset(self):
        return self.default_filter_active(self.scoped_queryset(super().get_queryset()))

    def create(self, request, *args, **kwargs):
        payload = request.data.dict() if hasattr(request.data, "dict") else {}
        campus = _clean_campus(payload)
        if campus is None:
            building_id = payload.get("building")
            place_id = payload.get("place")
            venue_id = payload.get("venue")
            if building_id:
                building = get_object_or_404(Building, pk=str(building_id))
                campus = building.campus
            elif place_id:
                place = get_object_or_404(Place, pk=str(place_id))
                campus = place.campus
            elif venue_id:
                venue = get_object_or_404(Venue, pk=str(venue_id))
                campus = venue.campus
        self.guard_create(campus)
        return super().create(request, *args, **kwargs)

    @action(detail=False, methods=["post"], url_path="bulk")
    def bulk(self, request, *args, **kwargs):
        """Upload several photos in one multipart request.

        The request is a multipart form with one or more ``images`` file
        fields plus a single ``building`` / ``place`` / ``venue`` / ``campus``
        target. Every image becomes a pending Photo row.
        """
        data = request.data
        images = data.getlist("images") if hasattr(data, "getlist") else []
        if not images:
            raise ValidationError({"images": "Provide at least one 'images' file field."})

        building_id = data.get("building")
        place_id = data.get("place")
        venue_id = data.get("venue")
        campus = _clean_campus(request.data.dict() if hasattr(request.data, "dict") else request.data)
        if campus is None:
            if building_id:
                campus = get_object_or_404(Building, pk=str(building_id)).campus
            elif place_id:
                campus = get_object_or_404(Place, pk=str(place_id)).campus
            elif venue_id:
                campus = get_object_or_404(Venue, pk=str(venue_id)).campus
        self.guard_create(campus)

        try:
            building = Building.objects.get(pk=building_id) if building_id else None
            place = Place.objects.get(pk=place_id) if place_id else None
            venue = Venue.objects.get(pk=venue_id) if venue_id else None
        except (Building.DoesNotExist, Place.DoesNotExist, Venue.DoesNotExist):
            raise ValidationError({"target": "The referenced building/place/venue does not exist."})

        created = []
        for image in images:
            ser = PhotoSerializer(
                data={
                    "campus": campus.pk if campus else None,
                    "building": building.pk if building else None,
                    "place": place.pk if place else None,
                    "venue": venue.pk if venue else None,
                    "image": image,
                    "caption": data.get("caption", ""),
                },
                context=self.get_serializer_context(),
            )
            ser.is_valid(raise_exception=True)
            obj = ser.save()
            created.append(PhotoSerializer(obj, context=self.get_serializer_context()).data)
        return Response(created, status=status.HTTP_201_CREATED)


class PathNodeViewSet(MapContentMixin, viewsets.ModelViewSet):
    queryset = PathNode.objects.select_related("campus")
    serializer_class = PathNodeSerializer
    filterset_class = PathNodeFilter

    def get_queryset(self):
        return self.default_filter_active(super().get_queryset())


class PathEdgeViewSet(MapContentMixin, viewsets.ModelViewSet):
    queryset = PathEdge.objects.select_related("campus", "start_node", "end_node")
    serializer_class = PathEdgeSerializer
    filterset_class = PathEdgeFilter

    def get_queryset(self):
        return self.default_filter_active(super().get_queryset())


class CampusContributorViewSet(viewsets.ModelViewSet):
    queryset = CampusContributor.objects.select_related("user", "campus")
    serializer_class = CampusContributorSerializer
    filterset_class = CampusContributorFilter

    def get_permissions(self):
        if self.request and self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [IsAuthenticated()]
        return [IsAuthenticated()]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if getattr(user, "is_anonymous", True):
            return qs.none()
        if is_superuser(user):
            return qs
        admin_campuses = CampusContributor.objects.filter(
            user=user, status="active", role="campus_admin"
        ).values_list("campus_id", flat=True)
        if admin_campuses.exists():
            return qs.filter(campus_id__in=list(admin_campuses))
        return qs.filter(user=user)

    def guard_campus_management(self, campus):
        if not can_manage_campus(self.request.user, campus, ROLE_CAMPUS_ADMIN):
            raise PermissionDenied("Campus admin or superuser access required.")

    def create(self, request, *args, **kwargs):
        campus = _clean_campus(request.data.dict() if hasattr(request.data, "dict") else request.data)
        self.guard_campus_management(campus)
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        self.guard_campus_management(instance.campus)
        partial = kwargs.pop("partial", False)
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.guard_campus_management(instance.campus)
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ReportCorrectionViewSet(viewsets.ModelViewSet):
    queryset = ReportCorrection.objects.select_related("reporter", "campus", "reviewed_by")
    serializer_class = ReportCorrectionSerializer
    filterset_class = ReportCorrectionFilter

    def get_permissions(self):
        return [IsAuthenticated()]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if getattr(user, "is_anonymous", True):
            return qs.none()
        if is_superuser(user):
            return qs
        moderated = CampusContributor.objects.filter(
            user=user, status="active"
        ).filter(role__in=["moderator", "campus_admin"]).values_list("campus_id", flat=True)
        if getattr(self, "action", None) == "list":
            if moderated.exists():
                return qs.filter(Q(reporter=user) | Q(campus_id__in=list(moderated)))
            return qs.filter(reporter=user)
        return qs

    def guard_review(self, obj):
        if is_superuser(self.request.user):
            return
        if not can_manage_campus(self.request.user, obj.campus, ROLE_MODERATOR):
            raise PermissionDenied("Moderator or campus admin access required.")

    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    def perform_update(self, serializer):
        instance = serializer.instance
        self.guard_review(instance)
        from django.utils import timezone

        status_changed = (
            "status" in serializer.validated_data
            and serializer.validated_data.get("status") != instance.status
        )
        if status_changed:
            serializer.save(
                reviewed_by=self.request.user, reviewed_at=timezone.now()
            )
        else:
            serializer.save()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if not is_superuser(request.user):
            raise PermissionDenied("Only superusers can delete reports.")
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(
    operation_id="map_incremental_sync",
    summary="Incremental synchronization since a version.",
    description=(
        "Returns only the objects that changed after ``since`` for a campus. "
        "The response is deterministic and version-based: created/updated "
        "objects are sent with their current state, deactivated or deleted "
        "objects are reported in ``deleted``. Pass ``since=0`` to start from v0."
    ),
    parameters=[
        OpenApiParameter("campus_id", OpenApiTypes.STR, OpenApiParameter.QUERY, required=True),
        OpenApiParameter("since", OpenApiTypes.INT, OpenApiParameter.QUERY, required=True),
    ],
    responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
)
class SyncDataView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        campus_id = request.query_params.get("campus_id")
        since_raw = request.query_params.get("since")
        if not campus_id:
            raise ValidationError({"campus_id": "campus_id is required."})
        if since_raw is None:
            raise ValidationError({"since": "since is required."})
        try:
            since = int(since_raw)
        except (ValueError, TypeError):
            raise ValidationError({"since": "since must be an integer version."})
        if since < 0:
            raise ValidationError({"since": "since cannot be negative."})

        campus = _active_campus_or_404(campus_id)
        current = sync.current_version(campus)
        if since > current:
            raise ValidationError(
                {"since": f"since ({since}) is ahead of the server version ({current})."}
            )

        changes, current = sync.changes_since(campus, since)
        return Response(
            {
                "campus_id": str(campus.id),
                "previous_version": since,
                "current_version": current,
                "server_time": timezone_now_iso(),
                "full_resync_required": False,
                **changes,
            }
        )


def timezone_now_iso():
    from django.utils import timezone

    return timezone.now().isoformat()


@extend_schema(
    operation_id="map_search",
    summary="Campus-aware search across buildings and places.",
    parameters=[
        OpenApiParameter("campus_id", OpenApiTypes.STR, OpenApiParameter.QUERY, required=True),
        OpenApiParameter("q", OpenApiTypes.STR, OpenApiParameter.QUERY, required=True),
    ],
    responses={200: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
)
class MapSearchView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        campus_id = request.query_params.get("campus_id")
        query = (request.query_params.get("q") or "").strip()
        if not campus_id:
            raise ValidationError({"campus_id": "campus_id is required."})
        campus = _active_campus_or_404(campus_id)

        results = []
        if query:
            buildings = (
                Building.objects.filter(campus=campus, is_active=True, status="approved")
                .filter(Q(name__icontains=query) | Q(code__icontains=query) | Q(address__icontains=query))
            )[:25]
            for building in buildings:
                results.append(
                    {
                        "kind": "building",
                        "id": str(building.id),
                        "name": building.name,
                        "code": building.code,
                        "campus_id": str(campus.id),
                        "location": gis.build_point(building.longitude, building.latitude),
                    }
                )

            type_values = [
                value
                for value, label in Place.PLACE_TYPES
                if query.lower() in value.replace("_", " ").lower()
                or query.lower() in label.lower()
            ]
            places_q = Place.objects.filter(campus=campus, is_active=True, status="approved")
            place_match = Q(name__icontains=query) | Q(room_number__icontains=query)
            if type_values:
                place_match |= Q(type__in=type_values)
            for place in places_q.filter(place_match)[:25]:
                results.append(
                    {
                        "kind": "place",
                        "id": str(place.id),
                        "name": place.name,
                        "type": place.type,
                        "building_id": str(place.building_id) if place.building_id else None,
                        "campus_id": str(campus.id),
                        "location": gis.build_point(place.longitude, place.latitude),
                    }
                )

            venue_type_values = [
                value
                for value, label in Venue.VENUE_TYPES
                if query.lower() in value.replace("_", " ").lower()
                or query.lower() in label.lower()
            ]
            venues_q = Venue.objects.filter(campus=campus, is_active=True, status="approved")
            venue_match = Q(name__icontains=query) | Q(number__icontains=query)
            if venue_type_values:
                venue_match |= Q(venue_type__in=venue_type_values)
            for venue in venues_q.filter(venue_match)[:25]:
                results.append(
                    {
                        "kind": "venue",
                        "id": str(venue.id),
                        "name": venue.name,
                        "number": venue.number,
                        "venue_type": venue.venue_type,
                        "building_id": str(venue.building_id) if venue.building_id else None,
                        "campus_id": str(campus.id),
                        "location": gis.build_point(venue.longitude, venue.latitude),
                    }
                )

        return Response({"campus_id": str(campus.id), "q": query, "count": len(results), "results": results})


@extend_schema(
    operation_id="map_nearby",
    summary="Nearby buildings and places (radius in meters).",
    description=(
        "Spatial query capped by a radius in meters. Uses PostGIS "
        "ST_DWithin/ST_DistanceSphere when available; otherwise an indexed "
        "bounding-box pre-filter with exact great-circle distances over the "
        "candidate set. Never scans the full campus table."
    ),
    parameters=[
        OpenApiParameter("campus_id", OpenApiTypes.STR, OpenApiParameter.QUERY, required=True),
        OpenApiParameter("lat", OpenApiTypes.NUMBER, OpenApiParameter.QUERY, required=True),
        OpenApiParameter("lng", OpenApiTypes.NUMBER, OpenApiParameter.QUERY, required=True),
        OpenApiParameter("radius", OpenApiTypes.INT, OpenApiParameter.QUERY, description="Radius in meters (default 500)."),
    ],
    responses={200: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
)
class NearbyView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        campus_id = request.query_params.get("campus_id")
        try:
            lat = float(request.query_params.get("lat"))
            lng = float(request.query_params.get("lng"))
        except (TypeError, ValueError):
            raise ValidationError({"lat/lng": "lat and lng are required numbers."})
        if no_good_coords(lat, lng):
            raise ValidationError({"lat/lng": "Coordinates out of range."})
        radius = request.query_params.get("radius")
        try:
            radius_m = int(radius) if radius else 500
        except (ValueError, TypeError):
            raise ValidationError({"radius": "radius must be an integer (meters)."})
        if radius_m <= 0:
            raise ValidationError({"radius": "radius must be positive."})

        campus = _active_campus_or_404(campus_id)

        buildings = Building.objects.filter(campus=campus, is_active=True, status="approved").select_related("campus")
        places = Place.objects.filter(campus=campus, is_active=True, status="approved").select_related("campus", "building")
        venues = Venue.objects.filter(campus=campus, is_active=True, status="approved").select_related("campus", "building")

        building_rows = gis.nearby_objects(buildings, lat, lng, radius_m, limit=50)
        place_rows = gis.nearby_objects(places, lat, lng, radius_m, limit=50)
        venue_rows = gis.nearby_objects(venues, lat, lng, radius_m, limit=50)

        from .serializers import BuildingSerializer, PlaceSerializer, VenueSerializer

        context = {"request": request}
        building_data = [
            {**BuildingSerializer(obj, context=context).data, "distance_m": round(dist, 2)}
            for obj, dist in building_rows
        ]
        place_data = [
            {**PlaceSerializer(obj, context=context).data, "distance_m": round(dist, 2)}
            for obj, dist in place_rows
        ]
        venue_data = [
            {**VenueSerializer(obj, context=context).data, "distance_m": round(dist, 2)}
            for obj, dist in venue_rows
        ]

        return Response(
            {
                "campus_id": str(campus.id),
                "latitude": lat,
                "longitude": lng,
                "radius_m": radius_m,
                "count": len(building_data) + len(place_data) + len(venue_data),
                "buildings": building_data,
                "places": place_data,
                "venues": venue_data,
            }
        )


def no_good_coords(lat, lng):
    return not (-90 <= lat <= 90) or not (-180 <= lng <= 180)
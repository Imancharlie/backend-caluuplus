"""django-filter FilterSets for Caluu Map list endpoints."""

import django_filters
from django.db.models import Q

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


class CampusFilter(django_filters.FilterSet):
    university = django_filters.UUIDFilter(field_name="university")
    university_id = django_filters.UUIDFilter(field_name="university")
    is_active = django_filters.BooleanFilter()
    q = django_filters.CharFilter(method="filter_search")

    class Meta:
        model = Campus
        fields = ["university", "university_id", "is_active"]

    def filter_search(self, queryset, name, value):
        return queryset.filter(Q(name__icontains=value) | Q(description__icontains=value))


class BuildingFilter(django_filters.FilterSet):
    campus = django_filters.UUIDFilter(field_name="campus")
    is_active = django_filters.BooleanFilter()
    q = django_filters.CharFilter(method="filter_search")

    class Meta:
        model = Building
        fields = ["campus", "is_active"]

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(name__icontains=value) | Q(code__icontains=value) | Q(address__icontains=value)
        )


class PlaceFilter(django_filters.FilterSet):
    campus = django_filters.UUIDFilter(field_name="campus")
    building = django_filters.UUIDFilter(field_name="building")
    type = django_filters.CharFilter(field_name="type")
    is_active = django_filters.BooleanFilter()
    q = django_filters.CharFilter(method="filter_search")

    class Meta:
        model = Place
        fields = ["campus", "building", "type", "is_active"]

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(name__icontains=value)
            | Q(room_number__icontains=value)
            | Q(type__icontains=value)
        )


class VenueFilter(django_filters.FilterSet):
    campus = django_filters.UUIDFilter(field_name="campus")
    building = django_filters.UUIDFilter(field_name="building")
    venue_type = django_filters.CharFilter(field_name="venue_type")
    is_active = django_filters.BooleanFilter()
    q = django_filters.CharFilter(method="filter_search")

    class Meta:
        model = Venue
        fields = ["campus", "building", "venue_type", "is_active"]

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(name__icontains=value)
            | Q(number__icontains=value)
            | Q(venue_type__icontains=value)
        )


class PathNodeFilter(django_filters.FilterSet):
    campus = django_filters.UUIDFilter(field_name="campus")
    node_type = django_filters.CharFilter(field_name="node_type")
    is_active = django_filters.BooleanFilter()
    q = django_filters.CharFilter(field_name="name", lookup_expr="icontains")

    class Meta:
        model = PathNode
        fields = ["campus", "node_type", "is_active"]


class PathEdgeFilter(django_filters.FilterSet):
    campus = django_filters.UUIDFilter(field_name="campus")
    start_node = django_filters.UUIDFilter(field_name="start_node")
    end_node = django_filters.UUIDFilter(field_name="end_node")
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = PathEdge
        fields = ["campus", "start_node", "end_node", "is_active"]


class PhotoFilter(django_filters.FilterSet):
    campus = django_filters.UUIDFilter(field_name="campus")
    building = django_filters.UUIDFilter(field_name="building")
    place = django_filters.UUIDFilter(field_name="place")
    venue = django_filters.UUIDFilter(field_name="venue")
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = Photo
        fields = ["campus", "building", "place", "venue", "is_active"]


class CampusContributorFilter(django_filters.FilterSet):
    campus = django_filters.UUIDFilter(field_name="campus")
    user = django_filters.UUIDFilter(field_name="user")
    role = django_filters.CharFilter(field_name="role")
    status = django_filters.CharFilter(field_name="status")

    class Meta:
        model = CampusContributor
        fields = ["campus", "user", "role", "status"]


class ReportCorrectionFilter(django_filters.FilterSet):
    campus = django_filters.UUIDFilter(field_name="campus")
    reporter = django_filters.UUIDFilter(field_name="reporter")
    status = django_filters.CharFilter(field_name="status")
    target_type = django_filters.CharFilter(field_name="target_type")

    class Meta:
        model = ReportCorrection
        fields = ["campus", "reporter", "status", "target_type"]
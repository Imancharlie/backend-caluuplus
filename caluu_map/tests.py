"""Tests for the Caluu Map feature.

Covers models, relationships, permissions (viewer / contributor / moderator /
campus admin / superuser), all major API endpoints, the PostGIS-ready nearby
query, the initial-data endpoint, and the version-based synchronization flow.
"""

import io
import uuid

from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError
from django.urls import reverse
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

from api.models import University, User

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
)
from .sync import changes_since, current_version


def make_png(name="test.png", size=(8, 8), color=(200, 30, 30)):
    """Return an in-memory PNG upload."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


def make_txt(name="test.txt"):
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile(name, b"not an image", content_type="text/plain")


class MapTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.university = University.objects.create(name="Test University", country="TZ")
        cls.campus = Campus.objects.create(
            university=cls.university,
            name="Main Campus",
            description="Central campus",
            latitude="-6.790000",
            longitude="39.200000",
        )

        cls.normal = cls._make_user("normal@test.com", "Normal User")
        cls.viewer = cls._make_user("viewer@test.com", "Viewer User")
        cls.contributor = cls._make_user("contributor@test.com", "Contributor User")
        cls.moderator = cls._make_user("moderator@test.com", "Moderator User")
        cls.campus_admin = cls._make_user("admin@test.com", "Campus Admin")
        cls.superuser = cls._make_user(
            "root@test.com", "Root", is_staff=True, is_superuser=True
        )

        cls._grant(cls.viewer, "viewer")
        cls._grant(cls.contributor, "contributor")
        cls._grant(cls.moderator, "moderator")
        cls._grant(cls.campus_admin, "campus_admin")

    @classmethod
    def _make_user(cls, email, display_name, **extra):
        return User.objects.create_user(
            email=email, display_name=display_name, password="password123", **extra
        )

    @classmethod
    def _grant(cls, user, role, campus=None, status_value="active"):
        return CampusContributor.objects.create(
            user=user, campus=campus or cls.campus, role=role, status=status_value
        )

    def _auth(self, user):
        self.client.force_authenticate(user=user)
        return self.client

    def _create_building(self, **kwargs):
        defaults = {
            "campus": self.campus,
            "name": "Engineering",
            "code": "ENG",
            "latitude": "-6.790100",
            "longitude": "39.200100",
        }
        defaults.update(kwargs)
        return Building.objects.create(**defaults)

    def _create_place(self, **kwargs):
        defaults = {
            "campus": self.campus,
            "name": "Lab 1",
            "type": "laboratory",
            "latitude": "-6.790200",
            "longitude": "39.200200",
        }
        defaults.update(kwargs)
        return Place.objects.create(**defaults)

    def _create_node(self, **kwargs):
        defaults = {
            "campus": self.campus,
            "name": "Gate A",
            "node_type": "entrance",
            "latitude": "-6.790000",
            "longitude": "39.200000",
        }
        defaults.update(kwargs)
        return PathNode.objects.create(**defaults)

    def _create_edge(self, a, b, **kwargs):
        defaults = {
            "campus": self.campus,
            "start_node": a,
            "end_node": b,
            "distance": "120.000",
            "geometry": {
                "type": "LineString",
                "coordinates": [[39.200000, -6.790000], [39.200300, -6.790200]],
            },
        }
        defaults.update(kwargs)
        return PathEdge.objects.create(**defaults)

    @staticmethod
    def _version(campus):
        return current_version(campus)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class ModelTests(MapTestCase):
    def test_university_is_reused_as_parent(self):
        campus = Campus.objects.get(pk=self.campus.pk)
        self.assertEqual(campus.university, self.university)
        self.assertIsInstance(self.university.campuses.first(), Campus)

    def test_multiple_campuses_per_university(self):
        second = Campus.objects.create(university=self.university, name="West Campus")
        self.assertEqual(self.university.campuses.count(), 2)
        self.assertTrue(second.university, self.university)

    def test_building_code_unique_within_campus(self):
        self._create_building(code="CS")
        with transaction.atomic(), self.assertRaises(IntegrityError):
            Building.objects.create(campus=self.campus, name="Duplicate", code="CS")

    def test_same_code_allowed_across_campuses(self):
        other = Campus.objects.create(university=self.university, name="Other")
        self._create_building(code="LIB")
        Building.objects.create(campus=other, name="Other Library", code="LIB")

    def test_photo_must_have_exactly_one_target(self):
        building = self._create_building()
        place = self._create_place(building=building)
        with transaction.atomic(), self.assertRaises(IntegrityError):
            Photo.objects.create(campus=self.campus, building=building, place=place, image=make_png())
        with transaction.atomic(), self.assertRaises(IntegrityError):
            Photo.objects.create(campus=self.campus, image=make_png())

    def test_place_building_must_match_campus(self):
        other = Campus.objects.create(university=self.university, name="Other")
        building_other = Building.objects.create(campus=other, name="B")
        place = Place(campus=self.campus, building=building_other, name="X")
        with self.assertRaises(ValidationError):
            place.clean()

    def test_path_edge_validation_rules(self):
        a = self._create_node(name="A")
        b = self._create_node(name="B")
        edge = PathEdge(campus=self.campus, start_node=a, end_node=a, distance="5")
        with self.assertRaises(ValidationError):
            edge.clean()

        other = Campus.objects.create(university=self.university, name="Other")
        distant = PathNode.objects.create(campus=other, name="D")
        edge2 = PathEdge(campus=self.campus, start_node=a, end_node=distant, distance="5")
        with self.assertRaises(ValidationError):
            edge2.clean()

        edge3 = PathEdge(campus=other, start_node=a, end_node=b, distance="5")
        with self.assertRaises(ValidationError):
            edge3.clean()

    def test_path_edge_distance_must_be_positive(self):
        a = self._create_node(name="A")
        b = self._create_node(name="B")
        with self.assertRaises(ValidationError):
            PathEdge(campus=self.campus, start_node=a, end_node=b, distance="0").clean()

    def test_invalid_coordinates_rejected(self):
        with self.assertRaises(ValidationError):
            Campus(
                university=self.university, name="Bad", latitude="91", longitude="30"
            ).full_clean(exclude=["name"])
        with self.assertRaises(ValidationError):
            Campus(
                university=self.university, name="Bad", longitude="181", latitude="0"
            ).full_clean(exclude=["name"])

    def test_save_bumps_sync_version(self):
        v0 = self._version(self.campus)
        self.assertEqual(v0, 0)
        building = self._create_building()
        self.assertEqual(self._version(self.campus), 1)
        building.name = "Renamed"
        building.save()
        self.assertEqual(self._version(self.campus), 2)


# ---------------------------------------------------------------------------
# Campuses API
# ---------------------------------------------------------------------------

class CampusAPITests(MapTestCase):
    def url_list(self):
        return reverse("map-campus-list")

    def url_detail(self, campus):
        return reverse("map-campus-detail", args=[campus.id])

    def test_anonymous_can_list_and_retrieve(self):
        resp = self.client.get(self.url_list())
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("results", resp.data)

    def test_filter_campuses_by_university(self):
        other_univ = University.objects.create(name="Other U", country="KE")
        Campus.objects.create(university=other_univ, name="Other Uni Campus")
        resp = self.client.get(self.url_list(), {"university_id": self.university.id})
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["name"], self.campus.name)

    def test_inactive_campus_hidden_from_public_list(self):
        campus2 = Campus.objects.create(university=self.university, name="Closed", is_active=False)
        resp = self.client.get(self.url_list())
        names = [row["name"] for row in resp.data["results"]]
        self.assertIn(self.campus.name, names)
        self.assertNotIn("Closed", names)
        detail = self.client.get(self.url_detail(campus2))
        self.assertEqual(detail.status_code, status.HTTP_404_NOT_FOUND)

    def test_only_superuser_can_create_campus(self):
        data = {
            "university": str(self.university.id),
            "name": "New Campus",
            "location": {"type": "Point", "coordinates": [39.2, -6.8]},
        }
        self._auth(self.contributor).post(self.url_list(), data, format="json")
        self.assertEqual(Campus.objects.filter(name="New Campus").count(), 0)
        resp = self._auth(self.superuser).post(self.url_list(), data, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        created = Campus.objects.get(id=resp.data["id"])
        self.assertEqual(str(created.latitude), "-6.800000")
        self.assertEqual(str(created.longitude), "39.200000")

    def test_campus_admin_can_update_own_campus(self):
        resp = self._auth(self.campus_admin).patch(
            self.url_detail(self.campus), {"description": "Updated"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.campus.refresh_from_db()
        self.assertEqual(self.campus.description, "Updated")

    def test_contributor_cannot_update_campus(self):
        resp = self._auth(self.contributor).patch(
            self.url_detail(self.campus), {"description": "Nope"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_hard_delete_disabled(self):
        resp = self._auth(self.superuser).delete(self.url_detail(self.campus))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_map_data_endpoint_returns_full_dataset(self):
        building = self._create_building(code="CIV")
        place = self._create_place(building=building)
        a = self._create_node(name="A")
        b = self._create_node(name="B")
        self._create_edge(a, b)
        url = reverse("map-campus-data", args=[self.campus.id])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["campus"]["name"], self.campus.name)
        self.assertEqual(len(resp.data["buildings"]), 1)
        self.assertEqual(len(resp.data["places"]), 1)
        self.assertEqual(len(resp.data["path_nodes"]), 2)
        self.assertEqual(len(resp.data["path_edges"]), 1)
        self.assertEqual(resp.data["sync_version"], self._version(self.campus))
        self.assertTrue(resp.data["buildings"][0]["location"]["type"] == "Point")


# ---------------------------------------------------------------------------
# Buildings / Places / content API
# ---------------------------------------------------------------------------

class ContentAPITests(MapTestCase):
    def building_payload(self, **overrides):
        payload = {
            "campus": str(self.campus.id),
            "name": "Engineering Block",
            "code": "ENG3",
            "location": {"type": "Point", "coordinates": [39.200100, -6.790100]},
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [[39.2000, -6.7900], [39.2004, -6.7900], [39.2004, -6.7905], [39.2000, -6.7905], [39.2000, -6.7900]]
                ],
            },
        }
        payload.update(overrides)
        return payload

    def test_contributor_can_create_and_update_building(self):
        url = reverse("map-building-list")
        resp = self._auth(self.contributor).post(url, self.building_payload(), format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        building_id = resp.data["id"]
        self.assertTrue(resp.data["location"]["coordinates"] == [39.200100, -6.790100])

        detail = reverse("map-building-detail", args=[building_id])
        resp = self._auth(self.contributor).patch(detail, {"name": "New Name"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_viewer_cannot_create_building(self):
        url = reverse("map-building-list")
        resp = self._auth(self.viewer).post(url, self.building_payload(), format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_cannot_create_and_can_read(self):
        url = reverse("map-building-list")
        resp = self.client.post(url, self.building_payload(), format="json")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
        get_resp = self.client.get(url)
        self.assertEqual(get_resp.status_code, status.HTTP_200_OK)

    def test_building_filter_by_campus_active_and_search(self):
        self._create_building(name="Engineering", code="ENG")
        self._create_building(name="Library", code="LIB")
        inactive = self._create_building(name="Old Block", code="OLD", is_active=False)
        url = reverse("map-building-list")

        resp = self.client.get(url, {"campus": str(self.campus.id)})
        self.assertEqual(resp.data["count"], 2)

        resp = self.client.get(url, {"q": "engi"})
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["name"], "Engineering")

        resp = self.client.get(url, {"is_active": "false"})
        self.assertTrue(resp.data["count"] >= 1)

    def test_moderator_can_deactivate_building(self):
        building = self._create_building()
        detail = reverse("map-building-detail", args=[building.id])
        resp = self._auth(self.moderator).patch(detail, {"is_active": False}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        building.refresh_from_db()
        self.assertFalse(building.is_active)

    def test_viewer_cannot_deactivate(self):
        building = self._create_building()
        detail = reverse("map-building-detail", args=[building.id])
        resp = self._auth(self.viewer).patch(detail, {"is_active": False}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_hard_delete_requires_superuser(self):
        building = self._create_building()
        detail = reverse("map-building-detail", args=[building.id])
        resp = self._auth(self.moderator).delete(detail)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        resp = self._auth(self.superuser).delete(detail)
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Building.objects.filter(pk=building.id).exists())

    def test_place_invalid_building_campus_rejected(self):
        other = Campus.objects.create(university=self.university, name="Other")
        foreign_building = Building.objects.create(campus=other, name="B")
        url = reverse("map-place-list")
        payload = {
            "campus": str(self.campus.id),
            "building": str(foreign_building.id),
            "name": "Bad Place",
            "type": "office",
        }
        resp = self._auth(self.contributor).post(url, payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_listing_separate_endpoints_work(self):
        building = self._create_building()
        self._create_place(building=building)
        self.assertEqual(self.client.get(reverse("map-place-list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("map-pathnode-list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("map-pathedge-list")).status_code, 200)


class PhotoAPITests(MapTestCase):
    def test_upload_valid_photo_to_building(self):
        building = self._create_building()
        url = reverse("map-photo-list")
        resp = self._auth(self.contributor).post(
            url,
            {"campus": str(self.campus.id), "building": str(building.id), "image": make_png()},
            format="multipart",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertTrue(resp.data["url"].startswith("http"))

    def test_reject_non_image_file(self):
        building = self._create_building()
        url = reverse("map-photo-list")
        resp = self._auth(self.contributor).post(
            url,
            {"campus": str(self.campus.id), "building": str(building.id), "image": make_txt()},
            format="multipart",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reject_photo_without_target(self):
        url = reverse("map-photo-list")
        resp = self._auth(self.contributor).post(
            url,
            {"campus": str(self.campus.id), "image": make_png()},
            format="multipart",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reject_photo_with_both_targets(self):
        building = self._create_building()
        place = self._create_place()
        url = reverse("map-photo-list")
        resp = self._auth(self.contributor).post(
            url,
            {
                "campus": str(self.campus.id),
                "building": str(building.id),
                "place": str(place.id),
                "image": make_png(),
            },
            format="multipart",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# Navigation API
# ---------------------------------------------------------------------------

class NavigationAPITests(MapTestCase):
    def test_partner_edges_validated(self):
        a = self._create_node(name="A")
        b = self._create_node(name="B")
        url = reverse("map-pathedge-list")
        payload = {
            "campus": str(self.campus.id),
            "start_node": str(a.id),
            "end_node": str(a.id),
            "distance": "50",
        }
        resp = self._auth(self.contributor).post(url, payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        other = Campus.objects.create(university=self.university, name="Other")
        distant = PathNode.objects.create(campus=other, name="D")
        payload.update(start_node=str(a.id), end_node=str(distant.id))
        resp = self._auth(self.contributor).post(url, payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        payload.update(start_node=str(a.id), end_node=str(b.id), distance="-5")
        resp = self._auth(self.contributor).post(url, payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_graph_crud_as_contributor(self):
        a = self._create_node(name="A")
        b = self._create_node(name="B")
        edge = self._create_edge(a, b)
        self.assertTrue(PathEdge.objects.filter(pk=edge.pk).exists())


# ---------------------------------------------------------------------------
# Permissions / contributors / reports
# ---------------------------------------------------------------------------

class ContributorAndReportTests(MapTestCase):
    def test_only_campus_admin_manages_contributors(self):
        url = reverse("map-contributor-list")
        new_user = self._make_user("newbie@test.com", "Newbie")
        payload = {
            "user": str(new_user.id),
            "campus": str(self.campus.id),
            "role": "contributor",
            "status": "active",
        }
        resp = self._auth(self.contributor).post(url, payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        resp = self._auth(self.campus_admin).post(url, payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)

    def test_normal_user_can_submit_report(self):
        url = reverse("map-report-list")
        payload = {
            "campus": str(self.campus.id),
            "target_type": "building",
            "description": "Wrong location",
            "proposed_correction": {"location": [39.5, -6.8]},
        }
        resp = self._auth(self.normal).post(url, payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_only_moderator_can_review_report(self):
        report = ReportCorrection.objects.create(
            reporter=self.normal,
            campus=self.campus,
            target_type="building",
            description="Fix it",
        )
        detail = reverse("map-report-detail", args=[report.id])

        resp = self._auth(self.contributor).patch(detail, {"status": "accepted"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        resp = self._auth(self.moderator).patch(detail, {"status": "accepted"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        report.refresh_from_db()
        self.assertEqual(report.status, "accepted")
        self.assertEqual(report.reviewed_by, self.moderator)
        self.assertIsNotNone(report.reviewed_at)

    def test_normal_user_sees_only_own_reports(self):
        ReportCorrection.objects.create(
            reporter=self.contributor, campus=self.campus, target_type="place", description="Mine"
        )
        ReportCorrection.objects.create(
            reporter=self.moderator, campus=self.campus, target_type="place", description="Theirs"
        )
        resp = self._auth(self.normal).get(reverse("map-report-list"))
        self.assertEqual(resp.data["count"], 0)

        other = ReportCorrection.objects.create(
            reporter=self.normal, campus=self.campus, target_type="place", description="Gazza"
        )
        resp = self._auth(self.normal).get(reverse("map-report-list"))
        self.assertEqual(resp.data["count"], 1)


# ---------------------------------------------------------------------------
# Search & Nearby
# ---------------------------------------------------------------------------

class SearchAndNearbyTests(MapTestCase):
    def test_search_finds_building_and_place(self):
        self._create_building(name="Engineering", code="ENG")
        self._create_place(name="Main Cafeteria", type="cafeteria")
        url = reverse("map-search")
        resp = self.client.get(url, {"campus_id": self.campus.id, "q": "cafeteria"})
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["kind"], "place")

        resp = self.client.get(url, {"campus_id": self.campus.id, "q": "ENG"})
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["kind"], "building")

    def test_nearby_returns_within_radius(self):
        Building.objects.create(
            campus=self.campus, name="Near Building", latitude="-6.790000", longitude="39.200000"
        )
        Place.objects.create(
            campus=self.campus,
            name="Far Place",
            type="gate",
            latitude="-6.792200",  # ~245 m south
            longitude="39.200000",
        )
        url = reverse("map-nearby")
        resp = self.client.get(
            url, {"campus_id": self.campus.id, "lat": "-6.79", "lng": "39.20", "radius": 500}
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["buildings"]), 1)
        self.assertNotEqual(len(resp.data["places"]), 0)

        resp = self.client.get(
            url, {"campus_id": self.campus.id, "lat": "-6.79", "lng": "39.20", "radius": 100}
        )
        self.assertEqual(len(resp.data["buildings"]), 1)
        self.assertEqual(len(resp.data["places"]), 0)

    def test_nearby_validates_radius_and_coords(self):
        url = reverse("map-nearby")
        resp = self.client.get(url, {"campus_id": self.campus.id, "lat": "200", "lng": "39.2"})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        resp = self.client.get(url, {"campus_id": self.campus.id, "lat": "-6.79", "lng": "39.2", "radius": "-5"})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# Synchronization
# ---------------------------------------------------------------------------

class SyncAPITests(MapTestCase):
    def url_sync(self):
        return reverse("map-sync")

    def test_empty_changes_when_nothing_happened(self):
        resp = self.client.get(
            self.url_sync(), {"campus_id": self.campus.id, "since": 0}
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["current_version"], 0)
        self.assertEqual(resp.data["created"]["buildings"], [])
        self.assertEqual(resp.data["deleted"]["buildings"], [])

    def test_invalid_versions_rejected(self):
        # Negative version
        resp = self.client.get(self.url_sync(), {"campus_id": self.campus.id, "since": -1})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        # Missing since
        resp = self.client.get(self.url_sync(), {"campus_id": self.campus.id})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        # Missing campus
        resp = self.client.get(self.url_sync(), {"since": 0})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        # Version ahead of server
        resp = self.client.get(self.url_sync(), {"campus_id": self.campus.id, "since": 999})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_new_building_appears_as_created(self):
        v0 = self._version(self.campus)
        self._create_building()
        resp = self.client.get(self.url_sync(), {"campus_id": self.campus.id, "since": v0})
        created = resp.data["created"]["buildings"]
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0]["name"], "Engineering")

    def test_updated_building_after_change(self):
        building = self._create_building()
        v1 = self._version(self.campus)
        building.name = "Engineering Complex"
        building.save()
        resp = self.client.get(self.url_sync(), {"campus_id": self.campus.id, "since": v1})
        updated = resp.data["updated"]["buildings"]
        self.assertEqual(len(updated), 1)
        self.assertEqual(updated[0]["name"], "Engineering Complex")
        self.assertEqual(resp.data["updated"]["places"], [])

    def test_new_place_after_change(self):
        v0 = self._version(self.campus)
        self._create_place(name="New Lab", type="laboratory")
        resp = self.client.get(self.url_sync(), {"campus_id": self.campus.id, "since": v0})
        self.assertEqual(len(resp.data["created"]["places"]), 1)
        self.assertEqual(resp.data["created"]["places"][0]["name"], "New Lab")

    def test_deactivated_place_reported_in_deleted(self):
        place = self._create_place(name="Doomed")
        v1 = self._version(self.campus)
        place.is_active = False
        place.save()
        resp = self.client.get(self.url_sync(), {"campus_id": self.campus.id, "since": v1})
        deleted = resp.data["deleted"]["places"]
        self.assertEqual(len(deleted), 1)
        self.assertEqual(deleted[0]["action"], "deactivated")
        self.assertEqual(deleted[0]["object"]["name"], "Doomed")
        self.assertFalse(deleted[0]["object"]["is_active"])

    def test_hard_deleted_building_reported(self):
        building = self._create_building()
        v1 = self._version(self.campus)
        building.delete()
        resp = self.client.get(self.url_sync(), {"campus_id": self.campus.id, "since": v1})
        deleted = resp.data["deleted"]["buildings"]
        self.assertEqual(len(deleted), 1)
        self.assertEqual(deleted[0]["action"], "deleted")

    def test_navigation_changes_flow_through_sync(self):
        v0 = self._version(self.campus)
        a = self._create_node(name="A")
        b = self._create_node(name="B")
        edge = self._create_edge(a, b)
        v2 = self._version(self.campus)
        edge.distance = "300.000"
        edge.save()

        resp = self.client.get(self.url_sync(), {"campus_id": self.campus.id, "since": v0})
        self.assertEqual(len(resp.data["created"]["path_nodes"]), 2)
        self.assertEqual(len(resp.data["created"]["path_edges"]), 1)

        resp = self.client.get(self.url_sync(), {"campus_id": self.campus.id, "since": v2})
        updated = resp.data["updated"]["path_edges"]
        self.assertEqual(len(updated), 1)
        self.assertEqual(updated[0]["distance"], "300.000")

    def test_deterministic_cumulative_view(self):
        building = self._create_building()
        v1 = self._version(self.campus)
        resp_a = self.client.get(self.url_sync(), {"campus_id": self.campus.id, "since": 0})
        resp_b = self.client.get(self.url_sync(), {"campus_id": self.campus.id, "since": v1})
        self.assertEqual(len(resp_a.data["created"]["buildings"]), 1)
        self.assertEqual(resp_b.data["created"]["buildings"], [])

    def test_sync_while_authenticated_and_anonymous(self):
        self.client.force_authenticate(user=self.contributor)
        resp = self.client.get(self.url_sync(), {"campus_id": self.campus.id, "since": 0})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.client.force_authenticate(user=None)
        resp2 = self.client.get(self.url_sync(), {"campus_id": self.campus.id, "since": 0})
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# JWT auth end-to-end
# ---------------------------------------------------------------------------

class JWTAuthTests(MapTestCase):
    def test_real_jwt_flow(self):
        from rest_framework_simplejwt.tokens import RefreshToken

        token = RefreshToken.for_user(self.contributor).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        url = reverse("map-building-list")
        resp = self.client.post(url, {
            "campus": str(self.campus.id),
            "name": "JWT Block",
            "code": "JWT",
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
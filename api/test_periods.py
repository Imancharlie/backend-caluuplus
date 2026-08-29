import uuid

from django.test import TestCase
from rest_framework.test import APIClient

from api.models import (
    College,
    Course,
    Program,
    Student,
    StudentCourse,
    StudentCourseEnrollment,
    StudentTerm,
    University,
    User,
)
from api.views import _ensure_catalog_contribution
from tokens.models import TokenWallet


class PeriodStorageTests(TestCase):
    def setUp(self):
        self.uni = University.objects.create(name="Test Univ", country="Ghana")
        self.college = College.objects.create(name="Test College", university=self.uni)
        self.program = Program.objects.create(name="BSc CS", college=self.college, duration=4)
        self.user = User.objects.create_user(
            email="student@example.com", display_name="Student", password="pw"
        )
        self.student = Student.objects.create(
            user=self.user,
            university=self.uni,
            college=self.college,
            program=self.program,
            year=1,
            semester=1,
        )

    def test_set_period_preserves_other_periods_and_normalizes(self):
        sc = StudentCourse.objects.create(student=self.student)
        sc.set_period(1, 1, [{"code": "CS101", "name": "Intro", "credits": 3}])
        sc.set_period(1, 2, [{"code": "CS102", "name": "Algo", "credits": 3}])

        self.assertIn("1_1", sc.get_periods())
        self.assertIn("1_2", sc.get_periods())
        self.assertEqual(sc.period_count(), 2)

        self.assertEqual(sc.get_periods(), sc.get_periods())
        self.assertEqual(sc.courses["_v"], StudentCourse.PERIODS_VERSION)

        sc.set_period(1, 1, [{"code": "CS103", "name": "DB", "credits": 3}])
        self.assertEqual([c["code"] for c in sc.get_period(1, 2)], ["CS102"])
        self.assertEqual([c["code"] for c in sc.get_period(1, 1)], ["CS103"])

    def test_add_course_dedupes_within_period(self):
        sc = StudentCourse.objects.create(student=self.student)
        cid = str(uuid.uuid4())
        sc.set_period(1, 1, [{"id": cid, "code": "CS101", "name": "Intro", "credits": 3}])
        cd, added = sc.add_course_to_period(
            1, 1, {"id": cid, "code": "CS101", "name": "Intro", "credits": 3}
        )
        self.assertFalse(added)
        self.assertEqual(sc.period_count(), 1)

    def test_add_course_distinct_id_adds(self):
        sc = StudentCourse.objects.create(student=self.student)
        sc.set_period(1, 1, [{"code": "CS101", "name": "Intro", "credits": 3}])
        cd, added = sc.add_course_to_period(
            1, 1, {"code": "CS101", "name": "Intro", "credits": 3}
        )
        self.assertTrue(added)
        self.assertEqual(sc.period_count(), 2)

    def test_remove_course_and_remove_period(self):
        sc = StudentCourse.objects.create(student=self.student)
        sc.set_period(1, 1, [{"id": "11111111-1111-1111-1111-111111111111", "code": "CS101", "name": "Intro", "credits": 3}])
        sc.set_period(2, 1, [{"code": "CS201", "name": "Adv", "credits": 3}])

        self.assertTrue(sc.remove_course_from_period(1, 1, "11111111-1111-1111-1111-111111111111"))
        self.assertNotIn("1_1", sc.get_periods())

        self.assertTrue(sc.remove_period(2, 1))
        self.assertEqual(sc.period_count(), 0)
        self.assertEqual(sc.get_periods(), {})

    def test_contribution_creates_catalog_course_and_rewards(self):
        sc = StudentCourse.objects.create(student=self.student)
        sc.set_period(1, 1, [{"code": "CSNEW200", "name": "New Course", "credits": 4, "type": "elective"}])

        result = _ensure_catalog_contribution(self.student, 1, 1, sc.get_period(1, 1), reward=True)
        self.assertIsNotNone(result)
        self.assertEqual(result["contributed"], 1)
        self.assertEqual(result["rewarded"], 1)

        course = Course.objects.get(program=self.program, code="CSNEW200")
        self.assertEqual(course.name, "New Course")
        self.assertEqual(course.credits, 4)
        self.assertEqual(course.type, "elective")
        self.assertEqual(course.semester, 1)
        self.assertEqual(course.year, 1)

        wallet = TokenWallet.objects.get(user=self.user)
        self.assertGreaterEqual(wallet.earned_balance, 5)

        # Second identical save contributes/rewards nothing new (idempotent).
        result2 = _ensure_catalog_contribution(self.student, 1, 1, sc.get_period(1, 1), reward=True)
        self.assertIsNone(result2)
        wallet.refresh_from_db()
        self.assertEqual(wallet.earned_balance, 5)

    def test_contribution_skips_existing_catalog_course(self):
        Course.objects.create(
            program=self.program, code="EXIST10", name="Existing",
            credits=3, type="core", semester=1, year=1,
        )
        sc = StudentCourse.objects.create(student=self.student)
        sc.set_period(1, 1, [{"code": "exi st10", "name": "Existing", "credits": 3}])
        result = _ensure_catalog_contribution(self.student, 1, 1, sc.get_period(1, 1), reward=True)
        self.assertIsNone(result)
        self.assertEqual(Course.objects.filter(program=self.program).count(), 1)

class TermEnrollmentApiTests(TestCase):
    def setUp(self):
        self.uni = University.objects.create(name="Test Univ", country="Ghana")
        self.college = College.objects.create(name="Test College", university=self.uni)
        self.program = Program.objects.create(name="BSc CS", college=self.college, duration=4)
        self.user = User.objects.create_user(email="s@x.com", display_name="S", password="pw")
        self.student = Student.objects.create(
            user=self.user, university=self.uni, college=self.college,
            program=self.program, year=1, semester=1,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_list_terms_empty(self):
        resp = self.client.get('/api/students/terms/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['total'], 0)

    def test_put_courses_upserts_and_preserves_other_terms(self):
        url = '/api/students/terms/1/1/courses/'
        resp = self.client.put(url, {'courses': [
            {'code': 'CS101', 'name': 'Intro', 'credits': 3, 'type': 'core'},
            {'code': 'CS102', 'name': 'Algo', 'credits': 3, 'type': 'elective'},
        ]}, format='json')
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data['total_courses'], 2)
        self.assertEqual(sorted(c['code'] for c in resp.data['courses']), ['CS101', 'CS102'])

        # Replacing with just CS101 should drop CS102.
        resp2 = self.client.put(url, {'courses': [
            {'code': 'CS101', 'name': 'Intro Updated', 'credits': 4, 'type': 'core'},
        ]}, format='json')
        self.assertEqual(resp2.status_code, 200, resp2.data)
        self.assertEqual(resp2.data['total_courses'], 1)
        self.assertEqual(resp2.data['courses'][0]['code'], 'CS101')
        self.assertEqual(resp2.data['courses'][0]['name'], 'Intro Updated')
        self.assertEqual(resp2.data['courses'][0]['credits'], 4)

        # Other term untouched.
        term2 = StudentTerm.objects.create(student=self.student, academic_year=1, semester=2)
        StudentCourseEnrollment.objects.create(term=term2, code='CS201', name='Adv', credits=3)
        resp3 = self.client.put('/api/students/terms/1/1/courses/', {'courses': [
            {'code': 'CS101', 'name': 'Intro Updated', 'credits': 4, 'type': 'core'},
        ]}, format='json')
        self.assertEqual(resp3.status_code, 200)
        self.assertEqual(StudentCourseEnrollment.objects.filter(term=term2, code='CS201').count(), 1)

    def test_get_term_detail_returns_courses_and_catalog(self):
        Course.objects.create(program=self.program, code='CAT1', name='Cat', credits=3, type='core', semester=1, year=1)
        Course.objects.create(program=self.program, code='CAT2', name='Cat2', credits=3, type='core', semester=1, year=1)
        self.client.put('/api/students/terms/1/1/courses/', {'courses': [
            {'code': 'CAT1', 'name': 'Cat', 'credits': 3, 'type': 'core', 'course_id': str(Course.objects.get(code='CAT1').id)},
        ]}, format='json')

        resp = self.client.get('/api/students/terms/1/1/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['period'], '1_1')
        self.assertEqual(resp.data['total_courses'], 1)
        self.assertEqual(resp.data['courses'][0]['code'], 'CAT1')
        self.assertEqual(resp.data['catalog']['has_courses'], True)
        self.assertEqual(resp.data['catalog']['total'], 2)

    def test_put_grades_sets_grade_marks_points(self):
        self.client.put('/api/students/terms/1/1/courses/', {'courses': [
            {'code': 'CS101', 'name': 'Intro', 'credits': 3, 'type': 'core'},
        ]}, format='json')
        resp = self.client.put('/api/students/terms/1/1/grades/', {'courses': [
            {'code': 'CS101', 'grade': 'A', 'marks': 90},
        ]}, format='json')
        self.assertEqual(resp.status_code, 200, resp.data)
        course = resp.data['courses'][0]
        self.assertEqual(course['grade'], 'A')
        self.assertEqual(course['marks'], 90)
        self.assertEqual(course['points'], 5.0)

    def test_put_courses_accepts_empty_list(self):
        resp = self.client.put('/api/students/terms/1/1/courses/', {'courses': []}, format='json')
        self.assertEqual(resp.status_code, 200)

    def test_delete_single_course_from_term(self):
        self.client.put('/api/students/terms/1/1/courses/', {'courses': [
            {'code': 'CS101', 'name': 'Intro', 'credits': 3, 'type': 'core'},
            {'code': 'CS102', 'name': 'Algo', 'credits': 3, 'type': 'elective'},
        ]}, format='json')
        enroll = StudentCourseEnrollment.objects.get(term__student=self.student, code='CS101')
        resp = self.client.delete(f'/api/students/terms/1/1/courses/{enroll.id}/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(StudentCourseEnrollment.objects.filter(term__student=self.student).count(), 1)

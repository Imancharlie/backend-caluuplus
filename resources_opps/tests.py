from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse
from .models import Resource, Opportunity
from api.models import University, College, Program

User = get_user_model()


class ResourceAPITestCase(APITestCase):
    """Test cases for Resource API endpoints."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            display_name='Test User'
        )

        self.university = University.objects.create(
            name='Test University',
            country='Test Country'
        )

        self.resource_data = {
            'university': self.university.id,
            'title': 'Test Resource',
            'description': 'Test description for resource'
        }

        # Create a test PDF file
        self.test_file = SimpleUploadedFile(
            'test.pdf',
            b'Fake PDF content',
            content_type='application/pdf'
        )

    def test_create_resource_authenticated(self):
        """Test creating a resource with authentication."""
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            '/api/resources_opps/resources/',
            {
                **self.resource_data,
                'file': self.test_file
            },
            format='multipart'
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Resource.objects.count(), 1)

        resource = Resource.objects.first()
        self.assertEqual(resource.title, 'Test Resource')
        self.assertEqual(resource.created_by, self.user)
        self.assertEqual(resource.file_type, 'pdf')

    def test_create_resource_unauthenticated(self):
        """Test creating a resource without authentication."""
        response = self.client.post(
            '/api/resources_opps/resources/',
            self.resource_data,
            format='multipart'
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(Resource.objects.count(), 0)

    def test_list_resources(self):
        """Test listing resources."""
        # Create a resource first
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            '/api/resources_opps/resources/',
            {
                **self.resource_data,
                'file': self.test_file
            },
            format='multipart'
        )

        # List resources
        response = self.client.get('/api/resources_opps/resources/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)

        resource_data = response.data['results'][0]
        self.assertEqual(resource_data['title'], 'Test Resource')
        self.assertIn('file_url', resource_data)
        self.assertIn('file_size', resource_data)
        self.assertIn('created_by_name', resource_data)

    def test_filter_resources_by_university(self):
        """Test filtering resources by university."""
        # Create another university and resource
        university2 = University.objects.create(
            name='Test University 2',
            country='Test Country'
        )

        self.client.force_authenticate(user=self.user)

        # Create resource for first university
        response1 = self.client.post(
            '/api/resources_opps/resources/',
            {
                **self.resource_data,
                'file': self.test_file
            },
            format='multipart'
        )

        # Create resource for second university
        response2 = self.client.post(
            '/api/resources_opps/resources/',
            {
                'university': university2.id,
                'title': 'Test Resource 2',
                'description': 'Test description 2',
                'file': self.test_file
            },
            format='multipart'
        )

        # Filter by first university
        response = self.client.get(f'/api/resources_opps/resources/?university={self.university.id}')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['title'], 'Test Resource')

    def test_search_resources(self):
        """Test searching resources."""
        self.client.force_authenticate(user=self.user)

        # Create resource
        self.client.post(
            '/api/resources_opps/resources/',
            {
                **self.resource_data,
                'file': self.test_file
            },
            format='multipart'
        )

        # Search by title
        response = self.client.get('/api/resources_opps/resources/?search=Test')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)

        # Search for non-existent term
        response = self.client.get('/api/resources_opps/resources/?search=nonexistent')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 0)

    def test_resource_file_validation(self):
        """Test file validation for resources."""
        self.client.force_authenticate(user=self.user)

        # Test with invalid file type (too large)
        large_file = SimpleUploadedFile(
            'large.pdf',
            b'x' * (51 * 1024 * 1024),  # 51MB file
            content_type='application/pdf'
        )

        response = self.client.post(
            '/api/resources_opps/resources/',
            {
                **self.resource_data,
                'file': large_file
            },
            format='multipart'
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_resource(self):
        """Test updating a resource."""
        self.client.force_authenticate(user=self.user)

        # Create resource
        response = self.client.post(
            '/api/resources_opps/resources/',
            {
                **self.resource_data,
                'file': self.test_file
            },
            format='multipart'
        )

        resource_id = response.data['id']

        # Update resource
        update_data = {
            'title': 'Updated Resource Title',
            'description': 'Updated description'
        }

        response = self.client.patch(
            f'/api/resources_opps/resources/{resource_id}/',
            update_data,
            content_type='application/json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], 'Updated Resource Title')

    def test_delete_resource(self):
        """Test deleting a resource."""
        self.client.force_authenticate(user=self.user)

        # Create resource
        response = self.client.post(
            '/api/resources_opps/resources/',
            {
                **self.resource_data,
                'file': self.test_file
            },
            format='multipart'
        )

        resource_id = response.data['id']
        self.assertEqual(Resource.objects.count(), 1)

        # Delete resource
        response = self.client.delete(f'/api/resources_opps/resources/{resource_id}/')

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Resource.objects.count(), 0)


class OpportunityAPITestCase(APITestCase):
    """Test cases for Opportunity API endpoints."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            display_name='Test User'
        )

        self.university = University.objects.create(
            name='Test University',
            country='Test Country'
        )

        self.opportunity_data = {
            'university': self.university.id,
            'category': 'seminar',
            'title': 'Test Seminar',
            'content': 'This is a test seminar opportunity.'
        }

        # Create a test image file
        self.test_image = SimpleUploadedFile(
            'test.jpg',
            b'Fake image content',
            content_type='image/jpeg'
        )

    def test_create_opportunity_authenticated(self):
        """Test creating an opportunity with authentication."""
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            '/api/resources_opps/opportunities/',
            {
                **self.opportunity_data,
                'cover_media': self.test_image
            },
            format='multipart'
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Opportunity.objects.count(), 1)

        opportunity = Opportunity.objects.first()
        self.assertEqual(opportunity.title, 'Test Seminar')
        self.assertEqual(opportunity.created_by, self.user)
        self.assertEqual(opportunity.media_type, 'image')

    def test_list_opportunities(self):
        """Test listing opportunities."""
        # Create an opportunity first
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            '/api/resources_opps/opportunities/',
            self.opportunity_data,
            content_type='application/json'
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # List opportunities
        response = self.client.get('/api/resources_opps/opportunities/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)

        opportunity_data = response.data['results'][0]
        self.assertEqual(opportunity_data['title'], 'Test Seminar')
        self.assertIn('cover_media_url', opportunity_data)
        self.assertIn('days_remaining', opportunity_data)
        self.assertIn('is_active', opportunity_data)

    def test_filter_opportunities_by_category(self):
        """Test filtering opportunities by category."""
        self.client.force_authenticate(user=self.user)

        # Create opportunities with different categories
        categories = ['seminar', 'competition', 'job']

        for i, category in enumerate(categories):
            response = self.client.post(
                '/api/resources_opps/opportunities/',
                {
                    **self.opportunity_data,
                    'category': category,
                    'title': f'Test {category.title()} {i+1}'
                },
                content_type='application/json'
            )

        # Filter by seminar category
        response = self.client.get('/api/resources_opps/opportunities/?category=seminar')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['category'], 'seminar')

    def test_filter_opportunities_by_university(self):
        """Test filtering opportunities by university."""
        # Create another university
        university2 = University.objects.create(
            name='Test University 2',
            country='Test Country'
        )

        self.client.force_authenticate(user=self.user)

        # Create opportunity for first university
        response1 = self.client.post(
            '/api/resources_opps/opportunities/',
            self.opportunity_data,
            content_type='application/json'
        )

        # Create opportunity for second university
        response2 = self.client.post(
            '/api/resources_opps/opportunities/',
            {
                **self.opportunity_data,
                'university': university2.id,
                'title': 'Test Opportunity 2'
            },
            content_type='application/json'
        )

        # Filter by first university
        response = self.client.get(f'/api/resources_opps/opportunities/?university={self.university.id}')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['title'], 'Test Seminar')

    def test_opportunity_categories_endpoint(self):
        """Test the categories endpoint."""
        response = self.client.get('/api/resources_opps/opportunities/categories/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 7)  # All categories from model

        # Check that it returns the expected format
        category = response.data[0]
        self.assertIn('value', category)
        self.assertIn('label', category)

    def test_opportunity_stats_endpoint(self):
        """Test the stats endpoint."""
        self.client.force_authenticate(user=self.user)

        # Create a few opportunities
        for i in range(3):
            self.client.post(
                '/api/resources_opps/opportunities/',
                {
                    **self.opportunity_data,
                    'title': f'Test Opportunity {i+1}'
                },
                content_type='application/json'
            )

        response = self.client.get('/api/resources_opps/opportunities/stats/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('total_opportunities', response.data)
        self.assertIn('category_breakdown', response.data)
        self.assertIn('university_breakdown', response.data)
        self.assertEqual(response.data['total_opportunities'], 3)

    def test_opportunity_date_validation(self):
        """Test date validation for opportunities."""
        self.client.force_authenticate(user=self.user)

        # Test invalid date range (start after end)
        invalid_data = {
            **self.opportunity_data,
            'start_date': '2024-12-31',
            'end_date': '2024-01-01'
        }

        response = self.client.post(
            '/api/resources_opps/opportunities/',
            invalid_data,
            content_type='application/json'
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_opportunity_media_validation(self):
        """Test media file validation for opportunities."""
        self.client.force_authenticate(user=self.user)

        # Test with invalid media file (too large)
        large_image = SimpleUploadedFile(
            'large.jpg',
            b'x' * (11 * 1024 * 1024),  # 11MB file
            content_type='image/jpeg'
        )

        response = self.client.post(
            '/api/resources_opps/opportunities/',
            {
                **self.opportunity_data,
                'cover_media': large_image
            },
            format='multipart'
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_opportunity_active_status(self):
        """Test the is_active field calculation."""
        from datetime import date, timedelta
        self.client.force_authenticate(user=self.user)

        # Create opportunity that starts tomorrow and ends in 7 days
        future_data = {
            **self.opportunity_data,
            'start_date': (date.today() + timedelta(days=1)).isoformat(),
            'end_date': (date.today() + timedelta(days=7)).isoformat()
        }

        response = self.client.post(
            '/api/resources_opps/opportunities/',
            future_data,
            content_type='application/json'
        )

        # Should not be active yet (starts tomorrow)
        self.assertEqual(response.data['is_active'], False)

        # Create opportunity that is currently active
        active_data = {
            **self.opportunity_data,
            'start_date': (date.today() - timedelta(days=1)).isoformat(),
            'end_date': (date.today() + timedelta(days=5)).isoformat()
        }

        response = self.client.post(
            '/api/resources_opps/opportunities/',
            active_data,
            content_type='application/json'
        )

        # Should be active
        self.assertEqual(response.data['is_active'], True)

    def test_search_opportunities(self):
        """Test searching opportunities."""
        self.client.force_authenticate(user=self.user)

        # Create opportunity
        self.client.post(
            '/api/resources_opps/opportunities/',
            self.opportunity_data,
            content_type='application/json'
        )

        # Search by title
        response = self.client.get('/api/resources_opps/opportunities/?search=Seminar')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)

        # Search for non-existent term
        response = self.client.get('/api/resources_opps/opportunities/?search=nonexistent')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 0)

    def test_create_with_empty_optional_fields(self):
        """Frontend often sends empty strings for optional fields in FormData."""
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            '/api/resources_opps/opportunities/',
            {
                **self.opportunity_data,
                'application_url': '',
                'start_date': '',
                'end_date': '',
            },
            content_type='application/json'
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_create_with_description_alias(self):
        """Accept description as an alias for content."""
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            '/api/resources_opps/opportunities/',
            {
                'university': self.university.id,
                'category': 'seminar',
                'title': 'Alias Test',
                'description': 'Submitted via description field.',
            },
            content_type='application/json'
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['content'], 'Submitted via description field.')

    def test_create_with_normalized_category(self):
        """Accept human-readable category labels from frontend selects."""
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            '/api/resources_opps/opportunities/',
            {
                **self.opportunity_data,
                'category': 'Online Course',
                'title': 'Category Label Test',
            },
            content_type='application/json'
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['category'], 'online_course')

    def test_create_without_university_uses_student_profile(self):
        """Auto-fill university from the authenticated student's profile."""
        from api.models import College, Program, Student

        college = College.objects.create(name='Test College', university=self.university)
        program = Program.objects.create(name='Test Program', college=college, duration=4)
        Student.objects.create(
            user=self.user,
            university=self.university,
            college=college,
            program=program,
            year=1,
            semester=1,
        )
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            '/api/resources_opps/opportunities/',
            {
                'category': 'seminar',
                'title': 'Auto University Test',
                'content': 'University should be inferred from profile.',
            },
            content_type='application/json'
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(str(response.data['university']), str(self.university.id))

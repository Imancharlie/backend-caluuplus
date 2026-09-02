c:\Users\USER\Downloads\udsm_buildings.geojson c:\Users\USER\Downloads\udsm_paths.geojson# Resources & Opportunities API Guide

This guide documents the complete API for the Resources and Opportunities Django app, designed for integration with React frontend applications.

## Overview

The `resources_opps` app provides two main models:
- **Resource**: Academic resources with file uploads (PDFs, documents, etc.)
- **Opportunity**: Opportunities like seminars, competitions, jobs, scholarships, etc.

## Base URL

All endpoints are prefixed with `/api/resources_opps/`

## Authentication

Most endpoints require authentication. Use JWT tokens in the Authorization header:

```
Authorization: Bearer <your-jwt-token>
```

## Models

### Resource Model

```json
{
  "id": "uuid",
  "university": "uuid",
  "university_name": "University of Dar es Salaam",
  "title": "Introduction to Computer Science",
  "description": "Comprehensive guide to CS fundamentals",
  "file": "resources/files/intro_cs.pdf",
  "file_type": "pdf",
  "file_size": "2.5MB",
  "file_url": "http://localhost:8000/media/resources/files/intro_cs.pdf",
  "created_by": "uuid",
  "created_by_name": "John Doe",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:00Z"
}
```

### Opportunity Model

```json
{
  "id": "uuid",
  "university": "uuid",
  "university_name": "University of Dar es Salaam",
  "category": "seminar",
  "title": "AI in Healthcare Seminar",
  "cover_media": "opportunities/media/ai_seminar.jpg",
  "cover_media_url": "http://localhost:8000/media/opportunities/media/ai_seminar.jpg",
  "media_type": "image",
  "content": "Join us for an exciting seminar on AI applications in healthcare...",
  "created_by": "uuid",
  "created_by_name": "Jane Smith",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:00Z",
  "start_date": "2024-02-01",
  "end_date": "2024-02-01",
  "application_url": "https://example.com/apply",
  "days_remaining": 17,
  "is_active": true
}
```

## Endpoints

### Resources

#### List Resources
```http
GET /api/resources_opps/resources/
```

**Query Parameters:**
- `university`: Filter by university ID
- `file_type`: Filter by file type (pdf, doc, image, etc.)
- `search`: Search in title and description
- `page`: Page number for pagination
- `limit`: Items per page (default: 12)

**Response:**
```json
{
  "count": 25,
  "next": "http://localhost:8000/api/resources_opps/resources/?page=2",
  "previous": null,
  "results": [
    {
      "id": "uuid",
      "university_name": "University of Dar es Salaam",
      "title": "Computer Science Notes",
      "file_size": "1.2MB",
      "file_url": "http://localhost:8000/media/resources/files/cs_notes.pdf",
      "created_by_name": "Dr. Smith",
      "created_at": "2024-01-15T10:30:00Z"
    }
  ]
}
```

#### Create Resource
```http
POST /api/resources_opps/resources/
Content-Type: multipart/form-data

{
  "university": "uuid",
  "title": "New Resource",
  "description": "Resource description",
  "file": <file-upload>
}
```

**Response:** Created resource object

#### Retrieve Resource
```http
GET /api/resources_opps/resources/{id}/
```

**Response:** Single resource object

#### Update Resource
```http
PUT /api/resources_opps/resources/{id}/
PATCH /api/resources_opps/resources/{id}/
Content-Type: application/json

{
  "title": "Updated Title",
  "description": "Updated description"
}
```

#### Delete Resource
```http
DELETE /api/resources_opps/resources/{id}/
```

#### Download Resource File
```http
GET /api/resources_opps/resources/{id}/download/
```

Downloads the actual file attached to the resource.

### Opportunities

#### List Opportunities
```http
GET /api/resources_opps/opportunities/
```

**Query Parameters:**
- `university`: Filter by university ID
- `category`: Filter by category (seminar, competition, job, etc.)
- `start_date`: Filter by start date (YYYY-MM-DD)
- `end_date`: Filter by end date (YYYY-MM-DD)
- `search`: Search in title and content
- `page`: Page number for pagination

**Response:**
```json
{
  "count": 15,
  "results": [
    {
      "id": "uuid",
      "university_name": "University of Dar es Salaam",
      "category": "seminar",
      "title": "AI Seminar",
      "cover_media_url": "http://localhost:8000/media/opportunities/media/ai.jpg",
      "days_remaining": 5,
      "is_active": true,
      "created_at": "2024-01-15T10:30:00Z"
    }
  ]
}
```

#### Create Opportunity
```http
POST /api/resources_opps/opportunities/
Content-Type: multipart/form-data

{
  "university": "uuid",
  "category": "seminar",
  "title": "New Seminar",
  "content": "Seminar description",
  "start_date": "2024-02-01",
  "end_date": "2024-02-01",
  "cover_media": <image-file>
}
```

**Response:** Created opportunity object

#### Retrieve Opportunity
```http
GET /api/resources_opps/opportunities/{id}/
```

**Response:** Single opportunity object

#### Update Opportunity
```http
PUT /api/resources_opps/opportunities/{id}/
PATCH /api/resources_opps/opportunities/{id}/
Content-Type: application/json

{
  "title": "Updated Title",
  "content": "Updated content"
}
```

#### Delete Opportunity
```http
DELETE /api/resources_opps/opportunities/{id}/
```

#### Download Opportunity Media
```http
GET /api/resources_opps/opportunities/{id}/download_media/
```

Downloads the cover media file.

#### Get Opportunity Categories
```http
GET /api/resources_opps/opportunities/categories/
```

**Response:**
```json
[
  {"value": "seminar", "label": "Seminar"},
  {"value": "competition", "label": "Competition"},
  {"value": "job", "label": "Job"},
  {"value": "meeting", "label": "Meeting"},
  {"value": "scholarship", "label": "Scholarship"},
  {"value": "internship", "label": "Internship"},
  {"value": "online_course", "label": "Online Course"}
]
```

#### Get Opportunity Statistics
```http
GET /api/resources_opps/opportunities/stats/
```

**Response:**
```json
{
  "total_opportunities": 45,
  "category_breakdown": {
    "seminar": 12,
    "competition": 8,
    "job": 15,
    "scholarship": 10
  },
  "university_breakdown": {
    "University of Dar es Salaam": 25,
    "Muhimbili University": 12,
    "Sokoine University": 8
  }
}
```

## File Uploads

### Supported File Types

#### Resources
- Documents: PDF, DOC, DOCX, XLS, XLSX, PPT, PPTX, TXT
- Archives: ZIP, RAR
- Media: Images (JPG, PNG, GIF, WebP), Videos (MP4, AVI, MOV), Audio (MP3, WAV)
- Maximum size: 50MB

#### Opportunities (Cover Media)
- Images: JPG, PNG, GIF, WebP
- Videos: MP4, AVI, MOV
- Maximum size: 10MB

### File Upload Requirements

For file uploads, use `multipart/form-data` content type:

```javascript
const formData = new FormData();
formData.append('university', universityId);
formData.append('title', 'My Resource');
formData.append('description', 'Resource description');
formData.append('file', fileInput.files[0]);

fetch('/api/resources_opps/resources/', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`
  },
  body: formData
});
```

## Filtering Examples

### Filter Resources by University
```http
GET /api/resources_opps/resources/?university=uuid-here
```

### Filter Opportunities by Category
```http
GET /api/resources_opps/opportunities/?category=seminar
```

### Filter Opportunities by Date Range
```http
GET /api/resources_opps/opportunities/?start_date=2024-02-01&end_date=2024-02-28
```

### Search Resources
```http
GET /api/resources_opps/resources/?search=computer+science
```

### Combine Multiple Filters
```http
GET /api/resources_opps/opportunities/?university=uuid&category=seminar&search=AI
```

## Error Handling

### Common Error Responses

#### 400 Bad Request
```json
{
  "file": ["File size must be less than 50.0MB."],
  "title": ["This field is required."]
}
```

#### 401 Unauthorized
```json
{
  "detail": "Authentication credentials were not provided."
}
```

#### 403 Forbidden
```json
{
  "detail": "You do not have permission to perform this action."
}
```

#### 404 Not Found
```json
{
  "detail": "Not found."
}
```

#### 415 Unsupported Media Type
```json
{
  "detail": "Unsupported media type 'application/json' in request."
}
```
*Note: Use `multipart/form-data` for file uploads, `application/json` for regular data.*

## React Integration Examples

### Fetch Resources
```javascript
const fetchResources = async (universityId) => {
  const response = await fetch(
    `/api/resources_opps/resources/?university=${universityId}`,
    {
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      }
    }
  );
  const data = await response.json();
  return data.results;
};
```

### Upload Resource
```javascript
const uploadResource = async (formData) => {
  const response = await fetch('/api/resources_opps/resources/', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`
    },
    body: formData // FormData object with file
  });

  if (!response.ok) {
    throw new Error('Upload failed');
  }

  return await response.json();
};
```

### Download File
```javascript
const downloadResource = async (resourceId) => {
  const response = await fetch(
    `/api/resources_opps/resources/${resourceId}/download/`,
    {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    }
  );

  const blob = await response.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'resource.pdf';
  document.body.appendChild(a);
  a.click();
  window.URL.revokeObjectURL(url);
};
```

## Pagination

All list endpoints support pagination:

```json
{
  "count": 100,
  "next": "http://localhost:8000/api/resources_opps/resources/?page=2",
  "previous": null,
  "results": [...]
}
```

Use `?page=2&limit=20` to control pagination.

## Rate Limiting

The API implements basic rate limiting. Be respectful with request frequency.

## Development Setup

1. Install dependencies:
```bash
pip install python-magic django-filter
```

2. Run migrations:
```bash
python manage.py migrate
```

3. Run tests:
```bash
python manage.py test resources_opps
```

4. Access API at: `http://localhost:8000/api/resources_opps/`

## Support

For issues or questions about the API, refer to the Django REST Framework documentation or check the test files for usage examples.








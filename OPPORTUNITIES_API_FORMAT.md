# Opportunities API Endpoint Format Guide

## Base URL
```
/api/resources_opps/opportunities/
```

## Authentication
All endpoints require authentication except GET (list and retrieve) operations.

---

## Endpoints Overview

### 1. List Opportunities
**GET** `/api/resources_opps/opportunities/`

Returns a list of opportunities filtered by user's university and query parameters.

#### Query Parameters:
- `university` (integer, optional) - Filter by university ID (admin/staff only)
- `category` (string, optional) - Filter by category
  - Values: `seminar`, `competition`, `job`, `meeting`, `scholarship`, `internship`, `online_course`
- `start_date` (date, optional) - Filter opportunities starting from this date (YYYY-MM-DD)
- `end_date` (date, optional) - Filter opportunities ending before this date (YYYY-MM-DD)
- `search` (string, optional) - Search in title and content
- `page` (integer, optional) - Page number for pagination
- `page_size` (integer, optional) - Items per page

#### Response (200 OK):
```json
[
  {
    "id": "uuid",
    "university": "uuid-or-null",
    "university_name": "University Name or null",
    "category": "seminar",
    "title": "Opportunity Title",
    "cover_media": "file-path-or-null",
    "cover_media_url": "http://domain.com/media/opportunities/media/file.jpg",
    "media_type": "image",
    "content": "Full description of the opportunity...",
    "created_by": "user-uuid",
    "created_by_name": "Creator Name",
    "created_at": "2024-01-15T10:30:00Z",
    "updated_at": "2024-01-15T10:30:00Z",
    "start_date": "2024-02-01",
    "end_date": "2024-02-28",
    "application_url": "https://example.com/apply",
    "days_remaining": 15,
    "is_active": true
  }
]
```

#### Example Requests:
```bash
# Get all opportunities for user's university
GET /api/resources_opps/opportunities/

# Filter by category
GET /api/resources_opps/opportunities/?category=scholarship

# Search opportunities
GET /api/resources_opps/opportunities/?search=engineering

# Filter by date range
GET /api/resources_opps/opportunities/?start_date=2024-02-01&end_date=2024-02-28

# Combine filters
GET /api/resources_opps/opportunities/?category=job&search=software&start_date=2024-01-01
```

---

### 2. Retrieve Single Opportunity
**GET** `/api/resources_opps/opportunities/{id}/`

Returns details of a specific opportunity.

#### Response (200 OK):
```json
{
  "id": "uuid",
  "university": "uuid-or-null",
  "university_name": "University Name",
  "category": "scholarship",
  "title": "Scholarship Opportunity",
  "cover_media": "file-path",
  "cover_media_url": "http://domain.com/media/opportunities/media/scholarship.jpg",
  "media_type": "image",
  "content": "Detailed description...",
  "created_by": "user-uuid",
  "created_by_name": "Admin User",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:00Z",
  "start_date": "2024-02-01",
  "end_date": "2024-03-31",
  "application_url": "https://example.com/apply",
  "days_remaining": 45,
  "is_active": true
}
```

#### Error Responses:
- `404 Not Found` - Opportunity doesn't exist or not accessible

---

### 3. Create Opportunity
**POST** `/api/resources_opps/opportunities/`

Creates a new opportunity. Requires authentication.

#### Request Headers:
```
Content-Type: multipart/form-data
Authorization: Bearer {token}
```

#### Request Body (Form Data):
```form-data
university: uuid (optional) - University ID, null for all universities
category: string (required) - One of: seminar, competition, job, meeting, scholarship, internship, online_course
title: string (required) - Max 255 characters
cover_media: file (optional) - Image or video file (max 10MB)
content: string (required) - Full description/explanation
start_date: date (optional) - Format: YYYY-MM-DD
end_date: date (optional) - Format: YYYY-MM-DD
application_url: url (optional) - Application link
```

#### Request Example (JSON):
```json
{
  "university": "uuid-or-null",
  "category": "scholarship",
  "title": "Engineering Scholarship 2024",
  "content": "Full scholarship opportunity for engineering students...",
  "start_date": "2024-02-01",
  "end_date": "2024-03-31",
  "application_url": "https://example.com/apply"
}
```

#### Request Example (Form Data with File):
```bash
curl -X POST \
  http://localhost:8000/api/resources_opps/opportunities/ \
  -H "Authorization: Bearer {token}" \
  -F "category=scholarship" \
  -F "title=Engineering Scholarship 2024" \
  -F "content=Full scholarship opportunity..." \
  -F "start_date=2024-02-01" \
  -F "end_date=2024-03-31" \
  -F "application_url=https://example.com/apply" \
  -F "cover_media=@/path/to/image.jpg"
```

#### Response (201 Created):
```json
{
  "id": "uuid",
  "university": "uuid",
  "university_name": "University Name",
  "category": "scholarship",
  "title": "Engineering Scholarship 2024",
  "cover_media": "opportunities/media/image.jpg",
  "cover_media_url": "http://domain.com/media/opportunities/media/image.jpg",
  "media_type": "image",
  "content": "Full scholarship opportunity...",
  "created_by": "user-uuid",
  "created_by_name": "Your Name",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:00Z",
  "start_date": "2024-02-01",
  "end_date": "2024-03-31",
  "application_url": "https://example.com/apply",
  "days_remaining": 45,
  "is_active": true
}
```

#### Error Responses:
- `400 Bad Request` - Validation errors
- `401 Unauthorized` - Not authenticated

#### Validation Rules:
- `category` must be one of the valid choices
- `title` is required, max 255 characters
- `content` is required
- `cover_media` must be image or video, max 10MB
- `start_date` must be before or equal to `end_date` if both provided
- `application_url` must be a valid URL format

---

### 4. Update Opportunity
**PUT/PATCH** `/api/resources_opps/opportunities/{id}/`

Updates an existing opportunity. Requires authentication.

- **PUT**: Update all fields (requires all fields)
- **PATCH**: Partial update (only provided fields)

#### Request Headers:
```
Content-Type: multipart/form-data (if including file) or application/json
Authorization: Bearer {token}
```

#### Request Body:
Same format as Create, but all fields are optional for PATCH.

#### Response (200 OK):
Same format as Create response.

#### Error Responses:
- `400 Bad Request` - Validation errors
- `401 Unauthorized` - Not authenticated
- `404 Not Found` - Opportunity doesn't exist

---

### 5. Delete Opportunity
**DELETE** `/api/resources_opps/opportunities/{id}/`

Deletes an opportunity. Requires authentication.

#### Response (204 No Content):
Empty response body.

#### Error Responses:
- `401 Unauthorized` - Not authenticated
- `404 Not Found` - Opportunity doesn't exist

---

### 6. Download Cover Media
**GET** `/api/resources_opps/opportunities/{id}/download_media/`

Downloads the cover media file for an opportunity.

#### Response (200 OK):
File download with appropriate content-type headers.

#### Error Responses:
- `404 Not Found` - Opportunity or media doesn't exist

---

### 7. Get Categories
**GET** `/api/resources_opps/opportunities/categories/`

Returns all available opportunity categories.

#### Response (200 OK):
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

---

### 8. Get Statistics
**GET** `/api/resources_opps/opportunities/stats/`

Returns statistics about opportunities (filtered by user's university).

#### Response (200 OK):
```json
{
  "total_opportunities": 150,
  "category_breakdown": {
    "seminar": 25,
    "competition": 15,
    "job": 40,
    "meeting": 10,
    "scholarship": 30,
    "internship": 20,
    "online_course": 10
  },
  "university_breakdown": {
    "University A": 50,
    "University B": 40,
    "University C": 60
  }
}
```

---

## Category Values

| Value | Label |
|-------|-------|
| `seminar` | Seminar |
| `competition` | Competition |
| `job` | Job |
| `meeting` | Meeting |
| `scholarship` | Scholarship |
| `internship` | Internship |
| `online_course` | Online Course |

---

## Media Type Values

| Value | Description |
|-------|-------------|
| `image` | Image file (jpg, jpeg, png, gif, webp) |
| `video` | Video file (mp4, avi, mov) |

---

## Field Descriptions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | UUID | Auto | Unique identifier |
| `university` | UUID | No | University ID (null for all universities) |
| `category` | String | Yes | Opportunity category |
| `title` | String | Yes | Title (max 255 chars) |
| `cover_media` | File | No | Cover image/video (max 10MB) |
| `media_type` | String | Auto | `image` or `video` (auto-detected) |
| `content` | Text | Yes | Full description/explanation |
| `start_date` | Date | No | Start date (YYYY-MM-DD) |
| `end_date` | Date | No | End date (YYYY-MM-DD) |
| `application_url` | URL | No | Application link |
| `created_by` | UUID | Auto | Creator user ID |
| `created_at` | DateTime | Auto | Creation timestamp |
| `updated_at` | DateTime | Auto | Last update timestamp |
| `days_remaining` | Integer | Read-only | Days until end_date |
| `is_active` | Boolean | Read-only | Whether opportunity is currently active |

---

## Example Usage

### JavaScript/Fetch Example:
```javascript
// List opportunities
const response = await fetch('/api/resources_opps/opportunities/?category=scholarship', {
  headers: {
    'Authorization': `Bearer ${token}`
  }
});
const opportunities = await response.json();

// Create opportunity
const formData = new FormData();
formData.append('category', 'scholarship');
formData.append('title', 'Engineering Scholarship');
formData.append('content', 'Full description...');
formData.append('start_date', '2024-02-01');
formData.append('end_date', '2024-03-31');
formData.append('application_url', 'https://example.com/apply');
formData.append('cover_media', fileInput.files[0]);

const createResponse = await fetch('/api/resources_opps/opportunities/', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`
  },
  body: formData
});
const newOpportunity = await createResponse.json();
```

### Python/Requests Example:
```python
import requests

# List opportunities
response = requests.get(
    'http://localhost:8000/api/resources_opps/opportunities/',
    params={'category': 'scholarship'},
    headers={'Authorization': f'Bearer {token}'}
)
opportunities = response.json()

# Create opportunity
data = {
    'category': 'scholarship',
    'title': 'Engineering Scholarship',
    'content': 'Full description...',
    'start_date': '2024-02-01',
    'end_date': '2024-03-31',
    'application_url': 'https://example.com/apply'
}
files = {'cover_media': open('image.jpg', 'rb')}

response = requests.post(
    'http://localhost:8000/api/resources_opps/opportunities/',
    data=data,
    files=files,
    headers={'Authorization': f'Bearer {token}'}
)
new_opportunity = response.json()
```

---

## Notes

1. **University Filtering**: Users automatically see opportunities from their university plus general (university=null) opportunities
2. **File Uploads**: Use `multipart/form-data` when including files
3. **Date Format**: Always use `YYYY-MM-DD` format for dates
4. **Media Size**: Cover media files are limited to 10MB
5. **Auto Fields**: `media_type`, `days_remaining`, and `is_active` are calculated automatically
6. **Permissions**: Create/Update/Delete require authentication; List/Retrieve are public


















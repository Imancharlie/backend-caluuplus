# Opportunities API - Complete Endpoint Documentation

This document provides complete endpoint specifications and data formats required for the full opportunities functionality, including user submissions and admin approval workflow.

## Base URL
```
http://localhost:8000/api/resources_opps/opportunities/
```

## Authentication
All endpoints require JWT authentication:
```
Authorization: Bearer <your_jwt_token>
```

---

## 1. List Opportunities (Public View)

**Endpoint:** `GET /api/resources_opps/opportunities/`

**Purpose:** Get all approved and active opportunities visible to the public

**Query Parameters:**
- `university` (optional): Filter by university ID (UUID)
- `category` (optional): Filter by category (seminar, competition, job, scholarship, internship, meeting, online_course)
- `start_date` (optional): Filter by start date (YYYY-MM-DD)
- `end_date` (optional): Filter by end date (YYYY-MM-DD)
- `search` (optional): Search in title and content
- `page` (optional): Page number for pagination (default: 1)
- `limit` (optional): Items per page (default: 12)

**Backend Requirement:** 
- **MUST** filter to only return opportunities where `is_active = true`
- **MUST NOT** return opportunities with `status = 'pending'` or `status = 'rejected'`

**Response (200):**
```json
{
  "count": 25,
  "next": "http://localhost:8000/api/resources_opps/opportunities/?page=2",
  "previous": null,
  "results": [
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
      "is_active": true,
      "status": "approved"
    }
  ]
}
```

---

## 2. List User's Own Opportunities

**Endpoint:** `GET /api/resources_opps/opportunities/`

**Purpose:** Get opportunities created by the current user (for My Opportunities page)

**Query Parameters:**
- `university` (required): User's university ID (UUID)
- `created_by` (optional): Filter by creator ID (can be used for filtering)
- `status` (optional): Filter by status (pending, approved, rejected)
- `page` (optional): Page number
- `limit` (optional): Items per page

**Backend Requirement:**
- **MUST** return all opportunities created by the authenticated user, regardless of status
- **SHOULD** support filtering by `created_by` query parameter
- **SHOULD** include `status` field in response

**Response (200):**
```json
{
  "count": 5,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": "uuid",
      "university": "uuid",
      "university_name": "University of Dar es Salaam",
      "category": "seminar",
      "title": "AI in Healthcare Seminar",
      "cover_media_url": "http://localhost:8000/media/opportunities/media/ai_seminar.jpg",
      "media_type": "image",
      "content": "Join us for an exciting seminar...",
      "created_by": "user_uuid",
      "created_by_name": "Jane Smith",
      "created_at": "2024-01-15T10:30:00Z",
      "updated_at": "2024-01-15T10:30:00Z",
      "start_date": "2024-02-01",
      "end_date": "2024-02-01",
      "application_url": "https://example.com/apply",
      "days_remaining": 17,
      "is_active": false,
      "status": "pending"
    },
    {
      "id": "uuid-2",
      "university": "uuid",
      "university_name": "University of Dar es Salaam",
      "category": "competition",
      "title": "Hackathon 2024",
      "cover_media_url": "http://localhost:8000/media/opportunities/media/hackathon.jpg",
      "media_type": "image",
      "content": "Join our annual hackathon...",
      "created_by": "user_uuid",
      "created_by_name": "Jane Smith",
      "created_at": "2024-01-10T10:30:00Z",
      "updated_at": "2024-01-12T10:30:00Z",
      "start_date": "2024-03-01",
      "end_date": "2024-03-03",
      "application_url": "https://example.com/hackathon",
      "days_remaining": 45,
      "is_active": true,
      "status": "approved"
    }
  ]
}
```

---

## 3. Create Opportunity (User Submission)

**Endpoint:** `POST /api/resources_opps/opportunities/`

**Purpose:** Allow users to submit new opportunities for their university

**Content-Type:** `multipart/form-data`

**Request Body (FormData):**
```
university: "uuid" (required) - User's university ID
title: "AI in Healthcare Seminar" (required)
category: "seminar" (required) - One of: seminar, competition, job, scholarship, internship, meeting, online_course
content: "Join us for an exciting seminar..." (required)
start_date: "2024-02-01" (required) - Format: YYYY-MM-DD
end_date: "2024-02-01" (required) - Format: YYYY-MM-DD
application_url: "https://example.com/apply" (optional)
cover_media: <file> (optional) - Image file (JPG, PNG, GIF, WebP) - Max 10MB
status: "pending" (optional) - Backend should set this automatically
is_active: "false" (optional) - Backend should set this automatically
```

**Backend Requirements:**
- **MUST** automatically set `created_by` to the authenticated user's ID
- **MUST** automatically set `status = 'pending'` if not provided
- **MUST** automatically set `is_active = false` if not provided
- **MUST** validate that `university` belongs to the user's profile
- **SHOULD** validate file size (max 10MB for cover_media)
- **SHOULD** validate file type (images only for cover_media)

**Response (201 Created):**
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
  "created_by": "user_uuid",
  "created_by_name": "Jane Smith",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:00Z",
  "start_date": "2024-02-01",
  "end_date": "2024-02-01",
  "application_url": "https://example.com/apply",
  "days_remaining": 17,
  "is_active": false,
  "status": "pending"
}
```

**Error Responses:**
- `400 Bad Request`: Validation errors
- `401 Unauthorized`: Not authenticated
- `403 Forbidden`: User doesn't have permission or university mismatch

---

## 4. Update Opportunity

**Endpoint:** `PATCH /api/resources_opps/opportunities/{id}/` or `PUT /api/resources_opps/opportunities/{id}/`

**Purpose:** Allow users to update their submitted opportunities

**Content-Type:** `multipart/form-data` (if updating file) or `application/json`

**Request Body (FormData or JSON):**
```
title: "Updated Title" (optional)
category: "seminar" (optional)
content: "Updated content" (optional)
start_date: "2024-02-05" (optional)
end_date: "2024-02-05" (optional)
application_url: "https://new-url.com/apply" (optional)
cover_media: <file> (optional) - New image file
```

**Backend Requirements:**
- **MUST** verify that the opportunity belongs to the authenticated user
- **SHOULD** reset `status = 'pending'` if opportunity was previously approved (requires re-approval)
- **SHOULD** set `is_active = false` if status is reset to pending
- **MUST** allow partial updates (PATCH)

**Response (200 OK):**
```json
{
  "id": "uuid",
  "university": "uuid",
  "university_name": "University of Dar es Salaam",
  "category": "seminar",
  "title": "Updated Title",
  "cover_media_url": "http://localhost:8000/media/opportunities/media/updated.jpg",
  "content": "Updated content",
  "created_by": "user_uuid",
  "created_by_name": "Jane Smith",
  "start_date": "2024-02-05",
  "end_date": "2024-02-05",
  "application_url": "https://new-url.com/apply",
  "is_active": false,
  "status": "pending",
  "updated_at": "2024-01-20T10:30:00Z"
}
```

**Error Responses:**
- `400 Bad Request`: Validation errors
- `401 Unauthorized`: Not authenticated
- `403 Forbidden`: User doesn't own this opportunity
- `404 Not Found`: Opportunity doesn't exist

---

## 5. Delete Opportunity

**Endpoint:** `DELETE /api/resources_opps/opportunities/{id}/`

**Purpose:** Allow users to delete their submitted opportunities

**Backend Requirements:**
- **MUST** verify that the opportunity belongs to the authenticated user
- **SHOULD** allow deletion regardless of status (pending, approved, rejected)

**Response (204 No Content)** or **(200 OK):**
```json
{
  "message": "Opportunity deleted successfully"
}
```

**Error Responses:**
- `401 Unauthorized`: Not authenticated
- `403 Forbidden`: User doesn't own this opportunity
- `404 Not Found`: Opportunity doesn't exist

---

## 6. Get Single Opportunity

**Endpoint:** `GET /api/resources_opps/opportunities/{id}/`

**Purpose:** Get detailed information about a specific opportunity

**Backend Requirements:**
- If `is_active = false` or `status != 'approved'`, only return to:
  - The creator (user who created it)
  - Admins/staff
- Public users should get 404 for non-active opportunities

**Response (200 OK):**
```json
{
  "id": "uuid",
  "university": "uuid",
  "university_name": "University of Dar es Salaam",
  "category": "seminar",
  "title": "AI in Healthcare Seminar",
  "cover_media_url": "http://localhost:8000/media/opportunities/media/ai_seminar.jpg",
  "media_type": "image",
  "content": "Full detailed content here...",
  "created_by": "user_uuid",
  "created_by_name": "Jane Smith",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:00Z",
  "start_date": "2024-02-01",
  "end_date": "2024-02-01",
  "application_url": "https://example.com/apply",
  "days_remaining": 17,
  "is_active": true,
  "status": "approved"
}
```

---

## 7. Get Opportunity Categories

**Endpoint:** `GET /api/resources_opps/opportunities/categories/`

**Purpose:** Get list of available opportunity categories

**Response (200 OK):**
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

## 8. Admin: Approve/Reject Opportunity (NEW - Required)

**Endpoint:** `PATCH /api/resources_opps/opportunities/{id}/approve/` or `POST /api/resources_opps/opportunities/{id}/approve/`

**Purpose:** Allow admins to approve or reject pending opportunities

**Content-Type:** `application/json`

**Request Body:**
```json
{
  "status": "approved",  // or "rejected"
  "is_active": true      // true if approved, false if rejected
}
```

**Backend Requirements:**
- **MUST** require admin/staff permissions
- **MUST** update both `status` and `is_active` fields
- **SHOULD** send notification to creator when status changes

**Response (200 OK):**
```json
{
  "id": "uuid",
  "status": "approved",
  "is_active": true,
  "message": "Opportunity approved successfully"
}
```

**Alternative Endpoint (if preferred):**
```
POST /api/resources_opps/opportunities/{id}/reject/
```

---

## 9. Admin: List Pending Opportunities (NEW - Recommended)

**Endpoint:** `GET /api/resources_opps/opportunities/pending/`

**Purpose:** Get all pending opportunities for admin review

**Query Parameters:**
- `university` (optional): Filter by university
- `page` (optional): Page number
- `limit` (optional): Items per page

**Backend Requirements:**
- **MUST** require admin/staff permissions
- **MUST** return only opportunities where `status = 'pending'` or (`is_active = false` AND `status IS NULL`)

**Response (200 OK):**
```json
{
  "count": 10,
  "results": [
    {
      "id": "uuid",
      "university_name": "University of Dar es Salaam",
      "title": "AI in Healthcare Seminar",
      "created_by_name": "Jane Smith",
      "created_at": "2024-01-15T10:30:00Z",
      "status": "pending",
      "is_active": false
    }
  ]
}
```

---

## Complete Opportunity Model (Backend Schema)

The backend Opportunity model should include:

```python
class Opportunity(models.Model):
    id = UUIDField(primary_key=True)
    university = ForeignKey(University)
    category = CharField(choices=CATEGORY_CHOICES)
    title = CharField(max_length=255)
    cover_media = ImageField(upload_to='opportunities/media/', null=True, blank=True)
    media_type = CharField(max_length=20, null=True, blank=True)
    content = TextField()
    created_by = ForeignKey(User)
    created_at = DateTimeField(auto_now_add=True)
    updated_at = DateTimeField(auto_now=True)
    start_date = DateField()
    end_date = DateField()
    application_url = URLField(null=True, blank=True)
    
    # NEW FIELDS REQUIRED:
    status = CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected')
        ],
        default='pending'
    )
    is_active = BooleanField(default=False)  # Only true when approved
    
    class Meta:
        ordering = ['-created_at']
```

---

## Status Field Logic

### Status Values:
- **`pending`**: Opportunity submitted, awaiting admin approval
- **`approved`**: Admin approved, visible to public (`is_active = true`)
- **`rejected`**: Admin rejected, not visible to public (`is_active = false`)

### Status Rules:
1. When user creates opportunity:
   - `status = 'pending'`
   - `is_active = false`

2. When admin approves:
   - `status = 'approved'`
   - `is_active = true`

3. When admin rejects:
   - `status = 'rejected'`
   - `is_active = false`

4. When user updates approved opportunity:
   - `status = 'pending'` (requires re-approval)
   - `is_active = false`

---

## Frontend Implementation Notes

### My Opportunities Page:
- Fetches: `GET /api/resources_opps/opportunities/?university={universityId}`
- Filters client-side by `created_by === current_user.id`
- Shows all statuses: pending, approved, rejected

### Public Opportunities Page:
- Fetches: `GET /api/resources_opps/opportunities/`
- Backend MUST filter to only return `is_active = true` AND `status = 'approved'`

### Create Opportunity:
```javascript
const formData = new FormData();
formData.append('university', universityId);
formData.append('title', 'My Opportunity');
formData.append('category', 'seminar');
formData.append('content', 'Description...');
formData.append('start_date', '2024-02-01');
formData.append('end_date', '2024-02-01');
formData.append('application_url', 'https://example.com');
formData.append('cover_media', fileInput.files[0]);
// Backend should automatically set status='pending' and is_active=false

await fetch('/api/resources_opps/opportunities/', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`
  },
  body: formData
});
```

---

## Error Responses

### 400 Bad Request
```json
{
  "title": ["This field is required."],
  "category": ["Invalid category. Choices are: seminar, competition, job..."],
  "cover_media": ["File size must be less than 10MB."]
}
```

### 401 Unauthorized
```json
{
  "detail": "Authentication credentials were not provided."
}
```

### 403 Forbidden
```json
{
  "detail": "You do not have permission to perform this action."
}
```

### 404 Not Found
```json
{
  "detail": "Not found."
}
```

---

## Summary of Required Backend Changes

1. **Add `status` field** to Opportunity model:
   - Choices: pending, approved, rejected
   - Default: pending

2. **Ensure `is_active` field** exists:
   - Default: false
   - Only true when status = approved

3. **Update List endpoint** to filter by `is_active = true` for public view

4. **Add admin approval endpoint**:
   - `PATCH /api/resources_opps/opportunities/{id}/approve/`
   - Requires admin permissions
   - Updates status and is_active

5. **Add pending list endpoint** (optional but recommended):
   - `GET /api/resources_opps/opportunities/pending/`
   - For admin dashboard

6. **Auto-set fields on create**:
   - `created_by` = authenticated user
   - `status` = 'pending'
   - `is_active` = false

7. **Permission checks**:
   - Users can only edit/delete their own opportunities
   - Only admins can approve/reject

---

## Testing Checklist

- [ ] User can create opportunity with pending status
- [ ] User can view their own opportunities (all statuses)
- [ ] Public page only shows approved opportunities
- [ ] User can edit their own opportunities
- [ ] User can delete their own opportunities
- [ ] Admin can approve pending opportunities
- [ ] Admin can reject pending opportunities
- [ ] Approved opportunities appear on public page
- [ ] Pending/rejected opportunities don't appear on public page
- [ ] Status badges display correctly in My Opportunities page


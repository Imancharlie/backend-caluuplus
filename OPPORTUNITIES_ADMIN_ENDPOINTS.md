# Opportunities Admin Management Endpoints

Complete API documentation for admin endpoints to manage opportunities (approve, reject, bulk operations, and statistics).

---

## Table of Contents
1. [Single Opportunity Actions](#single-opportunity-actions)
2. [Bulk Operations](#bulk-operations)
3. [Admin Lists & Filters](#admin-lists--filters)
4. [Statistics & Analytics](#statistics--analytics)
5. [Authentication](#authentication)
6. [Error Handling](#error-handling)

---

## Single Opportunity Actions

### 1. Approve Opportunity

**Endpoint:** `POST/PATCH /api/resources_opps/opportunities/{id}/approve/`

**Description:** Approve a single opportunity. Sets status to 'approved' and is_active to true.

**Authentication:** Admin only (`IsAdminUser`)

**Request:**
```http
POST /api/resources_opps/opportunities/{opportunity_id}/approve/
Authorization: Bearer <admin_token>
Content-Type: application/json

{
  "admin_note": "Optional note for approval"  // Optional
}
```

**Response (200 OK):**
```json
{
  "id": "uuid-string",
  "status": "approved",
  "is_active": true,
  "message": "Opportunity approved successfully",
  "opportunity": {
    "id": "uuid-string",
    "title": "Opportunity Title",
    "category": "seminar",
    "status": "approved",
    "is_active": true,
    "created_by": "user-id",
    "created_at": "2025-11-09T12:00:00Z",
    ...
  }
}
```

**Example:**
```bash
curl -X POST "http://localhost:8000/api/resources_opps/opportunities/123e4567-e89b-12d3-a456-426614174000/approve/" \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{"admin_note": "Looks good!"}'
```

---

### 2. Reject Opportunity

**Endpoint:** `POST/PATCH /api/resources_opps/opportunities/{id}/reject/`

**Description:** Reject a single opportunity. Sets status to 'rejected' and is_active to false.

**Authentication:** Admin only (`IsAdminUser`)

**Request:**
```http
POST /api/resources_opps/opportunities/{opportunity_id}/reject/
Authorization: Bearer <admin_token>
Content-Type: application/json

{
  "rejection_reason": "Content does not meet university guidelines"  // Optional
}
```

**Response (200 OK):**
```json
{
  "id": "uuid-string",
  "status": "rejected",
  "is_active": false,
  "rejection_reason": "Content does not meet university guidelines",
  "message": "Opportunity rejected successfully",
  "opportunity": {
    "id": "uuid-string",
    "title": "Opportunity Title",
    "category": "seminar",
    "status": "rejected",
    "is_active": false,
    ...
  }
}
```

**Example:**
```bash
curl -X POST "http://localhost:8000/api/resources_opps/opportunities/123e4567-e89b-12d3-a456-426614174000/reject/" \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{"rejection_reason": "Inappropriate content"}'
```

---

### 3. Set Status (Flexible)

**Endpoint:** `POST/PATCH /api/resources_opps/opportunities/{id}/set_status/`

**Description:** Set opportunity status to any value (approved, rejected, or pending). More flexible than approve/reject endpoints.

**Authentication:** Admin only (`IsAdminUser`)

**Request:**
```http
POST /api/resources_opps/opportunities/{opportunity_id}/set_status/
Authorization: Bearer <admin_token>
Content-Type: application/json

{
  "status": "approved",  // Required: "approved", "rejected", or "pending"
  "is_active": true      // Optional: defaults to true if status="approved", false otherwise
}
```

**Response (200 OK):**
```json
{
  "id": "uuid-string",
  "status": "approved",
  "is_active": true,
  "message": "Opportunity status set to approved",
  "opportunity": {
    "id": "uuid-string",
    "status": "approved",
    "is_active": true,
    ...
  }
}
```

**Error Response (400 Bad Request):**
```json
{
  "error": "status must be \"approved\", \"rejected\", or \"pending\""
}
```

**Example:**
```bash
curl -X POST "http://localhost:8000/api/resources_opps/opportunities/123e4567-e89b-12d3-a456-426614174000/set_status/" \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{"status": "pending", "is_active": false}'
```

---

## Bulk Operations

### 4. Bulk Approve

**Endpoint:** `POST /api/resources_opps/opportunities/bulk_approve/`

**Description:** Approve multiple opportunities at once.

**Authentication:** Admin only (`IsAdminUser`)

**Request:**
```http
POST /api/resources_opps/opportunities/bulk_approve/
Authorization: Bearer <admin_token>
Content-Type: application/json

{
  "opportunity_ids": [
    "uuid-1",
    "uuid-2",
    "uuid-3"
  ]
}
```

**Response (200 OK):**
```json
{
  "message": "Successfully approved 3 opportunity(ies)",
  "approved_count": 3,
  "total_requested": 3
}
```

**Error Response (400 Bad Request):**
```json
{
  "error": "opportunity_ids must be a non-empty array"
}
```

**Example:**
```bash
curl -X POST "http://localhost:8000/api/resources_opps/opportunities/bulk_approve/" \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "opportunity_ids": [
      "123e4567-e89b-12d3-a456-426614174000",
      "223e4567-e89b-12d3-a456-426614174001",
      "323e4567-e89b-12d3-a456-426614174002"
    ]
  }'
```

---

### 5. Bulk Reject

**Endpoint:** `POST /api/resources_opps/opportunities/bulk_reject/`

**Description:** Reject multiple opportunities at once with optional rejection reason.

**Authentication:** Admin only (`IsAdminUser`)

**Request:**
```http
POST /api/resources_opps/opportunities/bulk_reject/
Authorization: Bearer <admin_token>
Content-Type: application/json

{
  "opportunity_ids": [
    "uuid-1",
    "uuid-2",
    "uuid-3"
  ],
  "rejection_reason": "Does not meet quality standards"  // Optional
}
```

**Response (200 OK):**
```json
{
  "message": "Successfully rejected 3 opportunity(ies)",
  "rejected_count": 3,
  "total_requested": 3,
  "rejection_reason": "Does not meet quality standards"
}
```

**Error Response (400 Bad Request):**
```json
{
  "error": "opportunity_ids must be a non-empty array"
}
```

**Example:**
```bash
curl -X POST "http://localhost:8000/api/resources_opps/opportunities/bulk_reject/" \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "opportunity_ids": [
      "123e4567-e89b-12d3-a456-426614174000",
      "223e4567-e89b-12d3-a456-426614174001"
    ],
    "rejection_reason": "Content needs improvement"
  }'
```

---

## Admin Lists & Filters

### 6. Get Pending Opportunities

**Endpoint:** `GET /api/resources_opps/opportunities/pending/`

**Description:** Get all pending opportunities for admin review. Supports filtering and pagination.

**Authentication:** Admin only (`IsAdminUser`)

**Query Parameters:**
- `university` (optional): Filter by university ID
- `category` (optional): Filter by category (seminar, competition, job, etc.)
- `search` (optional): Search in title and content
- `page` (optional): Page number for pagination
- `page_size` (optional): Items per page (default: 20)

**Request:**
```http
GET /api/resources_opps/opportunities/pending/?page=1&page_size=20&university={id}&category=seminar&search=workshop
Authorization: Bearer <admin_token>
```

**Response (200 OK) - Paginated:**
```json
{
  "count": 45,
  "next": "http://localhost:8000/api/resources_opps/opportunities/pending/?page=2",
  "previous": null,
  "results": [
    {
      "id": "uuid-string",
      "title": "Opportunity Title",
      "category": "seminar",
      "status": "pending",
      "is_active": false,
      "created_by": "user-id",
      "created_at": "2025-11-09T12:00:00Z",
      ...
    },
    ...
  ]
}
```

**Response (200 OK) - Non-paginated:**
```json
{
  "count": 45,
  "results": [
    {
      "id": "uuid-string",
      "title": "Opportunity Title",
      ...
    },
    ...
  ]
}
```

**Example:**
```bash
curl -X GET "http://localhost:8000/api/resources_opps/opportunities/pending/?page=1&page_size=20&category=seminar" \
  -H "Authorization: Bearer <admin_token>"
```

---

### 7. Get All Opportunities (Any Status)

**Endpoint:** `GET /api/resources_opps/opportunities/all_statuses/`

**Description:** Get all opportunities regardless of status. Useful for admin dashboard showing all opportunities.

**Authentication:** Admin only (`IsAdminUser`)

**Query Parameters:**
- `status` (optional): Filter by status (pending, approved, rejected)
- `university` (optional): Filter by university ID
- `category` (optional): Filter by category
- `search` (optional): Search in title and content
- `page` (optional): Page number for pagination
- `page_size` (optional): Items per page (default: 20)

**Request:**
```http
GET /api/resources_opps/opportunities/all_statuses/?status=pending&university={id}&page=1&page_size=20
Authorization: Bearer <admin_token>
```

**Response (200 OK):**
```json
{
  "count": 120,
  "next": "http://localhost:8000/api/resources_opps/opportunities/all_statuses/?page=2",
  "previous": null,
  "results": [
    {
      "id": "uuid-string",
      "title": "Opportunity Title",
      "status": "pending",
      "is_active": false,
      ...
    },
    ...
  ]
}
```

**Example:**
```bash
curl -X GET "http://localhost:8000/api/resources_opps/opportunities/all_statuses/?status=approved&page=1" \
  -H "Authorization: Bearer <admin_token>"
```

---

## Statistics & Analytics

### 8. Admin Statistics

**Endpoint:** `GET /api/resources_opps/opportunities/admin_stats/`

**Description:** Get comprehensive statistics for opportunities management dashboard.

**Authentication:** Admin only (`IsAdminUser`)

**Request:**
```http
GET /api/resources_opps/opportunities/admin_stats/
Authorization: Bearer <admin_token>
```

**Response (200 OK):**
```json
{
  "total_opportunities": 150,
  "status_breakdown": {
    "pending": 45,
    "approved": 90,
    "rejected": 15
  },
  "category_breakdown": {
    "seminar": {
      "label": "Seminar",
      "total": 30,
      "pending": 10,
      "approved": 18,
      "rejected": 2
    },
    "competition": {
      "label": "Competition",
      "total": 25,
      "pending": 8,
      "approved": 15,
      "rejected": 2
    },
    "job": {
      "label": "Job",
      "total": 40,
      "pending": 12,
      "approved": 25,
      "rejected": 3
    },
    "meeting": {
      "label": "Meeting",
      "total": 15,
      "pending": 5,
      "approved": 8,
      "rejected": 2
    },
    "scholarship": {
      "label": "Scholarship",
      "total": 20,
      "pending": 6,
      "approved": 12,
      "rejected": 2
    },
    "internship": {
      "label": "Internship",
      "total": 15,
      "pending": 3,
      "approved": 10,
      "rejected": 2
    },
    "online_course": {
      "label": "Online Course",
      "total": 5,
      "pending": 1,
      "approved": 2,
      "rejected": 2
    }
  },
  "recent_pending_7_days": 12,
  "pending_percentage": 30.0,
  "approval_rate": 60.0
}
```

**Example:**
```bash
curl -X GET "http://localhost:8000/api/resources_opps/opportunities/admin_stats/" \
  -H "Authorization: Bearer <admin_token>"
```

---

## Authentication

All admin endpoints require:
- **Authentication:** Valid JWT token in `Authorization` header
- **Permission:** User must be admin (`is_staff=True` or `is_superuser=True`)

**Header Format:**
```http
Authorization: Bearer <access_token>
```

**Error Response (401 Unauthorized):**
```json
{
  "detail": "Authentication credentials were not provided."
}
```

**Error Response (403 Forbidden):**
```json
{
  "detail": "You do not have permission to perform this action."
}
```

---

## Error Handling

### Common Error Responses

**400 Bad Request:**
```json
{
  "error": "status must be \"approved\", \"rejected\", or \"pending\""
}
```

**404 Not Found:**
```json
{
  "detail": "Not found."
}
```

**500 Internal Server Error:**
```json
{
  "error": "Internal server error"
}
```

---

## Complete Workflow Example

### Admin Reviewing and Approving Opportunities

1. **Get pending opportunities:**
```bash
GET /api/resources_opps/opportunities/pending/?page=1&page_size=20
```

2. **View statistics:**
```bash
GET /api/resources_opps/opportunities/admin_stats/
```

3. **Approve an opportunity:**
```bash
POST /api/resources_opps/opportunities/{id}/approve/
```

4. **Reject another with reason:**
```bash
POST /api/resources_opps/opportunities/{id}/reject/
Body: {"rejection_reason": "Inappropriate content"}
```

5. **Bulk approve multiple:**
```bash
POST /api/resources_opps/opportunities/bulk_approve/
Body: {"opportunity_ids": ["id1", "id2", "id3"]}
```

6. **View all opportunities:**
```bash
GET /api/resources_opps/opportunities/all_statuses/?status=approved
```

---

## Frontend Integration Examples

### React/TypeScript Example

```typescript
// Approve opportunity
const approveOpportunity = async (opportunityId: string) => {
  const response = await fetch(
    `http://localhost:8000/api/resources_opps/opportunities/${opportunityId}/approve/`,
    {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${accessToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ admin_note: 'Approved' }),
    }
  );
  return response.json();
};

// Bulk approve
const bulkApprove = async (opportunityIds: string[]) => {
  const response = await fetch(
    'http://localhost:8000/api/resources_opps/opportunities/bulk_approve/',
    {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${accessToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ opportunity_ids: opportunityIds }),
    }
  );
  return response.json();
};

// Get pending list
const getPendingOpportunities = async (page = 1, pageSize = 20) => {
  const response = await fetch(
    `http://localhost:8000/api/resources_opps/opportunities/pending/?page=${page}&page_size=${pageSize}`,
    {
      headers: {
        'Authorization': `Bearer ${accessToken}`,
      },
    }
  );
  return response.json();
};

// Get admin stats
const getAdminStats = async () => {
  const response = await fetch(
    'http://localhost:8000/api/resources_opps/opportunities/admin_stats/',
    {
      headers: {
        'Authorization': `Bearer ${accessToken}`,
      },
    }
  );
  return response.json();
};
```

---

## Notes

1. **All endpoints require admin permissions** - Regular users cannot access these endpoints
2. **Bulk operations are efficient** - Use bulk approve/reject for better performance when handling multiple opportunities
3. **Pagination is supported** - Use `page` and `page_size` query parameters for large lists
4. **Filtering is flexible** - Combine multiple filters (university, category, search) for precise results
5. **Statistics update in real-time** - Admin stats reflect current database state

---

## Testing

Test all endpoints using:
- Postman
- cURL commands (examples provided above)
- Frontend application
- Django admin interface (for verification)

---

**Last Updated:** 2025-11-09




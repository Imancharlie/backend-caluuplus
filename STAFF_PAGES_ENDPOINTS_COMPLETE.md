# Staff Pages - Complete Endpoint Documentation

This document provides a comprehensive list of all endpoints and their formats required for the staff/admin pages to function properly.

## Base URL
```
http://localhost:8000/api
```

## Authentication
All endpoints require JWT authentication:
```
Authorization: Bearer <your_jwt_token>
```

---

## 1. Staff Dashboard Endpoints

### GET /admin/dashboard/
**Purpose:** Get dashboard statistics and overview data

**Response (200):**
```json
{
  "counts": {
    "user_count": 1250,
    "data_count": 3450,
    "program_count": 45,
    "college_count": 12,
    "course_count": 320,
    "feedback_count": 89,
    "confirmed_count": 1200
  },
  "usageData": [
    { "month": "January", "count": 120 },
    { "month": "February", "count": 145 },
    { "month": "March", "count": 180 },
    { "month": "April", "count": 165 }
  ],
  "dataByYear": [
    { "year": 2024, "count": 500 },
    { "year": 2023, "count": 450 }
  ],
  "programsByCollege": [
    { "program__name": "Computer Science", "total": 150 },
    { "program__name": "Engineering", "total": 120 }
  ],
  "recent_activities": [
    { "action": "New student registered", "time": "2 hours ago" },
    { "action": "Article published", "time": "5 hours ago" }
  ]
}
```

### GET /staff/me/roles/
**Purpose:** Get current user's roles and permissions

**Response (200):**
```json
{
  "is_admin": true,
  "is_ambassador": false,
  "ambassador_university_ids": []
}
```

### GET /admin/ambassadors/
**Purpose:** Get list of all ambassadors (for Staff Dashboard)

**Response (200):**
```json
{
  "results": [
    {
      "id": "uuid",
      "user": {
        "id": "uuid",
        "email": "ambassador@example.com",
        "display_name": "John Ambassador"
      },
      "universities": [
        {
          "id": "uuid",
          "name": "University of Dar es Salaam"
        }
      ],
      "created_at": "2024-01-15T10:30:00Z"
    }
  ],
  "count": 5
}
```

---

## 2. University Management Endpoints

### GET /universities/ (or GET /admin/universities/)
**Purpose:** List all universities

**Query Parameters:**
- `search` (optional): Search term to filter universities
- `page` (optional): Page number for pagination
- `page_size` (optional): Items per page

**Response (200):**
```json
{
  "results": [
    {
      "id": "uuid",
      "name": "University of Dar es Salaam",
      "country": "Tanzania",
      "created_at": "2024-01-15T10:30:00Z",
      "updated_at": "2024-01-15T10:30:00Z"
    }
  ],
  "count": 25,
  "next": null,
  "previous": null
}
```

**Alternative Response Format (if array directly):**
```json
[
  {
    "id": "uuid",
    "name": "University of Dar es Salaam",
    "country": "Tanzania"
  }
]
```

### POST /admin/universities/
**Purpose:** Create a new university

**Request Body:**
```json
{
  "name": "University Name",
  "country": "Country Name"
}
```

**Response (201):**
```json
{
  "id": "uuid",
  "name": "University Name",
  "country": "Country Name",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:00Z"
}
```

**Alternative Response Format:**
```json
{
  "message": "University created successfully",
  "data": {
    "id": "uuid",
    "name": "University Name",
    "country": "Country Name"
  }
}
```

### PATCH /admin/universities/{id}/ (or PUT)
**Purpose:** Update an existing university

**Request Body:**
```json
{
  "name": "Updated University Name",
  "country": "Updated Country"
}
```

**Response (200):**
```json
{
  "id": "uuid",
  "name": "Updated University Name",
  "country": "Updated Country",
  "updated_at": "2024-01-15T10:30:00Z"
}
```

### DELETE /admin/universities/{id}/
**Purpose:** Delete a university

**Response (204 No Content)** or **(200):**
```json
{
  "message": "University deleted successfully"
}
```

---

## 3. College Management Endpoints

### GET /admin/colleges/ (or GET /colleges/)
**Purpose:** List all colleges

**Query Parameters:**
- `search` (optional): Search term to filter colleges
- `university` (optional): Filter by university ID
- `page` (optional): Page number
- `page_size` (optional): Items per page

**Response (200):**
```json
{
  "results": [
    {
      "id": "uuid",
      "name": "College of Engineering",
      "university": "uuid",
      "university_name": "University of Dar es Salaam",
      "created_at": "2024-01-15T10:30:00Z",
      "updated_at": "2024-01-15T10:30:00Z"
    }
  ],
  "count": 50,
  "next": null,
  "previous": null
}
```

**Alternative Response Format (if array directly):**
```json
[
  {
    "id": "uuid",
    "name": "College of Engineering",
    "university": "uuid",
    "university_name": "University of Dar es Salaam"
  }
]
```

### POST /admin/colleges/
**Purpose:** Create a new college

**Request Body:**
```json
{
  "name": "College Name",
  "university": "university_uuid"
}
```

**Response (201):**
```json
{
  "id": "uuid",
  "name": "College Name",
  "university": "university_uuid",
  "university_name": "University Name",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:00Z"
}
```

**Alternative Response Format:**
```json
{
  "message": "College created successfully",
  "data": {
    "id": "uuid",
    "name": "College Name",
    "university": "university_uuid",
    "university_name": "University Name"
  }
}
```

### PATCH /admin/colleges/{id}/ (or PUT)
**Purpose:** Update an existing college

**Request Body:**
```json
{
  "name": "Updated College Name",
  "university": "university_uuid"
}
```

**Response (200):**
```json
{
  "id": "uuid",
  "name": "Updated College Name",
  "university": "university_uuid",
  "university_name": "University Name",
  "updated_at": "2024-01-15T10:30:00Z"
}
```

### DELETE /admin/colleges/{id}/
**Purpose:** Delete a college

**Response (204 No Content)** or **(200):**
```json
{
  "message": "College deleted successfully"
}
```

---

## 4. Program Management Endpoints

### GET /admin/programs/ (or GET /programs/)
**Purpose:** List all programs

**Query Parameters:**
- `search` (optional): Search term to filter programs
- `college` (optional): Filter by college ID
- `university` (optional): Filter by university ID
- `page` (optional): Page number
- `page_size` (optional): Items per page

**Response (200):**
```json
{
  "results": [
    {
      "id": "uuid",
      "name": "Bachelor of Science in Computer Science",
      "college": "uuid",
      "college_name": "College of Engineering",
      "university_name": "University of Dar es Salaam",
      "duration": 4,
      "created_at": "2024-01-15T10:30:00Z",
      "updated_at": "2024-01-15T10:30:00Z"
    }
  ],
  "count": 100,
  "next": null,
  "previous": null
}
```

**Alternative Response Format (if array directly):**
```json
[
  {
    "id": "uuid",
    "name": "Bachelor of Science in Computer Science",
    "college": "uuid",
    "college_name": "College of Engineering",
    "university_name": "University of Dar es Salaam",
    "duration": 4
  }
]
```

### POST /admin/programs/
**Purpose:** Create a new program

**Request Body:**
```json
{
  "name": "Program Name",
  "college": "college_uuid",
  "duration": 4
}
```

**Response (201):**
```json
{
  "id": "uuid",
  "name": "Program Name",
  "college": "college_uuid",
  "college_name": "College Name",
  "university_name": "University Name",
  "duration": 4,
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:00Z"
}
```

**Alternative Response Format:**
```json
{
  "message": "Program created successfully",
  "data": {
    "id": "uuid",
    "name": "Program Name",
    "college": "college_uuid",
    "college_name": "College Name",
    "university_name": "University Name",
    "duration": 4
  }
}
```

### PATCH /admin/programs/{id}/ (or PUT)
**Purpose:** Update an existing program

**Request Body:**
```json
{
  "name": "Updated Program Name",
  "college": "college_uuid",
  "duration": 5
}
```

**Response (200):**
```json
{
  "id": "uuid",
  "name": "Updated Program Name",
  "college": "college_uuid",
  "college_name": "College Name",
  "university_name": "University Name",
  "duration": 5,
  "updated_at": "2024-01-15T10:30:00Z"
}
```

### DELETE /admin/programs/{id}/
**Purpose:** Delete a program

**Response (204 No Content)** or **(200):**
```json
{
  "message": "Program deleted successfully"
}
```

---

## 5. Student Management Endpoints

### GET /staff/students/
**Purpose:** List all students with pagination and filtering (staff/admin only)

**Query Parameters:**
- `page` (optional): Page number (default: 1)
- `page_size` (optional): Items per page (default: 10)
- `search` (optional): Search in name, email
- `university` (optional): Filter by university ID
- `program` (optional): Filter by program ID
- `year` (optional): Filter by year of study
- `semester` (optional): Filter by semester
- `sort_by` (optional): Sort field (`name`, `email`, `university`, `program`, `created_at`)
- `sort_order` (optional): Sort direction (`asc`, `desc`)

**Response (200):**
```json
{
  "results": [
    {
      "id": "uuid",
      "email": "student@example.com",
      "display_name": "John Doe",
      "first_name": "John",
      "last_name": "Doe",
      "phone_number": "+255123456789",
      "university_name": "University of Dar es Salaam",
      "program_name": "Bachelor of Science in Computer Science",
      "year": 2,
      "semester": 1,
      "created_at": "2024-01-15T10:30:00Z",
      "updated_at": "2024-01-15T10:30:00Z"
    }
  ],
  "count": 1250,
  "next": "http://localhost:8000/api/staff/students/?page=2",
  "previous": null
}
```

**Alternative Response Format (if array directly):**
```json
[
  {
    "id": "uuid",
    "email": "student@example.com",
    "display_name": "John Doe",
    "university_name": "University of Dar es Salaam",
    "program_name": "Computer Science",
    "year": 2,
    "semester": 1
  }
]
```

**Alternative Response Format (if wrapped in data):**
```json
{
  "data": [
    {
      "id": "uuid",
      "email": "student@example.com",
      "display_name": "John Doe"
    }
  ]
}
```

### GET /staff/students/{id}/
**Purpose:** Get detailed information about a specific student

**Response (200):**
```json
{
  "id": "uuid",
  "email": "student@example.com",
  "display_name": "John Doe",
  "first_name": "John",
  "last_name": "Doe",
  "phone_number": "+255123456789",
  "university": {
    "id": "uuid",
    "name": "University of Dar es Salaam"
  },
  "college": {
    "id": "uuid",
    "name": "College of Engineering"
  },
  "program": {
    "id": "uuid",
    "name": "Bachelor of Science in Computer Science"
  },
  "year": 2,
  "semester": 1,
  "gpa": 3.75,
  "courses": [
    {
      "id": "uuid",
      "course_code": "CS101",
      "course_name": "Introduction to Programming",
      "grade": "A",
      "credits": 3
    }
  ],
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:00Z"
}
```

### PATCH /staff/students/{id}/ (or PUT)
**Purpose:** Update student information (admin only)

**Request Body:**
```json
{
  "year": 3,
  "semester": 2,
  "phone_number": "+255987654321"
}
```

**Response (200):**
```json
{
  "id": "uuid",
  "email": "student@example.com",
  "display_name": "John Doe",
  "year": 3,
  "semester": 2,
  "phone_number": "+255987654321",
  "updated_at": "2024-01-15T10:30:00Z"
}
```

### DELETE /staff/students/{id}/
**Purpose:** Delete a student (admin only - use with caution)

**Response (204 No Content)** or **(200):**
```json
{
  "message": "Student deleted successfully"
}
```

---

## 6. Slide Management Endpoints

### GET /slides/ (or GET /admin/slides/)
**Purpose:** List all slides

**Query Parameters:**
- `page` (optional): Page number
- `page_size` (optional): Items per page
- `type` (optional): Filter by slide type
- `include_inactive` (optional): Include inactive slides (`true`/`false`)

**Response (200):**
```json
{
  "results": [
    {
      "id": "uuid",
      "title": "Slide Title",
      "description": "Slide Description",
      "image": "slides/image.jpg",
      "image_url": "http://localhost:8000/media/slides/image.jpg",
      "link_url": "https://example.com",
      "background_gradient": "from-blue-500 to-purple-500",
      "order": 1,
      "is_active": true,
      "created_at": "2024-01-15T10:30:00Z",
      "updated_at": "2024-01-15T10:30:00Z"
    }
  ],
  "count": 10,
  "next": null,
  "previous": null
}
```

### POST /slides/
**Purpose:** Create a new slide

**Content-Type:** `multipart/form-data`

**Request Body (FormData):**
```
title: "Slide Title" (required)
description: "Slide Description" (required)
image: <file> (optional) - Image file
link_url: "https://example.com" (optional)
background_gradient: "from-blue-500 to-purple-500" (optional)
order: 1 (optional)
is_active: true (optional)
```

**Response (201):**
```json
{
  "id": "uuid",
  "title": "Slide Title",
  "description": "Slide Description",
  "image_url": "http://localhost:8000/media/slides/image.jpg",
  "link_url": "https://example.com",
  "background_gradient": "from-blue-500 to-purple-500",
  "order": 1,
  "is_active": true,
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:00Z"
}
```

### PATCH /slides/{id}/ (or PUT)
**Purpose:** Update an existing slide

**Content-Type:** `multipart/form-data` (if updating image) or `application/json`

**Request Body:**
```json
{
  "title": "Updated Title",
  "description": "Updated Description",
  "link_url": "https://new-url.com",
  "is_active": false,
  "order": 2
}
```

**Response (200):**
```json
{
  "id": "uuid",
  "title": "Updated Title",
  "description": "Updated Description",
  "image_url": "http://localhost:8000/media/slides/image.jpg",
  "link_url": "https://new-url.com",
  "is_active": false,
  "order": 2,
  "updated_at": "2024-01-15T10:30:00Z"
}
```

### DELETE /slides/{id}/
**Purpose:** Delete a slide

**Response (204 No Content)** or **(200):**
```json
{
  "message": "Slide deleted successfully"
}
```

---

## 7. Notification Management Endpoints

### GET /notifications/ (or GET /admin/notifications/)
**Purpose:** List all notifications

**Query Parameters:**
- `page` (optional): Page number (default: 1)
- `page_size` (optional): Items per page (default: 20)
- `include_read` (optional): Include read notifications (`true`/`false`)
- `user_id` (optional): Filter by user ID
- `type` (optional): Filter by notification type

**Response (200):**
```json
{
  "notifications": [
    {
      "id": "uuid",
      "title": "Notification Title",
      "body": "Notification Body",
      "type": "info",
      "link": "/dashboard",
      "is_read": false,
      "created_at": "2024-01-15T10:30:00Z",
      "read_at": null,
      "user": "user_uuid",
      "user_name": "User Display Name"
    }
  ],
  "page": 1,
  "page_size": 20,
  "total_count": 50,
  "has_next": true,
  "has_previous": false
}
```

**Alternative Response Format:**
```json
{
  "results": [
    {
      "id": "uuid",
      "title": "Notification Title",
      "body": "Notification Body",
      "is_read": false,
      "created_at": "2024-01-15T10:30:00Z"
    }
  ],
  "count": 50,
  "next": null,
  "previous": null
}
```

### POST /notifications/
**Purpose:** Create a new notification

**Request Body:**
```json
{
  "title": "Notification Title",
  "body": "Notification Body",
  "type": "info",
  "link": "/dashboard",
  "target_users": ["user_uuid1", "user_uuid2"],
  "target_universities": ["university_uuid"],
  "target_programs": ["program_uuid"]
}
```

**Response (201):**
```json
{
  "id": "uuid",
  "title": "Notification Title",
  "body": "Notification Body",
  "type": "info",
  "link": "/dashboard",
  "created_at": "2024-01-15T10:30:00Z"
}
```

### POST /notifications/bulk/
**Purpose:** Create multiple notifications at once

**Request Body:**
```json
{
  "notifications": [
    {
      "title": "Notification 1",
      "body": "Body 1",
      "type": "info",
      "target_users": ["user_uuid1"]
    },
    {
      "title": "Notification 2",
      "body": "Body 2",
      "type": "success",
      "target_universities": ["university_uuid"]
    }
  ]
}
```

**Response (201):**
```json
{
  "created": 2,
  "failed": 0
}
```

### PATCH /notifications/{id}/ (or PUT)
**Purpose:** Update an existing notification

**Request Body:**
```json
{
  "title": "Updated Title",
  "body": "Updated Body",
  "is_read": true
}
```

**Response (200):**
```json
{
  "id": "uuid",
  "title": "Updated Title",
  "body": "Updated Body",
  "is_read": true,
  "updated_at": "2024-01-15T10:30:00Z"
}
```

### DELETE /notifications/{id}/
**Purpose:** Delete a notification

**Response (204 No Content)** or **(200):**
```json
{
  "message": "Notification deleted successfully"
}
```

---

## 8. Quote Management Endpoints

### GET /quotes/
**Purpose:** List all quotes

**Query Parameters:**
- `page` (optional): Page number
- `page_size` (optional): Items per page
- `is_active` (optional): Filter by active status (`true`/`false`)

**Response (200):**
```json
{
  "results": [
    {
      "id": 1,
      "text": "Education is the most powerful weapon which you can use to change the world.",
      "author": "Nelson Mandela",
      "is_active": true,
      "created_at": "2024-01-15T10:30:00Z",
      "updated_at": "2024-01-15T10:30:00Z"
    }
  ],
  "count": 25,
  "next": null,
  "previous": null
}
```

### POST /quotes/ (or POST /quotes/create/)
**Purpose:** Create a new quote

**Request Body:**
```json
{
  "text": "Inspirational quote text",
  "author": "Quote Author",
  "is_active": true
}
```

**Response (201):**
```json
{
  "id": 1,
  "text": "Inspirational quote text",
  "author": "Quote Author",
  "is_active": true,
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:00Z"
}
```

### GET /quotes/{id}/
**Purpose:** Get a specific quote

**Response (200):**
```json
{
  "id": 1,
  "text": "Inspirational quote text",
  "author": "Quote Author",
  "is_active": true,
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:00Z"
}
```

### PATCH /quotes/{id}/ (or PUT)
**Purpose:** Update an existing quote

**Request Body:**
```json
{
  "text": "Updated quote text",
  "author": "Updated Author",
  "is_active": false
}
```

**Response (200):**
```json
{
  "id": 1,
  "text": "Updated quote text",
  "author": "Updated Author",
  "is_active": false,
  "updated_at": "2024-01-15T10:30:00Z"
}
```

### DELETE /quotes/{id}/
**Purpose:** Delete a quote

**Response (204 No Content)** or **(200):**
```json
{
  "message": "Quote deleted successfully"
}
```

---

## 9. Article Management Endpoints (Staff)

### GET /articles/
**Purpose:** List all articles (staff view with all articles)

**Query Parameters:**
- `page` (optional): Page number
- `page_size` (optional): Items per page
- `search` (optional): Search in title and content
- `category` (optional): Filter by category
- `status` (optional): Filter by status (`published`, `draft`, `archived`)

**Response (200):**
```json
{
  "results": [
    {
      "id": "uuid",
      "title": "Article Title",
      "content": "Article content...",
      "category": "study-tips",
      "status": "published",
      "author": {
        "id": "uuid",
        "display_name": "Author Name"
      },
      "created_at": "2024-01-15T10:30:00Z",
      "updated_at": "2024-01-15T10:30:00Z"
    }
  ],
  "count": 100,
  "next": null,
  "previous": null
}
```

### POST /articles/
**Purpose:** Create a new article (staff only)

**Content-Type:** `multipart/form-data` (if uploading image) or `application/json`

**Request Body:**
```json
{
  "title": "Article Title",
  "content": "Article content...",
  "category": "study-tips",
  "status": "published",
  "cover_image": <file> (optional)
}
```

**Response (201):**
```json
{
  "id": "uuid",
  "title": "Article Title",
  "content": "Article content...",
  "category": "study-tips",
  "status": "published",
  "cover_image_url": "http://localhost:8000/media/articles/image.jpg",
  "created_at": "2024-01-15T10:30:00Z"
}
```

### PATCH /articles/{id}/ (or PUT)
**Purpose:** Update an existing article

**Request Body:**
```json
{
  "title": "Updated Title",
  "content": "Updated content...",
  "status": "draft"
}
```

**Response (200):**
```json
{
  "id": "uuid",
  "title": "Updated Title",
  "content": "Updated content...",
  "status": "draft",
  "updated_at": "2024-01-15T10:30:00Z"
}
```

### DELETE /articles/{id}/
**Purpose:** Delete an article

**Response (204 No Content)** or **(200):**
```json
{
  "message": "Article deleted successfully"
}
```

---

## 10. Course Management Endpoints (Admin)

### GET /admin/courses/
**Purpose:** List all courses (admin view)

**Query Parameters:**
- `search` (optional): Search in code and name
- `program` (optional): Filter by program ID
- `year` (optional): Filter by year
- `semester` (optional): Filter by semester
- `type` (optional): Filter by type (`core`, `elective`)
- `page` (optional): Page number
- `page_size` (optional): Items per page

**Response (200):**
```json
{
  "results": [
    {
      "id": "uuid",
      "code": "CS101",
      "name": "Introduction to Programming",
      "credits": 3,
      "type": "core",
      "semester": 1,
      "year": 1,
      "program": "uuid",
      "program_name": "Computer Science",
      "created_at": "2024-01-15T10:30:00Z",
      "updated_at": "2024-01-15T10:30:00Z"
    }
  ],
  "count": 500,
  "next": null,
  "previous": null
}
```

### POST /admin/courses/
**Purpose:** Create a new course

**Request Body:**
```json
{
  "code": "CS101",
  "name": "Introduction to Programming",
  "credits": 3,
  "type": "core",
  "semester": 1,
  "year": 1,
  "program": "program_uuid"
}
```

**Response (201):**
```json
{
  "id": "uuid",
  "code": "CS101",
  "name": "Introduction to Programming",
  "credits": 3,
  "type": "core",
  "semester": 1,
  "year": 1,
  "program": "program_uuid",
  "program_name": "Computer Science",
  "created_at": "2024-01-15T10:30:00Z"
}
```

### PATCH /admin/courses/{id}/ (or PUT)
**Purpose:** Update an existing course

**Request Body:**
```json
{
  "code": "CS101",
  "name": "Updated Course Name",
  "credits": 4
}
```

**Response (200):**
```json
{
  "id": "uuid",
  "code": "CS101",
  "name": "Updated Course Name",
  "credits": 4,
  "updated_at": "2024-01-15T10:30:00Z"
}
```

### DELETE /admin/courses/{id}/
**Purpose:** Delete a course

**Response (204 No Content)** or **(200):**
```json
{
  "message": "Course deleted successfully"
}
```

---

## 11. Import/Export Endpoints

### POST /import/programs/
**Purpose:** Bulk import programs from file

**Content-Type:** `multipart/form-data`

**Request Body (FormData):**
```
file: <file> (required) - Excel or CSV file
university: "university_uuid" (required)
college: "college_uuid" (required)
```

**Response (202 Accepted):**
```json
{
  "job_id": "uuid",
  "message": "Import job started",
  "status": "pending"
}
```

### POST /import/courses/
**Purpose:** Bulk import courses from file

**Content-Type:** `multipart/form-data`

**Request Body (FormData):**
```
file: <file> (required) - Excel or CSV file
program: "program_uuid" (required)
```

**Response (202 Accepted):**
```json
{
  "job_id": "uuid",
  "message": "Import job started",
  "status": "pending"
}
```

### GET /import/jobs/{job_id}/
**Purpose:** Get import job status

**Response (200):**
```json
{
  "id": "uuid",
  "status": "completed",
  "progress": 100,
  "total_items": 100,
  "processed_items": 100,
  "successful_items": 95,
  "failed_items": 5,
  "errors": [
    {
      "row": 10,
      "error": "Invalid program code"
    }
  ],
  "created_at": "2024-01-15T10:30:00Z",
  "completed_at": "2024-01-15T10:35:00Z"
}
```

### GET /import/jobs/
**Purpose:** List all import jobs

**Response (200):**
```json
{
  "results": [
    {
      "id": "uuid",
      "status": "completed",
      "progress": 100,
      "created_at": "2024-01-15T10:30:00Z"
    }
  ],
  "count": 10
}
```

---

## Response Format Standards

### Paginated Responses
All list endpoints should return paginated responses in this format:
```json
{
  "results": [...],
  "count": 100,
  "next": "http://localhost:8000/api/endpoint/?page=2",
  "previous": null
}
```

### Success Responses
- **201 Created:** Returns the created object
- **200 OK:** Returns the updated/retrieved object
- **204 No Content:** For DELETE operations (no body)

### Error Responses

#### 400 Bad Request
```json
{
  "error": "Validation error",
  "errors": {
    "name": ["This field is required."],
    "email": ["Enter a valid email address."]
  }
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

#### 500 Internal Server Error
```json
{
  "error": "Internal server error",
  "message": "An unexpected error occurred."
}
```

---

## Important Notes

1. **PATCH vs PUT:** 
   - Use PATCH for partial updates (only send fields to update)
   - Use PUT for full updates (send all required fields)
   - Frontend tries PATCH first, falls back to PUT if PATCH fails

2. **Response Format Handling:**
   - Backend may return data directly: `{ "id": "...", "name": "..." }`
   - Or wrapped in `data` field: `{ "data": { "id": "...", "name": "..." } }`
   - Or wrapped in `message` and `data`: `{ "message": "...", "data": {...} }`
   - Frontend handles all these formats

3. **Pagination:**
   - Default page size: 10-20 items
   - Use `page` and `page_size` query parameters
   - Always return `count`, `next`, and `previous` fields

4. **Search:**
   - Use `search` query parameter for text search
   - Should search across relevant fields (name, email, title, etc.)

5. **Filtering:**
   - Use query parameters for filters (e.g., `university`, `program`, `status`)
   - Multiple filters can be combined

6. **Sorting:**
   - Use `sort_by` and `sort_order` query parameters
   - Default sort order: `asc`

---

## Endpoint Summary Table

| Endpoint | Method | Purpose | Auth Required |
|----------|--------|---------|---------------|
| `/admin/dashboard/` | GET | Dashboard statistics | Yes (Admin) |
| `/staff/me/roles/` | GET | Get user roles | Yes |
| `/admin/ambassadors/` | GET | List ambassadors | Yes (Admin) |
| `/universities/` | GET | List universities | No |
| `/admin/universities/` | POST | Create university | Yes (Admin) |
| `/admin/universities/{id}/` | PATCH/PUT | Update university | Yes (Admin) |
| `/admin/universities/{id}/` | DELETE | Delete university | Yes (Admin) |
| `/admin/colleges/` | GET | List colleges | Yes (Admin) |
| `/admin/colleges/` | POST | Create college | Yes (Admin) |
| `/admin/colleges/{id}/` | PATCH/PUT | Update college | Yes (Admin) |
| `/admin/colleges/{id}/` | DELETE | Delete college | Yes (Admin) |
| `/admin/programs/` | GET | List programs | Yes (Admin) |
| `/admin/programs/` | POST | Create program | Yes (Admin) |
| `/admin/programs/{id}/` | PATCH/PUT | Update program | Yes (Admin) |
| `/admin/programs/{id}/` | DELETE | Delete program | Yes (Admin) |
| `/staff/students/` | GET | List students | Yes (Staff) |
| `/staff/students/{id}/` | GET | Get student details | Yes (Staff) |
| `/staff/students/{id}/` | PATCH/PUT | Update student | Yes (Admin) |
| `/staff/students/{id}/` | DELETE | Delete student | Yes (Admin) |
| `/slides/` | GET | List slides | No |
| `/slides/` | POST | Create slide | Yes (Staff) |
| `/slides/{id}/` | PATCH/PUT | Update slide | Yes (Staff) |
| `/slides/{id}/` | DELETE | Delete slide | Yes (Staff) |
| `/notifications/` | GET | List notifications | Yes |
| `/notifications/` | POST | Create notification | Yes (Staff) |
| `/notifications/bulk/` | POST | Bulk create notifications | Yes (Staff) |
| `/notifications/{id}/` | PATCH/PUT | Update notification | Yes (Staff) |
| `/notifications/{id}/` | DELETE | Delete notification | Yes (Staff) |
| `/quotes/` | GET | List quotes | No |
| `/quotes/` | POST | Create quote | Yes (Staff) |
| `/quotes/{id}/` | GET | Get quote | No |
| `/quotes/{id}/` | PATCH/PUT | Update quote | Yes (Staff) |
| `/quotes/{id}/` | DELETE | Delete quote | Yes (Staff) |
| `/articles/` | GET | List articles | No |
| `/articles/` | POST | Create article | Yes (Staff) |
| `/articles/{id}/` | PATCH/PUT | Update article | Yes (Staff) |
| `/articles/{id}/` | DELETE | Delete article | Yes (Staff) |
| `/admin/courses/` | GET | List courses | Yes (Admin) |
| `/admin/courses/` | POST | Create course | Yes (Admin) |
| `/admin/courses/{id}/` | PATCH/PUT | Update course | Yes (Admin) |
| `/admin/courses/{id}/` | DELETE | Delete course | Yes (Admin) |
| `/import/programs/` | POST | Import programs | Yes (Admin) |
| `/import/courses/` | POST | Import courses | Yes (Admin) |
| `/import/jobs/{id}/` | GET | Get import job status | Yes (Admin) |
| `/import/jobs/` | GET | List import jobs | Yes (Admin) |

---

## Testing Checklist

- [ ] All list endpoints return paginated responses
- [ ] All create endpoints return created object
- [ ] All update endpoints support both PATCH and PUT
- [ ] All delete endpoints return 204 or success message
- [ ] Search functionality works on all list endpoints
- [ ] Filtering works correctly
- [ ] Sorting works correctly
- [ ] Error responses follow standard format
- [ ] Authentication is required for protected endpoints
- [ ] Admin-only endpoints check for admin permissions


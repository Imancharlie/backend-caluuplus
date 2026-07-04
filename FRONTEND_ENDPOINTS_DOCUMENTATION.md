# Frontend Endpoints Documentation

This document provides a comprehensive overview of all endpoints that the frontend expects from the backend, including their expected data structures, request/response formats, and important implementation notes.

## Table of Contents
1. [Authentication Endpoints](#authentication-endpoints)
2. [Academic Structure Endpoints](#academic-structure-endpoints)
3. [Student Management Endpoints](#student-management-endpoints)
4. [Course Management Endpoints](#course-management-endpoints)
5. [GPA Calculation Endpoints](#gpa-calculation-endpoints)
6. [Timetable Endpoints](#timetable-endpoints)
7. [Articles Endpoints](#articles-endpoints)
8. [Slides Endpoints](#slides-endpoints)
9. [Notifications Endpoints](#notifications-endpoints)
10. [Blog Endpoints](#blog-endpoints)
11. [Important Implementation Notes](#important-implementation-notes)

---

## Authentication Endpoints

### POST /auth/register/
**Purpose**: User registration
**Request Body**:
```json
{
  "email": "user@example.com",
  "password": "password123",
  "password_confirm": "password123",
  "display_name": "John Doe",
  "gender": "male", // optional
  "phone_number": "+255712345678" // optional
}
```
**Response (201)**:
```json
{
  "user": {
    "id": "uuid",
    "email": "user@example.com",
    "display_name": "John Doe",
    "gender": "male",
    "phone_number": "+255712345678"
  },
  "token": "jwt_token_here"
}
```
**Error Responses**:
- `400`: Email already exists, validation errors
- `500`: Server error

### POST /auth/login/
**Purpose**: User login
**Request Body**:
```json
{
  "email": "user@example.com",
  "password": "password123"
}
```
**Response (200)**:
```json
{
  "user": {
    "id": "uuid",
    "email": "user@example.com",
    "display_name": "John Doe"
  },
  "token": "jwt_token_here"
}
```

---

## Academic Structure Endpoints

### GET /universities/
**Purpose**: Get all universities
**Response (200)**:
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
**Purpose**: Create university (admin only)
**Request Body**:
```json
{
  "name": "University Name",
  "country": "Country Name"
}
```

### GET /universities/{universityId}/colleges/
**Purpose**: Get colleges by university
**Response (200)**:
```json
[
  {
    "id": "uuid",
    "name": "College of Engineering",
    "university": "university_uuid",
    "university_name": "University of Dar es Salaam"
  }
]
```

### POST /admin/colleges/
**Purpose**: Create college (admin only)
**Request Body**:
```json
{
  "name": "College Name",
  "university": "university_uuid"
}
```

### GET /colleges/{collegeId}/programs/
**Purpose**: Get programs by college
**Response (200)**:
```json
[
  {
    "id": "uuid",
    "name": "Computer Science",
    "college": "college_uuid",
    "college_name": "College of Engineering",
    "university_name": "University of Dar es Salaam",
    "duration": 4
  }
]
```

### POST /admin/programs/
**Purpose**: Create program (admin only)
**Request Body**:
```json
{
  "name": "Program Name",
  "college": "college_uuid",
  "duration": 4
}
```

### GET /programs/{programId}/courses/
**Purpose**: Get courses by program
**Query Parameters**:
- `year` (optional): Filter by year
- `semester` (optional): Filter by semester
**Response (200)**:
```json
[
  {
    "id": "uuid",
    "code": "CS101",
    "name": "Introduction to Programming",
    "credits": 3,
    "type": "core",
    "semester": 1,
    "year": 1,
    "program": "program_uuid",
    "program_name": "Computer Science"
  }
]
```

---

## Student Management Endpoints

### GET /students/data/
**Purpose**: Get student profile data
**Response (200)**:
```json
{
  "id": "uuid",
  "university": {
    "id": "uuid",
    "name": "University Name",
    "country": "Tanzania"
  },
  "college": {
    "id": "uuid",
    "name": "College Name",
    "university": "university_uuid",
    "university_name": "University Name"
  },
  "program": {
    "id": "uuid",
    "name": "Program Name",
    "college": "college_uuid",
    "college_name": "College Name",
    "university_name": "University Name",
    "duration": 4
  },
  "year": 2,
  "semester": 1,
  "courses": [
    {
      "id": "uuid",
      "course": "course_uuid",
      "course_code": "CS101",
      "course_name": "Introduction to Programming",
      "course_credits": 3,
      "course_type": "core",
      "grade": "A",
      "points": 4.0
    }
  ],
  "gpa": 3.5,
  "has_courses": true
}
```

### POST /students/profile/
**Purpose**: Create student profile
**Request Body**:
```json
{
  "university": "university_uuid",
  "college": "college_uuid",
  "program": "program_uuid",
  "year": 1,
  "semester": 1
}
```

### PUT /students/profile/
**Purpose**: Update student profile
**Request Body**: Same as POST

---

## Course Management Endpoints

### POST /students/courses/
**Purpose**: Add course to student
**Request Body**:
```json
{
  "course_id": "course_uuid"
}
```

### DELETE /students/courses/{courseId}/
**Purpose**: Remove course from student

### POST /students/courses/batch/
**Purpose**: Batch add courses
**Request Body**:
```json
{
  "courses": ["course_uuid1", "course_uuid2"]
}
```

### GET /students/courses/semester/{semester}/year/{year}/
**Purpose**: Get courses by semester and year

### GET /students/courses/filter/
**Purpose**: Get courses with filtering
**Query Parameters**:
- `semester` (optional): Filter by semester
- `year` (optional): Filter by year
- `type` (optional): Filter by type (core/elective)

### PUT /students/courses/{courseId}/grade/
**Purpose**: Update course grade
**Request Body**:
```json
{
  "grade": "A"
}
```

### GET /students/courses/
**Purpose**: Get all student courses
**Response (200)**:
```json
[
  {
    "id": "uuid",
    "course": "course_uuid",
    "course_code": "CS101",
    "course_name": "Introduction to Programming",
    "course_credits": 3,
    "course_type": "core",
    "grade": "A",
    "points": 4.0
  }
]
```

---

## GPA Calculation Endpoints

### GET /students/gpa/
**Purpose**: Calculate current GPA
**Response (200)**:
```json
{
  "gpa": 3.5,
  "total_credits": 12,
  "total_points": 42.0,
  "graded_courses": 4,
  "breakdown": [
    {
      "course_code": "CS101",
      "course_name": "Introduction to Programming",
      "credits": 3,
      "grade": "A",
      "points": 4.0,
      "contribution": 12.0
    }
  ]
}
```

### POST /students/gpa/target/
**Purpose**: Generate target GPA calculation
**Request Body**:
```json
{
  "target_gpa": 3.7
}
```
**Response (200)**:
```json
{
  "message": "To achieve a GPA of 3.7, you need to...",
  "target_gpa": 3.7,
  "actual_gpa": 3.5,
  "accuracy": "95%",
  "grades": [
    {
      "course_id": "uuid",
      "course_code": "CS102",
      "course_name": "Data Structures",
      "credits": 3,
      "required_grade": "A+",
      "required_points": 4.0
    }
  ]
}
```

### POST /students/gpa/reset/
**Purpose**: Reset all grades

### POST /gpa/calculations/
**Purpose**: Store GPA calculation usage event (privacy-preserving).
**Privacy**:
- Backend stores **ciphertext only** for GPA values (server-side automatic encryption).
- Backend tracks usage counts/trends via metadata/timestamps.
- No user passphrase prompt is required.

**Request Body**:
```json
{
  "gpa": 3.75,
  "semester": 1,
  "academic_year": 2,
  "is_target": false
}
```

**Optional backward-compatible encrypted fields** (older clients may still send):
- `gpa_ciphertext`
- `gpa_iv`
- `gpa_salt`
- `gpa_alg`

**Response (201)**:
```json
{
  "message": "Encrypted GPA calculation event saved successfully",
  "id": "uuid",
  "semester": 1,
  "academic_year": 2,
  "is_target": false,
  "gpa_alg": "AES-GCM-PBKDF2",
  "created_at": "2026-04-02T12:34:56Z"
}
```

---

## Timetable Endpoints

### GET /timetable-slots/
**Purpose**: List timetable slots
**Query Parameters**:
- `student` (optional): Filter by student ID
- `semester` (optional): Filter by semester
- `academic_year` (optional): Filter by academic year
**Response (200)**:
```json
[
  {
    "id": "uuid",
    "course": "course_uuid",
    "time_slot": "0800-0900",
    "day_of_week": "monday",
    "semester": 1,
    "academic_year": "2024",
    "class_type": "lecture",
    "venue": "Room 101",
    "instructor": "Dr. Smith",
    "description": "Introduction to Programming"
  }
]
```

### GET /timetable/my/
**Purpose**: Get current user's timetable (legacy)

### GET /timetable/current
**Purpose**: Get current semester timetable

### GET /timetable?semester={semester}&academic_year={year}
**Purpose**: Get timetable by semester and year

### GET /timetable-slots/{slotId}/
**Purpose**: Get specific timetable slot

### POST /timetable-slots/
**Purpose**: Create timetable slot
**Request Body**:
```json
{
  "course": "course_uuid",
  "time_slot": "0800-0900",
  "day_of_week": "monday",
  "semester": 1,
  "academic_year": "2024",
  "class_type": "lecture",
  "venue": "Room 101",
  "instructor": "Dr. Smith",
  "description": "Introduction to Programming"
}
```

### PATCH /timetable-slots/{slotId}/
**Purpose**: Update timetable slot (partial)
**Request Body**: Partial update data

### DELETE /timetable-slots/{slotId}/
**Purpose**: Delete timetable slot

### POST /timetable-slots/bulk-create/
**Purpose**: Bulk create timetable slots
**Request Body**:
```json
{
  "slots": [
    {
      "course": "course_uuid",
      "time_slot": "0800-0900",
      "day_of_week": "monday",
      "semester": 1,
      "academic_year": "2024",
      "class_type": "lecture",
      "venue": "Room 101",
      "instructor": "Dr. Smith",
      "description": "Introduction to Programming"
    }
  ]
}
```

### DELETE /timetable-slots/bulk-delete/
**Purpose**: Bulk delete timetable slots
**Request Body**:
```json
{
  "slot_ids": ["uuid1", "uuid2"]
}
```

---

## Articles Endpoints

### GET /articles/
**Purpose**: Get articles with filtering
**Query Parameters**:
- `category` (optional): Filter by category slug
- `search` (optional): Search in title/content
- `tags` (optional): Filter by tags
- `author` (optional): Filter by author
- `sort_by` (optional): Sort by newest/oldest/popular/trending
- `page` (optional): Page number
- `page_size` (optional): Items per page
**Response (200)**:
```json
{
  "results": [
    {
      "id": "uuid",
      "title": "Article Title",
      "content": "Full article content...",
      "excerpt": "Short excerpt...",
      "cover_image": "/media/articles/image.jpg",
      "category": {
        "id": "uuid",
        "name": "Academics",
        "slug": "academics",
        "description": "Academic content",
        "color": "bg-green-500",
        "icon": "📚"
      },
      "tags": ["study", "tips"],
      "author": {
        "id": "uuid",
        "name": "Author Name",
        "avatar": "/media/avatars/author.jpg"
      },
      "published_at": "2024-01-01T00:00:00Z",
      "updated_at": "2024-01-01T00:00:00Z",
      "read_time": 5,
      "views": 100,
      "likes": 10,
      "is_liked": false,
      "is_saved": false,
      "is_shared": false,
      "share_count": 2,
      "status": "published"
    }
  ],
  "count": 50,
  "next": "http://api/articles/?page=2",
  "previous": null
}
```

### GET /articles/{id}/
**Purpose**: Get single article

### POST /articles/{id}/view/
**Purpose**: Track article view
**Response (200)**:
```json
{
  "views": 101
}
```

### GET /articles/categories/
**Purpose**: Get article categories
**Response (200)**:
```json
[
  {
    "id": "uuid",
    "name": "Academics",
    "slug": "academics",
    "description": "Academic content",
    "color": "bg-green-500",
    "icon": "📚"
  }
]
```

### POST /articles/{id}/like/
**Purpose**: Like/unlike article
**Response (200)**:
```json
{
  "is_liked": true,
  "likes": 11
}
```

### POST /articles/{id}/save/
**Purpose**: Save/unsave article
**Response (200)**:
```json
{
  "is_saved": true
}
```

### POST /articles/{id}/share/
**Purpose**: Share article
**Request Body**:
```json
{
  "platform": "facebook"
}
```
**Response (200)**:
```json
{
  "share_count": 3
}
```

### GET /articles/saved/
**Purpose**: Get saved articles

### POST /admin/articles/
**Purpose**: Create article (admin/staff authenticated)
**Request Body (key fields)**:
```json
{
  "title": "How to prepare for exams",
  "content": "{\"type\":\"doc\",\"content\":[]}",
  "excerpt": "Quick preparation checklist",
  "category": "general",
  "tags": ["study", "tips"],
  "is_published": true
}
```
**Category behavior**:
- `category` is **optional**
- Default category is **`general`** when omitted
- `null` / empty category is coerced to `general`
- Category is normalized to lowercase before save
- Allowed values: `academic`, `campus_life`, `news`, `events`, `general`

### PUT/PATCH /admin/articles/{id}/
**Purpose**: Update article (author/admin/staff)
**Category behavior**:
- `category` is **optional**
- If supplied as `null` / empty string, it is saved as `general`
- Invalid category values are rejected

---

## Slides Endpoints

### GET /slides/
**Purpose**: Get all slides
**Response (200)**:
```json
[
  {
    "id": "uuid",
    "title": "Slide Title",
    "description": "Slide description",
    "image": "/media/slides/image.jpg",
    "image_url": "http://localhost:8000/media/slides/image.jpg",
    "image_url_display": "http://localhost:8000/media/slides/image.jpg",
    "display_image": "http://localhost:8000/media/slides/image.jpg",
    "background_gradient": "from-blue-500 to-purple-500",
    "link_url": "/dashboard",
    "order": 1,
    "is_active": true,
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z"
  }
]
```

### POST /slides/
**Purpose**: Create slide
**Request Body**:
```json
{
  "title": "Slide Title",
  "description": "Slide description",
  "image": "image_file",
  "background_gradient": "from-blue-500 to-purple-500",
  "link_url": "/dashboard",
  "order": 1,
  "is_active": true
}
```

### PUT /slides/{id}/
**Purpose**: Update slide

### DELETE /slides/{id}/
**Purpose**: Delete slide

---

## Notifications Endpoints

### GET /notifications/unread-count/
**Purpose**: Get unread notification count
**Response (200)**:
```json
{
  "unread": 5
}
```

### GET /notifications/
**Purpose**: Get notifications
**Query Parameters**:
- `page` (optional): Page number
- `page_size` (optional): Items per page
- `include_read` (optional): Include read notifications
- `show_all` (optional): Show all notifications
- `all` (optional): Show all notifications
- `read_status` (optional): Filter by read status
**Response (200)**:
```json
{
  "notifications": [
    {
      "id": "uuid",
      "title": "Notification Title",
      "body": "Notification body text",
      "created_at": "2024-01-01T00:00:00Z",
      "is_read": false,
      "type": "info",
      "link": "/dashboard",
      "slide": {
        "id": "uuid",
        "title": "Slide Title",
        "description": "Slide description",
        "image_url": "http://localhost:8000/media/slides/image.jpg",
        "link_url": "/dashboard"
      },
      "read_at": null
    }
  ],
  "page": 1,
  "page_size": 20,
  "total_count": 50,
  "has_next": true,
  "has_previous": false
}
```

### POST /notifications/{id}/read/
**Purpose**: Mark notification as read

### POST /notifications/mark-all-read/
**Purpose**: Mark all notifications as read

### DELETE /notifications/{id}/
**Purpose**: Delete notification

### GET /notifications/stream/
**Purpose**: Server-Sent Events stream for real-time notifications
**Headers**: Authorization: Bearer {token}
**Response**: text/event-stream

---

## Blog Endpoints

### GET /blog/posts/
**Purpose**: Get all blog posts
**Response (200)**:
```json
[
  {
    "id": "uuid",
    "title": "Blog Post Title",
    "content": "Full blog post content...",
    "excerpt": "Short excerpt...",
    "image": "/media/blog/image.jpg",
    "slug": "blog-post-title",
    "author": "Author Name",
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z",
    "likes": 10,
    "is_liked": false
  }
]
```

### GET /blog/posts/{slug}/
**Purpose**: Get single blog post

### POST /blog/posts/{id}/comments/
**Purpose**: Add comment to blog post
**Request Body**:
```json
{
  "content": "Comment text"
}
```
**Response (200)**:
```json
{
  "id": "uuid",
  "content": "Comment text",
  "author": "user_uuid",
  "authorName": "User Name",
  "createdAt": "2024-01-01T00:00:00Z"
}
```

### POST /blog/posts/{id}/like/
**Purpose**: Like blog post
**Response (200)**:
```json
{
  "likes": 11,
  "is_liked": true
}
```

### POST /blog/posts/{id}/unlike/
**Purpose**: Unlike blog post

### GET /blog/posts/{id}/comments/
**Purpose**: Get blog post comments

---

## Important Implementation Notes

### 1. Authentication
- All endpoints (except auth endpoints) require JWT token in Authorization header
- Format: `Authorization: Bearer {token}`
- Token should be included in request headers
- 401/403 responses should clear local storage and redirect to login

### 2. Error Handling
- Use consistent error response format:
```json
{
  "error": "Error message",
  "detail": "Detailed error information",
  "field_errors": {
    "field_name": ["Error message"]
  }
}
```

### 3. Pagination
- Use consistent pagination format:
```json
{
  "results": [...],
  "count": 100,
  "next": "http://api/endpoint/?page=2",
  "previous": null
}
```

### 4. Image URLs
- Handle both relative and absolute URLs
- Convert relative URLs to absolute URLs when needed
- Use proper media serving endpoints

### 5. CORS Configuration
- Enable CORS for frontend domain
- Allow credentials for authenticated requests
- Handle preflight requests properly

### 6. Rate Limiting
- Implement appropriate rate limiting
- Return 429 status code when rate limit exceeded
- Include retry-after header

### 7. Data Validation
- Validate all input data
- Return detailed validation errors
- Use appropriate HTTP status codes

### 8. Database Considerations
- Use UUIDs for all IDs
- Implement proper indexing
- Handle soft deletes where appropriate
- Use transactions for batch operations

### 9. Performance
- Implement caching where appropriate
- Use database queries efficiently
- Consider pagination for large datasets
- Optimize image serving

### 10. Security
- Sanitize all input data
- Implement proper authentication
- Use HTTPS in production
- Validate file uploads
- Implement CSRF protection

This documentation should serve as a comprehensive guide for implementing the backend endpoints that the frontend expects. Make sure to test all endpoints thoroughly and handle edge cases appropriately.

## Staff and Ambassador API Endpoints (Frontend Integration Guide)

This guide documents endpoints used by staff (admins) and ambassadors, with request/response examples for easy frontend wiring.

Notes
- All endpoints are prefixed with `/api`.
- Authentication: Bearer JWT required unless marked public.
- HTTP Statuses: 2xx success, 4xx client errors, 5xx server errors.


### Authentication

- POST `/auth/login/`
  - Body: `{ "email": "user@example.com", "password": "secret" }`
  - 200: `{ "token": "<JWT>" }`

- POST `/auth/change-password/`
  - Auth: required
  - Body:
    ```json
    {
      "old_password": "OldPass123",
      "new_password": "NewPass123!",
      "new_password_confirm": "NewPass123!"
    }
    ```
  - 200: `{ "message": "Password changed successfully" }`

---

### Staff & RBAC (Roles and Ambassador Assignment)

- GET `/staff/me/roles/`
  - Purpose: frontend gating; determine available menus/scope
  - Auth: required
  - 200:
    ```json
    {
      "is_admin": true,
      "is_ambassador": false,
      "ambassador_university_ids": ["uuid", "uuid"]
    }
    ```

- POST `/staff/ambassadors/assign/`
  - Purpose: admin assigns ambassador to a university
  - Auth: admin-only
  - Body: `{ "user_id": "uuid", "university_id": "uuid" }`
  - 200: `{ "message": "Assigned", "created": true }`

- POST `/staff/ambassadors/revoke/`
  - Purpose: admin revokes ambassador from a university
  - Auth: admin-only
  - Body: `{ "user_id": "uuid", "university_id": "uuid" }`
  - 200: `{ "message": "Revoked" }`

---

### Staff/Ambassador Search

- GET `/admin/search/?q=term`
  - Purpose: unified search across universities, colleges, programs, courses
  - Auth: required (admin sees all; ambassador sees scoped)
  - 200:
    ```json
    {
      "query": "term",
      "universities": [{"id":"uuid","name":"...","country":"..."}],
      "colleges": [{"id":"uuid","name":"...","university":"uuid","university_name":"..."}],
      "programs": [{"id":"uuid","name":"...","college":"uuid","college_name":"...","university_name":"...","duration":4}],
      "courses": [{"id":"uuid","code":"CS101","name":"...","credits":3,"type":"core","semester":1,"year":1,"program":"uuid","program_name":"..."}]
    }
    ```

---

### Staff Full-List Endpoints (Admin full control; Ambassador scoped)

- GET `/admin/list/universities/?search=term`
- GET `/admin/list/colleges/?search=term`
- GET `/admin/list/programs/?search=term`
- GET `/admin/list/courses/?search=term`
- GET `/admin/list/students/?search=term`
- GET `/admin/list/articles/?search=term`
- GET `/admin/list/quotes/?search=term`
- GET `/admin/list/notifications/?page=1&page_size=20&include_read=false&user_id=uuid`
- GET `/admin/list/slides/?page=1&page_size=20&type=banner&include_inactive=false`

Each endpoint returns:
```json
{ "results": [ ...objects... ], "count": 123 }
```

### Notifications Admin Management

- GET `/admin/list/notifications/`
  - Purpose: admin list all notifications with pagination and filtering
  - Auth: required (admin sees all; ambassador sees scoped)
  - Query Parameters:
    - `page`: Page number (default: 1)
    - `page_size`: Items per page (default: 20)
    - `include_read`: Include read notifications (`true`/`false`)
    - `user_id`: Filter by specific user ID
  - 200:
    ```json
    {
      "notifications": [
        {
          "id": "uuid",
          "user": "user_id",
          "user_name": "User Display Name",
          "title": "Notification Title",
          "body": "Notification Body",
          "created_at": "2025-10-08T14:40:43.000Z",
          "is_read": false,
          "type": "notification_type",
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

### Slides Admin Management

- GET `/admin/list/slides/`
  - Purpose: admin list all slides with pagination and filtering
  - Auth: required (admin sees all; ambassador sees scoped)
  - Query Parameters:
    - `page`: Page number (default: 1)
    - `page_size`: Items per page (default: 20)
    - `type`: Filter by slide type (`banner`, `popup`, etc.)
    - `include_inactive`: Include inactive slides (`true`/`false`)
  - 200:
    ```json
    {
      "slides": [
        {
          "id": "uuid",
          "title": "Slide Title",
          "description": "Slide Description",
          "image_url": "http://localhost:8000/media/slides/image.jpg",
          "link_url": "https://example.com",
          "slide_type": "banner",
          "is_active": true,
          "order": 1,
          "created_at": "2025-10-08T14:42:54.000Z"
        }
      ],
      "page": 1,
      "page_size": 20,
      "total_count": 25,
      "has_next": true,
      "has_previous": false
    }
    ```

---

### Universities

- GET `/universities/`
  - Purpose: list available universities (public)
  - 200: `[{ "id": "uuid", "name": "University Name", "country": "Country" }]`

- POST `/admin/universities/`
  - Purpose: create a university (authenticated users)
  - Body: `{ "name": "University Name", "country": "Country" }`
  - 201:
    ```json
    { "message": "University created successfully", "data": { "id": "uuid", "name": "University Name", "country": "Country" } }
    ```

---

### Colleges

- GET `/universities/{universityId}/colleges/`
  - Purpose: list colleges by university (public)
  - 200: `[{ "id": "uuid", "name": "College Name", "university": "uuid", "university_name": "University Name" }]`

- POST `/admin/colleges/`
  - Purpose: create a college (authenticated users)
  - Body: `{ "name": "College Name", "university": "uuid" }`
  - 201:
    ```json
    { "message": "College created successfully", "data": { "id": "uuid", "name": "College Name", "university": "uuid", "university_name": "University Name" } }
    ```

---

### Programs

- GET `/colleges/{collegeId}/programs/`
  - Purpose: list programs by college (public)
  - 200: `[{ "id": "uuid", "name": "Program", "college": "uuid", "college_name": "College Name", "university_name": "University Name", "duration": 4 }]`

- POST `/admin/programs/`
  - Purpose: create a program (authenticated users)
  - Body: `{ "name": "Program Name", "college": "uuid", "duration": 4 }`
  - 201:
    ```json
    { "message": "Program created successfully", "data": { "id": "uuid", "name": "Program Name", "college": "uuid", "college_name": "College Name", "university_name": "University Name", "duration": 4 } }
    ```

---

### Courses

- GET `/programs/{programId}/courses/?year=&semester=`
  - Options: `?search=term`
  - Purpose: list courses by program (public)
  - 200: `[{ "id": "uuid", "code": "CS101", "name": "Intro", "credits": 3, "type": "core", "semester": 1, "year": 1, "program": "uuid", "program_name": "Program" }]`

- POST `/admin/courses/`
  - Purpose: create a course (authenticated users)
  - Body:
    ```json
    {
      "code": "CS101",
      "name": "Intro",
      "credits": 3,
      "type": "core",
      "semester": 1,
      "year": 1,
      "program": "uuid"
    }
    ```
  - 201:
    ```json
    { "message": "Course created successfully", "data": { "id": "uuid", "code": "CS101", "name": "Intro", "credits": 3, "type": "core", "semester": 1, "year": 1, "program": "uuid", "program_name": "Program" } }
    ```

---

### Students

- Existing student endpoints remain unchanged for compatibility:
  - GET `/students/data/` – authenticated user’s profile data
  - POST `/students/profile/create/` – create/update profile
  - GET `/students/courses/` and related – manage student courses

---

### Articles

- GET `/articles/` – list; supports categories, saved, share, like (existing)
- POST `/articles/` – if enabling staff-only creation, add auth on frontend accordingly (current behavior unchanged)

---

### Quotes

- GET `/quotes/` – list active quotes (existing)
- POST `/quotes/create/` – create quote (auth)
- GET `/quotes/{quoteId}/` – get specific quote details
- PUT `/quotes/{quoteId}/` – update specific quote (auth)
- DELETE `/quotes/{quoteId}/` – delete specific quote (auth)

**Quote Detail Operations:**
```json
// GET /quotes/{quoteId}/
{
  "id": "uuid",
  "text": "Inspirational quote text",
  "author": "Quote Author",
  "is_active": true,
  "created_at": "2025-10-08T14:43:51.000Z"
}

// PUT /quotes/{quoteId}/
{
  "text": "Updated quote text",
  "author": "Updated Author",
  "is_active": false
}

// DELETE /quotes/{quoteId}/
{ "message": "Quote deleted successfully" }
```

---

### Error Patterns

- 401 Unauthenticated:
  ```json
  { "detail": "Authentication credentials were not provided." }
  ```

- 403 Unauthorized/Out of scope:
  ```json
  { "error": "Admin access required" }
  ```

- 400 Validation:
  ```json
  { "error": "Invalid data", "errors": { "field": ["message"] } }
  ```

---

### Frontend Integration Notes

- Always send `Authorization: Bearer <token>` header for protected routes.
- Use `/staff/me/roles/` at login/bootstrap to decide which menus and actions to enable.
- Handle 401 by redirecting to login; handle 403 by showing a friendly permission message.




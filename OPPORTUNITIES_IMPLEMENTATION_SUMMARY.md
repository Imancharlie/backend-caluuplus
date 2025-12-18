# Opportunities API Implementation Summary

## ✅ Implemented Features

All features from `OPPORTUNITIES_API_COMPLETE.md` have been implemented.

### 1. Model Changes ✅

**File:** `resources_opps/models.py`

- ✅ Added `status` field with choices: `pending`, `approved`, `rejected` (default: `pending`)
- ✅ Added `is_active` field (default: `False`)
- ✅ Added `Meta.ordering = ['-created_at']`

### 2. Serializer Changes ✅

**File:** `resources_opps/serializers.py`

- ✅ Added `status` field to serializer (read-only)
- ✅ Updated `get_is_active()` to check both `status='approved'` and `is_active=True`
- ✅ Status is read-only (users can't set it directly)

### 3. ViewSet Changes ✅

**File:** `resources_opps/views.py`

#### ✅ Auto-set Fields on Create
- `created_by` = authenticated user
- `status` = `'pending'`
- `is_active` = `False`
- Validates university belongs to user

#### ✅ Public List Endpoint (GET /api/resources_opps/opportunities/)
- **Filters to only show:** `status='approved'` AND `is_active=True`
- **Excludes:** `pending` and `rejected` opportunities
- Supports all query parameters: `category`, `search`, `start_date`, `end_date`, `university`

#### ✅ User's Own Opportunities
- When `created_by` or `status` query param is provided, shows all user's opportunities regardless of status
- Supports filtering by `status` query parameter

#### ✅ Single Opportunity Retrieval (GET /api/resources_opps/opportunities/{id}/)
- Public users: Only see `approved` and `active` opportunities (404 for others)
- Creator: Can see their own opportunities regardless of status
- Admin/Staff: Can see all opportunities

#### ✅ Update Opportunity (PATCH/PUT)
- ✅ Permission check: Only owner or admin/staff can update
- ✅ Auto-reset: If opportunity was `approved`, resets to `pending` and `is_active=False` on update
- ✅ Requires re-approval after update

#### ✅ Delete Opportunity (DELETE)
- ✅ Permission check: Only owner or admin/staff can delete
- ✅ Can delete regardless of status

#### ✅ Admin Approval Endpoint (NEW)
**Endpoint:** `PATCH /api/resources_opps/opportunities/{id}/approve/`

**Request:**
```json
{
  "status": "approved",  // or "rejected"
  "is_active": true      // true if approved, false if rejected
}
```

**Response:**
```json
{
  "id": "uuid",
  "status": "approved",
  "is_active": true,
  "message": "Opportunity approved successfully"
}
```

- ✅ Requires admin permissions (`IsAdminUser`)
- ✅ Updates both `status` and `is_active`
- ✅ TODO: Notification to creator (placeholder added)

#### ✅ Pending List Endpoint (NEW)
**Endpoint:** `GET /api/resources_opps/opportunities/pending/`

**Query Parameters:**
- `university` (optional) - Filter by university
- `page` (optional) - Page number
- `limit` (optional) - Items per page (default: 12)

**Response:**
```json
{
  "count": 10,
  "next": "...",
  "previous": null,
  "results": [...]
}
```

- ✅ Requires admin permissions
- ✅ Returns only `status='pending'` opportunities
- ✅ Supports pagination

### 4. Existing Endpoints (Maintained) ✅

- ✅ `GET /api/resources_opps/opportunities/categories/` - Get categories
- ✅ `GET /api/resources_opps/opportunities/stats/` - Get statistics
- ✅ `GET /api/resources_opps/opportunities/{id}/download_media/` - Download media

---

## Endpoint Summary

| Method | Endpoint | Auth Required | Description |
|--------|----------|---------------|-------------|
| GET | `/opportunities/` | No | List approved opportunities (public) |
| GET | `/opportunities/?created_by=...` | Yes | List user's own opportunities |
| GET | `/opportunities/{id}/` | Conditional | Get single opportunity |
| POST | `/opportunities/` | Yes | Create opportunity (auto: status=pending, is_active=false) |
| PATCH | `/opportunities/{id}/` | Yes (owner) | Update opportunity (resets to pending if approved) |
| DELETE | `/opportunities/{id}/` | Yes (owner) | Delete opportunity |
| PATCH | `/opportunities/{id}/approve/` | Yes (admin) | **NEW** Approve/reject opportunity |
| GET | `/opportunities/pending/` | Yes (admin) | **NEW** List pending opportunities |
| GET | `/opportunities/categories/` | No | Get categories |
| GET | `/opportunities/stats/` | No | Get statistics |

---

## Migration Required

Run these commands to apply database changes:

```bash
python manage.py makemigrations resources_opps
python manage.py migrate
```

**Migration will add:**
- `status` field (CharField, default='pending')
- `is_active` field (BooleanField, default=False)

---

## Testing Checklist

- [ ] User can create opportunity → status='pending', is_active=False
- [ ] Public list only shows approved opportunities
- [ ] User can view their own opportunities (all statuses)
- [ ] User can edit their own opportunities
- [ ] Approved opportunity resets to pending on update
- [ ] User can delete their own opportunities
- [ ] Admin can approve pending opportunities
- [ ] Admin can reject pending opportunities
- [ ] Admin can view pending list
- [ ] Non-approved opportunities return 404 for public users
- [ ] Creator can view their own non-approved opportunities

---

## Status Flow

```
User Creates → status='pending', is_active=False
     ↓
Admin Approves → status='approved', is_active=True (visible to public)
     OR
Admin Rejects → status='rejected', is_active=False (not visible)
     ↓
User Updates Approved → status='pending', is_active=False (requires re-approval)
```

---

## Notes

1. **Public View**: Only shows `status='approved'` AND `is_active=True`
2. **User's View**: Shows all their opportunities when filtering by `created_by` or `status`
3. **Permission Checks**: Users can only edit/delete their own opportunities
4. **Auto-Reset**: Updating an approved opportunity resets it to pending
5. **Admin Only**: Approval and pending list endpoints require admin permissions

All endpoints match the documentation in `OPPORTUNITIES_API_COMPLETE.md` exactly.


















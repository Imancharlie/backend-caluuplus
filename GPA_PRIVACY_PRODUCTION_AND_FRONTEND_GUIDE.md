# GPA Privacy: Production + Frontend Guide

## Goal
Store GPA calculations as encrypted payloads so backend stores ciphertext only, while still tracking usage trends.

---

## Production Rollout Checklist

1. Pull latest backend code.
2. Install dependencies:
   - `pip install -r requirements.txt`
3. Run migrations:
   - `python manage.py migrate`
4. Verify conversion and encrypted-field completeness:
   - `python manage.py verify_gpa_privacy`
5. Restart app workers.

If step 4 fails, do not continue rollout until missing encrypted fields are fixed.

---

## How Conversion Works

- Existing plaintext GPA rows are converted during migration into:
  - `gpa_ciphertext`
  - `gpa_iv`
  - `gpa_salt`
  - `gpa_alg`
- Plaintext column is removed afterwards.
- Post-migration, backend does not keep readable GPA values.

---

## Frontend Implementation (No Prompt Required)

### 1) Send GPA normally (plaintext over HTTPS)
Endpoint:
- `POST /api/gpa/calculations/`

Body:
```json
{
  "gpa": 3.75,
  "semester": 1,
  "academic_year": 2,
  "is_target": false
}
```

### 2) Backend encrypts automatically
- Backend derives a per-user encryption key using:
  - server secret
  - user-specific token surface (user id + password hash + email)
  - per-record random salt
- GPA is stored only as:
  - `gpa_ciphertext`
  - `gpa_iv`
  - `gpa_salt`
  - `gpa_alg`

### 3) Optional backward compatibility
- Backend still accepts encrypted payload fields if sent by older clients.
- Recommended new client flow: send only `gpa` and metadata.

---

## Privacy Notes

- Backend can still track:
  - usage count
  - usage timestamps
  - semester/year metadata
- Backend should not display decrypted GPA in admin analytics.
- Frontend should still avoid logging GPA payloads in production telemetry.


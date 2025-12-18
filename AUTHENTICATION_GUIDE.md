# Seamless Authentication Guide - Email/Password & Google Login

## Overview

The authentication system supports seamless login with both **email/password** and **Google OAuth**, with automatic account linking. Users can switch between login methods seamlessly.

---

## Authentication Flow

### Scenario 1: User First Registers with Email/Password

1. **User registers** with email and password
   - Account created with email/password
   - `firebase_uid` = null

2. **User later logs in with Google** (same email)
   - System finds user by email
   - Links Google account: sets `firebase_uid`
   - User can now login with **either** email/password **or** Google

3. **User logs in with email/password again**
   - Works normally
   - User has both login methods available

### Scenario 2: User First Logs in with Google

1. **User logs in with Google**
   - Account created with `firebase_uid`
   - No password set

2. **User later registers/sets password** (same email)
   - System finds existing user by email
   - Sets password on existing account
   - User can now login with **either** email/password **or** Google

3. **User logs in with Google again**
   - Works normally
   - User has both login methods available

---

## Endpoints

### 1. Register (Email/Password)
**POST** `/api/auth/register/`

**Request:**
```json
{
  "email": "user@example.com",
  "password": "securepassword123",
  "password_confirm": "securepassword123",
  "display_name": "John Doe",
  "gender": "male",
  "phone_number": "+255123456789"
}
```

**Response (201):**
```json
{
  "user": {
    "id": "uuid",
    "email": "user@example.com",
    "display_name": "John Doe",
    "firebase_uid": null,
    "has_google_linked": false,
    "account_linked": false
  },
  "access_token": "jwt_token",
  "refresh_token": "refresh_token",
  "message": "Account created successfully! You can now login with email/password or Google."
}
```

**Special Case:** If user previously logged in with Google (same email), registration will:
- Link the password to existing Google account
- Return `account_linked: true`
- Message: "Password set successfully! Your account is now linked."

---

### 2. Login (Email/Password)
**POST** `/api/auth/login/`

**Request:**
```json
{
  "email": "user@example.com",
  "password": "securepassword123"
}
```

**Response (200):**
```json
{
  "user": {
    "id": "uuid",
    "email": "user@example.com",
    "display_name": "John Doe",
    "firebase_uid": "firebase-uid-123" or null,
    "has_google_linked": true or false
  },
  "access_token": "jwt_token",
  "refresh_token": "refresh_token",
  "message": "Successfully logged in"
}
```

**Note:** Works even if user has `firebase_uid` (previously logged in with Google)

---

### 3. Login (Google OAuth)
**POST** `/api/auth/firebase-login/`

**Request:**
```json
{
  "token": "firebase_id_token_from_google_signin"
}
```

**Response (200):**
```json
{
  "user": {
    "id": "uuid",
    "email": "user@example.com",
    "display_name": "John Doe",
    "profile_picture": "https://...",
    "firebase_uid": "firebase-uid-123",
    "is_new_user": false,
    "account_linked": true,
    "has_password": true,
    "can_login_with_password": true
  },
  "access_token": "jwt_token",
  "refresh_token": "refresh_token",
  "message": "Welcome back! Your Google account has been linked to your existing account."
}
```

**Account Linking Logic:**
1. First checks by `firebase_uid` (user logged in with Google before)
2. If not found, checks by `email` (user has email/password account)
3. If found by email, links Google account (sets `firebase_uid`)
4. If not found, creates new user

---

## Account Linking Scenarios

### ✅ Scenario A: Email First → Google Later
```
1. Register: email + password → firebase_uid = null
2. Login with Google → Finds by email → Links → firebase_uid = "xxx"
3. Can login with either method
```

### ✅ Scenario B: Google First → Password Later
```
1. Login with Google → Creates account → firebase_uid = "xxx", no password
2. Register with same email → Finds by email → Sets password
3. Can login with either method
```

### ✅ Scenario C: Multiple Google Logins
```
1. Login with Google → Creates account
2. Login with Google again → Finds by firebase_uid → Works
```

### ✅ Scenario D: Multiple Email/Password Logins
```
1. Register with email/password
2. Login with email/password → Works
3. Still works even after Google login
```

---

## User Model Fields

| Field | Description | Auto-set |
|-------|-------------|----------|
| `email` | User email (unique) | Required |
| `password` | Hashed password | On registration |
| `firebase_uid` | Firebase user ID | On Google login |
| `display_name` | User's display name | Required |
| `profile_picture` | Profile picture URL | From Google |

---

## Frontend Implementation

### Email/Password Login
```javascript
const response = await fetch('/api/auth/login/', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    email: 'user@example.com',
    password: 'password123'
  })
});

const data = await response.json();
// Store tokens
localStorage.setItem('access_token', data.access_token);
localStorage.setItem('refresh_token', data.refresh_token);

// Check if Google is linked
if (data.user.has_google_linked) {
  console.log('User can also login with Google');
}
```

### Google Login
```javascript
// 1. Sign in with Google (Firebase SDK)
import { getAuth, GoogleAuthProvider, signInWithPopup } from 'firebase/auth';

const auth = getAuth();
const provider = new GoogleAuthProvider();

const result = await signInWithPopup(auth, provider);
const idToken = await result.user.getIdToken();

// 2. Send token to backend
const response = await fetch('/api/auth/firebase-login/', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ token: idToken })
});

const data = await response.json();
// Store tokens
localStorage.setItem('access_token', data.access_token);
localStorage.setItem('refresh_token', data.refresh_token);

// Check account status
if (data.user.account_linked) {
  console.log('Google account linked to existing account');
}
if (data.user.can_login_with_password) {
  console.log('User can also login with email/password');
}
```

### Registration
```javascript
const response = await fetch('/api/auth/register/', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    email: 'user@example.com',
    password: 'password123',
    password_confirm: 'password123',
    display_name: 'John Doe'
  })
});

const data = await response.json();
if (data.user.account_linked) {
  console.log('Password set on existing Google account');
}
```

---

## Firebase Setup (Optional)

The system works **without Firebase** for email/password authentication. Firebase is only needed for Google login.

### To Enable Google Login:

1. **Install Firebase Admin:**
   ```bash
   pip install firebase-admin
   ```

2. **Add Firebase Credentials:**
   - Place `firebase-credentials.json` in project root
   - Or set `FIREBASE_CREDENTIALS_PATH` environment variable

3. **Frontend Firebase Config:**
   - Initialize Firebase SDK in your frontend
   - Configure Google OAuth provider

### Without Firebase:
- Email/password authentication works normally
- Google login will return 503 error (service unavailable)
- System continues to function for email/password users

---

## Error Handling

### Firebase Not Available
```json
{
  "error": "Authentication temporarily unavailable",
  "message": "Please try again later or contact support if the issue persists."
}
```
**Status:** 503 Service Unavailable

### Invalid Credentials
```json
{
  "email": ["Invalid credentials"]
}
```
**Status:** 400 Bad Request

### Email Already Exists (with password)
```json
{
  "email": ["A user with this email already exists. Please login instead."]
}
```
**Status:** 400 Bad Request

---

## Security Notes

1. **Password Hashing:** All passwords are hashed using Django's password hashing
2. **JWT Tokens:** Access and refresh tokens for API authentication
3. **Account Linking:** Only links accounts with **same email address**
4. **Firebase UID:** Unique identifier from Google, prevents duplicate accounts

---

## Testing Scenarios

- [ ] Register with email/password → Login with email/password → Works
- [ ] Register with email/password → Login with Google (same email) → Links → Works
- [ ] Login with Google → Register with password (same email) → Links → Works
- [ ] Login with Google → Login with Google again → Works
- [ ] Login with email/password (after Google) → Works
- [ ] Login with Google (after email/password) → Works

---

## Summary

✅ **Seamless Account Linking:**
- Email/password and Google login work interchangeably
- Accounts automatically link by email address
- Users can switch login methods anytime

✅ **Backward Compatible:**
- Existing email/password users continue to work
- Google login links to existing accounts
- No breaking changes

✅ **User-Friendly:**
- Clear messages about account linking
- No duplicate accounts
- Single account, multiple login methods





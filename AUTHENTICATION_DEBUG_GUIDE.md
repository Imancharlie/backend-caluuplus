# Authentication Debug Guide

## Issue: Login Redirects Back to Login Page

### Symptoms
- User successfully logs in with email/password
- Login endpoint returns tokens successfully
- User immediately gets redirected back to login page
- Appears as if user is logged out

### Possible Causes

1. **Token Not Stored in Frontend**
   - Frontend receives tokens but doesn't store them
   - Check browser localStorage/sessionStorage
   - Verify token storage code in frontend

2. **Token Not Sent in Requests**
   - Frontend stores token but doesn't include it in Authorization header
   - Check if requests include: `Authorization: Bearer <token>`
   - Verify axios/fetch interceptors are configured

3. **Token Format Issue**
   - Token might need "Bearer " prefix
   - Check if frontend adds "Bearer " before token

4. **CORS Issues**
   - Browser might block Authorization header
   - Check CORS configuration allows Authorization header

5. **Token Validation Failing**
   - Token might be invalid immediately after generation
   - Check token expiration settings
   - Verify token signature

## Debugging Steps

### 1. Check Login Response
After login, check the response in browser DevTools:
```json
{
  "user": {...},
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "token_type": "Bearer",
  "message": "Successfully logged in"
}
```

### 2. Verify Token Storage
Check browser console:
```javascript
// Check if token is stored
localStorage.getItem('access_token')  // or whatever key you use
localStorage.getItem('refresh_token')
```

### 3. Test Token Verification Endpoint
After login, immediately call:
```bash
GET /api/auth/verify/
Headers:
  Authorization: Bearer <access_token>
```

Expected response:
```json
{
  "user": {...},
  "authenticated": true,
  "message": "Token is valid"
}
```

### 4. Check Server Logs
Look for these log messages:
- `Login successful for user <id> (<email>)`
- `Access token generated (length: <n>)`
- `Token verification request from user <id>`
- `Token validation failed: <error>` (if there's an issue)

### 5. Test Token Refresh
If access token expires, test refresh:
```bash
POST /api/auth/refresh/
Body:
{
  "refresh": "<refresh_token>"
}
```

## Frontend Checklist

### ✅ Token Storage
```javascript
// After successful login
const { access_token, refresh_token } = response.data;
localStorage.setItem('access_token', access_token);
localStorage.setItem('refresh_token', refresh_token);
```

### ✅ Request Interceptor
```javascript
// Add token to all requests
axios.interceptors.request.use(config => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});
```

### ✅ Response Interceptor (Token Refresh)
```javascript
// Handle 401 and refresh token
axios.interceptors.response.use(
  response => response,
  async error => {
    if (error.response?.status === 401) {
      const refreshToken = localStorage.getItem('refresh_token');
      if (refreshToken) {
        try {
          const { data } = await axios.post('/api/auth/refresh/', {
            refresh: refreshToken
          });
          localStorage.setItem('access_token', data.access_token);
          // Retry original request
          error.config.headers.Authorization = `Bearer ${data.access_token}`;
          return axios.request(error.config);
        } catch (refreshError) {
          // Refresh failed, redirect to login
          localStorage.removeItem('access_token');
          localStorage.removeItem('refresh_token');
          window.location.href = '/login';
        }
      }
    }
    return Promise.reject(error);
  }
);
```

### ✅ Check Authentication on App Load
```javascript
// On app initialization
const token = localStorage.getItem('access_token');
if (token) {
  // Verify token is still valid
  try {
    const response = await axios.get('/api/auth/verify/');
    if (response.data.authenticated) {
      // User is authenticated
      setUser(response.data.user);
    } else {
      // Token invalid, redirect to login
      localStorage.removeItem('access_token');
      window.location.href = '/login';
    }
  } catch (error) {
    // Token invalid, redirect to login
    localStorage.removeItem('access_token');
    window.location.href = '/login';
  }
}
```

## Backend Endpoints

### Login
```
POST /api/auth/login/
Body: { "email": "...", "password": "..." }
Response: { "user": {...}, "access_token": "...", "refresh_token": "...", "token_type": "Bearer" }
```

### Verify Token
```
GET /api/auth/verify/
Headers: Authorization: Bearer <access_token>
Response: { "user": {...}, "authenticated": true }
```

### Refresh Token
```
POST /api/auth/refresh/
Body: { "refresh": "<refresh_token>" }
Response: { "access_token": "...", "token_type": "Bearer" }
```

## Common Issues & Solutions

### Issue 1: Token Not Persisting
**Solution**: Check localStorage/sessionStorage permissions, ensure storage is enabled

### Issue 2: CORS Blocking Authorization Header
**Solution**: Verify CORS settings in `settings.py`:
```python
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',  # Make sure this is included
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
]
```

### Issue 3: Token Expires Immediately
**Solution**: Check `SIMPLE_JWT` settings:
```python
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),  # Should be 60 minutes
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),     # Should be 7 days
}
```

### Issue 4: Frontend Making Request Before Token Stored
**Solution**: Ensure token is stored BEFORE making any authenticated requests:
```javascript
// ❌ Wrong - making request before token stored
login().then(() => {
  fetchUserData();  // Token not stored yet!
});

// ✅ Correct - wait for token storage
login().then(response => {
  localStorage.setItem('access_token', response.data.access_token);
  fetchUserData();  // Token is now available
});
```

## Testing

### Test Login Flow
1. Open browser DevTools → Network tab
2. Login with email/password
3. Check login request response (should have tokens)
4. Check if next request includes `Authorization: Bearer <token>` header
5. If not, token storage/interceptor is the issue

### Test Token Verification
1. After login, manually call `/api/auth/verify/` with token
2. If it returns 401, token is invalid
3. If it returns 200, token is valid but frontend isn't using it

## Next Steps

1. **Check Frontend Code**: Verify token storage and request interceptors
2. **Check Browser Console**: Look for errors or warnings
3. **Check Network Tab**: Verify Authorization header is sent
4. **Check Server Logs**: Look for authentication errors
5. **Test Verify Endpoint**: Manually test token verification

If all checks pass but issue persists, the problem is likely in the frontend routing/state management.




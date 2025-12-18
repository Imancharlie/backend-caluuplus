# Authentication Duration Configuration Guide

## Overview
Users will now stay authenticated for **7 days** even after closing the browser tab. No login required during this period.

## Backend Changes

### JWT Token Lifetimes
- **Access Token**: 7 days (previously 60 minutes)
- **Refresh Token**: 14 days (previously 7 days)
- **Sliding Token**: 7 days (previously 5 minutes)

### What This Means
1. Users can close the browser tab and return within 7 days without needing to log in
2. Access tokens remain valid for 7 days
3. Refresh tokens provide an additional 7-day buffer (14 days total)
4. Tokens are automatically rotated for security

## Frontend Implementation Requirements

### 1. Token Storage
Store tokens in `localStorage` (not `sessionStorage`) so they persist after closing the tab:

```javascript
// After login
localStorage.setItem('access_token', response.data.access_token);
localStorage.setItem('refresh_token', response.data.refresh_token);
```

### 2. Token Refresh Logic (Optional but Recommended)
Even though access tokens last 7 days, implement automatic refresh for better UX:

```javascript
// Check token expiration and refresh if needed
const refreshTokenIfNeeded = async () => {
  const accessToken = localStorage.getItem('access_token');
  const refreshToken = localStorage.getItem('refresh_token');
  
  if (!accessToken || !refreshToken) {
    return false;
  }
  
  try {
    // Decode token to check expiration (using jwt-decode library)
    const decoded = jwt_decode(accessToken);
    const expirationTime = decoded.exp * 1000; // Convert to milliseconds
    const currentTime = Date.now();
    
    // Refresh if token expires in less than 24 hours
    if (expirationTime - currentTime < 24 * 60 * 60 * 1000) {
      const response = await fetch('/api/auth/refresh/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          refresh: refreshToken
        })
      });
      
      if (response.ok) {
        const data = await response.json();
        localStorage.setItem('access_token', data.access_token);
        return true;
      }
    }
  } catch (error) {
    console.error('Token refresh failed:', error);
    // If refresh fails, user will need to login again
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    return false;
  }
  
  return true;
};

// Call on app initialization
refreshTokenIfNeeded();
```

### 3. Check Authentication on App Load
```javascript
// On app initialization (e.g., in App.js or main component)
useEffect(() => {
  const checkAuth = async () => {
    const accessToken = localStorage.getItem('access_token');
    
    if (accessToken) {
      try {
        // Verify token is still valid
        const response = await fetch('/api/auth/verify/', {
          headers: {
            'Authorization': `Bearer ${accessToken}`
          }
        });
        
        if (response.ok) {
          const data = await response.json();
          if (data.authenticated) {
            // User is authenticated, set user state
            setUser(data.user);
            return;
          }
        }
      } catch (error) {
        console.error('Auth check failed:', error);
      }
    }
    
    // If no token or invalid token, redirect to login
    // (or show login page)
  };
  
  checkAuth();
}, []);
```

### 4. API Request Interceptor (Axios Example)
```javascript
import axios from 'axios';

// Add token to all requests
axios.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Handle 401 errors and refresh token
axios.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;
      
      const refreshToken = localStorage.getItem('refresh_token');
      if (refreshToken) {
        try {
          const response = await fetch('/api/auth/refresh/', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              refresh: refreshToken
            })
          });
          
          if (response.ok) {
            const data = await response.json();
            localStorage.setItem('access_token', data.access_token);
            originalRequest.headers.Authorization = `Bearer ${data.access_token}`;
            return axios(originalRequest);
          }
        } catch (refreshError) {
          // Refresh failed, redirect to login
          localStorage.removeItem('access_token');
          localStorage.removeItem('refresh_token');
          window.location.href = '/login';
          return Promise.reject(refreshError);
        }
      }
    }
    
    return Promise.reject(error);
  }
);
```

## Security Considerations

### Pros
- ✅ Better user experience - no frequent logins
- ✅ Reduced server load from fewer login requests
- ✅ Users can work across multiple sessions

### Cons
- ⚠️ Longer-lived tokens are less secure if compromised
- ⚠️ Stolen tokens remain valid for 7 days

### Mitigation Strategies
1. **Token Rotation**: Enabled (`ROTATE_REFRESH_TOKENS: True`)
2. **HTTPS Only**: Always use HTTPS in production
3. **Token Blacklisting**: Old tokens are blacklisted after rotation
4. **Logout**: Implement proper logout that clears tokens
5. **Token Storage**: Use `httpOnly` cookies if possible (more secure than localStorage)

## Testing

### Test Scenarios
1. ✅ Login and close browser tab → Return after 6 days → Should still be authenticated
2. ✅ Login and close browser tab → Return after 8 days → Should require login
3. ✅ Multiple tabs → Close one → Other tabs should still work
4. ✅ Token refresh → Should work seamlessly

## Logout Implementation

Make sure logout clears tokens:

```javascript
const handleLogout = () => {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
  // Clear any other user-related data
  setUser(null);
  // Redirect to login
  window.location.href = '/login';
};
```

## Notes

- **Current Settings**: Access tokens valid for 7 days, refresh tokens for 14 days
- **Token Storage**: Use `localStorage` (not `sessionStorage`) for persistence
- **Automatic Refresh**: Implement token refresh logic for seamless experience
- **Security**: Consider implementing additional security measures for production

## Changing Token Duration

To change the duration, edit `academic_backend/settings.py`:

```python
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=7),  # Change this
    'REFRESH_TOKEN_LIFETIME': timedelta(days=14),  # Change this
    # ... other settings
}
```

**Note**: After changing settings, users with existing tokens will need to log in again for the new duration to take effect.






# Frontend Debugging Guide - Excessive API Calls

## 🚨 Problem Identified
The frontend is making excessive API calls to:
- `/api/user/basic-details/` 
- `/api/notifications/unread-count/`

These endpoints are being called multiple times per second, causing performance issues.

## 🔧 Backend Fixes Applied

### 1. **Rate Limiting Added**
- `user_basic_details`: Max 5 calls per 30 seconds
- `notification_unread_count`: Max 10 calls per 30 seconds
- Returns HTTP 429 when limit exceeded

### 2. **Caching Implemented**
- User details cached for 60 seconds
- Notification count cached for 30 seconds
- Cache automatically invalidated when data changes

### 3. **Response Format Fixed**
- Delete operations now return explicit success message
- Notification count returns `unread` (not `unread_count`)

## 🐛 Frontend Issues to Check

### 1. **Infinite Re-rendering Loops**
Check for:
```javascript
// ❌ BAD - Missing dependency array
useEffect(() => {
  fetchUserDetails();
}, []); // Missing dependencies

// ✅ GOOD - Proper dependency array
useEffect(() => {
  fetchUserDetails();
}, [userId]); // Only re-run when userId changes
```

### 2. **State Updates in useEffect**
Check for:
```javascript
// ❌ BAD - State update causing re-render
useEffect(() => {
  setUserData(data);
  fetchUserDetails(); // This will cause another re-render
}, [data]);

// ✅ GOOD - Separate concerns
useEffect(() => {
  fetchUserDetails();
}, [userId]);

useEffect(() => {
  setUserData(data);
}, [data]);
```

### 3. **Polling Intervals Too Frequent**
Check for:
```javascript
// ❌ BAD - Too frequent polling
setInterval(() => {
  fetchNotifications();
}, 1000); // Every second!

// ✅ GOOD - Reasonable polling
setInterval(() => {
  fetchNotifications();
}, 30000); // Every 30 seconds
```

### 4. **Missing Cleanup**
Check for:
```javascript
// ❌ BAD - No cleanup
useEffect(() => {
  const interval = setInterval(() => {
    fetchNotifications();
  }, 5000);
  // Missing cleanup!
}, []);

// ✅ GOOD - Proper cleanup
useEffect(() => {
  const interval = setInterval(() => {
    fetchNotifications();
  }, 5000);
  
  return () => clearInterval(interval); // Cleanup
}, []);
```

## 🔍 Debugging Steps

### 1. **Check Network Tab**
- Open DevTools → Network tab
- Look for rapid calls to the same endpoints
- Check if calls are being made unnecessarily

### 2. **Add Console Logs**
```javascript
useEffect(() => {
  console.log('Fetching user details...', new Date().toISOString());
  fetchUserDetails();
}, [dependencies]);
```

### 3. **Check Component Re-renders**
```javascript
// Add this to components that fetch data
console.log('Component rendered:', componentName, new Date().toISOString());
```

### 4. **Use React DevTools**
- Install React DevTools extension
- Check for unnecessary re-renders
- Look for components that update too frequently

## 🚀 Recommended Solutions

### 1. **Implement Proper Polling**
```javascript
// Use a custom hook for polling
const usePolling = (callback, interval = 30000) => {
  useEffect(() => {
    const intervalId = setInterval(callback, interval);
    return () => clearInterval(intervalId);
  }, [callback, interval]);
};

// Use it in your component
usePolling(() => {
  fetchNotifications();
}, 30000); // 30 seconds
```

### 2. **Add Request Deduplication**
```javascript
// Prevent duplicate requests
const requestCache = new Map();

const fetchWithCache = async (url, key) => {
  if (requestCache.has(key)) {
    return requestCache.get(key);
  }
  
  const promise = fetch(url);
  requestCache.set(key, promise);
  
  // Clear cache after 5 seconds
  setTimeout(() => requestCache.delete(key), 5000);
  
  return promise;
};
```

### 3. **Use React Query or SWR**
Consider using libraries like React Query or SWR for better data fetching:
```javascript
// With React Query
const { data: userDetails } = useQuery('userDetails', fetchUserDetails, {
  staleTime: 60000, // 60 seconds
  cacheTime: 300000, // 5 minutes
});

// With SWR
const { data: notifications } = useSWR('/api/notifications/unread-count/', fetcher, {
  refreshInterval: 30000, // 30 seconds
});
```

## 📊 Monitoring

### 1. **Add Performance Monitoring**
```javascript
// Track API call frequency
const apiCallTracker = {
  calls: new Map(),
  
  track(endpoint) {
    const now = Date.now();
    const key = `${endpoint}_${Math.floor(now / 1000)}`;
    this.calls.set(key, (this.calls.get(key) || 0) + 1);
    
    // Log if too many calls
    if (this.calls.get(key) > 5) {
      console.warn(`Too many calls to ${endpoint}:`, this.calls.get(key));
    }
  }
};
```

### 2. **Set Up Alerts**
- Monitor API call frequency
- Alert when rate limits are hit
- Track response times

## 🎯 Expected Results

After implementing these fixes:
- ✅ API calls reduced from 10+ per second to 1-2 per minute
- ✅ Better user experience with faster loading
- ✅ Reduced server load and costs
- ✅ Proper error handling for rate limits

## 📞 Support

If you need help implementing these fixes, please:
1. Check the browser console for errors
2. Use the Network tab to identify problematic calls
3. Share the component code that's causing issues
4. Test with the rate limiting in place

The backend is now optimized to handle the load, but the frontend needs to be fixed to prevent the excessive calls in the first place.




















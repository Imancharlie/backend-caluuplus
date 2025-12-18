// Frontend Fix Script for Excessive API Calls
// Add this to your frontend code to fix the rapid fetching issue

// 1. Fix Notification Polling
// Replace this:
// setInterval(() => fetchNotifications(), 1000); // ❌ BAD - Every second

// With this:
let notificationInterval;
const startNotificationPolling = () => {
  // Clear existing interval
  if (notificationInterval) {
    clearInterval(notificationInterval);
  }
  
  // Set new interval - every 30 seconds
  notificationInterval = setInterval(() => {
    fetchNotifications();
  }, 30000); // ✅ GOOD - Every 30 seconds
};

// 2. Add Request Deduplication
const requestCache = new Map();

const fetchWithDeduplication = async (url, options = {}) => {
  const cacheKey = `${url}_${JSON.stringify(options)}`;
  
  // Check if request is already in progress
  if (requestCache.has(cacheKey)) {
    console.log('Request already in progress, returning cached promise');
    return requestCache.get(cacheKey);
  }
  
  // Create new request
  const promise = fetch(url, options)
    .then(response => {
      // Remove from cache when completed
      requestCache.delete(cacheKey);
      return response;
    })
    .catch(error => {
      // Remove from cache on error
      requestCache.delete(cacheKey);
      throw error;
    });
  
  // Store in cache
  requestCache.set(cacheKey, promise);
  
  // Auto-remove after 5 seconds to prevent memory leaks
  setTimeout(() => {
    requestCache.delete(cacheKey);
  }, 5000);
  
  return promise;
};

// 3. Fix useEffect Dependencies
// Replace this:
// useEffect(() => {
//   fetchUserDetails();
//   fetchNotifications();
// }, []); // ❌ BAD - Missing dependencies

// With this:
useEffect(() => {
  fetchUserDetails();
  fetchNotifications();
}, [userId]); // ✅ GOOD - Only re-run when userId changes

// 4. Add Error Handling for Rate Limits
const handleApiResponse = (response) => {
  if (response.status === 429) {
    console.warn('Rate limited, using cached data');
    // Don't make another request immediately
    return null;
  }
  return response.json();
};

// 5. Implement Smart Polling
class SmartPoller {
  constructor(fetchFunction, interval = 30000) {
    this.fetchFunction = fetchFunction;
    this.interval = interval;
    this.intervalId = null;
    this.isActive = false;
  }
  
  start() {
    if (this.isActive) return;
    
    this.isActive = true;
    this.intervalId = setInterval(() => {
      this.fetchFunction();
    }, this.interval);
  }
  
  stop() {
    if (this.intervalId) {
      clearInterval(this.intervalId);
      this.intervalId = null;
    }
    this.isActive = false;
  }
  
  // Pause polling when user is not active
  pause() {
    this.stop();
  }
  
  // Resume polling when user becomes active
  resume() {
    this.start();
  }
}

// 6. Usage Example
const notificationPoller = new SmartPoller(fetchNotifications, 30000);

// Start polling when component mounts
useEffect(() => {
  notificationPoller.start();
  
  // Cleanup when component unmounts
  return () => {
    notificationPoller.stop();
  };
}, []);

// Pause when user is not active
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    notificationPoller.pause();
  } else {
    notificationPoller.resume();
  }
});

// 7. Fix Component Re-rendering
// Add this to prevent unnecessary re-renders
const useMemoizedCallback = (callback, deps) => {
  return useMemo(() => callback, deps);
};

// 8. Add Request Logging for Debugging
const logApiCall = (endpoint, method = 'GET') => {
  console.log(`API Call: ${method} ${endpoint} at ${new Date().toISOString()}`);
};

// Wrap your fetch calls
const fetchNotifications = async () => {
  logApiCall('/api/notifications/unread-count/');
  try {
    const response = await fetchWithDeduplication('/api/notifications/unread-count/');
    const data = await handleApiResponse(response);
    if (data) {
      setNotificationCount(data.unread);
    }
  } catch (error) {
    console.error('Failed to fetch notifications:', error);
  }
};

// 9. Add Performance Monitoring
const performanceMonitor = {
  calls: new Map(),
  
  track(endpoint) {
    const now = Date.now();
    const key = `${endpoint}_${Math.floor(now / 1000)}`;
    const count = this.calls.get(key) || 0;
    this.calls.set(key, count + 1);
    
    // Warn if too many calls
    if (count > 5) {
      console.warn(`⚠️ Too many calls to ${endpoint}: ${count + 1} calls in the last second`);
    }
  }
};

// 10. Final Implementation
const fetchNotifications = async () => {
  performanceMonitor.track('/api/notifications/unread-count/');
  
  try {
    const response = await fetchWithDeduplication('/api/notifications/unread-count/');
    const data = await handleApiResponse(response);
    
    if (data) {
      setNotificationCount(data.unread);
      console.log('Notifications updated:', data.unread);
    }
  } catch (error) {
    console.error('Failed to fetch notifications:', error);
  }
};

// Export for use in other components
export { 
  fetchWithDeduplication, 
  handleApiResponse, 
  SmartPoller, 
  performanceMonitor 
};




















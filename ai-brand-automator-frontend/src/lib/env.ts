/**
 * Environment configuration
 * Centralized configuration for environment-specific settings
 */

// Dynamic API URL that works from any hostname (localhost, network IP, etc.)
const getBaseApiUrl = (): string => {
  // In browser: detect production domain and route to api subdomain
  try {
    if (typeof window !== 'undefined' && window.location) {
      const { protocol, hostname } = window.location;
      // Production: zorven.ai → api.zorven.ai
      if (hostname === 'zorven.ai' || hostname === 'www.zorven.ai') {
        return `${protocol}//api.zorven.ai`;
      }
      // Cloud Run direct URL: use the backend Cloud Run URL
      if (hostname.includes('.run.app')) {
        return `${protocol}//zorven-backend-977911773818.us-central1.run.app`;
      }
      // Local dev: same hostname, port 8000
      return `${protocol}//${hostname}:8000`;
    }
  } catch {
    // Silently fall through to default during SSR
  }

  // Check for explicit env var (SSR context)
  if (process.env.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL;
  }

  // Default for SSR/static generation
  return 'http://localhost:8000';
};

export const env = {
  // API Configuration - dynamically determined
  get apiUrl() {
    return getBaseApiUrl();
  },
  apiVersion: 'v1',
  
  // Environment
  isDevelopment: process.env.NODE_ENV === 'development',
  isProduction: process.env.NODE_ENV === 'production',
  isTest: process.env.NODE_ENV === 'test',
  
  // Feature Flags
  enableErrorTracking: process.env.NEXT_PUBLIC_ENABLE_ERROR_TRACKING === 'true',
  enableAnalytics: process.env.NEXT_PUBLIC_ENABLE_ANALYTICS === 'true',
  
  // Validation
  validate() {
    const missing: string[] = [];
    
    if (!this.apiUrl) {
      missing.push('NEXT_PUBLIC_API_URL');
    }
    
    if (missing.length > 0) {
      console.error(
        `Missing required environment variables: ${missing.join(', ')}\n` +
        'Please check your .env.local file.'
      );
    }
    
    return missing.length === 0;
  },
  
  // Get full API URL
  getApiUrl(path: string = '') {
    const base = `${this.apiUrl}/api/${this.apiVersion}`;
    return path ? `${base}${path.startsWith('/') ? path : `/${path}`}` : base;
  },
};

// Validate on load in development
if (env.isDevelopment) {
  env.validate();
}

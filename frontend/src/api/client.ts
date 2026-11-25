/**
 * Same-Origin Fetch Client with CSRF token extraction and session authentication.
 */

export function getCsrfToken(): string {
  // Check meta tag first
  const meta = document.querySelector('meta[name="csrf-token"]') as HTMLMetaElement;
  if (meta && meta.content) {
    return meta.content;
  }

  // Fallback to cookie
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : '';
}

export interface ApiError {
  error: string;
  reason?: string;
  status: number;
}

export async function fetchApi<T = any>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const csrfToken = getCsrfToken();
  const headers = new Headers(options.headers || {});

  if (!headers.has('Accept')) {
    headers.set('Accept', 'application/json');
  }

  const isFormData = options.body instanceof FormData;
  if (!isFormData && !headers.has('Content-Type') && options.method && options.method !== 'GET') {
    headers.set('Content-Type', 'application/json');
  }

  if (csrfToken && !['GET', 'HEAD', 'OPTIONS'].includes(options.method || 'GET')) {
    headers.set('X-CSRFToken', csrfToken);
  }

  headers.set('X-Requested-With', 'XMLHttpRequest');

  const url = endpoint.startsWith('http') ? endpoint : endpoint;

  const response = await fetch(url, {
    ...options,
    headers,
    credentials: 'include', // Same-origin session cookie
  });

  if (response.status === 401) {
    window.location.href = `/login/?next=${encodeURIComponent(window.location.pathname)}`;
    throw new Error('Authentication required');
  }

  let data: any = null;
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    try {
      data = await response.json();
    } catch {
      data = null;
    }
  }

  if (!response.ok) {
    const errorMsg = data?.error || data?.reason || `HTTP Error ${response.status}: ${response.statusText}`;
    const err: ApiError = {
      error: errorMsg,
      reason: data?.reason,
      status: response.status,
    };
    throw err;
  }

  return data as T;
}

export const api = {
  get: <T = any>(endpoint: string, options: RequestInit = {}) =>
    fetchApi<T>(endpoint, { ...options, method: 'GET' }),
  post: <T = any>(endpoint: string, data?: any, options: RequestInit = {}) =>
    fetchApi<T>(endpoint, {
      ...options,
      method: 'POST',
      body: data !== undefined ? (typeof data === 'string' ? data : JSON.stringify(data)) : undefined,
    }),
  patch: <T = any>(endpoint: string, data?: any, options: RequestInit = {}) =>
    fetchApi<T>(endpoint, {
      ...options,
      method: 'PATCH',
      body: data !== undefined ? (typeof data === 'string' ? data : JSON.stringify(data)) : undefined,
    }),
  delete: <T = any>(endpoint: string, options: RequestInit = {}) =>
    fetchApi<T>(endpoint, { ...options, method: 'DELETE' }),
};

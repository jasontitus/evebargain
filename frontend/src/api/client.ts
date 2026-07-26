const API_BASE = '/api';

export interface RequestOptions extends RequestInit {
  /** Treat 401 as a normal outcome instead of bouncing to EVE SSO. */
  allowUnauthenticated?: boolean;
}

async function fetchAPI<T>(path: string, options?: RequestOptions): Promise<T> {
  const { allowUnauthenticated, ...init } = options ?? {};

  const response = await fetch(`${API_BASE}${path}`, {
    credentials: 'include',
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...init.headers,
    },
  });

  if (response.status === 401) {
    // A 401 on the startup session probe just means "not logged in yet" --
    // the caller renders the login screen. Anywhere else it means the session
    // expired mid-use, so hand off to SSO.
    if (!allowUnauthenticated) {
      window.location.href = `${API_BASE}/auth/login`;
    }
    throw new Error('Not authenticated');
  }

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  return response.json();
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) => fetchAPI<T>(path, options),
  post: <T>(path: string, body?: unknown) =>
    fetchAPI<T>(path, {
      method: 'POST',
      body: body ? JSON.stringify(body) : undefined,
    }),
  put: <T>(path: string, body: unknown) =>
    fetchAPI<T>(path, {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
  delete: <T>(path: string) =>
    fetchAPI<T>(path, { method: 'DELETE' }),
};

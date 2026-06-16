const API_BASE = import.meta.env.VITE_API_BASE || "";
let refreshRequest = null;

/**
 * Build headers for authenticated API requests.
 *
 * Returns:
 *   Request headers containing JSON content type and bearer token when present.
 */
function buildHeaders() {
  const token = window.localStorage.getItem("access_token");
  const bootstrapToken = window.localStorage.getItem("bootstrap_access_token");
  const headers = {
    "Content-Type": "application/json"
  };
  if (token || bootstrapToken) {
    headers.Authorization = `Bearer ${token || bootstrapToken}`;
  }
  return headers;
}

/**
 * Clear all locally persisted authentication state and return to the login page.
 *
 * Returns:
 *   None. Browser storage is cleared and the page is redirected when needed.
 */
function clearSessionAndRedirect() {
  window.localStorage.removeItem("access_token");
  window.localStorage.removeItem("refresh_token");
  window.localStorage.removeItem("bootstrap_access_token");
  if (window.location.pathname !== "/login") {
    window.location.assign("/login");
  }
}

/**
 * Refresh the access session when the backend reports that the access token expired.
 *
 * Returns:
 *   Promise that resolves to the new access token string.
 *
 * Throws:
 *   Error: Raised when no refresh token exists or the refresh request fails.
 */
async function refreshAccessToken() {
  const refreshToken = window.localStorage.getItem("refresh_token");
  if (!refreshToken) {
    throw new Error("Refresh token missing");
  }

  const response = await fetch(`${API_BASE}/api/auth/refresh`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      refresh_token: refreshToken
    })
  });
  if (!response.ok) {
    let detail = "Session refresh failed";
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch (_) {
      detail = response.statusText || detail;
    }
    throw new Error(detail);
  }

  const tokenPair = await response.json();
  window.localStorage.setItem("access_token", tokenPair.access_token);
  window.localStorage.setItem("refresh_token", tokenPair.refresh_token);
  return tokenPair.access_token;
}

/**
 * Retry an authenticated request after refreshing an expired access token.
 *
 * Args:
 *   path: API path starting with /api.
 *   options: Original fetch options.
 *
 * Returns:
 *   Fetch response after retrying with a refreshed access token.
 */
async function retryWithRefreshedToken(path, options) {
  if (!refreshRequest) {
    refreshRequest = refreshAccessToken().finally(() => {
      refreshRequest = null;
    });
  }
  await refreshRequest;
  return fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      ...buildHeaders(),
      ...(options.headers || {})
    }
  });
}

/**
 * Execute a JSON API request against the backend.
 *
 * Args:
 *   path: API path starting with /api.
 *   options: Fetch options such as method and body.
 *
 * Returns:
 *   Parsed JSON response body.
 *
 * Throws:
 *   Error: Raised when the backend responds with a non-success status.
 */
export async function request(path, options = {}) {
  let response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      ...buildHeaders(),
      ...(options.headers || {})
    }
  });
  if (
    response.status === 401 &&
    window.localStorage.getItem("access_token") &&
    window.localStorage.getItem("refresh_token") &&
    !path.startsWith("/api/auth/")
  ) {
    try {
      response = await retryWithRefreshedToken(path, options);
    } catch (_) {
      clearSessionAndRedirect();
      throw new Error("登录已过期，请重新登录");
    }
  }
  if (!response.ok) {
    let detail = "Request failed";
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch (_) {
      detail = response.statusText || detail;
    }
    if (response.status === 401) {
      clearSessionAndRedirect();
    }
    throw new Error(detail);
  }
  if (response.status === 204) {
    return null;
  }
  return await response.json();
}

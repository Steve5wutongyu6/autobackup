const API_BASE = import.meta.env.VITE_API_BASE || "";

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
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      ...buildHeaders(),
      ...(options.headers || {})
    }
  });
  if (!response.ok) {
    let detail = "Request failed";
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch (_) {
      detail = response.statusText || detail;
    }
    throw new Error(detail);
  }
  if (response.status === 204) {
    return null;
  }
  return await response.json();
}

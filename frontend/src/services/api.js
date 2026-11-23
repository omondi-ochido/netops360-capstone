const VITE_ENV = import.meta.env || {};
const API_BASE_URL = (VITE_ENV.VITE_API_BASE_URL || "http://127.0.0.1:5050").replace(/\/+$/, "");
const API_KEY = VITE_ENV.VITE_API_KEY || "";

export async function apiRequest(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (options.body !== undefined) headers.set("Content-Type", "application/json");
  if (API_KEY) headers.set("X-API-Key", API_KEY);
  const response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = payload.error?.message || payload.error || `Request failed (${response.status})`;
    const error = new Error(message);
    error.status = response.status;
    error.code = payload.error?.code;
    throw error;
  }
  return payload;
}

export function listData(payload) {
  if (Array.isArray(payload.data)) return payload.data;
  if (Array.isArray(payload.devices)) return payload.devices;
  throw new Error("The API response did not contain a list.");
}

export function resourceData(payload) {
  return payload.data;
}

export function queryString(values = {}) {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") params.set(key, value);
  });
  const query = params.toString();
  return query ? `?${query}` : "";
}

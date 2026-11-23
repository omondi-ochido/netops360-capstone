import { getSupabaseClient } from "./supabaseClient.js";

const VITE_ENV = import.meta.env || {};
const API_BASE_URL = (VITE_ENV.VITE_API_BASE_URL || "http://127.0.0.1:5050").replace(/\/+$/, "");

function apiError(payload, status) {
  const error = new Error(payload.error?.message || payload.error || `Request failed (${status})`);
  error.status = status;
  error.code = payload.error?.code;
  return error;
}

async function send(path, options, accessToken) {
  const headers = new Headers(options.headers || {});
  if (options.body !== undefined) headers.set("Content-Type", "application/json");
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  if (!headers.has("X-Request-ID") && globalThis.crypto?.randomUUID) {
    headers.set("X-Request-ID", globalThis.crypto.randomUUID());
  }
  return fetch(`${API_BASE_URL}${path}`, { ...options, headers });
}

export async function apiRequest(path, options = {}) {
  const client = getSupabaseClient();
  const { data: { session }, error: sessionError } = await client.auth.getSession();
  if (sessionError) throw new Error(sessionError.message || "Could not restore the Supabase session.");
  if (!session?.access_token) {
    const error = new Error("Sign in to continue.");
    error.status = 401; error.code = "missing_session";
    throw error;
  }

  let response = await send(path, options, session.access_token);
  if (response.status === 401) {
    const refreshed = await client.auth.refreshSession();
    if (refreshed.error || !refreshed.data.session?.access_token) {
      void client.auth.signOut({ scope: "local" });
      throw apiError({ error: { code: "session_expired", message: "Your session expired. Sign in again." } }, 401);
    }
    response = await send(path, options, refreshed.data.session.access_token);
    if (response.status === 401) void client.auth.signOut({ scope: "local" });
  }

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw apiError(payload, response.status);
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

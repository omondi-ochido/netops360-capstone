import { createClient } from "@supabase/supabase-js";

const env = import.meta.env || {};
let client;

export function getSupabaseClient() {
  if (client) return client;
  const url = env.VITE_SUPABASE_URL;
  const publishableKey = env.VITE_SUPABASE_PUBLISHABLE_KEY;
  if (!url || !publishableKey) {
    throw new Error("Supabase Auth is not configured. Set VITE_SUPABASE_URL and VITE_SUPABASE_PUBLISHABLE_KEY.");
  }
  client = createClient(url, publishableKey, {
    auth: {
      persistSession: true,
      autoRefreshToken: true,
      detectSessionInUrl: true,
      storage: typeof window === "undefined" ? undefined : window.sessionStorage,
    },
  });
  return client;
}

export function supabaseConfigured() {
  return Boolean(env.VITE_SUPABASE_URL && env.VITE_SUPABASE_PUBLISHABLE_KEY);
}

export function oauthProviderEnabled(provider) {
  if (provider === "azure") return env.VITE_SUPABASE_MICROSOFT_ENABLED === "true";
  return ["google", "github"].includes(provider);
}

// Allows isolated fetch-contract tests to provide a Supabase Auth stub.
export function setSupabaseClientForTests(value) {
  client = value;
}

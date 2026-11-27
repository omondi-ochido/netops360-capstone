import { apiRequest, resourceData } from "./api.js";
import { getSupabaseClient } from "./supabaseClient.js";

const PENDING_REGISTRATION_KEY = "netops360.pendingCompanyRegistration";

function callbackUrl(registration = false) {
  const url = new URL("/auth/callback", window.location.origin);
  if (registration) url.searchParams.set("flow", "company-registration");
  return url.toString();
}

function savePendingRegistration(details) {
  try {
    window.sessionStorage?.setItem(PENDING_REGISTRATION_KEY, JSON.stringify({
      full_name: details.full_name || "", company_name: details.company_name || "",
    }));
  } catch { /* onboarding can ask again if browser storage is unavailable */ }
}

export function getPendingCompanyRegistration() {
  try {
    const raw = window.sessionStorage?.getItem(PENDING_REGISTRATION_KEY);
    const value = raw ? JSON.parse(raw) : {};
    return {
      full_name: typeof value.full_name === "string" ? value.full_name : "",
      company_name: typeof value.company_name === "string" ? value.company_name : "",
    };
  } catch { return { full_name: "", company_name: "" }; }
}

export function clearPendingCompanyRegistration() {
  try { window.sessionStorage?.removeItem(PENDING_REGISTRATION_KEY); } catch { /* no-op */ }
}

export async function signIn(email, password) {
  const { data, error } = await getSupabaseClient().auth.signInWithPassword({ email: email.trim(), password });
  if (error) throw error;
  return data.session;
}

export async function signUpCompany({ email, full_name, password, company_name }) {
  const details = {
    full_name: full_name.trim().replace(/\s+/g, " "),
    company_name: company_name.trim().replace(/\s+/g, " "),
  };
  savePendingRegistration(details);
  const { data, error } = await getSupabaseClient().auth.signUp({
    email: email.trim(),
    password,
    options: {
      // Company identity and authority are submitted to Flask after the user
      // authenticates; user_metadata is editable and never trusted for either.
      data: { full_name: full_name.trim() },
      emailRedirectTo: callbackUrl(true),
    },
  });
  if (error) throw error;
  if (data.session) {
    await registerCompany(details);
    clearPendingCompanyRegistration();
  }
  return { hasSession: Boolean(data.session) };
}

export async function signInWithProvider(provider, registrationDetails = null) {
  const scopes = provider === "azure" ? "email" : undefined;
  if (registrationDetails) savePendingRegistration(registrationDetails);
  const { error } = await getSupabaseClient().auth.signInWithOAuth({
    provider,
    options: { redirectTo: callbackUrl(Boolean(registrationDetails)), ...(scopes ? { scopes } : {}) },
  });
  if (error) throw error;
}

export async function registerCompany({ full_name, company_name }) {
  return resourceData(await apiRequest("/api/auth/register-company", {
    method: "POST",
    body: JSON.stringify({ full_name, company_name }),
  }));
}

export async function sendRecoveryCode(email) {
  const redirectTo = `${window.location.origin}/reset-password`;
  const { error } = await getSupabaseClient().auth.resetPasswordForEmail(email.trim(), { redirectTo });
  if (error) throw error;
}

export async function verifyRecoveryCode(email, code) {
  const { data, error } = await getSupabaseClient().auth.verifyOtp({
    email: email.trim(), token: code.trim(), type: "recovery",
  });
  if (error) throw error;
  return data.session;
}

export async function updatePassword(password) {
  const { error } = await getSupabaseClient().auth.updateUser({ password });
  if (error) throw error;
  void apiRequest("/api/auth/security-events", { method: "POST", body: JSON.stringify({ event: "password_changed" }) }).catch(() => {});
}

export async function getCurrentSession() {
  const { data, error } = await getSupabaseClient().auth.getSession();
  if (error) throw error;
  return data.session;
}

export async function getCurrentIdentity() {
  return resourceData(await apiRequest("/api/auth/me"));
}

export async function revokeCurrentSession() {
  let revokeError;
  try {
    await apiRequest("/api/auth/logout", { method: "POST" });
  } catch (error) {
    revokeError = error;
  }
  const { error: signOutError } = await getSupabaseClient().auth.signOut({ scope: "local" });
  if (signOutError) {
    throw new Error("The current Supabase session could not be cleared.");
  }
  if (revokeError) {
    throw new Error("Signed out of Supabase, but immediate API session revocation could not be recorded.");
  }
}

export async function setInvitePassword(password) {
  const session = await getCurrentSession();
  if (!session?.user) throw new Error("The invitation link is invalid or expired. Ask an administrator to send another invitation.");
  await updatePassword(password);
}

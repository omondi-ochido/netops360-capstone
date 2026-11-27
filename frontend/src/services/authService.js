import { apiRequest, resourceData } from "./api.js";
import { getSupabaseClient } from "./supabaseClient.js";

export async function signIn(email, password) {
  const { data, error } = await getSupabaseClient().auth.signInWithPassword({ email: email.trim(), password });
  if (error) throw error;
  return data.session;
}

export async function signUpCompany({ email, full_name, password, company_name }) {
  const { data, error } = await getSupabaseClient().auth.signUp({
    email: email.trim(),
    password,
    options: {
      data: { full_name: full_name.trim(), company_name: company_name.trim() },
      emailRedirectTo: `${window.location.origin}/auth/callback`,
    },
  });
  if (error) throw error;
  if (data.session) {
    await apiRequest("/api/auth/onboard-company", {
      method: "POST",
      body: JSON.stringify({ full_name: full_name.trim(), company_name: company_name.trim() }),
    });
  }
  return { hasSession: Boolean(data.session) };
}

export async function signInWithProvider(provider) {
  const scopes = provider === "azure" ? "email" : undefined;
  const { error } = await getSupabaseClient().auth.signInWithOAuth({
    provider,
    options: { redirectTo: `${window.location.origin}/auth/callback`, ...(scopes ? { scopes } : {}) },
  });
  if (error) throw error;
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
  const { error: signOutError } = await getSupabaseClient().auth.signOut({ scope: "global" });
  if (signOutError) {
    void getSupabaseClient().auth.signOut({ scope: "local" });
    throw new Error("Signed out of this browser, but Supabase could not revoke other sessions.");
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

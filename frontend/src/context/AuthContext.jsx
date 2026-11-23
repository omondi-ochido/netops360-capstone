import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { getCurrentIdentity, revokeCurrentSession, signIn } from "../services/authService.js";
import { getSupabaseClient, supabaseConfigured } from "../services/supabaseClient.js";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [identity, setIdentity] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const generation = useRef(0);

  const clearIdentity = useCallback((message = "") => {
    generation.current += 1;
    setIdentity(null); setError(message); setLoading(false);
  }, []);

  const loadIdentity = useCallback(async () => {
    const current = ++generation.current;
    try {
      const result = await getCurrentIdentity();
      if (generation.current === current) { setIdentity(result); setError(""); setLoading(false); }
      return result;
    } catch (requestError) {
      if (generation.current === current) {
        setIdentity(null); setError(requestError.message); setLoading(false);
        try { await getSupabaseClient().auth.signOut({ scope: "local" }); } catch { /* local state is already cleared */ }
      }
      return null;
    }
  }, []);

  useEffect(() => {
    if (!supabaseConfigured()) {
      clearIdentity("Authentication is not configured. Add the Supabase URL and publishable key.");
      return undefined;
    }
    const client = getSupabaseClient();
    const { data: { subscription } } = client.auth.onAuthStateChange((event, session) => {
      if (event === "SIGNED_OUT" || !session) {
        clearIdentity("");
      } else if (["INITIAL_SESSION", "SIGNED_IN", "TOKEN_REFRESHED", "USER_UPDATED"].includes(event)) {
        setLoading(true);
        window.setTimeout(() => { void loadIdentity(); }, 0);
      }
    });
    void client.auth.getSession().then(({ data, error: sessionError }) => {
      if (sessionError || !data.session) clearIdentity(sessionError?.message || "");
      else void loadIdentity();
    }).catch((sessionError) => clearIdentity(sessionError.message));
    return () => { generation.current += 1; subscription.unsubscribe(); };
  }, [clearIdentity, loadIdentity]);

  const login = useCallback(async (email, password) => {
    setError(""); setLoading(true);
    try {
      await signIn(email, password);
      const current = await loadIdentity();
      if (!current) throw new Error("This account is not enabled for NetOps360. Contact an administrator.");
      return current;
    } catch (loginError) {
      setError(loginError.message || "Sign-in failed."); setLoading(false);
      throw loginError;
    }
  }, [loadIdentity]);

  const logout = useCallback(async () => {
    setError("");
    try { await revokeCurrentSession(); clearIdentity(""); }
    catch (logoutError) { clearIdentity(logoutError.message); throw logoutError; }
  }, [clearIdentity]);

  const permissions = identity?.permissions || [];
  const value = useMemo(() => ({
    user: identity?.user || null,
    roles: identity?.roles || [],
    permissions,
    loading,
    error,
    login,
    logout,
    hasPermission: (permission) => permissions.includes("*") || permissions.includes(permission),
  }), [identity, permissions, loading, error, login, logout]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider.");
  return value;
}

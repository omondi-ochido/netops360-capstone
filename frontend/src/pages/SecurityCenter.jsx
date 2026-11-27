import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { apiRequest, resourceData } from "../services/api.js";
import { getSupabaseClient } from "../services/supabaseClient.js";
import { useAuth } from "../context/AuthContext.jsx";

export default function SecurityCenter({ embedded = false }) {
  const { roles, mfaRequired, refreshIdentity, logout } = useAuth();
  const navigate = useNavigate();
  const [factors, setFactors] = useState([]); const [session, setSession] = useState(null);
  const [pending, setPending] = useState(null); const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false); const [error, setError] = useState(""); const [notice, setNotice] = useState("");
  const admin = roles.some((role) => ["super_admin", "company_admin", "admin"].includes(role));
  const reload = useCallback(async () => {
    const client = getSupabaseClient();
    const [factorResult, sessionResult] = await Promise.all([
      client.auth.mfa.listFactors(), resourceData(await apiRequest("/api/auth/session")),
    ]);
    if (factorResult.error) throw factorResult.error;
    const data = factorResult.data || {};
    setFactors([...(data.totp || []), ...(data.phone || [])]); setSession(sessionResult);
  }, []);
  useEffect(() => { void reload().catch((e) => setError(e.message || "Could not load security settings.")); }, [reload]);

  async function startEnrollment() {
    setBusy(true); setError(""); setNotice("");
    try {
      const { data, error: enrollError } = await getSupabaseClient().auth.mfa.enroll({ factorType: "totp", friendlyName: "NetOps360 authenticator" });
      if (enrollError) throw enrollError;
      setPending(data); setCode(""); setNotice("Scan this QR code in an authenticator app, then enter its six-digit code to confirm enrollment.");
    } catch (e) { setError(e.message || "Could not start authenticator enrollment."); }
    finally { setBusy(false); }
  }
  async function verifyCode(event) {
    event.preventDefault(); if (!/^\d{6}$/.test(code)) return setError("Enter the current six-digit authenticator code.");
    setBusy(true); setError(""); setNotice("");
    try {
      const client = getSupabaseClient();
      if (pending) {
        const { data: challenge, error: challengeError } = await client.auth.mfa.challenge({ factorId: pending.id });
        if (challengeError) throw challengeError;
        const { error: verifyError } = await client.auth.mfa.verify({ factorId: pending.id, challengeId: challenge.id, code });
        if (verifyError) throw verifyError;
        await apiRequest("/api/auth/security-events", { method: "POST", body: JSON.stringify({ event: "mfa_enrolled" }) }).catch(() => {});
        setPending(null); setCode(""); await reload(); await refreshIdentity(); setNotice("Authenticator verification succeeded. Save your recovery codes in a secure place if Supabase provides them.");
      } else {
        const factor = factors.find((item) => item.status === "verified" && item.factor_type === "totp");
        if (!factor) throw new Error("No verified authenticator is available. Enroll one first.");
        const { error: verifyError } = await client.auth.mfa.challengeAndVerify({ factorId: factor.id, code });
        if (verifyError) throw verifyError;
        setCode(""); await refreshIdentity(); setNotice("Authenticator verified. You can now continue to the application.");
      }
    } catch (e) { setError(e.message || "The authenticator code could not be verified."); }
    finally { setBusy(false); }
  }
  async function removeFactor(factor) {
    if (admin && factors.filter((item) => item.status === "verified" && item.factor_type === "totp").length <= 1) {
      setError("Company and Super Admin accounts must keep at least one verified authenticator enrolled."); return;
    }
    setBusy(true); setError(""); setNotice("");
    try {
      const { error: unenrollError } = await getSupabaseClient().auth.mfa.unenroll({ factorId: factor.id });
      if (unenrollError) throw unenrollError;
      await apiRequest("/api/auth/security-events", { method: "POST", body: JSON.stringify({ event: "mfa_removed" }) }).catch(() => {});
      await reload(); await refreshIdentity(); setNotice("Authenticator removed.");
    } catch (e) { setError(e.message || "Could not remove authenticator."); }
    finally { setBusy(false); }
  }
  async function revokeAll() {
    setBusy(true); setError(""); setNotice("");
    try {
      await apiRequest("/api/auth/sessions/revoke-all", { method: "POST" });
      await getSupabaseClient().auth.signOut({ scope: "local" });
      navigate("/login", { replace: true, state: { passwordChanged: false } });
    } catch (e) { setError(e.message || "Could not revoke sessions. Verify MFA again and retry."); }
    finally { setBusy(false); }
  }
  const verifiedTotp = factors.some((factor) => factor.status === "verified" && factor.factor_type === "totp");
  return <div className={embedded ? "page-stack" : "login-page"}><section className={embedded ? "panel-card" : "login-card"}>
    <h1>Account security</h1>
    <p>{admin ? "A verified authenticator is required for administrator access. Sensitive actions require a recent authenticator check." : "Manage your authenticator and current session."}</p>
    {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    {mfaRequired && <p role="status">Complete authenticator enrollment or verification to unlock administrative features.</p>}
    <section aria-labelledby="mfa-heading"><h2 id="mfa-heading">Authenticator app</h2>
      {pending?.totp?.qr_code && <div><img alt="QR code for authenticator enrollment" width="220" height="220" src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(pending.totp.qr_code)}`} /><p>Manual setup key: <code>{pending.totp.secret}</code></p></div>}
      {!pending && !verifiedTotp && <button type="button" className="primary-button" disabled={busy} onClick={() => void startEnrollment()}>Enroll authenticator</button>}
      {verifiedTotp && !pending && <p>Authenticator enrolled and verified.</p>}
      {(pending || verifiedTotp) && <form className="login-form" onSubmit={verifyCode}><label><span>{pending ? "Confirm enrollment code" : "Verify authenticator for this session"}</span><input aria-label="Six-digit authenticator code" autoComplete="one-time-code" inputMode="numeric" pattern="[0-9]{6}" maxLength={6} value={code} onChange={(e) => setCode(e.target.value)} required /></label><button className="primary-button" disabled={busy}>Verify code</button></form>}
      {factors.filter((factor) => factor.status === "verified").map((factor) => <p key={factor.id}>{factor.friendly_name || "Authenticator"} <button type="button" className="secondary-button" disabled={busy} onClick={() => void removeFactor(factor)}>Remove</button></p>)}
      <p>Keep recovery codes in a password manager or another secure offline location. Recovery codes and authenticator secrets are never sent to NetOps360.</p>
    </section>
    <section aria-labelledby="session-heading"><h2 id="session-heading">Current session</h2>{session ? <dl><dt>Assurance</dt><dd>{session.assurance_level}</dd><dt>Issued</dt><dd>{session.issued_at ? new Date(session.issued_at).toLocaleString() : "Unavailable"}</dd><dt>Expires</dt><dd>{new Date(session.expires_at).toLocaleString()}</dd></dl> : <p>Loading session…</p>}
      <p>The app can display this session. Supabase does not expose an active-device list through the current client path.</p>
      <button type="button" className="secondary-button" disabled={busy} onClick={revokeAll}>Revoke all sessions</button> <button type="button" className="secondary-button" disabled={busy} onClick={() => void logout().then(() => navigate("/login", { replace: true })).catch((e) => setError(e.message))}>Log out this session</button>
    </section>
    {mfaRequired && verifiedTotp && <button className="primary-button" type="button" onClick={() => navigate("/")}>Continue to NetOps360</button>}
    {!embedded && <p><Link to="/login">Sign in</Link></p>}
  </section></div>;
}

import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { updatePassword, verifyRecoveryCode } from "../services/authService.js";
import { getSupabaseClient } from "../services/supabaseClient.js";

export default function ResetPassword() {
  const [params] = useSearchParams(); const navigate = useNavigate();
  const [email, setEmail] = useState(params.get("email") || ""); const [code, setCode] = useState("");
  const [verified, setVerified] = useState(false); const [password, setPassword] = useState(""); const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  async function verify(event) { event.preventDefault(); setBusy(true); setError(""); try { await verifyRecoveryCode(email, code); setVerified(true); } catch (err) { setError(err.message || "That recovery code is invalid or expired."); } finally { setBusy(false); } }
  async function save(event) { event.preventDefault(); setError(""); if (password.length < 12) return setError("Use at least 12 characters for your new password."); if (password !== confirm) return setError("The passwords do not match."); setBusy(true); try { await updatePassword(password); await getSupabaseClient().auth.signOut({ scope: "global" }); navigate("/login", { replace: true, state: { passwordChanged: true } }); } catch (err) { setError(err.message || "Could not update your password."); } finally { setBusy(false); } }
  return <section className="login-page"><div className="login-card"><h1>Reset your password</h1>
    {!verified ? <form className="login-form" onSubmit={verify}><p>Enter the email address and code from your recovery email.</p><label><span>Email</span><input type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} /></label><label><span>Email recovery code</span><input inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} required value={code} onChange={(e) => setCode(e.target.value)} /></label><button className="primary-button full-width" disabled={busy}>Verify code</button></form> : <form className="login-form" onSubmit={save}><p>Choose a new password to continue.</p><label><span>New password</span><input type="password" autoComplete="new-password" minLength={12} required value={password} onChange={(e) => setPassword(e.target.value)} /></label><label><span>Confirm new password</span><input type="password" autoComplete="new-password" minLength={12} required value={confirm} onChange={(e) => setConfirm(e.target.value)} /></label><button className="primary-button full-width" disabled={busy}>Save new password</button></form>}
    {error && <p role="alert">{error}</p>}<Link to="/forgot-password">Request another code</Link>
  </div></section>;
}

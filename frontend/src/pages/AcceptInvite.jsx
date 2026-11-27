import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getCurrentSession, setInvitePassword } from "../services/authService.js";
import { acceptInvitation } from "../services/operationsService.js";
import { getSupabaseClient } from "../services/supabaseClient.js";

export default function AcceptInvite() {
  const navigate = useNavigate(); const [password, setPassword] = useState(""); const [confirm, setConfirm] = useState(""); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  async function submit(e) { e.preventDefault(); setError(""); if (password.length < 12) return setError("Use at least 12 characters."); if (password !== confirm) return setError("The passwords do not match."); setBusy(true); try { if (!(await getCurrentSession())?.user) throw new Error("The invitation link is invalid or expired."); await setInvitePassword(password); await acceptInvitation(); await getSupabaseClient().auth.signOut({ scope: "global" }); navigate("/login", { replace: true }); } catch (err) { setError(err.message); } finally { setBusy(false); } }
  return <section className="login-page"><div className="login-card"><h1>Set your password</h1><p>Choose a password to activate your invited account.</p><form className="login-form" onSubmit={submit}><label><span>New password</span><input type="password" autoComplete="new-password" minLength={12} required value={password} onChange={(e) => setPassword(e.target.value)} /></label><label><span>Confirm password</span><input type="password" autoComplete="new-password" minLength={12} required value={confirm} onChange={(e) => setConfirm(e.target.value)} /></label>{error && <p role="alert">{error}</p>}<button className="primary-button full-width" disabled={busy}>Set password</button></form><Link to="/login">Back to sign in</Link></div></section>;
}

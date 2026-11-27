import { useState } from "react";
import { Link } from "react-router-dom";
import { sendRecoveryCode } from "../services/authService.js";

export default function ForgotPassword() {
  const [email, setEmail] = useState(""); const [sent, setSent] = useState(false); const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  async function submit(event) { event.preventDefault(); setBusy(true); setError(""); try { await sendRecoveryCode(email); } catch { /* Keep provider errors from disclosing whether an account exists. */ } finally { setSent(true); setBusy(false); } }
  return <section className="login-page"><div className="login-card"><h1>Recover your password</h1>
    {sent ? <><p>If an account exists for that email, a recovery code has been sent. Enter the code on the next screen.</p><Link to={`/reset-password?email=${encodeURIComponent(email)}`}>Enter recovery code</Link></> : <form className="login-form" onSubmit={submit}><p>We’ll email you a one-time recovery code.</p><label><span>Email</span><input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></label>{error && <p role="alert">{error}</p>}<button className="primary-button full-width" disabled={busy}>Send recovery code</button></form>}
    <Link to="/login">Back to sign in</Link>
  </div></section>;
}

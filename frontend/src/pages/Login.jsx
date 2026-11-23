import { useState } from "react";
import { Link } from "react-router-dom";
import NetOps360Logo from "../components/common/NetOps360Logo";
import { useAuth } from "../context/AuthContext";
import { signInWithProvider } from "../services/authService.js";

export default function Login() {
  const { login, error, loading } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [formError, setFormError] = useState("");
  const [providerLoading, setProviderLoading] = useState("");
  async function submit(event) {
    event.preventDefault(); setFormError("");
    try { await login(email, password); } catch (err) { setFormError(err.message || "Unable to sign in."); }
  }
  async function socialSignIn(provider, label) {
    setFormError(""); setProviderLoading(provider);
    try { await signInWithProvider(provider); }
    catch (err) { setFormError(err.message || `${label} sign-in is unavailable.`); setProviderLoading(""); }
  }
  return <div className="login-page"><div className="login-card">
    <div className="login-logo-banner"><NetOps360Logo size={88} variant="banner" /></div>
    <form className="login-form" onSubmit={submit}>
      <p>Sign in with the account invited by your NetOps360 administrator.</p>
      <label><span>Email</span><input type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} /></label>
      <label><span>Password</span><input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} /></label>
      {(formError || error) && <p role="alert">{formError || error}</p>}
      <button type="submit" className="primary-button full-width" disabled={loading || Boolean(providerLoading)}>Sign in</button>
      <Link to="/forgot-password">Forgot password?</Link>
    </form>
    <div className="oauth-divider" aria-label="Or sign in with a connected provider"><span /><span className="oauth-divider-label">OR CONTINUE WITH</span><span /></div>
    <div className="oauth-buttons">
      <button type="button" className="oauth-button" disabled={loading || Boolean(providerLoading)} onClick={() => void socialSignIn("google", "Google")}>
        <svg viewBox="0 0 48 48" aria-hidden="true"><path fill="#4285F4" d="M43.6 24.5c0-1.6-.1-3.1-.4-4.5H24v8.5h11c-.5 2.7-2 5-4.3 6.5v5.3h7c4.1-3.8 6.5-9.4 6.5-15.8Z"/><path fill="#34A853" d="M24 44c5.9 0 10.8-2 14.4-5.3l-7-5.3c-2 1.3-4.4 2.1-7.4 2.1-5.7 0-10.5-3.8-12.2-9H4.6v5.5C8.2 39.2 15.5 44 24 44Z"/><path fill="#FBBC05" d="M11.8 26.5a12 12 0 0 1 0-7V14H4.6a21 21 0 0 0 0 18l7.2-5.5Z"/><path fill="#EA4335" d="M24 10.5c3.2 0 6.1 1.1 8.4 3.3l6.3-6.3C34.9 4.1 29.9 2 24 2 15.5 2 8.2 6.8 4.6 14l7.2 5.5c1.7-5.2 6.5-9 12.2-9Z"/></svg>
        {providerLoading === "google" ? "Connecting to Google…" : "Continue with Google"}
      </button>
      <button type="button" className="oauth-button" disabled={loading || Boolean(providerLoading)} onClick={() => void socialSignIn("github", "GitHub")}>
        <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 .9a11.1 11.1 0 0 0-3.51 21.63c.56.1.76-.24.76-.54v-2.08c-3.1.68-3.76-1.32-3.76-1.32-.5-1.3-1.24-1.65-1.24-1.65-1.01-.7.08-.69.08-.69 1.12.08 1.72 1.15 1.72 1.15 1 .1.56 2.18 3.7 1.55.1-.73.39-1.23.7-1.51-2.48-.28-5.09-1.24-5.09-5.52 0-1.22.44-2.22 1.15-3-.12-.28-.5-1.42.11-2.96 0 0 .94-.3 3.05 1.14a10.6 10.6 0 0 1 5.56 0c2.11-1.43 3.04-1.14 3.04-1.14.61 1.54.23 2.68.12 2.96.72.78 1.14 1.78 1.14 3.01 0 4.29-2.61 5.23-5.1 5.5.4.35.75 1.03.75 2.08v3.08c0 .3.2.65.77.54A11.1 11.1 0 0 0 12 .9Z"/></svg>
        {providerLoading === "github" ? "Connecting to GitHub…" : "Continue with GitHub"}
      </button>
      <button type="button" className="oauth-button" disabled={loading || Boolean(providerLoading)} onClick={() => void socialSignIn("azure", "Microsoft")}>
        <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="#F25022" d="M1 1h10v10H1z"/><path fill="#7FBA00" d="M13 1h10v10H13z"/><path fill="#00A4EF" d="M1 13h10v10H1z"/><path fill="#FFB900" d="M13 13h10v10H13z"/></svg>
        {providerLoading === "azure" ? "Connecting to Microsoft…" : "Continue with Microsoft"}
      </button>
    </div>
    {providerLoading && <p role="status">Redirecting to your identity provider…</p>}
  </div></div>;
}

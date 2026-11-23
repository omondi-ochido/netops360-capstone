import { useState } from "react";
import { Link } from "react-router-dom";
import NetOps360Logo from "../components/common/NetOps360Logo";
import { useAuth } from "../context/AuthContext";

export default function Login() {
  const { login, error, loading } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [formError, setFormError] = useState("");
  async function submit(event) {
    event.preventDefault(); setFormError("");
    try { await login(email, password); } catch (err) { setFormError(err.message || "Unable to sign in."); }
  }
  return <div className="login-page"><div className="login-card">
    <div className="login-logo-banner"><NetOps360Logo size={88} variant="banner" /></div>
    <form className="login-form" onSubmit={submit}>
      <p>Sign in with the account invited by your NetOps360 administrator.</p>
      <label><span>Email</span><input type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} /></label>
      <label><span>Password</span><input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} /></label>
      {(formError || error) && <p role="alert">{formError || error}</p>}
      <button type="submit" className="primary-button full-width" disabled={loading}>Sign in</button>
      <Link to="/forgot-password">Forgot password?</Link>
    </form>
  </div></div>;
}

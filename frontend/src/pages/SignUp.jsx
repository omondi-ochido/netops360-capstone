import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import NetOps360Logo from "../components/common/NetOps360Logo";
import { signInWithProvider, signUpCompany } from "../services/authService.js";
import { oauthProviderEnabled } from "../services/supabaseClient.js";
import { registrationFeedback, validateCompanyRegistration } from "../services/registrationFeedback.js";

export default function SignUp() {
  const navigate = useNavigate();
  const [form, setForm] = useState({ full_name: "", email: "", password: "", confirm_password: "", company_name: "" });
  const [feedback, setFeedback] = useState(null);
  const [busy, setBusy] = useState(false);
  const [confirmationSent, setConfirmationSent] = useState(false);
  const [providerLoading, setProviderLoading] = useState("");

  function update(event) {
    setForm((current) => ({ ...current, [event.target.name]: event.target.value }));
  }

  async function submit(event) {
    event.preventDefault();
    const validation = validateCompanyRegistration(form, { includeCredentials: true });
    if (validation) { setFeedback({ kind: "invalid-input", title: "Check your details", message: validation }); return; }
    setFeedback(null);
    setBusy(true);
    try {
      const result = await signUpCompany(form);
      if (result.hasSession) navigate("/", { replace: true });
      else setConfirmationSent(true);
    } catch (signupError) {
      setFeedback(registrationFeedback(signupError));
    } finally {
      setBusy(false);
    }
  }

  async function registerWithProvider(provider) {
    const validation = validateCompanyRegistration(form);
    if (validation) { setFeedback({ kind: "invalid-input", title: "Company details required", message: validation }); return; }
    setFeedback(null);
    setProviderLoading(provider);
    try {
      await signInWithProvider(provider, { full_name: form.full_name.trim(), company_name: form.company_name.trim() });
    } catch (oauthError) {
      setFeedback(registrationFeedback(oauthError));
      setProviderLoading("");
    }
  }

  const duplicate = feedback?.kind === "duplicate-company";
  const methodsDisabled = busy || Boolean(providerLoading);

  return (
    <section className="login-page">
      <div className="login-card registration-card">
        <div className="login-logo-banner"><NetOps360Logo size={88} variant="banner" /></div>
        <h1>Create a company account</h1>
        {confirmationSent ? (
          <div className="registration-feedback" role="status" aria-live="polite">
            <h2>Verify your email</h2>
            <p>Check your inbox for a confirmation link. After confirming, sign in to complete your company registration.</p>
            <Link className="primary-button registration-action" to="/login">Continue to sign in</Link>
          </div>
        ) : (
          <>
            <p>Register your company to start using NetOps360.</p>
            <form className="login-form" onSubmit={submit} noValidate>
              <label htmlFor="signup-full-name"><span>Full Name</span><input id="signup-full-name" name="full_name" autoComplete="name" maxLength={120} required value={form.full_name} onChange={update} /></label>
              <label htmlFor="signup-company"><span>Company Name</span><input id="signup-company" name="company_name" autoComplete="organization" maxLength={150} required value={form.company_name} onChange={update} /></label>
              <label htmlFor="signup-email"><span>Email Address</span><input id="signup-email" name="email" type="email" autoComplete="email" required value={form.email} onChange={update} /></label>
              <label htmlFor="signup-password"><span>Password</span><input id="signup-password" name="password" type="password" autoComplete="new-password" minLength={12} required value={form.password} onChange={update} /><small>Use at least 12 characters.</small></label>
              <label htmlFor="signup-confirm-password"><span>Confirm Password</span><input id="signup-confirm-password" name="confirm_password" type="password" autoComplete="new-password" minLength={12} required value={form.confirm_password} onChange={update} /></label>
              {feedback && <div className={`registration-feedback ${duplicate ? "registration-feedback-conflict" : ""}`} role="alert" aria-live="assertive">
                <h2>{feedback.title}</h2><p>{feedback.message}</p>
                {duplicate && <Link className="primary-button registration-action" to="/login">Sign In</Link>}
              </div>}
              <button type="submit" className="primary-button full-width" disabled={methodsDisabled}>{busy ? "Creating account…" : "Register with email"}</button>
            </form>
            <div className="oauth-divider" aria-label="Or register with a connected provider"><span /><span className="oauth-divider-label">OR REGISTER WITH</span><span /></div>
            <div className="oauth-buttons">
              {oauthProviderEnabled("google") && <button type="button" className="oauth-button" disabled={methodsDisabled} onClick={() => void registerWithProvider("google")}>{providerLoading === "google" ? "Connecting to Google…" : "Continue with Google"}</button>}
              {oauthProviderEnabled("github") && <button type="button" className="oauth-button" disabled={methodsDisabled} onClick={() => void registerWithProvider("github")}>{providerLoading === "github" ? "Connecting to GitHub…" : "Continue with GitHub"}</button>}
              {oauthProviderEnabled("azure") && <button type="button" className="oauth-button" disabled={methodsDisabled} onClick={() => void registerWithProvider("azure")}>{providerLoading === "azure" ? "Connecting to Microsoft…" : "Continue with Microsoft"}</button>}
            </div>
            {providerLoading && <p role="status" aria-live="polite">Redirecting to your identity provider…</p>}
          </>
        )}
        {!confirmationSent && <p className="registration-signin">Already have an account? <Link to="/login">Sign in</Link></p>}
      </div>
    </section>
  );
}

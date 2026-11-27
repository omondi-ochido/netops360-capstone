import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import NetOps360Logo from "../components/common/NetOps360Logo";
import { useAuth } from "../context/AuthContext";
import {
  clearPendingCompanyRegistration, getPendingCompanyRegistration, registerCompany,
} from "../services/authService.js";
import { registrationFeedback, validateCompanyRegistration } from "../services/registrationFeedback.js";

export default function CompanyOnboarding() {
  const navigate = useNavigate();
  const { user, logout, refreshIdentity } = useAuth();
  const [form, setForm] = useState(getPendingCompanyRegistration);
  const [feedback, setFeedback] = useState(null);
  const [busy, setBusy] = useState(false);

  function update(event) {
    setForm((current) => ({ ...current, [event.target.name]: event.target.value }));
  }

  async function submit(event) {
    event.preventDefault();
    const validation = validateCompanyRegistration(form);
    if (validation) { setFeedback({ kind: "invalid-input", title: "Check your details", message: validation }); return; }
    setFeedback(null);
    setBusy(true);
    try {
      await registerCompany({
        full_name: form.full_name.trim(),
        company_name: form.company_name.trim(),
      });
      clearPendingCompanyRegistration();
      await refreshIdentity();
      navigate("/", { replace: true });
    } catch (registrationError) {
      setFeedback(registrationFeedback(registrationError));
    } finally {
      setBusy(false);
    }
  }

  async function signOut() {
    try { await logout(); }
    catch (logoutError) { setFeedback(registrationFeedback(logoutError)); }
    finally { navigate("/login", { replace: true }); }
  }

  return <section className="login-page"><div className="login-card">
    <div className="login-logo-banner"><NetOps360Logo size={88} variant="banner" /></div>
    <h1>Complete company registration</h1>
    <p>Sign-in is complete. Enter the company details to finish setting up your account.</p>
    {user?.email && <p>{user.email}</p>}
    <form className="login-form" onSubmit={submit} noValidate>
      <label htmlFor="onboarding-full-name"><span>Full Name</span><input id="onboarding-full-name" name="full_name" autoComplete="name" maxLength={120} required value={form.full_name} onChange={update} /></label>
      <label htmlFor="onboarding-company"><span>Company Name</span><input id="onboarding-company" name="company_name" autoComplete="organization" maxLength={150} required value={form.company_name} onChange={update} /></label>
      {feedback && <div className={`registration-feedback ${feedback.kind === "duplicate-company" ? "registration-feedback-conflict" : ""}`} role="alert" aria-live="assertive">
        <h2>{feedback.title}</h2><p>{feedback.message}</p>
        {feedback.kind === "duplicate-company" && <Link className="primary-button registration-action" to="/login">Sign In</Link>}
      </div>}
      <button type="submit" className="primary-button full-width" disabled={busy}>{busy ? "Registering company…" : "Register company"}</button>
    </form>
    <button type="button" className="secondary-button" onClick={() => void signOut()}>Sign out</button>
  </div></section>;
}

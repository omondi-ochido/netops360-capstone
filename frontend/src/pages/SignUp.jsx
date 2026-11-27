import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import NetOps360Logo from "../components/common/NetOps360Logo";
import { signUpCompany } from "../services/authService.js";

export default function SignUp() {
  const navigate = useNavigate();
  const [form, setForm] = useState({
    full_name: "", email: "", password: "", company_name: "",
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirmationSent, setConfirmationSent] = useState(false);

  function update(event) {
    setForm((current) => ({ ...current, [event.target.name]: event.target.value }));
  }

  async function submit(event) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      const result = await signUpCompany(form);
      if (result.hasSession) {
        navigate("/", { replace: true });
      } else {
        setConfirmationSent(true);
      }
    } catch (signupError) {
      setError(signupError.message || "Company registration could not be completed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="login-page">
      <div className="login-card">
        <div className="login-logo-banner"><NetOps360Logo size={88} variant="banner" /></div>
        <h1>Create a company account</h1>
        {confirmationSent ? (
          <>
            <p role="status">Check your work email to confirm your account. You can continue after following the link.</p>
            <Link to="/login">Back to sign in</Link>
          </>
        ) : (
          <form className="login-form" onSubmit={submit}>
            <p>Register your company to start using NetOps360.</p>
            <label>
              <span>Full Name</span>
              <input name="full_name" autoComplete="name" maxLength={120} required value={form.full_name} onChange={update} />
            </label>
            <label>
              <span>Work Email</span>
              <input name="email" type="email" autoComplete="email" required value={form.email} onChange={update} />
            </label>
            <label>
              <span>Password</span>
              <input name="password" type="password" autoComplete="new-password" minLength={12} required value={form.password} onChange={update} />
            </label>
            <label>
              <span>Company Name</span>
              <input name="company_name" autoComplete="organization" maxLength={150} required value={form.company_name} onChange={update} />
            </label>
            {error && <p role="alert">{error}</p>}
            <button type="submit" className="primary-button full-width" disabled={busy}>
              {busy ? "Creating account..." : "Create company account"}
            </button>
          </form>
        )}
        {!confirmationSent && <Link to="/login">Already have an account? Sign in</Link>}
      </div>
    </section>
  );
}

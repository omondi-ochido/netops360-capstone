import { Link, Navigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

function callbackFeedback(params, authError) {
  const code = (params.get("error") || params.get("error_code") || "").toLowerCase();
  const description = (params.get("error_description") || "").replaceAll("+", " ");
  const detail = `${code} ${description}`.toLowerCase();
  if (/access_denied|cancel|denied/.test(detail)) {
    return { title: "Sign-up was cancelled", message: "You can try again or continue with email registration." };
  }
  if (/provider.{0,30}(disabled|not enabled|unavailable|not configured)|unsupported_provider|server_error/.test(detail)) {
    return { title: "Sign-in provider unavailable", message: "This provider could not complete sign-in. Choose another provider or contact support." };
  }
  if (authError) return { title: "Sign-in could not be completed", message: authError };
  return { title: "Sign-in link expired", message: "The authentication link is invalid or expired. Start again and request a new link if needed." };
}

export default function AuthCallback() {
  const { user, loading, error } = useAuth();
  const [params] = useSearchParams();
  if (loading) return <div className="login-page" role="status" aria-live="polite">Completing sign-in…</div>;
  if (user) return <Navigate to="/" replace />;
  const feedback = callbackFeedback(params, error);
  return (
    <section className="login-page">
      <div className="login-card registration-card">
        <h1>{feedback.title}</h1>
        <p role="alert" aria-live="assertive">{feedback.message}</p>
        <p><Link to="/login">Back to sign in</Link></p>
        <p><Link to="/signup">Create a company account</Link></p>
      </div>
    </section>
  );
}

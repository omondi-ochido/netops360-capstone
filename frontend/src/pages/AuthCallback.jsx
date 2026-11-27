import { Link, Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function AuthCallback() {
  const { user, loading, error } = useAuth();
  if (loading) {
    return <div className="login-page" role="status">Completing sign-in...</div>;
  }
  if (user) return <Navigate to="/" replace />;
  return (
    <section className="login-page">
      <div className="login-card">
        <h1>Sign-in could not be completed</h1>
        <p role="alert">{error || "The authentication link is invalid or expired."}</p>
        <Link to="/login">Back to sign in</Link>
      </div>
    </section>
  );
}

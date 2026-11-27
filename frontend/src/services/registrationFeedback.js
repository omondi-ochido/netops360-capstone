export const DUPLICATE_COMPANY_TITLE = "Company already registered";
export const DUPLICATE_COMPANY_MESSAGE = "This company already has an account on NetOps360. Please sign in or contact your company's administrator to receive an invitation.";

export function registrationFeedback(error) {
  const code = String(error?.code || "").toLowerCase();
  const message = String(error?.message || "");
  const lowered = message.toLowerCase();

  if (code === "company_already_registered" || (error?.status === 409 && code.includes("company"))) {
    return { kind: "duplicate-company", title: DUPLICATE_COMPANY_TITLE, message: DUPLICATE_COMPANY_MESSAGE };
  }
  if (code === "session_expired" || code === "missing_session" || error?.status === 401) {
    return { kind: "session-expired", title: "Your sign-in expired", message: "Sign in again to complete company registration." };
  }
  if (code === "access_denied" || code === "user_cancelled" || /cancel(l)?ed|user denied|access_denied/.test(lowered)) {
    return { kind: "oauth-cancelled", title: "Sign-up was cancelled", message: "You can continue with email or try social sign-up again." };
  }
  if (["provider_disabled", "provider_not_enabled", "unsupported_provider"].includes(code)
      || /provider.{0,30}(not enabled|disabled|unavailable|not configured)/.test(lowered)) {
    return { kind: "provider-unavailable", title: "Provider unavailable", message: "That sign-up provider is not configured. Choose another method or contact support." };
  }
  if (error instanceof TypeError || /failed to fetch|network|load failed|connection timed out/.test(lowered)) {
    return { kind: "network", title: "Connection problem", message: "Check your connection and try again. Your password has not been saved." };
  }
  if (["weak_password", "password_too_short"].includes(code)) {
    return { kind: "invalid-input", title: "Check your details", message: "Use a password with at least 12 characters." };
  }
  if (["invalid_email", "email_address_invalid"].includes(code)) {
    return { kind: "invalid-input", title: "Check your details", message: "Enter a valid email address." };
  }
  return { kind: "error", title: "Registration could not be completed", message: message || "Please try again." };
}

export function validateCompanyRegistration(form, { includeCredentials = false } = {}) {
  if (!String(form.full_name || "").trim()) return "Enter your full name.";
  if (!String(form.company_name || "").trim()) return "Company name is required.";
  if (includeCredentials && !/^\S+@\S+\.\S+$/.test(String(form.email || "").trim())) return "Enter a valid email address.";
  if (includeCredentials && String(form.password || "").length < 12) return "Use a password with at least 12 characters.";
  if (includeCredentials && form.password !== form.confirm_password) return "The passwords do not match.";
  return "";
}

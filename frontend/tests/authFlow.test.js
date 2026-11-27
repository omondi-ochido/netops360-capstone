import test from "node:test";
import assert from "node:assert/strict";
import { sendRecoveryCode, signInWithProvider, signUpCompany, updatePassword, verifyRecoveryCode } from "../src/services/authService.js";
import { setSupabaseClientForTests } from "../src/services/supabaseClient.js";
import { DUPLICATE_COMPANY_MESSAGE, DUPLICATE_COMPANY_TITLE, registrationFeedback, validateCompanyRegistration } from "../src/services/registrationFeedback.js";

test("registration feedback maps duplicate company and authentication conditions to distinct UX", () => {
  const duplicate = registrationFeedback({ code: "company_already_registered", status: 409, message: "internal duplicate detail" });
  assert.equal(duplicate.kind, "duplicate-company");
  assert.equal(duplicate.title, DUPLICATE_COMPANY_TITLE);
  assert.equal(duplicate.message, DUPLICATE_COMPANY_MESSAGE);
  assert.equal(registrationFeedback({ code: "access_denied" }).kind, "oauth-cancelled");
  assert.equal(registrationFeedback({ code: "provider_not_enabled" }).kind, "provider-unavailable");
  assert.equal(registrationFeedback({ code: "session_expired", status: 401 }).kind, "session-expired");
  assert.equal(registrationFeedback(new TypeError("Failed to fetch")).kind, "network");
});

test("company registration validates name, email, password, and password confirmation", () => {
  const base = { full_name: "Ada Lovelace", company_name: "Analytical Engines", email: "ada@example.com", password: "long-enough-password", confirm_password: "long-enough-password" };
  assert.equal(validateCompanyRegistration({ ...base, company_name: " " }), "Company name is required.");
  assert.equal(validateCompanyRegistration({ ...base, confirm_password: "different-password" }, { includeCredentials: true }), "The passwords do not match.");
  assert.equal(validateCompanyRegistration(base, { includeCredentials: true }), "");
  assert.equal(validateCompanyRegistration({ full_name: "Ada", company_name: " " }), "Company name is required.");
});

test("recovery sends email, verifies the recovery OTP type, and updates the password", async () => {
  const calls = [];
  setSupabaseClientForTests({ auth: {
    resetPasswordForEmail: async (...args) => { calls.push(["send", ...args]); return { error: null }; },
    verifyOtp: async (...args) => { calls.push(["verify", ...args]); return { data: { session: {} }, error: null }; },
    updateUser: async (...args) => { calls.push(["update", ...args]); return { error: null }; },
  } });
  const originalWindow = globalThis.window;
  globalThis.window = { location: { origin: "https://netops.example" } };
  try {
    await sendRecoveryCode(" User@example.com ");
    await verifyRecoveryCode("User@example.com", "123456");
    await updatePassword("a-new-secure-password");
  } finally {
    if (originalWindow === undefined) delete globalThis.window; else globalThis.window = originalWindow;
  }
  assert.equal(calls[0][1], "User@example.com");
  assert.equal(calls[0][2].redirectTo, "https://netops.example/reset-password");
  assert.deepEqual(calls[1][1], { email: "User@example.com", token: "123456", type: "recovery" });
  assert.deepEqual(calls[2][1], { password: "a-new-secure-password" });
});

test("social login preserves the provider and redirects back to the app", async () => {
  const calls = [];
  setSupabaseClientForTests({ auth: { signInWithOAuth: async (args) => { calls.push(args); return { error: null }; } } });
  const originalWindow = globalThis.window;
  globalThis.window = { location: { origin: "https://netops.example" } };
  try {
    await signInWithProvider("google");
    await signInWithProvider("github");
    await signInWithProvider("azure");
  } finally {
    if (originalWindow === undefined) delete globalThis.window; else globalThis.window = originalWindow;
  }
  assert.deepEqual(calls.map((call) => call.provider), ["google", "github", "azure"]);
  assert.equal(calls[0].options.redirectTo, "https://netops.example/auth/callback");
  assert.equal(calls[2].options.scopes, "email");
});

test("email company sign-up sends only display metadata and preserves required onboarding details", async () => {
  const calls = [];
  const stored = new Map();
  setSupabaseClientForTests({ auth: {
    signUp: async (...args) => { calls.push(args); return { data: { session: null }, error: null }; },
  } });
  const originalWindow = globalThis.window;
  globalThis.window = { location: { origin: "https://netops.example" }, sessionStorage: {
    setItem: (key, value) => stored.set(key, value),
    getItem: (key) => stored.get(key) || null,
    removeItem: (key) => stored.delete(key),
  } };
  try {
    const result = await signUpCompany({
      email: " founder@example.com ", full_name: " Founder ", password: "twelve-character-password",
      company_name: " Example Co ",
    });
    assert.equal(result.hasSession, false);
    assert.deepEqual(JSON.parse(stored.get("netops360.pendingCompanyRegistration")), {
      full_name: "Founder", company_name: "Example Co",
    });
  } finally {
    if (originalWindow === undefined) delete globalThis.window; else globalThis.window = originalWindow;
  }
  assert.deepEqual(calls[0][0], {
    email: "founder@example.com",
    password: "twelve-character-password",
    options: {
      data: { full_name: "Founder" },
      emailRedirectTo: "https://netops.example/auth/callback?flow=company-registration",
    },
  });
});

test("social company registration preserves onboarding intent and does not trust OAuth metadata", async () => {
  const calls = [];
  const stored = new Map();
  setSupabaseClientForTests({ auth: {
    signInWithOAuth: async (args) => { calls.push(args); return { error: null }; },
  } });
  const originalWindow = globalThis.window;
  globalThis.window = { location: { origin: "https://netops.example" }, sessionStorage: {
    setItem: (key, value) => stored.set(key, value),
    getItem: (key) => stored.get(key) || null,
  } };
  try {
    await signInWithProvider("google", { full_name: "Founder", company_name: "Example Co" });
  } finally {
    if (originalWindow === undefined) delete globalThis.window; else globalThis.window = originalWindow;
  }
  assert.equal(calls[0].provider, "google");
  assert.equal(calls[0].options.redirectTo, "https://netops.example/auth/callback?flow=company-registration");
  assert.deepEqual(JSON.parse(stored.get("netops360.pendingCompanyRegistration")), {
    full_name: "Founder", company_name: "Example Co",
  });
});

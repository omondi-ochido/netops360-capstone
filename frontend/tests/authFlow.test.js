import test from "node:test";
import assert from "node:assert/strict";
import { sendRecoveryCode, signInWithProvider, signUpCompany, updatePassword, verifyRecoveryCode } from "../src/services/authService.js";
import { setSupabaseClientForTests } from "../src/services/supabaseClient.js";

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

test("company sign-up stores profile metadata and targets the auth callback", async () => {
  const calls = [];
  setSupabaseClientForTests({ auth: {
    signUp: async (...args) => { calls.push(args); return { data: { session: null }, error: null }; },
  } });
  const originalWindow = globalThis.window;
  globalThis.window = { location: { origin: "https://netops.example" } };
  try {
    const result = await signUpCompany({
      email: " founder@example.com ", full_name: " Founder ", password: "twelve-character-password",
      company_name: " Example Co ",
    });
    assert.equal(result.hasSession, false);
  } finally {
    if (originalWindow === undefined) delete globalThis.window; else globalThis.window = originalWindow;
  }
  assert.deepEqual(calls[0][0], {
    email: "founder@example.com",
    password: "twelve-character-password",
    options: {
      data: { full_name: "Founder", company_name: "Example Co" },
      emailRedirectTo: "https://netops.example/auth/callback",
    },
  });
});

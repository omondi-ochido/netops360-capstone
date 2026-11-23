import test from "node:test";
import assert from "node:assert/strict";
import { sendRecoveryCode, updatePassword, verifyRecoveryCode } from "../src/services/authService.js";
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

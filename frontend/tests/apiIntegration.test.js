import test from "node:test";
import assert from "node:assert/strict";
import { fetchDevices, createDevice } from "../src/services/deviceService.js";
import { fetchRules, acknowledgeIncident } from "../src/services/operationsService.js";
import { setSupabaseClientForTests } from "../src/services/supabaseClient.js";

const originalFetch = globalThis.fetch;
const authStub = { auth: { getSession: async () => ({ data: { session: { access_token: "test-access-token" } }, error: null }), refreshSession: async () => ({ data: { session: { access_token: "refreshed-token" } }, error: null }), signOut: async () => ({ error: null }) } };
setSupabaseClientForTests(authStub);

test.afterEach(() => { globalThis.fetch = originalFetch; });

test("device inventory consumes Flask's persisted device response", async () => {
  let requestUrl;
  globalThis.fetch = async (url, options) => {
    requestUrl = url;
    assert.equal(options.headers.get("Authorization"), "Bearer test-access-token");
    return new Response(JSON.stringify({ devices: [{ id: "d-1", hostname: "edge", ip_address: "192.0.2.1",
      device_type: "access_point", current_status: "Unknown", last_latency_ms: null,
      last_packet_loss: null, last_checked_at: null, monitoring_enabled: true }], pagination: { limit: 20, offset: 0 } }));
  };
  const result = await fetchDevices({ limit: 20 });
  assert.match(requestUrl, /\/api\/devices\?limit=20/);
  assert.equal(result.devices[0].deviceType, "Access Point");
  assert.equal(result.devices[0].status, "Unknown");
  assert.equal(result.devices[0].lastChecked, "Never");
  assert.equal(result.devices[0].latencyMs, null);
});

test("device creation sends canonical Flask payload and surfaces API errors", async () => {
  let options;
  globalThis.fetch = async (_url, request) => {
    options = request;
    return new Response(JSON.stringify({ data: { id: "d-2", hostname: "new", ip_address: "192.0.2.2", device_type: "host" } }), { status: 201 });
  };
  const created = await createDevice({ hostname: "new", ip_address: "192.0.2.2", device_type: "host" });
  assert.equal(options.method, "POST");
  assert.deepEqual(JSON.parse(options.body), { hostname: "new", ip_address: "192.0.2.2", device_type: "host" });
  assert.equal(created.id, "d-2");

  globalThis.fetch = async (_url, request) => {
    assert.match(request.headers.get("Authorization"), /^Bearer (test-access-token|refreshed-token)$/);
    return new Response(JSON.stringify({ error: { code: "unauthorized", message: "Invalid or expired access token." } }), { status: 401 });
  };
  await assert.rejects(createDevice({}), /Invalid or expired access token/);
});

test("rules and incident actions call existing Flask resource routes", async () => {
  const requests = [];
  globalThis.fetch = async (url, options = {}) => {
    requests.push({ url, options });
    return new Response(JSON.stringify({ data: url.includes("rules") ? [{ id: "r-1" }] : { id: "i-1", status: "acknowledged" } }));
  };
  assert.equal((await fetchRules({ limit: 10 }))[0].id, "r-1");
  const incident = await acknowledgeIncident("i-1");
  assert.match(requests[0].url, /\/api\/rules\?limit=10$/);
  assert.match(requests[1].url, /\/api\/incidents\/i-1\/acknowledge$/);
  assert.equal(requests[1].options.method, "POST");
  assert.equal(incident.status, "acknowledged");
});

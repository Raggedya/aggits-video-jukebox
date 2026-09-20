import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import test from "node:test";

import worker, { canonicalRequest, deliveryIdempotencyKey, safeRecipient } from "../src/index.js";


const SECRET = "worker-test-secret";
const REVISION = "a".repeat(40);
const BASE = "https://raggedya.github.io/aggits-video-jukebox";
const URL = `${BASE}/crispy-bits/test-music/`;
const PNG = new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10, 1, 2, 3]);


class FakeDB {
  constructor() {
    this.nonces = new Map();
    this.deliveries = new Map();
  }

  prepare(sql) {
    const db = this;
    return {
      values: [],
      bind(...values) { this.values = values; return this; },
      async first() {
        if (sql.includes("FROM deliveries")) return db.deliveries.get(this.values.join("|")) || null;
        return null;
      },
      async run() {
        if (sql.startsWith("DELETE FROM delivery_nonces")) {
          for (const [nonce, expiry] of db.nonces) if (expiry < this.values[0]) db.nonces.delete(nonce);
        } else if (sql.startsWith("INSERT INTO delivery_nonces")) {
          if (db.nonces.has(this.values[0])) throw new Error("UNIQUE constraint failed");
          db.nonces.set(this.values[0], this.values[1]);
        } else if (sql.startsWith("INSERT OR IGNORE INTO deliveries")) {
          const [slug, revision, title, publicUrl, recipient, idempotencyKey] = this.values;
          const key = [slug, revision, recipient].join("|");
          if (!db.deliveries.has(key)) db.deliveries.set(key, { provider_id: "", status: "attempting", created_at: null, title, publicUrl, idempotencyKey });
        } else if (sql.startsWith("UPDATE deliveries SET provider_id")) {
          const [providerId, slug, revision, recipient] = this.values;
          const key = [slug, revision, recipient].join("|");
          const record = db.deliveries.get(key);
          Object.assign(record, { provider_id: providerId, status: "sent", created_at: record.created_at || "2026-09-18T00:00:00Z" });
        } else if (sql.startsWith("UPDATE deliveries SET status = 'failed'")) {
          const [, slug, revision, recipient] = this.values;
          db.deliveries.get([slug, revision, recipient].join("|")).status = "failed";
        }
        return { success: true };
      },
    };
  }
}


function environment(overrides = {}) {
  return {
    DELIVERY_HMAC_SECRET: SECRET,
    RESEND_API_KEY: "resend-test-key",
    REPORT_FROM_EMAIL: "CRISPY BITS <test@example.com>",
    PUBLIC_BASE_URL: BASE,
    GITHUB_OWNER: "Raggedya",
    GITHUB_REPOSITORY: "aggits-video-jukebox",
    ALLOW_LEGACY_DELIVERY: "false",
    OWNER_EMAIL: "owner@example.com",
    DB: new FakeDB(),
    ...overrides,
  };
}


function payload(overrides = {}) {
  return {
    slug: "test-music",
    title: "Test Music",
    email: "listener@example.com",
    publicUrl: URL,
    qrUrl: `${URL}qr-card.png`,
    revision: REVISION,
    brand: "CRISPY BITS",
    projectType: "music",
    productName: "CRISPY BITS MUSIC",
    ...overrides,
  };
}


function signedRequest(bodyValue, { timestamp = Math.floor(Date.now() / 1000), nonce = "1".repeat(32), secret = SECRET } = {}) {
  const body = new TextEncoder().encode(JSON.stringify(bodyValue));
  const canonical = canonicalRequest(String(timestamp), nonce, body);
  const signature = createHmac("sha256", secret).update(canonical).digest("hex");
  return new Request(`https://worker.example${"/api/deliveries"}`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-crispy-timestamp": String(timestamp),
      "x-crispy-nonce": nonce,
      "x-crispy-signature": signature,
    },
    body,
  });
}


function installFetchMock({ machineAvailable = true, qrAvailable = true, resendOk = true, machineProjectType = "music", machineTitle = "Test Music", rawMachineTitle = machineTitle } = {}) {
  const calls = [];
  const original = globalThis.fetch;
  globalThis.fetch = async (input, init = {}) => {
    const url = String(input);
    calls.push({ url, init });
    if (url === "https://api.resend.com/emails") {
      return new Response(JSON.stringify(resendOk ? { id: `email-${calls.length}` } : { message: "rejected" }), {
        status: resendOk ? 200 : 502,
        headers: { "content-type": "application/json" },
      });
    }
    if (url.includes("machine.json")) {
      const title = url.includes("raw.githubusercontent.com") ? rawMachineTitle : machineTitle;
      return new Response(machineAvailable ? JSON.stringify({ slug: "test-music", projectType: machineProjectType, title, videos: [{ videoId: "video-1" }] }) : "missing", {
        status: machineAvailable ? 200 : 404,
        headers: { "content-type": "application/json" },
      });
    }
    if (url.includes("qr-card.png")) return new Response(qrAvailable ? PNG : "missing", { status: qrAvailable ? 200 : 404 });
    throw new Error(`Unexpected URL ${url}`);
  };
  return { calls, restore: () => { globalThis.fetch = original; } };
}


test("valid authenticated Business and Music requests are accepted and recipient is authoritative", async () => {
  for (const projectType of ["business", "music"]) {
    const env = environment();
    const mock = installFetchMock({ machineProjectType: projectType, machineTitle: projectType === "business" ? "Test Business" : "Test Music" });
    try {
      const body = payload({ projectType, title: projectType === "business" ? "Test Business" : "Test Music" });
      const response = await worker.fetch(signedRequest(body, { nonce: projectType === "business" ? "2".repeat(32) : "3".repeat(32) }), env);
      assert.equal(response.status, 201);
      const resend = mock.calls.find((call) => call.url.includes("api.resend.com"));
      assert.deepEqual(JSON.parse(resend.init.body).to, ["listener@example.com"]);
    } finally { mock.restore(); }
  }
});


test("valid authenticated Tourism request is accepted without changing recipient security", async () => {
  const env = environment();
  const mock = installFetchMock({ machineProjectType: "tourism", machineTitle: "Visit Test Region" });
  try {
    const body = payload({ projectType: "tourism", title: "Visit Test Region", productName: "CRISPY BITS TOURISM" });
    const response = await worker.fetch(signedRequest(body, { nonce: "aa".repeat(16) }), env);
    assert.equal(response.status, 201);
    const resend = mock.calls.find((call) => call.url.includes("api.resend.com"));
    assert.deepEqual(JSON.parse(resend.init.body).to, ["listener@example.com"]);
    assert.equal(env.DB.deliveries.size, 1);
  } finally { mock.restore(); }
});


test("missing invalid modified expired and future authentication is rejected without secret disclosure", async () => {
  const now = Math.floor(Date.now() / 1000);
  const cases = [
    new Request("https://worker.example/api/deliveries", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(payload()) }),
    signedRequest(payload(), { secret: "wrong-secret", nonce: "4".repeat(32) }),
    signedRequest(payload(), { timestamp: now - 301, nonce: "5".repeat(32) }),
    signedRequest(payload(), { timestamp: now + 301, nonce: "6".repeat(32) }),
  ];
  for (const request of cases) {
    const response = await worker.fetch(request, environment());
    assert.equal(response.status, 401);
    assert.equal((await response.text()).includes(SECRET), false);
  }
  const signed = signedRequest(payload(), { nonce: "7".repeat(32) });
  const headers = Object.fromEntries(signed.headers);
  const modified = new Request(signed.url, { method: "POST", headers, body: JSON.stringify(payload({ email: "other@example.com" })) });
  assert.equal((await worker.fetch(modified, environment())).status, 401);
});


test("replayed nonce is rejected inside the five minute window", async () => {
  const env = environment();
  const mock = installFetchMock();
  try {
    const first = await worker.fetch(signedRequest(payload(), { nonce: "8".repeat(32) }), env);
    const second = await worker.fetch(signedRequest(payload(), { nonce: "8".repeat(32) }), env);
    assert.equal(first.status, 201);
    assert.equal(second.status, 409);
    assert.equal((await second.json()).error, "delivery_replay_rejected");
  } finally { mock.restore(); }
});


test("malformed injected recipient unknown type and mismatched URL are rejected", async () => {
  const cases = [
    payload({ email: "a@example.com\nb@example.com" }),
    payload({ email: "a@example.com,b@example.com" }),
    payload({ projectType: "unknown" }),
    payload({ publicUrl: `${BASE}/crispy-bits/another/` }),
    payload({ qrUrl: "https://example.com/arbitrary.png" }),
  ];
  for (let index = 0; index < cases.length; index += 1) {
    const response = await worker.fetch(signedRequest(cases[index], { nonce: (index + 10).toString(16).padStart(32, "0") }), environment());
    assert.equal(response.status, 400);
  }
  assert.equal(safeRecipient("Name <a@example.com>"), "");
});


test("delivery identity is slug revision recipient and exact retries never resend", async () => {
  const env = environment();
  const mock = installFetchMock();
  try {
    const first = await worker.fetch(signedRequest(payload(), { nonce: "a".repeat(32) }), env);
    const retry = await worker.fetch(signedRequest(payload(), { nonce: "b".repeat(32) }), env);
    const changedRecipient = await worker.fetch(signedRequest(payload({ email: "new@example.com" }), { nonce: "c".repeat(32) }), env);
    const changedRevision = await worker.fetch(signedRequest(payload({ revision: "b".repeat(40) }), { nonce: "9".repeat(32) }), env);
    assert.equal(first.status, 201);
    assert.equal(retry.status, 200);
    assert.equal((await retry.json()).duplicate, true);
    assert.equal(changedRecipient.status, 201);
    assert.equal(changedRevision.status, 201);
    assert.equal(mock.calls.filter((call) => call.url.includes("api.resend.com")).length, 3);
    assert.match(await deliveryIdempotencyKey("slug", REVISION, "a@example.com"), /^[0-9a-f]{64}$/);
  } finally { mock.restore(); }
});


test("an attempting record retries Resend with the same provider idempotency key", async () => {
  const env = environment();
  const key = ["test-music", REVISION, "listener@example.com"].join("|");
  env.DB.deliveries.set(key, { provider_id: "", status: "attempting", created_at: null });
  const mock = installFetchMock();
  try {
    const response = await worker.fetch(signedRequest(payload(), { nonce: "d".repeat(32) }), env);
    assert.equal(response.status, 201);
    const resend = mock.calls.find((call) => call.url.includes("api.resend.com"));
    assert.equal(resend.init.headers["Idempotency-Key"], await deliveryIdempotencyKey("test-music", REVISION, "listener@example.com"));
  } finally { mock.restore(); }
});


test("live machine QR or revision mismatch prevents delivery", async () => {
  for (const options of [{ machineAvailable: false }, { qrAvailable: false }, { rawMachineTitle: "Different revision content" }]) {
    const mock = installFetchMock(options);
    try {
      const nonce = options.machineAvailable === false ? "e".repeat(32) : options.qrAvailable === false ? "f".repeat(32) : "0".repeat(32);
      const response = await worker.fetch(signedRequest(payload(), { nonce }), environment());
      assert.equal(response.status, 409);
      assert.equal(mock.calls.some((call) => call.url.includes("api.resend.com")), false);
    } finally { mock.restore(); }
  }
});


test("missing Worker secret fails safely without exposing configuration", async () => {
  const response = await worker.fetch(signedRequest(payload(), { nonce: "7a".repeat(16) }), environment({ DELIVERY_HMAC_SECRET: "" }));
  assert.equal(response.status, 503);
  const text = await response.text();
  assert.equal(text.includes(SECRET), false);
  assert.match(text, /delivery_auth_not_configured/);
});


test("legacy compatibility is opt-in and always uses fixed OWNER_EMAIL", async () => {
  const legacyPayload = payload({ email: "attacker@example.com" });
  delete legacyPayload.projectType;
  const legacyRequest = () => new Request("https://worker.example/api/deliveries", {
    method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(legacyPayload),
  });
  assert.equal((await worker.fetch(legacyRequest(), environment())).status, 401);
  const mock = installFetchMock({ machineProjectType: null });
  try {
    const response = await worker.fetch(legacyRequest(), environment({ ALLOW_LEGACY_DELIVERY: "true" }));
    const result = await response.clone().json();
    assert.equal(response.status, 201, JSON.stringify(result));
    const resend = mock.calls.find((call) => call.url.includes("api.resend.com"));
    assert.deepEqual(JSON.parse(resend.init.body).to, ["owner@example.com"]);
  } finally { mock.restore(); }
});

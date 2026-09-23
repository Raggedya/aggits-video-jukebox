import assert from "node:assert/strict";
import { createHash, createHmac } from "node:crypto";
import test from "node:test";

import worker, { canonicalRequest } from "../src/index.js";


const SECRET = "campaign-worker-secret";
const PATH = "/api/campaign-deliveries";
const BASE = "https://raggedya.github.io/aggits-video-jukebox";
const CAMPAIGN_ID = "123e4567-e89b-42d3-a456-426614174000";


class FakeDB {
  constructor() { this.nonces = new Map(); this.deliveries = new Map(); }
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
          Object.assign(db.deliveries.get([slug, revision, recipient].join("|")), { provider_id: providerId, status: "sent", created_at: "2026-09-24T00:00:00Z" });
        } else if (sql.startsWith("UPDATE deliveries SET status = 'failed'")) {
          const [, slug, revision, recipient] = this.values;
          db.deliveries.get([slug, revision, recipient].join("|")).status = "failed";
        }
        return { success: true };
      },
    };
  }
}


function environment() {
  return {
    DELIVERY_HMAC_SECRET: SECRET,
    RESEND_API_KEY: "resend-test-key",
    REPORT_FROM_EMAIL: "CRISPY BITS <test@example.com>",
    OWNER_EMAIL: "owner@example.com",
    PUBLIC_BASE_URL: BASE,
    DB: new FakeDB(),
  };
}


function payload(overrides = {}) {
  const machines = [{ candidateNumber: 1, organisationName: "Fixture One", publicUrl: `${BASE}/crispy-bits/fixture-one/` }];
  const idempotencyKey = createHash("sha256").update(`${CAMPAIGN_ID}\n${machines[0].publicUrl}`).digest("hex");
  return {
    campaignId: CAMPAIGN_ID,
    campaignName: "Dance - Melbourne",
    machines,
    counts: { approved: 1, built: 1, published: 1, failed: 0 },
    attachments: [
      { filename: "campaign.csv", content: "YQ==" },
      { filename: "qr-sheet.pdf", content: "Yg==" },
      { filename: "prospect-cards.zip", content: "Yw==" },
      { filename: "qr-codes.zip", content: "ZA==" },
    ],
    idempotencyKey,
    ...overrides,
  };
}


function signedRequest(value, { path = PATH, nonce = "1".repeat(32) } = {}) {
  const body = new TextEncoder().encode(JSON.stringify(value));
  const timestamp = String(Math.floor(Date.now() / 1000));
  const signature = createHmac("sha256", SECRET).update(canonicalRequest(timestamp, nonce, body, path)).digest("hex");
  return new Request(`https://worker.example${PATH}`, {
    method: "POST",
    headers: { "content-type": "application/json", "x-crispy-timestamp": timestamp, "x-crispy-nonce": nonce, "x-crispy-signature": signature },
    body,
  });
}


function installFetch() {
  const calls = [];
  const original = globalThis.fetch;
  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), init });
    return new Response(JSON.stringify({ id: "campaign-email-1" }), { status: 200, headers: { "content-type": "application/json" } });
  };
  return { calls, restore: () => { globalThis.fetch = original; } };
}


test("authenticated campaign package goes only to fixed OWNER_EMAIL with server-generated subject and body", async () => {
  const env = environment();
  const mock = installFetch();
  try {
    const response = await worker.fetch(signedRequest(payload()), env);
    assert.equal(response.status, 201);
    const sent = JSON.parse(mock.calls[0].init.body);
    assert.deepEqual(sent.to, ["owner@example.com"]);
    assert.equal(sent.subject, "CRISPY BITS — Dance - Melbourne — 1 MACHINES");
    assert.match(sent.text, /01\. Fixture One/);
    assert.deepEqual(sent.attachments.map((item) => item.filename), ["campaign.csv", "qr-sheet.pdf", "prospect-cards.zip", "qr-codes.zip"]);
  } finally { mock.restore(); }
});


test("campaign endpoint rejects recipient subject body and unapproved attachments", async () => {
  const cases = [
    payload({ recipient: "attacker@example.com" }),
    payload({ subject: "arbitrary" }),
    payload({ body: "arbitrary" }),
    payload({ attachments: [{ filename: "malware.exe", content: "YQ==" }] }),
  ];
  for (let index = 0; index < cases.length; index += 1) {
    const response = await worker.fetch(signedRequest(cases[index], { nonce: String(index + 2).repeat(32).slice(0, 32) }), environment());
    assert.equal(response.status, 400);
  }
});


test("campaign delivery is idempotent and a repeat does not resend", async () => {
  const env = environment();
  const mock = installFetch();
  try {
    const first = await worker.fetch(signedRequest(payload(), { nonce: "a".repeat(32) }), env);
    const second = await worker.fetch(signedRequest(payload(), { nonce: "b".repeat(32) }), env);
    assert.equal(first.status, 201);
    assert.equal(second.status, 200);
    assert.equal((await second.json()).duplicate, true);
    assert.equal(mock.calls.length, 1);
  } finally { mock.restore(); }
});


test("campaign HMAC is route-specific and URLs must be verified publication namespace", async () => {
  assert.equal((await worker.fetch(signedRequest(payload(), { path: "/api/deliveries", nonce: "c".repeat(32) }), environment())).status, 401);
  const badMachines = [{ candidateNumber: 1, organisationName: "Fixture", publicUrl: "https://youtube.com/watch?v=bad" }];
  const response = await worker.fetch(signedRequest(payload({ machines: badMachines }), { nonce: "d".repeat(32) }), environment());
  assert.equal(response.status, 400);
});


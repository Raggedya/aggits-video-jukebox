import assert from "node:assert/strict";
import test from "node:test";

import worker, { safeFirstName, safeYouTubeVideo } from "../src/index.js";


class SubmissionDB {
  constructor() {
    this.guards = new Map();
  }

  prepare(sql) {
    const db = this;
    return {
      values: [],
      bind(...values) { this.values = values; return this; },
      async first() {
        if (sql.startsWith("INSERT INTO banjo_submission_guards") && sql.includes("'rate'")) {
          const [key, expiry] = this.values;
          const existing = db.guards.get(key);
          const count = existing ? existing.count + 1 : 1;
          db.guards.set(key, { type: "rate", count, expiry });
          return { count };
        }
        return null;
      },
      async run() {
        if (sql.startsWith("DELETE FROM banjo_submission_guards WHERE expires_at")) {
          const now = this.values[0];
          for (const [key, record] of db.guards) if (record.expiry <= now) db.guards.delete(key);
          return { success: true, meta: { changes: 0 } };
        }
        if (sql.startsWith("INSERT OR IGNORE INTO banjo_submission_guards")) {
          const [key, expiry] = this.values;
          if (db.guards.has(key)) return { success: true, meta: { changes: 0 } };
          db.guards.set(key, { type: "duplicate", count: 1, expiry });
          return { success: true, meta: { changes: 1 } };
        }
        if (sql.startsWith("DELETE FROM banjo_submission_guards WHERE guard_key")) {
          const changed = db.guards.delete(this.values[0]) ? 1 : 0;
          return { success: true, meta: { changes: changed } };
        }
        throw new Error(`Unexpected SQL: ${sql}`);
      },
    };
  }
}


function environment(overrides = {}) {
  return {
    DELIVERY_HMAC_SECRET: "submission-hash-secret",
    RESEND_API_KEY: "resend-test-key",
    REPORT_FROM_EMAIL: "CRISPY BITS <test@example.com>",
    OWNER_EMAIL: "owner@example.com",
    DB: new SubmissionDB(),
    ...overrides,
  };
}


function submission(overrides = {}) {
  return {
    first_name: "Steve",
    email: "steve@example.com",
    youtube_url: "https://youtu.be/AbCdEf123_4",
    project_slug: "banjos-world-of-cars",
    project_type: "banjo",
    company: "",
    ...overrides,
  };
}


function request(body = submission(), { method = "POST", address = "203.0.113.10" } = {}) {
  return new Request("https://worker.example/api/banjo/submissions", {
    method,
    headers: { "content-type": "application/json", "cf-connecting-ip": address },
    body: method === "POST" ? JSON.stringify(body) : undefined,
  });
}


function installProviderMock({ ok = true } = {}) {
  const calls = [];
  const original = globalThis.fetch;
  globalThis.fetch = async (input, init = {}) => {
    calls.push({ url: String(input), init });
    return new Response(JSON.stringify(ok ? { id: "submission-email" } : { message: "provider detail" }), {
      status: ok ? 201 : 502,
      headers: { "content-type": "application/json" },
    });
  };
  return { calls, restore: () => { globalThis.fetch = original; } };
}


test("valid Banjo submission uses fixed recipient subject body and safe Reply-To", async () => {
  const env = environment();
  const provider = installProviderMock();
  try {
    const response = await worker.fetch(request(), env);
    assert.equal(response.status, 201);
    assert.deepEqual(await response.json(), { ok: true });
    assert.equal(provider.calls.length, 1);
    const email = JSON.parse(provider.calls[0].init.body);
    assert.deepEqual(email.to, ["owner@example.com"]);
    assert.equal(email.subject, "NEW CAR FOR BANJO");
    assert.equal(email.reply_to, "steve@example.com");
    assert.match(email.text, /First name:\nSteve/);
    assert.match(email.text, /YouTube:\nhttps:\/\/www\.youtube\.com\/watch\?v=AbCdEf123_4/);
    assert.match(email.text, /Video ID:\nAbCdEf123_4/);
    assert.match(email.text, /Source:\nBanjo's World of Cars/);
    assert.match(email.text, /Submitted:\n\d{4}-\d{2}-\d{2}T/);
  } finally { provider.restore(); }
});


test("supported YouTube video URL forms normalize without a YouTube API credential", () => {
  for (const url of [
    "https://www.youtube.com/watch?v=AbCdEf123_4",
    "https://youtu.be/AbCdEf123_4?t=10",
    "https://youtube.com/shorts/AbCdEf123_4",
    "https://www.youtube.com/embed/AbCdEf123_4",
    "https://m.youtube.com/live/AbCdEf123_4",
  ]) {
    assert.deepEqual(safeYouTubeVideo(url), { videoId: "AbCdEf123_4", url: "https://www.youtube.com/watch?v=AbCdEf123_4" });
  }
  assert.equal(safeYouTubeVideo("https://example.com/watch?v=AbCdEf123_4"), null);
  assert.equal(safeYouTubeVideo("javascript:alert(1)"), null);
  assert.equal(safeYouTubeVideo("file:///C:/video.mp4"), null);
});


test("invalid email name header injection and non-YouTube URLs never call provider", async () => {
  const cases = [
    submission({ email: "not-an-email" }),
    submission({ email: "steve@example.com\nBcc:attacker@example.com" }),
    submission({ first_name: "Steve\r\nBcc: attacker@example.com" }),
    submission({ youtube_url: "https://example.com/video" }),
  ];
  for (let index = 0; index < cases.length; index += 1) {
    const provider = installProviderMock();
    try {
      const response = await worker.fetch(request(cases[index], { address: `203.0.113.${20 + index}` }), environment());
      assert.equal(response.status, 400);
      assert.equal(provider.calls.length, 0);
    } finally { provider.restore(); }
  }
  assert.equal(safeFirstName("Anne-Marie O'Neil"), "Anne-Marie O'Neil");
});


test("arbitrary recipient subject body HTML and sender fields are rejected as open-relay attempts", async () => {
  for (const field of ["recipient", "to", "subject", "body", "html", "from", "reply_to"]) {
    const provider = installProviderMock();
    try {
      const response = await worker.fetch(request(submission({ [field]: "attacker@example.com" })), environment());
      assert.equal(response.status, 400);
      assert.equal((await response.json()).error, "unexpected_fields");
      assert.equal(provider.calls.length, 0);
    } finally { provider.restore(); }
  }
});


test("oversized non-JSON and non-POST requests are rejected before provider", async () => {
  const provider = installProviderMock();
  try {
    const oversized = request(submission({ first_name: "A".repeat(3000) }));
    assert.equal((await worker.fetch(oversized, environment())).status, 413);
    const plain = new Request("https://worker.example/api/banjo/submissions", { method: "POST", headers: { "content-type": "text/plain" }, body: "text" });
    assert.equal((await worker.fetch(plain, environment())).status, 415);
    assert.equal((await worker.fetch(request(undefined, { method: "GET" }), environment())).status, 405);
    assert.equal(provider.calls.length, 0);
  } finally { provider.restore(); }
});


test("honeypot is accepted silently without sending operator email", async () => {
  const provider = installProviderMock();
  try {
    const response = await worker.fetch(request(submission({ company: "bot value" })), environment());
    assert.equal(response.status, 202);
    assert.deepEqual(await response.json(), { ok: true });
    assert.equal(provider.calls.length, 0);
  } finally { provider.restore(); }
});


test("sixth submission from one network address in an hour is rate limited", async () => {
  const env = environment();
  const provider = installProviderMock();
  try {
    for (let index = 0; index < 5; index += 1) {
      const videoId = `RATE${String(index).padStart(7, "0")}`;
      const response = await worker.fetch(request(submission({ youtube_url: `https://youtu.be/${videoId}` })), env);
      assert.equal(response.status, 201);
    }
    const blocked = await worker.fetch(request(submission({ youtube_url: "https://youtu.be/RATE0000005" })), env);
    assert.equal(blocked.status, 429);
    assert.equal((await blocked.json()).error, "rate_limited");
    assert.equal(provider.calls.length, 5);
  } finally { provider.restore(); }
});


test("same email and video within 24 hours sends only one operator email", async () => {
  const env = environment();
  const provider = installProviderMock();
  try {
    assert.equal((await worker.fetch(request(), env)).status, 201);
    const duplicate = await worker.fetch(request(), env);
    assert.equal(duplicate.status, 409);
    assert.equal((await duplicate.json()).error, "duplicate_submission");
    assert.equal(provider.calls.length, 1);
  } finally { provider.restore(); }
});


test("provider failure is public-safe and releases duplicate reservation for retry", async () => {
  const env = environment();
  const failedProvider = installProviderMock({ ok: false });
  try {
    const failed = await worker.fetch(request(), env);
    assert.equal(failed.status, 502);
    assert.deepEqual(await failed.json(), { ok: false, error: "submission_unavailable" });
  } finally { failedProvider.restore(); }
  const workingProvider = installProviderMock();
  try {
    assert.equal((await worker.fetch(request(), env)).status, 201);
    assert.equal(workingProvider.calls.length, 1);
  } finally { workingProvider.restore(); }
});


test("missing server configuration fails safely without calling provider", async () => {
  for (const missing of ["RESEND_API_KEY", "DELIVERY_HMAC_SECRET", "OWNER_EMAIL", "REPORT_FROM_EMAIL", "DB"]) {
    const env = environment();
    delete env[missing];
    const provider = installProviderMock();
    try {
      const response = await worker.fetch(request(), env);
      assert.equal(response.status, 503);
      assert.deepEqual(await response.json(), { ok: false, error: "submission_unavailable" });
      assert.equal(provider.calls.length, 0);
    } finally { provider.restore(); }
  }
});

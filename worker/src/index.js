const DELIVERY_PATH = "/api/deliveries";
const REPLAY_WINDOW_SECONDS = 300;
const MAX_BODY_BYTES = 16 * 1024;

const json = (value, status = 200, headers = {}) => new Response(JSON.stringify(value), {
  status,
  headers: { "content-type": "application/json; charset=utf-8", ...headers },
});

const cors = {
  "access-control-allow-origin": "*",
  "access-control-allow-methods": "GET,POST,OPTIONS",
  "access-control-allow-headers": "content-type,x-crispy-timestamp,x-crispy-nonce,x-crispy-signature",
};

function safeSlug(value) {
  const slug = String(value || "").toLowerCase();
  return /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(slug) ? slug : "";
}

function safeRecipient(value) {
  const recipient = String(value || "").trim().toLowerCase();
  if (!recipient || recipient.length > 254 || /[\r\n]/.test(recipient)) return "";
  return /^[^\s@<>,;:"()[\]\\]+@[^\s@<>,;:"()[\]\\]+\.[^\s@<>,;:"()[\]\\]+$/.test(recipient) ? recipient : "";
}

function asBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
  }
  return btoa(binary);
}

function hexToBytes(value) {
  if (!/^[0-9a-f]{64}$/i.test(value)) return null;
  return new Uint8Array(value.match(/.{2}/g).map((part) => Number.parseInt(part, 16)));
}

function constantTimeEqual(left, right) {
  if (!(left instanceof Uint8Array) || !(right instanceof Uint8Array) || left.length !== right.length) return false;
  let difference = 0;
  for (let index = 0; index < left.length; index += 1) difference |= left[index] ^ right[index];
  return difference === 0;
}

function canonicalRequest(timestamp, nonce, bodyBytes) {
  const prefix = new TextEncoder().encode(`${timestamp}\n${nonce}\nPOST\n${DELIVERY_PATH}\n`);
  const canonical = new Uint8Array(prefix.length + bodyBytes.length);
  canonical.set(prefix);
  canonical.set(bodyBytes, prefix.length);
  return canonical;
}

async function expectedSignature(secret, timestamp, nonce, bodyBytes) {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  return new Uint8Array(await crypto.subtle.sign("HMAC", key, canonicalRequest(timestamp, nonce, bodyBytes)));
}

async function authenticate(request, env, bodyBytes, nowSeconds = Math.floor(Date.now() / 1000)) {
  if (!env.DELIVERY_HMAC_SECRET) return { ok: false, response: json({ ok: false, error: "delivery_auth_not_configured" }, 503, cors) };
  const timestamp = request.headers.get("x-crispy-timestamp") || "";
  const nonce = request.headers.get("x-crispy-nonce") || "";
  const supplied = hexToBytes(request.headers.get("x-crispy-signature") || "");
  const parsedTimestamp = Number(timestamp);
  if (!Number.isInteger(parsedTimestamp) || Math.abs(nowSeconds - parsedTimestamp) > REPLAY_WINDOW_SECONDS || !/^[0-9a-f]{32,64}$/i.test(nonce) || !supplied) {
    return { ok: false, response: json({ ok: false, error: "delivery_authentication_failed" }, 401, cors) };
  }
  const expected = await expectedSignature(env.DELIVERY_HMAC_SECRET, timestamp, nonce, bodyBytes);
  if (!constantTimeEqual(supplied, expected)) {
    return { ok: false, response: json({ ok: false, error: "delivery_authentication_failed" }, 401, cors) };
  }
  await env.DB.prepare("DELETE FROM delivery_nonces WHERE expires_at < ?1").bind(nowSeconds).run();
  try {
    await env.DB.prepare("INSERT INTO delivery_nonces (nonce, expires_at) VALUES (?1, ?2)").bind(nonce, nowSeconds + REPLAY_WINDOW_SECONDS).run();
  } catch {
    return { ok: false, response: json({ ok: false, error: "delivery_replay_rejected" }, 409, cors) };
  }
  return { ok: true, legacy: false };
}

async function legacyRecipient(request, env, bodyBytes) {
  const hasAuthHeader = request.headers.has("x-crispy-timestamp") || request.headers.has("x-crispy-nonce") || request.headers.has("x-crispy-signature");
  if (hasAuthHeader || env.ALLOW_LEGACY_DELIVERY !== "true") return null;
  const recipient = safeRecipient(env.OWNER_EMAIL);
  if (!recipient) return null;
  return { recipient, legacy: true, bodyBytes };
}

async function sha256(buffer) {
  return new Uint8Array(await crypto.subtle.digest("SHA-256", buffer));
}

async function verifyPublishedAssets(env, { slug, revision, expectedUrl, projectType, legacy = false }) {
  const publicBase = String(env.PUBLIC_BASE_URL || "").replace(/\/+$/, "");
  const owner = String(env.GITHUB_OWNER || "");
  const repository = String(env.GITHUB_REPOSITORY || "");
  if (!publicBase || !owner || !repository) return { ok: false, error: "publication_verification_not_configured", status: 503 };
  const liveMachineUrl = `${expectedUrl}machine.json?revision=${encodeURIComponent(revision)}`;
  const liveQrUrl = `${expectedUrl}qr-card.png?revision=${encodeURIComponent(revision)}`;
  const commitBase = `https://raw.githubusercontent.com/${encodeURIComponent(owner)}/${encodeURIComponent(repository)}/${encodeURIComponent(revision)}/public/crispy-bits/${encodeURIComponent(slug)}/`;
  const [liveMachineResponse, liveQrResponse, commitMachineResponse, commitQrResponse] = await Promise.all([
    fetch(liveMachineUrl, { cf: { cacheTtl: 0 } }),
    fetch(liveQrUrl, { cf: { cacheTtl: 0 } }),
    fetch(`${commitBase}machine.json`, { cf: { cacheTtl: 0 } }),
    fetch(`${commitBase}qr-card.png`, { cf: { cacheTtl: 0 } }),
  ]);
  if (![liveMachineResponse, liveQrResponse, commitMachineResponse, commitQrResponse].every((response) => response.ok)) {
    return { ok: false, error: "published_assets_not_ready", status: 409 };
  }
  const [liveMachine, commitMachine, liveQr, commitQr] = await Promise.all([
    liveMachineResponse.json(),
    commitMachineResponse.json(),
    liveQrResponse.arrayBuffer(),
    commitQrResponse.arrayBuffer(),
  ]);
  const effectiveType = (machine) => machine.projectType || (legacy ? "business" : "");
  const validMachine = (machine) => machine && machine.slug === slug && effectiveType(machine) === projectType && Array.isArray(machine.videos) && machine.videos.length > 0;
  if (!validMachine(liveMachine) || !validMachine(commitMachine)) {
    return { ok: false, error: "published_machine_failed_validation", status: 422 };
  }
  const liveIdentity = JSON.stringify([liveMachine.slug, effectiveType(liveMachine), liveMachine.title, liveMachine.videos.map((video) => video.videoId || video.video_id)]);
  const commitIdentity = JSON.stringify([commitMachine.slug, effectiveType(commitMachine), commitMachine.title, commitMachine.videos.map((video) => video.videoId || video.video_id)]);
  const qrMatches = constantTimeEqual(await sha256(liveQr), await sha256(commitQr));
  if (liveIdentity !== commitIdentity || !qrMatches) return { ok: false, error: "published_revision_mismatch", status: 409 };
  return { ok: true, machine: liveMachine, qr: liveQr };
}

async function deliveryIdempotencyKey(slug, revision, recipient) {
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(`${slug}:${revision}:${recipient}`)));
  return Array.from(digest, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function handleDelivery(request, env) {
  if (!env.RESEND_API_KEY) return json({ ok: false, error: "delivery_service_not_configured" }, 503, cors);
  const bodyBuffer = await request.arrayBuffer();
  if (bodyBuffer.byteLength > MAX_BODY_BYTES) return json({ ok: false, error: "request_too_large" }, 413, cors);
  const bodyBytes = new Uint8Array(bodyBuffer);
  const legacy = await legacyRecipient(request, env, bodyBytes);
  let auth;
  if (legacy) {
    auth = { ok: true, legacy: true };
  } else {
    auth = await authenticate(request, env, bodyBytes);
    if (!auth.ok) return auth.response;
  }
  let body;
  try { body = JSON.parse(new TextDecoder().decode(bodyBytes)); } catch { return json({ ok: false, error: "invalid_json" }, 400, cors); }
  const slug = safeSlug(body.slug);
  const revision = String(body.revision || "").trim();
  const requestedProjectType = String(body.projectType || "");
  const projectType = ["business", "music", "tourism", "banjo"].includes(requestedProjectType) ? requestedProjectType : legacy && !requestedProjectType ? "business" : "";
  const brandPath = "/crispy-bits";
  const requestedUrl = String(body.publicUrl || "").replace(/\/+$/, "") + "/";
  const expectedUrl = `${String(env.PUBLIC_BASE_URL || "").replace(/\/+$/, "")}${brandPath}/${slug}/`;
  const requestedQrUrl = String(body.qrUrl || "");
  const recipient = legacy ? legacy.recipient : safeRecipient(body.email);
  if (!slug || !/^[0-9a-f]{40}$/i.test(revision) || !projectType || !recipient || requestedUrl !== expectedUrl || requestedQrUrl !== `${expectedUrl}qr-card.png`) {
    return json({ ok: false, error: "invalid_publication_or_recipient" }, 400, cors);
  }

  const existing = await env.DB.prepare("SELECT provider_id, status, created_at FROM deliveries WHERE slug = ?1 AND revision = ?2 AND recipient = ?3")
    .bind(slug, revision, recipient).first();
  if (existing && existing.status === "sent") {
    return json({ ok: true, duplicate: true, id: existing.provider_id, sentAt: existing.created_at, legacy: Boolean(legacy) }, 200, cors);
  }

  const verified = await verifyPublishedAssets(env, { slug, revision, expectedUrl, projectType, legacy: Boolean(legacy) });
  if (!verified.ok) return json({ ok: false, error: verified.error }, verified.status, cors);
  const machine = verified.machine;
  const title = String(machine.title || slug).slice(0, 150);
  const qr = asBase64(verified.qr);
  const idempotencyKey = await deliveryIdempotencyKey(slug, revision, recipient);
  await env.DB.prepare("INSERT OR IGNORE INTO deliveries (slug, revision, title, public_url, recipient, provider_id, status, idempotency_key, last_attempt_at) VALUES (?1, ?2, ?3, ?4, ?5, '', 'attempting', ?6, CURRENT_TIMESTAMP)")
    .bind(slug, revision, title, expectedUrl, recipient, idempotencyKey).run();

  const response = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      authorization: `Bearer ${env.RESEND_API_KEY}`,
      "content-type": "application/json",
      "Idempotency-Key": idempotencyKey,
    },
    body: JSON.stringify({
      from: env.REPORT_FROM_EMAIL,
      to: [recipient],
      subject: `${title} — CRISPY BITS video jukebox is live`,
      html: `<div style="background:#080706;color:#f2e4bf;padding:32px;font-family:Arial,sans-serif"><div style="color:#b88a4f;font-family:Georgia,serif;font-size:28px;font-weight:bold">CRISPY BITS VIDEO JUKEBOX</div><h1>${title.replace(/[<>&]/g, "")}</h1><p>Your video discovery machine is live.</p><p><a href="${expectedUrl}" style="display:inline-block;background:#b88a4f;color:#080706;padding:14px 22px;text-decoration:none;font-weight:bold">OPEN JUKEBOX</a></p><p>The titled QR card is attached.</p></div>`,
      attachments: [{ filename: `${slug}-crispy-bits-qr.png`, content: qr }],
    }),
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) {
    await env.DB.prepare("UPDATE deliveries SET status = 'failed', last_error = ?1, last_attempt_at = CURRENT_TIMESTAMP WHERE slug = ?2 AND revision = ?3 AND recipient = ?4")
      .bind(String(result.message || `resend_${response.status}`).slice(0, 300), slug, revision, recipient).run();
    return json({ ok: false, error: result.message || `resend_${response.status}` }, response.status === 429 ? 429 : 502, cors);
  }

  await env.DB.prepare("UPDATE deliveries SET provider_id = ?1, status = 'sent', last_error = NULL, last_attempt_at = CURRENT_TIMESTAMP WHERE slug = ?2 AND revision = ?3 AND recipient = ?4")
    .bind(String(result.id || ""), slug, revision, recipient).run();
  return json({ ok: true, id: result.id || null, sentAt: new Date().toISOString(), legacy: Boolean(legacy) }, 201, cors);
}

export { authenticate, canonicalRequest, constantTimeEqual, deliveryIdempotencyKey, handleDelivery, safeRecipient, verifyPublishedAssets };

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
    if (request.method === "GET" && url.pathname === "/") return json({ ok: true, service: "aggits-video-jukebox-delivery" }, 200, cors);
    if (request.method === "POST" && url.pathname === DELIVERY_PATH) return handleDelivery(request, env);
    return json({ ok: false, error: "not_found" }, 404, cors);
  },
};

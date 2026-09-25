const DELIVERY_PATH = "/api/deliveries";
const CAMPAIGN_DELIVERY_PATH = "/api/campaign-deliveries";
const BANJO_SUBMISSION_PATH = "/api/banjo/submissions";
const REPLAY_WINDOW_SECONDS = 300;
const MAX_BODY_BYTES = 16 * 1024;
const MAX_CAMPAIGN_BODY_BYTES = 12 * 1024 * 1024;
const MAX_SUBMISSION_BODY_BYTES = 2 * 1024;
const SUBMISSION_RATE_LIMIT = 5;
const SUBMISSION_RATE_WINDOW_SECONDS = 60 * 60;
const SUBMISSION_DUPLICATE_WINDOW_SECONDS = 24 * 60 * 60;
const BANJO_SUBMISSION_SLUG = "banjos-world-of-cars";

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

function safeFirstName(value) {
  const name = String(value || "").trim().replace(/\s+/g, " ");
  if (!name || name.length > 50 || /[\u0000-\u001f\u007f]/.test(name)) return "";
  return /^[\p{L}\p{M}][\p{L}\p{M} '\u2019-]{0,49}$/u.test(name) ? name : "";
}

function safeYouTubeVideo(value) {
  const raw = String(value || "").trim();
  if (!raw || raw.length > 300 || /[\u0000-\u001f\u007f]/.test(raw)) return null;
  let url;
  try { url = new URL(raw); } catch { return null; }
  if (!['https:', 'http:'].includes(url.protocol)) return null;
  const host = url.hostname.toLowerCase().replace(/^www\./, "").replace(/^m\./, "");
  let videoId = "";
  if (host === "youtu.be") videoId = url.pathname.split("/").filter(Boolean)[0] || "";
  if (host === "youtube.com") {
    if (url.pathname === "/watch") videoId = url.searchParams.get("v") || "";
    else {
      const parts = url.pathname.split("/").filter(Boolean);
      if (["shorts", "embed", "live"].includes(parts[0])) videoId = parts[1] || "";
    }
  }
  if (!/^[A-Za-z0-9_-]{11}$/.test(videoId)) return null;
  return { videoId, url: `https://www.youtube.com/watch?v=${videoId}` };
}

function escapeHtml(value) {
  return String(value || "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character]);
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

function canonicalRequest(timestamp, nonce, bodyBytes, path = DELIVERY_PATH) {
  const prefix = new TextEncoder().encode(`${timestamp}\n${nonce}\nPOST\n${path}\n`);
  const canonical = new Uint8Array(prefix.length + bodyBytes.length);
  canonical.set(prefix);
  canonical.set(bodyBytes, prefix.length);
  return canonical;
}

async function expectedSignature(secret, timestamp, nonce, bodyBytes, path = DELIVERY_PATH) {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  return new Uint8Array(await crypto.subtle.sign("HMAC", key, canonicalRequest(timestamp, nonce, bodyBytes, path)));
}

async function authenticate(request, env, bodyBytes, nowSeconds = Math.floor(Date.now() / 1000), path = DELIVERY_PATH) {
  if (!env.DELIVERY_HMAC_SECRET) return { ok: false, response: json({ ok: false, error: "delivery_auth_not_configured" }, 503, cors) };
  const timestamp = request.headers.get("x-crispy-timestamp") || "";
  const nonce = request.headers.get("x-crispy-nonce") || "";
  const supplied = hexToBytes(request.headers.get("x-crispy-signature") || "");
  const parsedTimestamp = Number(timestamp);
  if (!Number.isInteger(parsedTimestamp) || Math.abs(nowSeconds - parsedTimestamp) > REPLAY_WINDOW_SECONDS || !/^[0-9a-f]{32,64}$/i.test(nonce) || !supplied) {
    return { ok: false, response: json({ ok: false, error: "delivery_authentication_failed" }, 401, cors) };
  }
  const expected = await expectedSignature(env.DELIVERY_HMAC_SECRET, timestamp, nonce, bodyBytes, path);
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

async function sha256Hex(value) {
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(String(value))));
  return Array.from(digest, (byte) => byte.toString(16).padStart(2, "0")).join("");
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
  const projectType = ["business", "music", "tourism", "banjo", "channel_master", "white_label"].includes(requestedProjectType) ? requestedProjectType : legacy && !requestedProjectType ? "business" : "";
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

async function handleBanjoSubmission(request, env, nowSeconds = Math.floor(Date.now() / 1000)) {
  if (!env.RESEND_API_KEY || !env.DELIVERY_HMAC_SECRET || !safeRecipient(env.OWNER_EMAIL) || !env.REPORT_FROM_EMAIL || !env.DB) {
    return json({ ok: false, error: "submission_unavailable" }, 503, cors);
  }
  if (!String(request.headers.get("content-type") || "").toLowerCase().startsWith("application/json")) {
    return json({ ok: false, error: "invalid_content_type" }, 415, cors);
  }
  const declaredLength = Number(request.headers.get("content-length") || 0);
  if (declaredLength > MAX_SUBMISSION_BODY_BYTES) return json({ ok: false, error: "request_too_large" }, 413, cors);
  const bodyBuffer = await request.arrayBuffer();
  if (bodyBuffer.byteLength > MAX_SUBMISSION_BODY_BYTES) return json({ ok: false, error: "request_too_large" }, 413, cors);
  let body;
  try { body = JSON.parse(new TextDecoder().decode(bodyBuffer)); } catch { return json({ ok: false, error: "invalid_json" }, 400, cors); }
  if (!body || typeof body !== "object" || Array.isArray(body)) return json({ ok: false, error: "invalid_submission" }, 400, cors);

  const allowedFields = new Set(["first_name", "email", "youtube_url", "project_slug", "project_type", "company"]);
  if (Object.keys(body).some((key) => !allowedFields.has(key))) {
    console.log("Banjo submission rejected: unexpected field");
    return json({ ok: false, error: "unexpected_fields" }, 400, cors);
  }
  if (body.project_type !== "banjo" || safeSlug(body.project_slug) !== BANJO_SUBMISSION_SLUG) {
    return json({ ok: false, error: "invalid_banjo_machine" }, 400, cors);
  }

  const clientAddress = String(request.headers.get("cf-connecting-ip") || "unknown").slice(0, 128);
  const rateWindow = Math.floor(nowSeconds / SUBMISSION_RATE_WINDOW_SECONDS);
  const rateKey = await sha256Hex(`banjo-rate:${env.DELIVERY_HMAC_SECRET}:${clientAddress}:${rateWindow}`);
  const rateExpiry = (rateWindow + 1) * SUBMISSION_RATE_WINDOW_SECONDS;
  await env.DB.prepare("DELETE FROM banjo_submission_guards WHERE expires_at <= ?1").bind(nowSeconds).run();
  const rateRecord = await env.DB.prepare("INSERT INTO banjo_submission_guards (guard_key, guard_type, count, expires_at) VALUES (?1, 'rate', 1, ?2) ON CONFLICT(guard_key) DO UPDATE SET count = count + 1 RETURNING count")
    .bind(rateKey, rateExpiry).first();
  if (Number(rateRecord?.count || 0) > SUBMISSION_RATE_LIMIT) {
    console.log("Banjo submission rate-limited");
    return json({ ok: false, error: "rate_limited" }, 429, cors);
  }

  if (String(body.company || "").trim()) {
    console.log("Banjo submission rejected: honeypot");
    return json({ ok: true }, 202, cors);
  }
  const firstName = safeFirstName(body.first_name);
  if (!firstName) return json({ ok: false, error: "invalid_first_name" }, 400, cors);
  const submitter = safeRecipient(body.email);
  if (!submitter) return json({ ok: false, error: "invalid_email" }, 400, cors);
  const youtube = safeYouTubeVideo(body.youtube_url);
  if (!youtube) {
    console.log("Banjo submission rejected: invalid YouTube URL");
    return json({ ok: false, error: "invalid_youtube_url" }, 400, cors);
  }

  const duplicateKey = await sha256Hex(`banjo-duplicate:${env.DELIVERY_HMAC_SECRET}:${submitter}:${youtube.videoId}`);
  const duplicateResult = await env.DB.prepare("INSERT OR IGNORE INTO banjo_submission_guards (guard_key, guard_type, count, expires_at) VALUES (?1, 'duplicate', 1, ?2)")
    .bind(duplicateKey, nowSeconds + SUBMISSION_DUPLICATE_WINDOW_SECONDS).run();
  const duplicateInserted = Number(duplicateResult?.meta?.changes ?? duplicateResult?.changes ?? 0) > 0;
  if (!duplicateInserted) return json({ ok: false, error: "duplicate_submission" }, 409, cors);

  const submittedAt = new Date(nowSeconds * 1000).toISOString();
  const operatorRecipient = safeRecipient(env.OWNER_EMAIL);
  const subject = "NEW CAR FOR BANJO";
  const text = [
    subject, "", "First name:", firstName, "", "Email:", submitter, "", "YouTube:", youtube.url,
    "", "Video ID:", youtube.videoId, "", "Source:", "Banjo's World of Cars", "", "Submitted:", submittedAt,
  ].join("\n");
  const providerResponse = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      authorization: `Bearer ${env.RESEND_API_KEY}`,
      "content-type": "application/json",
      "Idempotency-Key": duplicateKey,
    },
    body: JSON.stringify({
      from: env.REPORT_FROM_EMAIL,
      to: [operatorRecipient],
      reply_to: submitter,
      subject,
      text,
      html: `<div style="font-family:Arial,sans-serif"><h1>${subject}</h1><p><strong>First name:</strong><br>${escapeHtml(firstName)}</p><p><strong>Email:</strong><br>${escapeHtml(submitter)}</p><p><strong>YouTube:</strong><br><a href="${escapeHtml(youtube.url)}">${escapeHtml(youtube.url)}</a></p><p><strong>Video ID:</strong><br>${escapeHtml(youtube.videoId)}</p><p><strong>Source:</strong><br>Banjo&#39;s World of Cars</p><p><strong>Submitted:</strong><br>${escapeHtml(submittedAt)}</p></div>`,
    }),
  });
  if (!providerResponse.ok) {
    await env.DB.prepare("DELETE FROM banjo_submission_guards WHERE guard_key = ?1 AND guard_type = 'duplicate'").bind(duplicateKey).run();
    console.log("Banjo submission provider failure");
    return json({ ok: false, error: "submission_unavailable" }, providerResponse.status === 429 ? 429 : 502, cors);
  }
  console.log("Banjo submission accepted");
  return json({ ok: true }, 201, cors);
}

async function handleCampaignDelivery(request, env) {
  if (!env.RESEND_API_KEY) return json({ ok: false, error: "delivery_service_not_configured" }, 503, cors);
  const bodyBuffer = await request.arrayBuffer();
  if (bodyBuffer.byteLength > MAX_CAMPAIGN_BODY_BYTES) return json({ ok: false, error: "request_too_large" }, 413, cors);
  const bodyBytes = new Uint8Array(bodyBuffer);
  const auth = await authenticate(request, env, bodyBytes, Math.floor(Date.now() / 1000), CAMPAIGN_DELIVERY_PATH);
  if (!auth.ok) return auth.response;
  let body;
  try { body = JSON.parse(new TextDecoder().decode(bodyBytes)); } catch { return json({ ok: false, error: "invalid_json" }, 400, cors); }
  if (!body || typeof body !== "object" || Array.isArray(body)) return json({ ok: false, error: "invalid_campaign_delivery" }, 400, cors);
  const allowedFields = new Set(["campaignId", "campaignName", "machines", "counts", "attachments", "idempotencyKey"]);
  if (Object.keys(body).some((key) => !allowedFields.has(key))) return json({ ok: false, error: "unexpected_fields" }, 400, cors);
  const campaignId = String(body.campaignId || "").toLowerCase();
  const campaignName = String(body.campaignName || "").trim();
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(campaignId) || !campaignName || campaignName.length > 120 || /[\u0000-\u001f\u007f]/.test(campaignName)) {
    return json({ ok: false, error: "invalid_campaign_identity" }, 400, cors);
  }
  const machines = Array.isArray(body.machines) ? body.machines : [];
  if (!machines.length || machines.length > 20) return json({ ok: false, error: "invalid_campaign_machines" }, 400, cors);
  const publicBase = String(env.PUBLIC_BASE_URL || "").replace(/\/+$/, "");
  const normalizedMachines = [];
  const seenNumbers = new Set();
  const seenUrls = new Set();
  for (const machine of machines) {
    const number = Number(machine?.candidateNumber);
    const name = String(machine?.organisationName || "").trim();
    const publicUrl = String(machine?.publicUrl || "");
    let parsed;
    try { parsed = new URL(publicUrl); } catch { return json({ ok: false, error: "invalid_campaign_machine" }, 400, cors); }
    const prefix = `${publicBase}/crispy-bits/`;
    if (!Number.isInteger(number) || number < 1 || number > 999 || seenNumbers.has(number) || !name || name.length > 120 || /[\u0000-\u001f\u007f]/.test(name) || !publicUrl.startsWith(prefix) || parsed.protocol !== "https:" || !publicUrl.endsWith("/") || seenUrls.has(publicUrl)) {
      return json({ ok: false, error: "invalid_campaign_machine" }, 400, cors);
    }
    seenNumbers.add(number); seenUrls.add(publicUrl);
    normalizedMachines.push({ number, name, publicUrl });
  }
  normalizedMachines.sort((left, right) => left.number - right.number);
  const expectedIdempotency = await sha256Hex(`${campaignId}\n${normalizedMachines.map((item) => item.publicUrl).join("\n")}`);
  if (String(body.idempotencyKey || "") !== expectedIdempotency) return json({ ok: false, error: "invalid_campaign_idempotency" }, 400, cors);
  const allowedAttachments = new Set(["campaign.csv", "qr-sheet.pdf", "prospect-cards.zip", "qr-codes.zip"]);
  const requiredAttachments = new Set(["campaign.csv", "qr-sheet.pdf", "prospect-cards.zip"]);
  const attachments = Array.isArray(body.attachments) ? body.attachments : [];
  const names = new Set();
  let decodedBytes = 0;
  for (const attachment of attachments) {
    const filename = String(attachment?.filename || "");
    const content = String(attachment?.content || "");
    if (!allowedAttachments.has(filename) || names.has(filename) || !content || !/^[A-Za-z0-9+/]+={0,2}$/.test(content)) return json({ ok: false, error: "invalid_campaign_attachment" }, 400, cors);
    names.add(filename);
    decodedBytes += Math.floor(content.length * 3 / 4);
  }
  if ([...requiredAttachments].some((name) => !names.has(name)) || decodedBytes > 8 * 1024 * 1024) return json({ ok: false, error: "invalid_campaign_attachments" }, 400, cors);
  const recipient = safeRecipient(env.OWNER_EMAIL);
  if (!recipient) return json({ ok: false, error: "delivery_recipient_not_configured" }, 503, cors);
  const slug = `campaign-${campaignId.replaceAll("-", "")}`;
  const revision = expectedIdempotency.slice(0, 40);
  const existing = await env.DB.prepare("SELECT provider_id, status, created_at FROM deliveries WHERE slug = ?1 AND revision = ?2 AND recipient = ?3").bind(slug, revision, recipient).first();
  if (existing && existing.status === "sent") return json({ ok: true, duplicate: true, id: existing.provider_id, sentAt: existing.created_at }, 200, cors);
  const counts = body.counts && typeof body.counts === "object" ? body.counts : {};
  const safeCount = (key) => Math.max(0, Math.min(999, Number.parseInt(counts[key], 10) || 0));
  const subject = `CRISPY BITS — ${campaignName} — ${normalizedMachines.length} MACHINES`;
  const lines = [subject, "", `Approved: ${safeCount("approved")}`, `Built: ${safeCount("built")}`, `Published: ${normalizedMachines.length}`, `Failures: ${safeCount("failed")}`, "", ...normalizedMachines.map((item) => `${String(item.number).padStart(2, "0")}. ${item.name} — ${item.publicUrl}`)];
  await env.DB.prepare("INSERT OR IGNORE INTO deliveries (slug, revision, title, public_url, recipient, provider_id, status, idempotency_key, last_attempt_at) VALUES (?1, ?2, ?3, ?4, ?5, '', 'attempting', ?6, CURRENT_TIMESTAMP)").bind(slug, revision, campaignName, normalizedMachines[0].publicUrl, recipient, expectedIdempotency).run();
  const providerResponse = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: { authorization: `Bearer ${env.RESEND_API_KEY}`, "content-type": "application/json", "Idempotency-Key": expectedIdempotency },
    body: JSON.stringify({
      from: env.REPORT_FROM_EMAIL, to: [recipient], subject, text: lines.join("\n"),
      html: `<div style="font-family:Arial,sans-serif"><h1>${escapeHtml(subject)}</h1><p>Approved: ${safeCount("approved")}<br>Built: ${safeCount("built")}<br>Published: ${normalizedMachines.length}<br>Failures: ${safeCount("failed")}</p><ol>${normalizedMachines.map((item) => `<li><strong>${escapeHtml(item.name)}</strong> — <a href="${escapeHtml(item.publicUrl)}">${escapeHtml(item.publicUrl)}</a></li>`).join("")}</ol></div>`,
      attachments: attachments.map((attachment) => ({ filename: attachment.filename, content: attachment.content })),
    }),
  });
  if (!providerResponse.ok) {
    await env.DB.prepare("UPDATE deliveries SET status = 'failed', last_error = ?1, last_attempt_at = CURRENT_TIMESTAMP WHERE slug = ?2 AND revision = ?3 AND recipient = ?4").bind(`provider_${providerResponse.status}`, slug, revision, recipient).run();
    return json({ ok: false, error: "campaign_delivery_failed" }, providerResponse.status === 429 ? 429 : 502, cors);
  }
  let provider = {};
  try { provider = await providerResponse.json(); } catch { provider = {}; }
  const providerId = String(provider.id || "");
  await env.DB.prepare("UPDATE deliveries SET provider_id = ?1, status = 'sent', created_at = COALESCE(created_at, CURRENT_TIMESTAMP), last_attempt_at = CURRENT_TIMESTAMP, last_error = NULL WHERE slug = ?2 AND revision = ?3 AND recipient = ?4").bind(providerId, slug, revision, recipient).run();
  return json({ ok: true, id: providerId, sentAt: new Date().toISOString() }, 201, cors);
}

export {
  authenticate, canonicalRequest, constantTimeEqual, deliveryIdempotencyKey, handleBanjoSubmission,
  handleCampaignDelivery, handleDelivery, safeFirstName, safeRecipient, safeYouTubeVideo, verifyPublishedAssets,
};

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
    if (request.method === "GET" && url.pathname === "/") return json({ ok: true, service: "aggits-video-jukebox-delivery" }, 200, cors);
    if (request.method === "POST" && url.pathname === DELIVERY_PATH) return handleDelivery(request, env);
    if (request.method === "POST" && url.pathname === CAMPAIGN_DELIVERY_PATH) return handleCampaignDelivery(request, env);
    if (request.method === "POST" && url.pathname === BANJO_SUBMISSION_PATH) return handleBanjoSubmission(request, env);
    if (url.pathname === BANJO_SUBMISSION_PATH) return json({ ok: false, error: "method_not_allowed" }, 405, { ...cors, allow: "POST" });
    return json({ ok: false, error: "not_found" }, 404, cors);
  },
};

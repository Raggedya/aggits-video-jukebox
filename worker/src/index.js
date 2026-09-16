const json = (value, status = 200, headers = {}) => new Response(JSON.stringify(value), {
  status,
  headers: { "content-type": "application/json; charset=utf-8", ...headers },
});

const cors = {
  "access-control-allow-origin": "*",
  "access-control-allow-methods": "GET,POST,OPTIONS",
  "access-control-allow-headers": "content-type",
};

function safeSlug(value) {
  const slug = String(value || "").toLowerCase();
  return /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(slug) ? slug : "";
}

function asBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
  }
  return btoa(binary);
}

async function handleDelivery(request, env) {
  if (!env.RESEND_API_KEY) return json({ ok: false, error: "delivery_service_not_configured" }, 503, cors);
  let body;
  try { body = await request.json(); } catch { return json({ ok: false, error: "invalid_json" }, 400, cors); }
  const slug = safeSlug(body.slug);
  const revision = String(body.revision || "").trim();
  const requestedUrl = String(body.publicUrl || "").replace(/\/+$/, "") + "/";
  const expectedUrl = `${String(env.PUBLIC_BASE_URL).replace(/\/+$/, "")}/${slug}/`;
  if (!slug || !/^[0-9a-f]{40}$/i.test(revision) || requestedUrl !== expectedUrl) {
    return json({ ok: false, error: "invalid_publication" }, 400, cors);
  }

  const existing = await env.DB.prepare("SELECT provider_id FROM deliveries WHERE slug = ?1 AND revision = ?2").bind(slug, revision).first();
  if (existing) return json({ ok: true, duplicate: true, id: existing.provider_id }, 200, cors);

  const [machineResponse, qrResponse] = await Promise.all([
    fetch(`${expectedUrl}machine.json?revision=${encodeURIComponent(revision)}`, { cf: { cacheTtl: 0 } }),
    fetch(`${expectedUrl}qr-card.png?revision=${encodeURIComponent(revision)}`, { cf: { cacheTtl: 0 } }),
  ]);
  if (!machineResponse.ok || !qrResponse.ok) return json({ ok: false, error: "published_assets_not_ready" }, 409, cors);
  const machine = await machineResponse.json();
  if (machine.slug !== slug || !Array.isArray(machine.videos) || !machine.videos.length) {
    return json({ ok: false, error: "published_machine_failed_validation" }, 422, cors);
  }
  const title = String(machine.title || body.title || slug).slice(0, 150);
  const qr = asBase64(await qrResponse.arrayBuffer());
  const recipient = String(env.OWNER_EMAIL || "").trim().toLowerCase();
  if (!recipient) return json({ ok: false, error: "owner_email_not_configured" }, 503, cors);

  const response = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: { authorization: `Bearer ${env.RESEND_API_KEY}`, "content-type": "application/json" },
    body: JSON.stringify({
      from: env.REPORT_FROM_EMAIL,
      to: [recipient],
      subject: `${title} — AGGITS video jukebox is live`,
      html: `<div style="background:#080706;color:#f2e4bf;padding:32px;font-family:Arial,sans-serif"><div style="color:#b88a4f;font-family:Georgia,serif;font-size:28px;font-weight:bold">AGGITS VIDEO JUKEBOX</div><h1>${title.replace(/[<>&]/g, "")}</h1><p>Your video discovery machine is live.</p><p><a href="${expectedUrl}" style="display:inline-block;background:#b88a4f;color:#080706;padding:14px 22px;text-decoration:none;font-weight:bold">OPEN JUKEBOX</a></p><p>The titled QR card is attached.</p></div>`,
      attachments: [{ filename: `${slug}-aggits-qr.png`, content: qr }],
    }),
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) return json({ ok: false, error: result.message || `resend_${response.status}` }, response.status === 429 ? 429 : 502, cors);

  await env.DB.prepare("INSERT INTO deliveries (slug, revision, title, public_url, recipient, provider_id) VALUES (?1, ?2, ?3, ?4, ?5, ?6)")
    .bind(slug, revision, title, expectedUrl, recipient, String(result.id || "")).run();
  return json({ ok: true, id: result.id || null }, 201, cors);
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
    if (request.method === "GET" && url.pathname === "/") return json({ ok: true, service: "aggits-video-jukebox-delivery" }, 200, cors);
    if (request.method === "POST" && url.pathname === "/api/deliveries") return handleDelivery(request, env);
    return json({ ok: false, error: "not_found" }, 404, cors);
  },
};

import assert from "node:assert/strict";
import test from "node:test";

import {
  handleLoveMyLocalsEat,
  normaliseEatPlace,
  selectDiverseEatPlaces,
} from "../src/index.js";

const MACHINE_URL = "https://example.test/crispy-bits/bairnsdale/machine.json";

function machine(locations = ["Bairnsdale"]) {
  return {
    slug: "bairnsdale",
    projectType: "love_my_locals",
    loveMyLocalsConfig: { locations, resolvedGeography: "Victoria, Australia" },
  };
}

function place(id, name, primaryType = "restaurant", options = {}) {
  return {
    id,
    displayName: { text: name },
    primaryType,
    primaryTypeDisplayName: { text: options.typeLabel || primaryType.replaceAll("_", " ") },
    types: options.types || [primaryType, "food", "point_of_interest"],
    formattedAddress: `${name}, Bairnsdale VIC, Australia`,
    shortFormattedAddress: `${name}, Bairnsdale VIC`,
    addressComponents: [{ longText: options.locality || "Bairnsdale", types: ["locality"] }],
    businessStatus: options.businessStatus || "OPERATIONAL",
    rating: options.rating,
    userRatingCount: options.reviewCount,
    attributions: options.attributions || [],
  };
}

function request() {
  return new Request("https://worker.test/api/love-my-locals/eat?slug=bairnsdale");
}

function env() {
  return { GOOGLE_PLACES_API_KEY: "test-key", PUBLIC_BASE_URL: "https://example.test" };
}

async function withFetch(mock, callback) {
  const original = globalThis.fetch;
  globalThis.fetch = mock;
  try { return await callback(); } finally { globalThis.fetch = original; }
}

test("normalised EAT records include cafes restaurants pubs ratings and factual fields", () => {
  const now = "2026-09-27T00:00:00.000Z";
  const location = { name: "Bairnsdale" };
  const cafe = normaliseEatPlace(place("cafe-1", "Town Cafe", "cafe", { rating: 4.6, reviewCount: 128 }), location, now).item;
  const restaurant = normaliseEatPlace(place("restaurant-1", "Town Table", "restaurant"), location, now).item;
  const pub = normaliseEatPlace(place("pub-1", "Town Pub", "bar"), location, now).item;
  assert.equal(cafe.category, "Cafe");
  assert.equal(cafe.rating, 4.6);
  assert.equal(cafe.reviewCount, 128);
  assert.equal(cafe.image, "");
  assert.equal(cafe.source, "google-places-new");
  assert.equal(cafe.retrievedAt, now);
  assert.match(restaurant.category, /restaurant/i);
  assert.equal(pub.category, "Pub • Food & Drink");
});

test("inappropriate retail permanently closed malformed and externally attributed records are excluded", () => {
  const location = { name: "Bairnsdale" };
  const values = [
    place("shop", "Food Shop", "supermarket"),
    place("closed", "Closed Cafe", "cafe", { businessStatus: "CLOSED_PERMANENTLY" }),
    { id: "bad", primaryType: "restaurant" },
    place("attributed", "Attributed Cafe", "cafe", { attributions: [{ provider: "Other" }] }),
    place("outside", "Outside Cafe", "cafe", { locality: "Sale" }),
  ].map((value) => normaliseEatPlace(value, location, "now").rejected);
  assert.deepEqual(values, ["inappropriate_type", "permanently_closed", "malformed", "external_attribution_required", "outside_nominated_location"]);
});

test("selection deduplicates place IDs and names, caps nine, and mixes categories and locations", () => {
  const records = [];
  const categories = ["cafe", "restaurant", "pub", "bakery", "casual"];
  for (let index = 0; index < 15; index += 1) {
    records.push({
      sourceId: `id-${index}`, name: `Venue ${index}`, address: `Address ${index}`,
      matchedLocation: index % 2 ? "Box Hill" : "Box Hill North", categoryKey: categories[index % categories.length],
    });
  }
  records.push({ ...records[0] });
  const result = selectDiverseEatPlaces(records);
  assert.equal(result.selected.length, 9);
  assert.equal(result.duplicateCount, 1);
  assert.ok(new Set(result.selected.map((item) => item.categoryKey)).size > 2);
  assert.deepEqual(new Set(result.selected.map((item) => item.matchedLocation)), new Set(["Box Hill", "Box Hill North"]));
});

test("missing credential fails closed without contacting Google or fixtures", async () => {
  let called = false;
  await withFetch(async () => { called = true; throw new Error("unexpected"); }, async () => {
    const response = await handleLoveMyLocalsEat(request(), { PUBLIC_BASE_URL: "https://example.test" });
    assert.equal(response.status, 503);
    assert.equal((await response.json()).error, "eat_provider_not_configured");
  });
  assert.equal(called, false);
});

test("live endpoint validates the published machine and returns at most nine information-only places", async () => {
  const providerPlaces = [
    place("1", "Cafe One", "cafe", { rating: 4.5, reviewCount: 20 }),
    place("2", "Restaurant Two", "restaurant"),
    place("3", "Pub Three", "bar"),
    place("4", "Bakery Four", "bakery"),
    ...Array.from({ length: 12 }, (_, index) => place(`extra-${index}`, `Extra ${index}`, "restaurant")),
    place("closed", "Closed", "cafe", { businessStatus: "CLOSED_PERMANENTLY" }),
  ];
  await withFetch(async (url, options = {}) => {
    if (String(url) === MACHINE_URL) return new Response(JSON.stringify(machine()), { status: 200 });
    assert.equal(String(url), "https://places.googleapis.com/v1/places:searchText");
    assert.equal(options.headers["x-goog-api-key"], "test-key");
    assert.ok(options.headers["x-goog-fieldmask"].includes("places.rating"));
    assert.doesNotMatch(options.headers["x-goog-fieldmask"], /photos|websiteUri|googleMapsUri/);
    const body = JSON.parse(options.body);
    assert.match(body.textQuery, /Bairnsdale, Victoria, Australia/);
    return new Response(JSON.stringify({ places: providerPlaces }), { status: 200 });
  }, async () => {
    const response = await handleLoveMyLocalsEat(request(), env());
    assert.equal(response.status, 200);
    assert.equal(response.headers.get("cache-control"), "no-store");
    const payload = await response.json();
    assert.equal(payload.data.source, "google-places-new");
    assert.equal(payload.data.environment, "live");
    assert.equal(payload.data.attribution, "Google Maps");
    assert.equal(payload.data.items.length, 9);
    assert.equal(payload.diagnostics.rawCount, providerPlaces.length);
    assert.equal(payload.diagnostics.rawCount, payload.diagnostics.finalCount + payload.diagnostics.rejectedCount);
    assert.equal(payload.diagnostics.missingImageCount, 9);
    assert.ok(payload.diagnostics.rejectionReasons.permanently_closed >= 1);
    const encoded = JSON.stringify(payload.data.items).toLowerCase();
    for (const forbidden of ["url", "href", "book", "menu", "direction", "reserve"]) assert.doesNotMatch(encoded, new RegExp(forbidden));
  });
});

test("fewer than nine and missing rating/review/image fields remain omitted rather than fabricated", async () => {
  await withFetch(async (url) => String(url) === MACHINE_URL
    ? new Response(JSON.stringify(machine()), { status: 200 })
    : new Response(JSON.stringify({ places: [place("1", "Only Cafe", "cafe")] }), { status: 200 }), async () => {
    const payload = await (await handleLoveMyLocalsEat(request(), env())).json();
    assert.equal(payload.data.items.length, 1);
    assert.equal(payload.data.items[0].rating, null);
    assert.equal(payload.data.items[0].reviewCount, null);
    assert.equal(payload.data.items[0].image, "");
    assert.equal(payload.diagnostics.missingRatingCount, 1);
  });
});

test("three configured locations produce three provider searches and locality-balanced output", async () => {
  const locations = ["Box Hill", "Box Hill North", "Box Hill South"];
  let providerCalls = 0;
  await withFetch(async (url, options = {}) => {
    if (String(url) === MACHINE_URL) return new Response(JSON.stringify(machine(locations)), { status: 200 });
    providerCalls += 1;
    const query = JSON.parse(options.body).textQuery;
    const matched = [...locations].sort((left, right) => right.length - left.length).find((name) => query.includes(name)) || "Box Hill";
    return new Response(JSON.stringify({ places: [
      place(`${providerCalls}-cafe`, `${matched} Cafe`, "cafe", { locality: matched }),
      place(`${providerCalls}-pub`, `${matched} Pub`, "bar", { locality: matched }),
    ] }), { status: 200 });
  }, async () => {
    const payload = await (await handleLoveMyLocalsEat(request(), env())).json();
    assert.equal(providerCalls, 3);
    assert.equal(payload.data.items.length, 6);
    assert.deepEqual(new Set(payload.data.items.map((item) => item.locality)), new Set(locations));
  });
});

test("invalid credential quota malformed response timeout zero results and invalid machine fail safely", async (t) => {
  const cases = [
    ["invalid credential", new Response("{}", { status: 403 }), 503, "provider_request_failed"],
    ["quota", new Response("{}", { status: 429 }), 429, "provider_quota_exceeded"],
    ["malformed", new Response(JSON.stringify({ unexpected: [] }), { status: 200 }), 502, "malformed_provider_response"],
    ["zero", new Response(JSON.stringify({ places: [] }), { status: 200 }), 404, "no_suitable_places"],
  ];
  for (const [name, providerResponse, status, error] of cases) {
    await t.test(name, async () => withFetch(async (url) => String(url) === MACHINE_URL
      ? new Response(JSON.stringify(machine()), { status: 200 }) : providerResponse.clone(), async () => {
      const response = await handleLoveMyLocalsEat(request(), env());
      assert.equal(response.status, status);
      assert.equal((await response.json()).error, error);
    }));
  }
  await t.test("timeout", async () => withFetch(async (url) => {
    if (String(url) === MACHINE_URL) return new Response(JSON.stringify(machine()), { status: 200 });
    throw new DOMException("timeout", "AbortError");
  }, async () => {
    const response = await handleLoveMyLocalsEat(request(), env());
    assert.equal(response.status, 504);
    assert.equal((await response.json()).error, "provider_timeout");
  }));
  await t.test("invalid machine", async () => withFetch(async () => new Response(JSON.stringify({ ...machine(), projectType: "business" }), { status: 200 }), async () => {
    const response = await handleLoveMyLocalsEat(request(), env());
    assert.equal(response.status, 404);
    assert.equal((await response.json()).error, "invalid_machine");
  }));
});

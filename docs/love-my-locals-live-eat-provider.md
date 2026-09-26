# Love My Locals — Live EAT provider

Milestone 2A uses the official Google Places API (New) Text Search web service through the existing Cloudflare Worker. The browser never receives the provider credential.

## Required configuration

Enable **Places API (New)** for the Google Cloud project, create a restricted server-side API key, and configure it only as a Worker secret:

```powershell
wrangler secret put GOOGLE_PLACES_API_KEY
```

Do not add the value to `wrangler.jsonc`, source code, project JSON, generated machine files, Git, or browser JavaScript.

The Worker endpoint is:

```text
GET /api/love-my-locals/eat?slug=<published-love-my-locals-slug>
```

The Worker validates the slug against the published Love My Locals `machine.json`, obtains its configured location list, and performs at most one Text Search request per configured location. Arbitrary client-supplied search text is not accepted.

## Provider request

The adapter calls `POST https://places.googleapis.com/v1/places:searchText` with a restricted field mask. It does not request website URLs, Google Maps URLs, reviews, photos, telephone numbers, menus, booking data, or directions.

Requested fields are limited to place identity, display name, structured type, address/locality, business status, rating, rating count, and provider attribution metadata.

## Attribution and photos

Live EAT content is labelled `Google Maps` inside the utility chamber, using the required unmodified text treatment. Google place photos are deliberately disabled in Milestone 2A because the approved Crispy Bits cards prohibit external source links, while Google's photo policy requires source-photo access and author attribution in applicable cases. Cards therefore use the neutral Love My Locals placeholder treatment.

Provider records carrying additional third-party attribution requirements are excluded rather than displayed without their required attribution.

## Freshness and failure behaviour

Google Places content is not stored in project data, generated static machine files, D1, or the Worker cache. The browser retains one successful normalised response only in memory for the provider-supplied `refreshAfter` interval (15 minutes), preventing repeat calls during card rendering while avoiding a permanently frozen static snapshot.

If the secret is missing, the provider rejects the request, quota is exhausted, the request times out, the published project is invalid, or no suitable venue remains after filtering, the public machine displays the clean EAT unavailable state. It never falls back to development fixtures in live mode.

Development EAT fixtures remain available only when `LoveMyLocalsConfig.utility_data_mode` is explicitly set to `development-fixture`. The default is `live`.

## Provider documentation

- Google Places API (New) Text Search: https://developers.google.com/maps/documentation/places/web-service/text-search
- Field masks: https://developers.google.com/maps/documentation/places/web-service/choose-fields
- Places policies and attribution: https://developers.google.com/maps/documentation/places/web-service/policies
- Place Photos policy: https://developers.google.com/maps/documentation/places/web-service/place-photos

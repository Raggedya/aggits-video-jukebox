# Doug Anthony All Stars statistics

DAAS retains its existing five event types. All other machine types send only
`spin`, scoped by their project slug, on the production GitHub Pages origin.
Local previews never send events. No machine mechanics change. Football counts
spins for the whole machine, not separately per club. Slugs are project identities
and must remain unique across the root and `crispy-bits` publication namespaces.

- `page_view`: page load, including refreshes. Not unique people.
- Distinct `session_id`: browser-tab sessions, not unique people/devices. Reloads
  normally reuse the tab ID; blocked storage creates a fresh ID on each load.
- `spin`: machine accepted a spin (entered SPINNING), including the lever.
- `play_click`: enabled Play button pressed, not proof of successful playback.
- `share_click`: enabled Share button pressed, not proof sharing completed.
- `spotify_click`: enabled primary Spotify CTA pressed, not proof of a listen.

Events store a random event UUID, tab-session UUID, machine slug, event name,
optional video ID, and a server UTC timestamp. No IP, email, full URL, referrer,
browser fingerprint or third-party analytics. No cookies. Cloudflare may retain
its own operational logs separately. Events are retained until owner deletion.
Ad blockers/offline use can undercount. Public collectors can be spoofed; strict
origin/field checks, UUID deduplication and 60/session/minute plus 600 total/minute
limits (plus 6,000 across all machines/minute) reduce accidental duplication/abuse
but are not proof of human activity. Valid slugs are not authenticated publishers;
the public counter is approximate, not an audited business metric.

Collector: `worker/stats.wrangler.jsonc` (separate from the delivery Worker).
Database: existing `aggits-video-jukebox-production`, additive table
`machine_statistics`. Raw public reports are unavailable. `GET /api/spins?slug=...`
returns only `{count: number}` for that machine's recorded spin events, cached for
30 seconds in the Worker and browser. It exposes no sessions or other metrics.
The UI reads once on load and again only after an accepted spin; there is no
polling or optimistic increment. Failures hide the counter. Totals can lag by
30 seconds. The tooltip/accessibility label clarifies when tracking began.

Authenticated report command (substitute the installed Wrangler command):

    wrangler d1 execute aggits-video-jukebox-production --remote --config worker/stats.wrangler.jsonc --command "SELECT event_name, COUNT(*) AS total FROM machine_statistics WHERE slug='doug-anthony-allstars' GROUP BY event_name; SELECT COUNT(DISTINCT session_id) AS tab_sessions, MIN(received_at) AS first_event_utc, MAX(received_at) AS latest_event_utc FROM machine_statistics WHERE slug='doug-anthony-allstars';"

For date reports, convert Australia/Sydney midnight boundaries to UTC (respecting
daylight saving), then filter `received_at >= start AND received_at < end`.
This is forward-only measurement, not reconstructed historical activity.

SiteBuilder includes the script for every machine on future source builds. The Pages
workflow also runs `tools/inject_daas_statistics.py` before uploading its artifact,
so republishing with an older desktop EXE retains tracking. It includes all player
pages at `public/<slug>/` and `public/crispy-bits/<slug>/`, including standalone
Trivia, but skips non-player pages and nested review directories. Injection is
idempotent. No new EXE is needed for the published counter.

## Local-only counter implementation / future deployment order

Nothing in this implementation deploys automatically. On separate approval:

1. Back up D1 and verify the existing schema/migration ledger. Migration 0004 was
   originally applied manually; do not replay unrelated migrations blindly.
2. Apply 0005 once to widen machine identities, preserving all DAAS rows. Verify
   DAAS counts before/after. SQLite local migration tests exercise preservation.
3. Deploy only the statistics Worker using `worker/stats.wrangler.jsonc`, not the
   delivery Worker. Verify aggregate reads and existing event ingestion.
4. Release the collector plus Pages injection/workflow changes to the approved
   Pages source and run its deployment. Do not include unrelated dirty work.
5. Verify real mobile/desktop counts. Remove only explicitly identified QA events.

DAAS history starts 18 October 2026. Other machines start only when enabled;
historical spins cannot be recovered. No customer project or EXE changes required.

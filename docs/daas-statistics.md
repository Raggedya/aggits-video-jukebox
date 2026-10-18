# Doug Anthony All Stars statistics

Only `doug-anthony-allstars` on the production GitHub Pages origin is tracked.
Local previews and other machines do not send events. No machine mechanics change.

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
limits reduce accidental duplication/abuse but are not proof of human activity.

Collector: `worker/stats.wrangler.jsonc` (separate from the delivery Worker).
Database: existing `aggits-video-jukebox-production`, additive table
`machine_statistics`. Public reports are deliberately unavailable.

Authenticated report command (substitute the installed Wrangler command):

    wrangler d1 execute aggits-video-jukebox-production --remote --config worker/stats.wrangler.jsonc --command "SELECT event_name, COUNT(*) AS total FROM machine_statistics WHERE slug='doug-anthony-allstars' GROUP BY event_name; SELECT COUNT(DISTINCT session_id) AS tab_sessions, MIN(received_at) AS first_event_utc, MAX(received_at) AS latest_event_utc FROM machine_statistics WHERE slug='doug-anthony-allstars';"

For date reports, convert Australia/Sydney midnight boundaries to UTC (respecting
daylight saving), then filter `received_at >= start AND received_at < end`.
This is forward-only measurement, not reconstructed historical activity.

SiteBuilder includes the script for this slug on future source builds. The Pages
workflow also runs `tools/inject_daas_statistics.py` before uploading its artifact,
so republishing with an older desktop EXE retains tracking. It touches only this
slug and is idempotent. No new EXE is needed for this statistics-only change.

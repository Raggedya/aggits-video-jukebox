-- Additive only. No changes to deliveries or existing security tables.
CREATE TABLE IF NOT EXISTS machine_statistics (
  event_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  slug TEXT NOT NULL CHECK(slug = 'doug-anthony-allstars'),
  event_name TEXT NOT NULL CHECK(event_name IN ('page_view','spin','play_click','share_click','spotify_click')),
  video_id TEXT NOT NULL DEFAULT '',
  received_at INTEGER NOT NULL DEFAULT (unixepoch())
);
CREATE INDEX IF NOT EXISTS machine_statistics_time ON machine_statistics(slug, received_at);
CREATE INDEX IF NOT EXISTS machine_statistics_session ON machine_statistics(session_id, received_at);

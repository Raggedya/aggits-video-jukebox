-- Widen event names only. Preserve every historical UUID, session, video and timestamp.
-- Apply this migration alone after backing up machine_statistics; do not replay 0001-0005.
CREATE TABLE machine_statistics_detailed (
  event_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  slug TEXT NOT NULL CHECK(length(slug) BETWEEN 1 AND 100),
  event_name TEXT NOT NULL CHECK(event_name IN (
    'page_view','spin','play_click','share_click','spotify_click',
    'cta_click','cta2_click','contact_click','membership_click')),
  video_id TEXT NOT NULL DEFAULT '',
  received_at INTEGER NOT NULL DEFAULT (unixepoch())
);
INSERT INTO machine_statistics_detailed SELECT * FROM machine_statistics;
DROP TABLE machine_statistics;
ALTER TABLE machine_statistics_detailed RENAME TO machine_statistics;
CREATE INDEX machine_statistics_time ON machine_statistics(slug,received_at);
CREATE INDEX machine_statistics_session ON machine_statistics(session_id,received_at);
CREATE INDEX machine_statistics_spins ON machine_statistics(slug,event_name);
CREATE INDEX machine_statistics_global_time ON machine_statistics(received_at);

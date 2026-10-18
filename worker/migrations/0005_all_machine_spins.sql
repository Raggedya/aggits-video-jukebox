-- Preserve all existing DAAS records while relaxing the former single-machine constraint.
-- Apply once through D1 migrations. No delivery/security tables are changed.
CREATE TABLE machine_statistics_expanded (
  event_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  slug TEXT NOT NULL CHECK(length(slug) BETWEEN 1 AND 100),
  event_name TEXT NOT NULL CHECK(event_name IN ('page_view','spin','play_click','share_click','spotify_click')),
  video_id TEXT NOT NULL DEFAULT '',
  received_at INTEGER NOT NULL DEFAULT (unixepoch())
);
INSERT INTO machine_statistics_expanded SELECT * FROM machine_statistics;
DROP TABLE machine_statistics;
ALTER TABLE machine_statistics_expanded RENAME TO machine_statistics;
CREATE INDEX machine_statistics_time ON machine_statistics(slug,received_at);
CREATE INDEX machine_statistics_session ON machine_statistics(session_id,received_at);
CREATE INDEX machine_statistics_spins ON machine_statistics(slug,event_name);
CREATE INDEX machine_statistics_global_time ON machine_statistics(received_at);

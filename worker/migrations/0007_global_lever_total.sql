-- Derived projection of the EXISTING deduplicated spin event stream.
-- Run only after a verified backup and explicit production approval.
-- Applying this schema locally never changes production.
CREATE TABLE IF NOT EXISTS network_lever_total (
  singleton INTEGER PRIMARY KEY CHECK(singleton=1),
  total INTEGER NOT NULL CHECK(total>=0),
  since INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE TRIGGER IF NOT EXISTS network_lever_accepted_insert
AFTER INSERT ON machine_statistics WHEN NEW.event_name='spin'
BEGIN
  UPDATE network_lever_total SET total=total+1,updated_at=unixepoch() WHERE singleton=1;
END;
-- Install the trigger BEFORE the atomic backfill. Until the singleton exists,
-- an incoming event is still included by the subsequent COUNT; afterwards the
-- same transaction's trigger increments it. No install-time gap or double count.
INSERT OR IGNORE INTO network_lever_total(singleton,total,since,updated_at)
SELECT 1,COUNT(*),COALESCE(MIN(received_at),unixepoch()),unixepoch()
FROM machine_statistics WHERE event_name='spin';
-- No DELETE trigger: removing a listing, unpublishing or later event retention
-- must never erase accepted historical contributions. Do not reset this row.

CREATE TABLE IF NOT EXISTS banjo_submission_guards (
  guard_key TEXT PRIMARY KEY,
  guard_type TEXT NOT NULL CHECK (guard_type IN ('rate', 'duplicate')),
  count INTEGER NOT NULL DEFAULT 1,
  expires_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS banjo_submission_guards_expiry
  ON banjo_submission_guards(expires_at);

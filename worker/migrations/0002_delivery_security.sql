CREATE TABLE IF NOT EXISTS delivery_nonces (
  nonce TEXT PRIMARY KEY,
  expires_at INTEGER NOT NULL
);

CREATE TABLE deliveries_v2 (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT NOT NULL,
  revision TEXT NOT NULL,
  title TEXT NOT NULL,
  public_url TEXT NOT NULL,
  recipient TEXT NOT NULL,
  provider_id TEXT,
  status TEXT NOT NULL DEFAULT 'sent',
  idempotency_key TEXT NOT NULL DEFAULT '',
  last_attempt_at TEXT,
  last_error TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(slug, revision, recipient)
);

INSERT OR IGNORE INTO deliveries_v2 (
  slug, revision, title, public_url, recipient, provider_id, status,
  idempotency_key, last_attempt_at, created_at
)
SELECT slug, revision, title, public_url, recipient, provider_id, 'sent',
       slug || ':' || revision || ':' || recipient, created_at, created_at
FROM deliveries;

DROP TABLE deliveries;
ALTER TABLE deliveries_v2 RENAME TO deliveries;

CREATE INDEX IF NOT EXISTS delivery_nonces_expiry ON delivery_nonces(expires_at);

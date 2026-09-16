CREATE TABLE IF NOT EXISTS deliveries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT NOT NULL,
  revision TEXT NOT NULL,
  title TEXT NOT NULL,
  public_url TEXT NOT NULL,
  recipient TEXT NOT NULL,
  provider_id TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(slug, revision)
);

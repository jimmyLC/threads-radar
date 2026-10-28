PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS keywords (
  id      INTEGER PRIMARY KEY,
  term    TEXT NOT NULL UNIQUE,
  enabled INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS posts (
  id             TEXT PRIMARY KEY,
  author         TEXT NOT NULL,
  text           TEXT NOT NULL,
  permalink      TEXT NOT NULL,
  posted_at      TEXT NOT NULL,
  is_reply       INTEGER NOT NULL DEFAULT 0,
  topic_tag      TEXT,
  summary        TEXT,
  first_seen_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mentions (
  post_id      TEXT NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
  keyword_id   INTEGER NOT NULL REFERENCES keywords(id) ON DELETE CASCADE,
  is_top       INTEGER NOT NULL DEFAULT 0,
  window_hours INTEGER NOT NULL DEFAULT 24,
  seen_at      TEXT NOT NULL,
  PRIMARY KEY (post_id, keyword_id)
);

CREATE TABLE IF NOT EXISTS runs (
  id          INTEGER PRIMARY KEY,
  started_at  TEXT NOT NULL,
  finished_at TEXT,
  status      TEXT NOT NULL,
  detail      TEXT
);

CREATE TABLE IF NOT EXISTS settings (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_posts_posted_at  ON posts(posted_at);
CREATE INDEX IF NOT EXISTS idx_mentions_kw_seen ON mentions(keyword_id, seen_at);
CREATE INDEX IF NOT EXISTS idx_mentions_post    ON mentions(post_id);

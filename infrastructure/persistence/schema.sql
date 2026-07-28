CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    rating INTEGER NOT NULL DEFAULT 1200,
    created_at TEXT NOT NULL
);

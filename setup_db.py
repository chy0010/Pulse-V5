import sqlite3

DB_PATH = "marketpulse_v5.db"


def setup():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT UNIQUE,
            channel_handle TEXT,
            channel_name TEXT,
            video_title TEXT,
            published_at TEXT,
            source_tier TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT,
            comment_id TEXT UNIQUE,
            text TEXT,
            author TEXT,
            like_count INTEGER,
            reply_count INTEGER,
            is_reply INTEGER DEFAULT 0,
            parent_comment_id TEXT,
            published_at TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (video_id) REFERENCES videos(video_id)
        )
    """)

    conn.commit()
    conn.close()
    print("Database ready:", DB_PATH)


if __name__ == "__main__":
    setup()

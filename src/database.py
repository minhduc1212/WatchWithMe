import sqlite3
from src.config import DB_PATH, logger

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    logger.info("Initializing SQLite database tables...")
    conn = get_db()
    cursor = conn.cursor()
    
    # Create movies table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS movies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT,
        duration INTEGER DEFAULT 0,
        playlist_url TEXT,
        thumbnail_url TEXT,
        status TEXT DEFAULT 'processing',
        error_message TEXT,
        progress INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    
    # Create subtitles table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS subtitles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        movie_id INTEGER,
        language TEXT NOT NULL,
        vtt_url TEXT NOT NULL,
        FOREIGN KEY(movie_id) REFERENCES movies(id) ON DELETE CASCADE
    );
    """)
    
    # Check for progress column if DB existed without it
    cursor.execute("PRAGMA table_info(movies)")
    columns = [row[1] for row in cursor.fetchall()]
    if "progress" not in columns:
        logger.info("Database migration: Adding 'progress' column to movies table...")
        cursor.execute("ALTER TABLE movies ADD COLUMN progress INTEGER DEFAULT 0")
        
    conn.commit()
    conn.close()
    logger.info("Database tables initialized successfully.")

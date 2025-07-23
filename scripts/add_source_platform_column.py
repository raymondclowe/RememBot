import sqlite3
from pathlib import Path

def add_source_platform_column(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    # Check if column already exists
    cursor.execute("PRAGMA table_info(content_items)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'source_platform' not in columns:
        cursor.execute("ALTER TABLE content_items ADD COLUMN source_platform TEXT")
        print("Added 'source_platform' column to content_items table.")
    else:
        print("'source_platform' column already exists.")
    conn.commit()
    conn.close()

if __name__ == "__main__":
    db_path = str(Path.home() / ".remembot" / "remembot.db")
    add_source_platform_column(db_path)
    print("Migration complete.")

#!/usr/bin/env python3
import os
import sqlite3

def main():
    # 1) Compute path to your app’s DB
    here    = os.path.dirname(__file__)
    db_path = os.path.join(here, "app", "db.sqlite3")   # <- same file your Flask app uses
    if not os.path.exists(db_path):
        print("❌ DB not found at", db_path)
        return

    # 2) Connect & delete all shifts
    conn   = sqlite3.connect(db_path)
    cur    = conn.cursor()
    cur.execute("DELETE FROM shifts;")
    deleted = cur.rowcount
    conn.commit()
    conn.close()

    print(f"✅ Deleted {deleted} rows from shifts in {db_path}")

if __name__ == "__main__":
    main()

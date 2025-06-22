'''
    I did not write this source file, passed to chat-gpt then scanned/corrected errors 
'''

import os
import sqlite3
import subprocess
import pytest
from datetime import date

BIN_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__),
                 os.pardir,
                 "app", "scripts", "fill_shifts")
)

CREATE_SCHEMA = """
CREATE TABLE users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT UNIQUE NOT NULL,
  user_id TEXT UNIQUE NOT NULL,
  shifts_worked INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'GENERAL'
);

CREATE TABLE shifts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  week TEXT NOT NULL,
  slot INTEGER NOT NULL,
  location TEXT NOT NULL,
  UNIQUE(week, slot, location)
);
"""

SEED_USERS = [
    ("alice@g.edu", "Alice", "GENERAL"),
    ("bob@g.edu",   "Bob",   "GENERAL"),
    ("carol@g.edu", "Carol", "BAR"),
    ("dan@g.edu",   "Dan",   "BAR"),
]

@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test.sqlite3"
    conn = sqlite3.connect(db_file)
    conn.executescript(CREATE_SCHEMA)
    cur = conn.cursor()
    for email, uid, status in SEED_USERS:
        cur.execute(
            "INSERT INTO users (email, user_id, status) VALUES (?, ?, ?)",
            (email, uid, status)
        )
    conn.commit()
    conn.close()
    return str(db_file)

def run_fill(db_path, week_iso):
    res = subprocess.run(
        [BIN_PATH, db_path, week_iso],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    assert res.returncode == 0, f"fill_shifts failed:\n{res.stderr}"
    return res.stdout

def query_count(db_path, week, *, loc_like=None, slots=None):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    q = "SELECT COUNT(*) FROM shifts WHERE week = ?"
    args = [week]
    if loc_like:
        q += " AND location LIKE ?"
        args.append(loc_like)
    if slots:
        q += " AND slot IN ({})".format(",".join("?"*len(slots)))
        args.extend(slots)
    cur.execute(q, args)
    n, = cur.fetchone()
    conn.close()
    return n

def test_capacity_and_bar_exclusions(temp_db):
    week = date.today().isoformat()
    # run it once
    run_fill(temp_db, week)

    # total shifts == users * 2 picks each
    total = query_count(temp_db, week)
    assert total == len(SEED_USERS) * 2

    # Bar1/Bar2 in early slots 44 & 45 must stay empty
    assert query_count(temp_db, week, loc_like="Bar%", slots=[44,45]) == 0

    # But Bar1/Bar2 in later slots should have some assignments
    assert query_count(temp_db, week, loc_like="Bar%", slots=[46,47,0,1]) > 0

def test_idempotent_runs(temp_db):
    week = date.today().isoformat()
    run_fill(temp_db, week)
    before = query_count(temp_db, week)
    run_fill(temp_db, week)
    after = query_count(temp_db, week)
    assert before == after, "Running fill_shifts twice should not change the manifest"

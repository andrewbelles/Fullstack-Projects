import os
import subprocess
import pytest
import psycopg2
from datetime import date

# Path to your C++ binary (no more sqlite path!)
BIN_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__),
                 os.pardir,
                 "app", "scripts", "fill_shifts")
)

# Postgres connection info from CI environment
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_NAME = os.getenv("DB_NAME")
DB_HOST = "127.0.0.1"
DB_PORT = 5432

# Build a libpq URL for psycopg2 and pqxx alike
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# The same schema you had in SQLite, now in Postgres DDL
CREATE_SCHEMA = """
CREATE TABLE users (
  id SERIAL PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  user_id TEXT UNIQUE NOT NULL,
  status TEXT NOT NULL DEFAULT 'GENERAL'
);

CREATE TABLE shifts (
  id SERIAL PRIMARY KEY,
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

@pytest.fixture(scope="session")
def pg_conn():
    """Create a psycopg2 connection to the test database."""
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    yield conn
    conn.close()

@pytest.fixture(autouse=True)
def reset_schema(pg_conn):
    """
    Before each test, drop & recreate public schema,
    then apply CREATE_SCHEMA and seed users.
    """
    cur = pg_conn.cursor()
    # Drop everything
    cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    # Rebuild tables
    cur.execute(CREATE_SCHEMA)
    # Seed users
    for email, uid, status in SEED_USERS:
        cur.execute(
            "INSERT INTO users (email, user_id, status) VALUES (%s, %s, %s)",
            (email, uid, status)
        )
    cur.close()
    yield
    # (schema will be reset at next test)

def run_fill(week_iso):
    """Run the C++ binary against Postgres via DATABASE_URL."""
    env = os.environ.copy()
    env["DATABASE_URL"] = DATABASE_URL
    # binary now only takes the week string
    res = subprocess.run(
        [BIN_PATH, week_iso],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env
    )
    assert res.returncode == 0, f"fill_shifts failed:\n{res.stderr}"
    return res.stdout

def query_count(pg_conn, week, *, loc_like=None, slots=None):
    """
    Count rows in shifts for the given week.
    Optionally filter by location LIKE and slot IN.
    """
    cur = pg_conn.cursor()
    q = "SELECT COUNT(*) FROM shifts WHERE week = %s"
    args = [week]
    if loc_like:
        q += " AND location LIKE %s"
        args.append(loc_like)
    if slots:
        placeholders = ",".join("%s" for _ in slots)
        q += f" AND slot IN ({placeholders})"
        args.extend(slots)
    cur.execute(q, args)
    (n,) = cur.fetchone()
    cur.close()
    return n

def test_capacity_and_bar_exclusions(pg_conn):
    week = date.today().isoformat()

    # run it once
    run_fill(week)

    # total shifts == users * 2 picks each
    total = query_count(pg_conn, week)
    assert total == len(SEED_USERS) * 2

    # Bar1/Bar2 in early slots 44 & 45 must stay empty
    assert query_count(pg_conn, week, loc_like="Bar%", slots=[44,45]) == 0

    # But Bar1/Bar2 in later slots should have some assignments
    assert query_count(pg_conn, week, loc_like="Bar%", slots=[46,47,0,1]) > 0

def test_idempotent_runs(pg_conn):
    week = date.today().isoformat()
    run_fill(week)
    before = query_count(pg_conn, week)
    run_fill(week)
    after = query_count(pg_conn, week)
    assert before == after, "Running fill_shifts twice should not change the manifest"

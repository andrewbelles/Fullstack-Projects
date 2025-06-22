import os
import pytest
from datetime import date
from freezegun import freeze_time
from dotenv import load_dotenv

from app import create_app, db
from app.routes import week_start
from app.models import User, Shift

load_dotenv()
TEST_USER = os.getenv("TEST_USER")

@pytest.fixture
def app():
    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False})
    with app.app_context():
        db.create_all()
        # insert the TEST_USER record so login_as can find it
        u = User(email=TEST_USER, shifts_worked=0, status="GENERAL")
        db.session.add(u)
        db.session.commit()
        yield app
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def login_as(client):
    def _login(email):
        user = User.query.filter_by(email=email).first()
        assert user, f"test fixture error: no user {email!r}"
        with client.session_transaction() as sess:
            sess["user"] = {
                "db_id": user.id,
                "email": user.email,
                "sub": user.id,
                "name": user.user_id,
                "status": user.status
            }
    return _login

def seed_shifts_for_week(week):
    s = Shift(user_id=1, week=week, slot=10, location="Front1")
    db.session.add(s)
    db.session.commit()

def get_shifts_for_today(client):
    resp = client.get("/api/shifts")
    assert resp.status_code == 200
    return resp.get_json()

def test_same_manifest_mon_wed(client, login_as):
    week = week_start(date(2025, 6, 16))
    seed_shifts_for_week(week)

    # Monday
    with freeze_time("2025-06-16 09:00:00"):
        login_as(TEST_USER)
        mon = get_shifts_for_today(client)

    # Wednesday
    with freeze_time("2025-06-18 14:00:00"):
        login_as(TEST_USER)
        wed = get_shifts_for_today(client)

    assert mon == wed
    assert mon == [{
      "week": week.isoformat(),
      "slot":  10,
      "location": "Front1",
      "user_id":  1
    }]

def test_rolls_over_on_sunday(client, login_as):
    week1 = week_start(date(2025, 6, 15))
    week2 = week_start(date(2025, 6, 22))
    seed_shifts_for_week(week1)
    seed_shifts_for_week(week2)

    with freeze_time("2025-06-21 23:59:59"):
        login_as(TEST_USER)
        sat = get_shifts_for_today(client)

    with freeze_time("2025-06-22 00:00:01"):
        login_as(TEST_USER)
        sun = get_shifts_for_today(client)

    assert sat != sun
    assert sat[0]["week"] == week1.isoformat()
    assert sun[0]["week"] == week2.isoformat()

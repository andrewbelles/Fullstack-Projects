import pytest
from freezegun import freeze_time
from datetime import date

from app import create_app, db
from app.models import User, Shift
from app.routes import FIRST_SLOT, LAST_SLOT, TOTAL_SLOTS, LOCATIONS
from fill_shifts import fill_unassigned_shifts_for_week

@pytest.fixture
def app():
    # Configure a test app with in-memory SQLite
    app = create_app()
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

def test_scheduler_fills_missing_shifts(app):
    # Create two sample users
    with app.app_context():
        user1 = User(email='u1@dartmouth.edu', sub='sub1', name='User One', user_id='u1')
        user2 = User(email='u2@dartmouth.edu', sub='sub2', name='User Two', user_id='u2')
        db.session.add_all([user1, user2])
        db.session.commit()

        # Use a Wednesday before Thursday
        week_date = date(2025, 6, 18)
        # Prefill two shifts manually
        s1 = Shift(user_id=user1.id, week=week_date, slot=FIRST_SLOT, location=LOCATIONS[0])
        s2 = Shift(user_id=user2.id, week=week_date, slot=FIRST_SLOT+1, location=LOCATIONS[1])
        db.session.add_all([s1, s2])
        db.session.commit()
        assert Shift.query.filter_by(week=week_date).count() == 2

    # Advance to Thursday and trigger the fill
    with freeze_time("2025-06-19"):
        fill_unassigned_shifts_for_week(week_date)

    # Verify that all slots for that week are now filled
    with app.app_context():
        total = Shift.query.filter_by(week=week_date).count()
        expected_slots = list(range(FIRST_SLOT, TOTAL_SLOTS)) + list(range(0, LAST_SLOT+1))
        expected_total = len(expected_slots) * len(LOCATIONS)
        assert total == expected_total, f"Expected {expected_total} shifts, got {total}"

        # Ensure there are no missing (slot,location) pairs
        filled = {(s.slot, s.location) for s in Shift.query.filter_by(week=week_date)}
        missing = [
            (slot, loc)
            for slot in expected_slots
            for loc in LOCATIONS
            if (slot, loc) not in filled
        ]
        assert missing == [], f"Missing slots: {missing}"

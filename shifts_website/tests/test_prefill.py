import pytest, re
from datetime import date 
from app import create_app, db
from app.models import User, Shift 

@pytest.fixture
def app():
    app = create_app()
    app.config.update({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///db.sqlite3"
    })
    with app.app_context():
        yield app

@pytest.fixture 
def client(app):
    return app.test_client()

def test_prefill_from_static_db(client, app):
    with app.app_context():
        users = User.query.order_by(User.id).all()
        assert len(users) >= 4, "Expected at least 4 users!"

        u1, u2, u3, u4 = users[:4]

        u3_email = u3.email
        u3_id    = u3.id
        u1_disp  = u1.user_id
        u2_disp  = u2.user_id
        u3_disp  = u3.user_id
        u4_disp  = u4.user_id

        today = date.today()

        Shift.query.filter_by(week=today).delete()
        db.session.commit()

        shifts = [
            Shift(user_id=u1.id, week=today, slot=47, location="Front1"),
            Shift(user_id=u1.id, week=today, slot=2, location="Runner"),
            Shift(user_id=u2.id, week=today, slot=1, location="Side"),
            Shift(user_id=u2.id, week=today, slot=3, location="Back")
        ]

        db.session.add_all(shifts)
        db.session.commit()

    with client.session_transaction() as session:
        session["user"] = {"email": u3_email, "sub": u3_id}

    resp = client.get("/")
    html = resp.get_data(as_text=True)
    print(html)

    def count_inactive(display_name):
        pattern = re.compile(
            rf'<div\s+class="slot inactive"[^>]*>\s*{re.escape(display_name)}\s*</div>',
            re.IGNORECASE
        )
        return len(pattern.findall(html))

    assert resp.status_code == 200
    assert count_inactive(u1_disp) == 2, f"Expected 2 occurences of {u1_disp!r}"
    assert count_inactive(u2_disp) == 2, f"Expected 2 occurences of {u2_disp!r}"
    
    assert count_inactive(u3_disp) == 0 
    assert count_inactive(u4_disp) == 0

import pytest, os 
from dotenv import load_dotenv
from app import create_app, db 
from app.models import User, Shift 
from datetime import date

load_dotenv()
TEST_USER = os.getenv("TEST_USER")

@pytest.fixture 
def app():
    app = create_app({
        "TESTING": True, 
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory",
        "SQLALCHEMY_TRACK_MODIFICATIONS": False
    })

    with app.app_context():
        db.drop_all()
        db.create_all()
        yield app 

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture 
def runner(app):
    return app.test_cli_runner()

@pytest.fixture
def login_as(client):
    def _login(email: str = TEST_USER):
        user = User.query.filter_by(email=email).first()

        if user is None:
            user = User(email=email, shifts_worked=0, status="GENERAL")
            db.session.add(user)
            db.session.commit()

        with client.session_transaction() as sess:
            sess["user"] = {"db_id": user.id, "status": user.status}
    return _login

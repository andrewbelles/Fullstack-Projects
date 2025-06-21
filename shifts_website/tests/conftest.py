import pytest 
from app import create_app, db 
from app.models import User, Shift 
from datetime import date

@pytest.fixture 
def app():
    app = create_app()
    app.config.update({
        "TESTING": True, 
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory"
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
def login_as(client, app):

    def _login(email):
        user = User.query.filter_by(email=email).first()
        if not user: 
            raise ValueError(f"No user with email {email!r}")
        with client.session_transaction() as session: 
            session["user"] = {"email": user.email, "sub": user.id}

    return _login

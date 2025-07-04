import os
from dotenv import load_dotenv
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from authlib.integrations.flask_client import OAuth

load_dotenv()

oauth = OAuth()
db    = SQLAlchemy()

def create_app(test_config: dict | None = None):

    app = Flask(
        __name__,
        instance_relative_config=True,
        static_folder="static",
        template_folder="templates"
    )

    if test_config:
        app.config.update(test_config)

    app.secret_key = os.getenv("FLASK_KEY")

    DB_USER  = os.getenv("DB_USER")
    DB_PASS  = os.getenv("DB_PASS")
    DB_NAME  = os.getenv("DB_NAME")
    INSTANCE = os.getenv("INSTANCE_CONNECTION_NAME")

    # configure the database to live in app/db.sqlite3
    app.config["SQLALCHEMY_DATABASE_URI"] = (
        f"postgresql+psycopg2://{DB_USER}:{DB_PASS}"
        f"@localhost/{DB_NAME}"
        f"?host=/cloudsql/{INSTANCE}"
    )

    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_pre_ping": True, 
        "pool_size": 5,
        "max_overflow": 2
    }

    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)

    # initialize OAuth
    oauth.init_app(app)
    oauth.register(
        name="google",
        client_id=os.getenv("GOOGLE_ID"),
        client_secret=os.getenv("GOOGLE_SECRET"),
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={ "scope": "openid email profile" },
    )

    # register blueprints
    from .auth   import bp as auth_bp
    from .routes import bp as main_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)

    # get scheduler 
    from app.scheduler import init_scheduler
    if not app.config.get("TESTING"):
        init_scheduler(app)

    return app

import os
from dotenv import load_dotenv
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from authlib.integrations.flask_client import OAuth

oauth = OAuth()
db    = SQLAlchemy()
load_dotenv()

def create_app():
    # bootstrap the Flask app, serving static files from app/static/
    app = Flask(
        __name__,
        static_folder="static",      # resolves to app/static/
        template_folder="templates"  # resolves to app/templates/
    )
    app.secret_key = os.getenv("FLASK_KEY")

    # initialize OAuth
    oauth.init_app(app)
    oauth.register(
        name="google",
        client_id=os.getenv("GOOGLE_ID"),
        client_secret=os.getenv("GOOGLE_SECRET"),
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={ "scope": "openid email profile" },
    )

    # configure the database to live in app/db.sqlite3
    db_path = os.path.join(app.root_path, "db.sqlite3")
    app.config["SQLALCHEMY_DATABASE_URI"]        = f"sqlite:///{db_path}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # initialize and create tables
    db.init_app(app)
    with app.app_context():
        db.create_all()

    # delayed imports 
    
    # register blueprints
    from .auth   import bp as auth_bp
    from .routes import bp as main_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)

    # get scheduler 
    from app.scheduler import init_scheduler
    init_scheduler(app)

    return app

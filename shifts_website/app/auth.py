import functools
from flask import Blueprint, render_template, url_for, redirect, session, request, redirect 
from . import oauth, db
from .models import User

bp = Blueprint("auth", __name__, url_prefix="/auth")

@bp.route("/login")
def login():
    redirect_uri = url_for("auth.callback", _external=True)
    return oauth.google.authorize_redirect(redirect_uri)

@bp.route("/callback")
def callback():
    _token = oauth.google.authorize_access_token()
    userinfo = oauth.google.userinfo()

    email = userinfo["email"]
    if not email.endswith("@dartmouth.edu"):
        return redirect(
            url_for("auth.forbidden_page", message="You must sign in with your @dartmouth.edu email")
        )

    user = User.query.filter_by(email=email).first()
    if not user:
        return redirect(
            url_for("auth.forbidden_page", message="Email not recognized. Please contact Andy")
        )

    session["user"] = {
        "db_id": user.id,          # clearer name, avoids "id vs sub" mix-ups
        "sub":   userinfo["sub"],
        "email": email,
        "name":  userinfo["name"],
    }
    return redirect(url_for("main.index"))

@bp.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("main.index"))

@bp.route("/forbidden")
def forbidden_page():
    msg = request.args.get("message", "Access denied")
    return render_template("auth/forbidden.html", message=msg)

def login_required(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        u = session.get("user")
        # require the new schema
        if not u or "db_id" not in u:
            session.pop("user", None)      # drop bad cookie
            return redirect(url_for("auth.login"))
        return fn(*args, **kwargs)
    return wrapper

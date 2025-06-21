# app/routes.py
from flask import Blueprint, render_template, request, jsonify, session
from datetime import date
from .auth import login_required
from . import db
from .models import Shift

bp = Blueprint("main", __name__)

FIRST_SLOT  = 44
LAST_SLOT   = 2
TOTAL_SLOTS = 48
LOCATIONS   = ["Front1", "Front2", "Side", "Runner", "Back", "Bar1", "Bar2"]

def slot_to_time(slot: int) -> str:
    hr = (slot // 2) % 12
    hr = hr if hr != 0 else 12
    minute = "00" if slot % 2 == 0 else "30"
    ampm = "AM" if slot < 24 else "PM"
    return f"{hr}:{minute} {ampm}"

@bp.route("/")
@login_required
def index():
    db_id = session["user"]["db_id"]

    slots = list(range(FIRST_SLOT, TOTAL_SLOTS)) + list(range(0, LAST_SLOT + 1))
    times = {s: slot_to_time(s) for s in range(TOTAL_SLOTS)}

    today = date.today()

    # build a nested dict so Jinja can do prefill[slot][loc]
    existing = Shift.query.filter_by(week=today).all()
    if existing is None:
        raise RuntimeError("Empty Schedule!")

    prefill = {}
    for s in existing:
        if not s.user:
            continue
        prefill.setdefault(s.slot, {})[s.location] = s.user.user_id


    return render_template(
        "index.html",
        slots=slots,
        times=times,
        locations=LOCATIONS,
        user_id=db_id,
        prefill=prefill
    )

@bp.route("/submit", methods=["POST"])
@login_required
def submit_shifts():
    data = request.get_json(force=True)
    shifts = data.get("shifts", [])
    if not isinstance(shifts, list) or len(shifts) < 2:
        return jsonify(error="Pick at least two shifts"), 400

    today   = date.today()
    db_id   = session["user"]["db_id"]

    # remove their old picks for this week
    Shift.query.filter_by(week=today, user_id=db_id).delete()

    # insert the new ones
    for s in shifts:
        db.session.add(Shift(
            user_id=db_id,
            week=today,
            slot=s["slot"],
            location=s["location"]
        ))

    db.session.commit()

    # sanity-check in your console
    print("JUST WROTE:", Shift.query.filter_by(user_id=db_id, week=today).all())

    return jsonify(success=True), 200

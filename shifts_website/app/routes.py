from datetime import datetime, time, date, timedelta, timezone
from zoneinfo import ZoneInfo
from flask import (
    Blueprint, render_template, request, jsonify, session
)
from sqlalchemy.orm import joinedload
from .auth import login_required
from . import db
from .models import Shift

bp = Blueprint("main", __name__)

FIRST_SLOT  = 44
LAST_SLOT   = 2
TOTAL_SLOTS = 48
LOCATIONS   = ["Front1", "Front2", "Side", "Runner", "Back", "Bar1", "Bar2"]

EASTERN  = ZoneInfo("America/New_York")
LOCK_END = time(4, 0)        # Sun 04:00

def editing_lock(now: datetime | None = None) -> bool:
    """
    True from Fri 00:00 through Sun 04:00 (America/Chicago).
    """
    if now is None:
        now = datetime.now(timezone.utc).astimezone(EASTERN)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=EASTERN)
    else:
        now = now.astimezone(EASTERN)

    wd = now.weekday()
    if wd in (4, 5):
        return True
    if wd == 6:
        return now.time() < LOCK_END
    return False


def week_start(d: date) -> date:
    """Return the Sunday on or before the date `d`."""
    days_since_sunday = (d.weekday() + 1) % 7
    return d - timedelta(days=days_since_sunday)


def slot_to_time(slot: int) -> str:
    hr = (slot // 2) % 12
    hr = 12 if hr == 0 else hr
    minute = "00" if slot % 2 == 0 else "30"
    ampm = "AM" if slot < 24 else "PM"
    return f"{hr}:{minute} {ampm}"


@bp.route("/")
@login_required
def index():
    db_id       = session["user"]["db_id"]
    user_status = session["user"]["status"]

    slots = list(range(FIRST_SLOT, TOTAL_SLOTS)) + list(range(0, LAST_SLOT + 1))
    times = {s: slot_to_time(s) for s in range(TOTAL_SLOTS)}
    current_week = week_start(date.today())

    existing = (
        db.session.query(Shift)
        .filter(Shift.week == current_week)
        .options(joinedload(Shift.user))
        .all()
    )

    prefill: dict[int, dict[str, dict[str, str | int]]] = {}
    for shift in existing:
        display = shift.user.user_id or f"User {shift.user.id}"
        prefill.setdefault(shift.slot, {})[shift.location] = {
            "db_id": shift.user.id,
            "name":  display,
        }

    return render_template(
        "index.html",
        slots=slots,
        times=times,
        locations=LOCATIONS,
        user_id=db_id,
        user_status=user_status,
        editing_locked=editing_lock(),
        prefill=prefill,
    )


@bp.route("/submit", methods=["POST"])
@login_required
def submit_shifts():
    if editing_lock():
        return (
            jsonify(error="Schedule is locked Fri 12:00 AM → Sun 04:00 AM"),
            403,
        )

    data   = request.get_json(force=True)
    shifts = data.get("shifts", [])

    if not isinstance(shifts, list) or len(shifts) < 2:
        return jsonify(error="Pick at least two shifts"), 400

    current_week = week_start(date.today())
    db_id        = session["user"]["db_id"]
    user_status  = session["user"]["status"]

    existing = {
        (s.slot, s.location)
        for s in Shift.query.filter_by(week=current_week, user_id=db_id).all()
    }

    added = 0
    for s in shifts:
        slot      = int(s["slot"])
        location  = s["location"]

        # under-21 (GENERAL) may not pick Bar
        if user_status == "GENERAL" and location.startswith("Bar"):
            return jsonify(error="You are not allowed to pick Bar shifts"), 400

        if (slot, location) in existing:
            continue

        db.session.add(
            Shift(
                user_id=db_id,
                week=current_week,
                slot=slot,
                location=location,
            )
        )
        added += 1

    if added == 0:
        return jsonify(error="No new shifts selected"), 400

    db.session.commit()
    return jsonify(success=True), 200


@bp.route("/delete", methods=["POST"])
@login_required
def delete_shifts():
    if editing_lock():
        return (
            jsonify(error="Schedule is locked Fri 12:00 AM → Sun 04:00 AM"),
            403,
        )

    data   = request.get_json(force=True) or {}
    shifts = data.get("shifts") or data.get("removals") or []

    if not shifts:
        return jsonify(error="Nothing to delete"), 400

    current_week = week_start(date.today())
    uid          = session["user"]["db_id"]

    current_total = Shift.query.filter_by(week=current_week, user_id=uid).count()
    if current_total - len(shifts) == 1:
        return (
            jsonify(error="You must keep at least 2 shifts or delete them both"),
            400,
        )

    deleted_total = 0
    for s in shifts:
        try:
            slot = int(s["slot"])
            loc  = str(s["location"])
        except (KeyError, ValueError, TypeError):
            continue

        deleted_total += (
            Shift.query.filter_by(
                week=current_week,
                slot=slot,
                location=loc,
                user_id=uid,
            ).delete(synchronize_session=False)
        )

    db.session.commit()

    if deleted_total == 0:
        return jsonify(error="Nothing matched"), 404
    return jsonify(success=True, deleted=deleted_total), 200


@bp.route("/api/shifts")
@login_required
def api_shifts():
    current_week = week_start(date.today())
    shifts = Shift.query.filter_by(week=current_week).all()
    return jsonify(
        [
            {
                "week": s.week.isoformat(),
                "slot": s.slot,
                "location": s.location,
                "user_id": s.user_id,
            }
            for s in shifts
        ]
    )

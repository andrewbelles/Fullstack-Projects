import os
import math
import random
import logging
from datetime import date
from app import create_app, db
from app.models import Shift, User
from app.routes import FIRST_SLOT, LAST_SLOT, TOTAL_SLOTS, LOCATIONS

# Probability/Logistic Curve Parameters 
STEEPNESS = 10.0
MIDPOINT  = 0.5
EPSILON   = 1e-3

def logistic_weight(count, max_count):
    x   = count / max_count
    raw = 1.0 / (1.0 + math.exp(STEEPNESS * (x - MIDPOINT)))
    return max(EPSILON, min(1.0, raw))

def fill_unassigned_shifts_for_week(week_date=None):
    app = create_app()
    with app.app_context():
        users = User.query.all()

        # count historic shifts and build weights
        counts = {u.id: Shift.query.filter_by(user_id=u.id).count() for u in users}
        max_count = max(counts.values()) or 1
        weights   = {uid: logistic_weight(cnt, max_count) for uid, cnt in counts.items()}

        # find missing slots
        slots   = list(range(FIRST_SLOT, TOTAL_SLOTS)) + list(range(0, LAST_SLOT + 1))
        existing = Shift.query.filter_by(week=week_date).all()
        filled   = {(s.slot, s.location) for s in existing}
        missing  = [(slot, loc) for slot in slots for loc in LOCATIONS if (slot, loc) not in filled]

        if not missing:
            return

        # capacity per user (max 2)
        capacity = {u.id: 2 for u in users}

        # build the queue of exactly len(missing) entries
        queue = []
        while len(queue) < len(missing):
            pick = random.choices(list(weights), weights=list(weights.values()), k=1)[0]
            if capacity[pick] > 0:
                queue.append(pick)
                capacity[pick] -= 1

        # track existing slots per user to avoid overlaps
        assigned_slots = {
            u.id: {s.slot for s in Shift.query.filter_by(user_id=u.id).all()}
            for u in users
        }

        random.shuffle(queue)

        # assign each queue entry to one of the missing (slot,loc)
        for user_id in queue:
            # prefer non-conflicting
            candidates = [(sl, lc) for sl, lc in missing if sl not in assigned_slots[user_id]]
            if not candidates:
                candidates = missing
            slot, loc = random.choice(candidates)

            db.session.add(Shift(
                user_id=user_id,
                week=week_date,
                slot=slot,
                location=loc
            ))

            assigned_slots[user_id].add(slot)
            missing.remove((slot, loc))

        db.session.commit()

if __name__ == "__main__":
    # set up error-only logging
    root = os.path.dirname(os.path.dirname(__file__))
    log_dir = os.path.join(root, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "fill_shifts.log")
    logging.basicConfig(
        filename=log_file,
        level=logging.ERROR,
        format="%(asctime)s %(levelname)s: %(message)s"
    )

    WEEK = os.getenv("WEEK_DATE")
    try:
        week_date = date.fromisoformat(WEEK) if WEEK else date.today()
        fill_unassigned_shifts_for_week(week_date)
    except Exception:
        logging.exception("Failed to auto-fill shifts for week %s", WEEK or date.today())
        # re-raise if you want the app’s scheduler to know there was an error
        raise

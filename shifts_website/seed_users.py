import os, sys
from app import create_app, db
from app.models import User

INPUT_FILE = ".ignore/users.txt"

def seed():
    app = create_app()
    with app.app_context():
        if not os.path.exists(INPUT_FILE):
            print(f"ERROR: {INPUT_FILE} not found", file=sys.stderr)
            sys.exit(1)

        existing = {u.email: u for u in User.query.all()}
        added = 0

        with open(INPUT_FILE) as f:
            for lineno, raw in enumerate(f, start=1):
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                email, shifts_str, code = [p.strip() for p in line.split(",")]
                shifts_worked = int(shifts_str) if shifts_str.isdigit() else 0
                status = code.upper() if code.upper() in ("GENERAL","BAR") else "GENERAL"

                if email in existing:
                    # we _do not_ overwrite shifts_worked or status
                    continue

                u = User(email=email, shifts_worked=shifts_worked, status=status)
                db.session.add(u)
                added += 1
                print(f"[{lineno}] added {email} (shifts={shifts_worked}, status={status})")

        if added:
            db.session.commit()
            print(f"Committed {added} new user(s).")
        else:
            print("No new users to add.")

if __name__=="__main__":
    seed()

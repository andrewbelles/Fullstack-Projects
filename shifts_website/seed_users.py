import os, sys 
from app import create_app, db 
from app.models import User 

INPUT_FILE = "users.txt"

def seed():
    app = create_app()
    with app.app_context():
        if not os.path.exists(INPUT_FILE):
            print(f"ERROR: {INPUT_FILE} not found", file=sys.stderr)
            sys.exit(1)

        added = 0
        with open(INPUT_FILE, "r") as f:
            for lineno, raw in enumerate(f, start=1):
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue

                parts = [p.strip() for p in line.split(",")]
                email = parts[0]
                if len(parts) > 1 and parts[1].isdigit():
                    shifts_worked = int(parts[1])
                else:
                    shifts_worked = 0

                existing = User.query.filter_by(email=email).first()
                if existing:
                    print(f"[{lineno}] {email} already has been registered...")
                    continue 

                u = User(email=email, shifts_worked=shifts_worked)
                db.session.add(u)
                added += 1
                print(f"[{lineno}] added {u.user_id} ({email}, shifts_worked={shifts_worked})")

        if added: 
            db.session.commit()
            print(f"Commited {added} new user(s).")
        else: 
            print("No new users added.")

if __name__ == "__main__":
    seed()

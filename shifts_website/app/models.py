from . import db

def extract_user_id(email: str) -> str:
    """
    Given an email like first.m.last.2X@dartmouth.edu,
    extract “First Last” as the display user_id.
    """
    local = email.split("@", 1)[0]       # "first.m.last.2X"
    parts = local.split(".")         # ["first", "m", "last"]
    first = parts[0].capitalize()
    last = ""
    if len(parts) >= 3:
        candidate = parts[-2]
        if candidate.isalpha():
            last = candidate.capitalize()
    elif len(parts) == 2 and parts[1].isalpha():
        last = parts[1].capitalize()

    return f"{first} {last}"

class User(db.Model):
    __tablename__ = "users"

    id            = db.Column(db.Integer, primary_key=True)
    email         = db.Column(db.String, unique=True, nullable=False)
    user_id       = db.Column(db.String, unique=True, nullable=False)
    shifts_worked = db.Column(db.Integer, default=0, nullable=False)
    status        = db.Column(db.String(10), nullable=False, default='GENERAL')

    shifts = db.relationship("Shift", backref="user", cascade="all, delete-orphan")
    
    def __init__(self, email, shifts_worked=0, status="GENERAL"):
        self.email         = email
        self.user_id       = extract_user_id(email)
        self.shifts_worked = shifts_worked
        self.status        = status

    def __repr__(self):
        return f"<User {self.user_id} ({self.email})>"

class Shift(db.Model):
    __tablename__ = "shifts"

    id        = db.Column(db.Integer, primary_key=True)
    user_id   = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    week      = db.Column(db.Date, nullable=False)
    slot      = db.Column(db.Integer, nullable=False)
    location  = db.Column(db.String, nullable=False)

    # Enforce one user per slot+location per week
    __table_args__ = (
        db.UniqueConstraint("week", "slot", "location", name="uix_week_slot_loc"),
    )

    def __init__(self, *, user_id: int, week, slot: int, location: str):
        self.user_id  = user_id
        self.week     = week
        self.slot     = slot
        self.location = location

    def __repr__(self):
        return f"<Shift {self.week} slot={self.slot} loc={self.location} by={self.user_id}>"

"""
Helper to reset shifts manually in case of fatal error.
Prints every row it will delete, then wipes the table.
"""

from sqlalchemy import text
from app import create_app, db


def main() -> None:
    app = create_app()

    with app.app_context():
        # 1) Preview rows -----------------------------------------------------------------
        rows = db.session.execute(
            text("SELECT id, user_id, week, slot, location FROM shifts")
        ).fetchall()

        if not rows:
            print("No shifts to delete — table is already empty.")
            return

        print("Rows to be deleted:")
        for r in rows:
            # `r` is a SQLAlchemy Row; attribute access works
            print(
                f"  id={r.id:<3} "
                f"user={r.user_id:<3} "
                f"week={r.week} "
                f"slot={r.slot:<2} "
                f"loc={r.location}"
            )

        # 2) Delete rows ------------------------------------------------------------------
        try:
            result = db.session.execute(text("DELETE FROM shifts;"))
            db.session.commit()
            deleted = result.rowcount if hasattr(result, "rowcount") else "all"
        except Exception as exc:  # noqa: BLE001  (generic CLI helper)
            print(f"Error deleting shifts: {exc}")
            return

    print(f"Deleted {deleted} rows from shifts")


if __name__ == "__main__":
    main()

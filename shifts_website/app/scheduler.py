import os, subprocess 
from flask_apscheduler import APScheduler
from datetime import date

scheduler = APScheduler()

class Config:
    SCHEDULER_API_ENABLED = True

def fill_job():
    base   = os.path.dirname(__file__)
    script = os.path.join(base, "scripts", "fill_shifts")
    db     = os.path.join(base, "db.sqlite3")

    subprocess.run([script, db, date.today().isoformat()], 
                   check=True,
                   cwd=base)

def init_scheduler(app):
    app.config.from_object(Config)
    scheduler.init_app(app)
    scheduler.start()
    scheduler.add_job(
        id="fill_shifts",
        func=fill_job,
        trigger="cron",
        day_of_week="fri",
        hour=0,
        minute=0
    )

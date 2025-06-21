from flask_apscheduler import APScheduler
from datetime import date

scheduler = APScheduler()

class Config:
    SCHEDULER_API_ENABLED = True

def fill_job():
    from fill_shifts import fill_unassigned_shifts_for_week 
    fill_unassigned_shifts_for_week(date.today())

def init_scheduler(app):
    app.config.from_object(Config)

    scheduler.init_app(app)
    scheduler.start()

    scheduler.add_job(
        id="fill_shifts",
        func=fill_job,
        trigger="cron",
        day_of_week="thu",
        hour=0,
        minute=0
            )

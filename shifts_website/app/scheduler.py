'''
Starts the scheduler tasked with proc'ing the fill_shifts script every thursday
'''

import os, subprocess 
from flask_apscheduler import APScheduler 
from app.routes import week_start 
from datetime import date
from dotenv import load_dotenv 

scheduler = APScheduler()
load_dotenv()

class Config: 
    SCHEDULER_API_ENABLED = True 

def fill_job() -> None:
    # Get inputs to fill_shifts script 
    base   = os.path.dirname(__file__)
    script = os.path.join(base, "scripts", "fill_shifts")
    week   = week_start(date.today()).isoformat()

    print(os.getenv("DATABASE_URL"))

    subprocess.run(
        [script, week],
        check=True,
        cwd=base,
    )

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

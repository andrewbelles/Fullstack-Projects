import os, subprocess 
from datetime import date 
from app.routes import week_start 

def main(): 
    base   = os.path.join(os.path.dirname(__file__), "app")
    script = os.path.join(base, "scripts", "fill_shifts")
    week   = week_start(date.today()).isoformat()

    subprocess.run(
        [script, week],
        check=True,
        cwd=base
    )

    print("Ran")

if __name__ == "__main__":
    main()

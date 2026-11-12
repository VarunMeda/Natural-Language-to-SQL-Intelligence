from pathlib import Path
from database.connection import connect
ROOT=Path(__file__).resolve().parents[1]
def initialize_database(reset=False):
    con=connect()
    if reset:
        for name in ("marks","examinations","enrollments","courses","instructors","students","departments"): con.execute(f"DROP TABLE IF EXISTS {name}")
    con.executescript((ROOT/"database"/"demo_schema.sql").read_text(encoding="utf-8")); con.executescript((ROOT/"database"/"demo_seed.sql").read_text(encoding="utf-8")); con.commit(); con.close()
if __name__=="__main__": initialize_database()


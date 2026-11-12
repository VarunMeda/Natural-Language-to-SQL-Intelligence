import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from database.init_db import initialize_database
initialize_database(); print('Demo database initialized.')


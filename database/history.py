from datetime import datetime, timezone
from database.connection import connect

def initialize_history():
    con = connect()
    con.execute('''CREATE TABLE IF NOT EXISTS query_history (
        history_id INTEGER PRIMARY KEY AUTOINCREMENT,
        question TEXT NOT NULL,
        strategy TEXT NOT NULL,
        generated_sql TEXT NOT NULL,
        execution_success INTEGER NOT NULL,
        execution_time_ms REAL NOT NULL,
        correction_iterations INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    )''')
    con.commit(); con.close()

def record_history(question, strategy, generated_sql, result, correction_iterations=0):
    initialize_history(); con=connect()
    con.execute('''INSERT INTO query_history
        (question,strategy,generated_sql,execution_success,execution_time_ms,correction_iterations,created_at)
        VALUES (?,?,?,?,?,?,?)''', (question, strategy, generated_sql, int(bool(result.get('success'))), float(result.get('duration_ms',0)), correction_iterations, datetime.now(timezone.utc).isoformat()))
    con.commit(); con.close()

def get_history(limit=100):
    initialize_history(); con=connect(); rows=[dict(r) for r in con.execute('SELECT * FROM query_history ORDER BY history_id DESC LIMIT ?', (int(limit),))]; con.close(); return rows


import sqlite3
from pathlib import Path

def database_path(db_root,db_id):
    root=Path(db_root); candidates=[root/db_id/(db_id+'.sqlite'),root/db_id/(db_id+'.db'),root/(db_id+'.sqlite')]
    for candidate in candidates:
        if candidate.exists(): return candidate
    raise FileNotFoundError(f'Spider database not found for db_id={db_id} under {root}')

def inspect_spider_database(db_path):
    con=sqlite3.connect(db_path); schema={}
    for (table,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
        columns=[{'name':row[1],'type':row[2],'nullable':not bool(row[3]),'primary_key':bool(row[5])} for row in con.execute(f'PRAGMA table_info("{table}")')]
        fks=[{'column':row[3],'references_table':row[2],'references_column':row[4]} for row in con.execute(f'PRAGMA foreign_key_list("{table}")')]
        schema[table]={'columns':columns,'foreign_keys':fks}
    con.close(); return schema

def schema_context(db_path):
    schema=inspect_spider_database(db_path); lines=[]
    for table,info in schema.items():
        columns=', '.join(f"{c['name']} {c['type']}{' PK' if c['primary_key'] else ''}" for c in info['columns']); lines.append(f'TABLE {table} ({columns})')
        lines.extend(f"FK {table}.{fk['column']} -> {fk['references_table']}.{fk['references_column']}" for fk in info['foreign_keys'])
    return '\n'.join(lines),schema

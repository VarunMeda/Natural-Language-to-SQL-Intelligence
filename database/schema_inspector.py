from database.connection import connect
from core.config import settings
def inspect_schema():
    if not settings.database_url.startswith('sqlite:///'):
        from database.postgres import sqlalchemy_inspect_schema
        return sqlalchemy_inspect_schema(settings.database_url)
    con=connect(); tables={}
    for row in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
        name=row[0]; cols=[]
        for col in con.execute(f"PRAGMA table_info({name})"): cols.append({"name":col[1],"type":col[2],"nullable":not bool(col[3]),"primary_key":bool(col[5])})
        fks=[{"column":r[3],"references_table":r[2],"references_column":r[4]} for r in con.execute(f"PRAGMA foreign_key_list({name})")]
        tables[name]={"columns":cols,"foreign_keys":fks}
    con.close(); return tables
def schema_text(schema=None):
    schema=schema or inspect_schema(); lines=[]
    for table,info in schema.items():
        cols=", ".join(f"{c['name']} {c['type']}{' PK' if c['primary_key'] else ''}" for c in info['columns']); lines.append(f"TABLE {table} ({cols})")
        lines.extend(f"  FK {table}.{fk['column']} -> {fk['references_table']}.{fk['references_column']}" for fk in info['foreign_keys'])
    return "\n".join(lines)


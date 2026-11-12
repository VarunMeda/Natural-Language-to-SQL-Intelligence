import time
from core.config import settings
from database.connection import connect
from database.schema_inspector import inspect_schema
from sql_validator.validator import validate_sql
from core.config import settings
def execute_sql(sql):
    check=validate_sql(sql,inspect_schema())
    if not check.valid:return {"success":False,"sql":sql,"error":"; ".join(check.errors),"rows":[],"columns":[],"duration_ms":0}
    start=time.perf_counter()
    try:
        if settings.database_url.startswith('sqlite:///'):
            con=connect(); cur=con.execute(check.sql); rows=[dict(r) for r in cur.fetchmany(settings.max_result_rows)]; cols=[d[0] for d in cur.description or []]; con.close()
        else:
            from sqlalchemy import create_engine, text
            with create_engine(settings.database_url, pool_pre_ping=True).connect() as con:
                result=con.execute(text(check.sql)); cols=list(result.keys()); rows=[dict(r._mapping) for r in result.fetchmany(settings.max_result_rows)]
        return {"success":True,"sql":check.sql,"error":None,"rows":rows,"columns":cols,"duration_ms":round((time.perf_counter()-start)*1000,2),"truncated":len(rows)>=settings.max_result_rows}
    except Exception as exc:return {"success":False,"sql":check.sql,"error":str(exc),"rows":[],"columns":[],"duration_ms":round((time.perf_counter()-start)*1000,2)}


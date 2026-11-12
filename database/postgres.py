def sqlalchemy_inspect_schema(database_url):
    from sqlalchemy import create_engine, inspect
    engine=create_engine(database_url, pool_pre_ping=True)
    inspector=inspect(engine); tables={}
    for table in inspector.get_table_names():
        pks=set(inspector.get_pk_constraint(table).get('constrained_columns') or [])
        columns=[{'name':c['name'],'type':str(c['type']),'nullable':bool(c.get('nullable',True)),'primary_key':c['name'] in pks} for c in inspector.get_columns(table)]
        fks=[]
        for fk in inspector.get_foreign_keys(table):
            for col,ref in zip(fk.get('constrained_columns') or [],fk.get('referred_columns') or []): fks.append({'column':col,'references_table':fk.get('referred_table'),'references_column':ref})
        tables[table]={'columns':columns,'foreign_keys':fks}
    return tables


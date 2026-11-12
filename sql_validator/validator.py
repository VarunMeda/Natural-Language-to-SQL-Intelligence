import re
from dataclasses import dataclass
UNSAFE=re.compile(r"\b(DROP|DELETE|UPDATE|INSERT|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|ATTACH|DETACH|PRAGMA|VACUUM|REPLACE)\b",re.I)
@dataclass
class Validation: valid: bool; sql: str; errors: list[str]
def validate_sql(sql,schema=None):
    errors=[]; cleaned=sql.strip()
    if not cleaned:return Validation(False,cleaned,["SQL is empty"])
    if cleaned.endswith(';'):cleaned=cleaned[:-1].strip()
    if ';' in cleaned:errors.append("Multiple SQL statements are not allowed")
    if not re.match(r"^(SELECT|WITH)\b",cleaned,re.I):errors.append("Only SELECT or WITH read-only queries are allowed")
    if UNSAFE.search(cleaned):errors.append("Unsafe SQL operation detected")
    try:
        import sqlglot
        statements=sqlglot.parse(cleaned, read='sqlite')
        if len(statements)!=1 or statements[0].key.upper() not in ('SELECT','WITH'):
            errors.append('SQLGlot parsed a non-read-only statement')
    except ImportError: pass
    except Exception as exc: errors.append(f'SQL parse error: {exc}')
    if schema is not None:
        known={x.lower() for x in schema}; refs={m.group(2).lower() for m in re.finditer(r"\b(FROM|JOIN)\s+([A-Za-z_][\w]*)",cleaned,re.I)}; missing=sorted(refs-known)
        if missing:errors.append("Unknown table(s): "+", ".join(missing))
    return Validation(not errors,cleaned,errors)


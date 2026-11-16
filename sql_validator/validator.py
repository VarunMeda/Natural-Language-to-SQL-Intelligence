import re
from dataclasses import dataclass

# Statement types that must never appear anywhere in the parsed tree.
UNSAFE=re.compile(r"\b(DROP|DELETE|UPDATE|INSERT|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|ATTACH|DETACH|PRAGMA|VACUUM|MERGE)\b",re.I)
_STRING_LITERAL=re.compile(r"'(?:[^']|'')*'")
_QUOTED_IDENT=re.compile(r'"(?:[^"]|"")*"|`[^`]*`|\[[^\]]*\]')


@dataclass
class Validation: valid: bool; sql: str; errors: list[str]


def _dialect():
    try:
        from core.config import settings
        return 'postgres' if settings.database_url.startswith('postgres') else 'sqlite'
    except Exception:
        return 'sqlite'


def _strip_literals(sql):
    """Remove string literals and quoted identifiers so keyword checks only see SQL syntax."""
    return _QUOTED_IDENT.sub('""', _STRING_LITERAL.sub("''", sql))


def validate_sql(sql,schema=None):
    errors=[]; cleaned=sql.strip()
    if not cleaned:return Validation(False,cleaned,["SQL is empty"])
    if cleaned.endswith(';'):cleaned=cleaned[:-1].strip()
    syntax_only=_strip_literals(cleaned)
    if ';' in syntax_only:errors.append("Multiple SQL statements are not allowed")
    if not re.match(r"^\(*\s*(SELECT|WITH)\b",cleaned,re.I):errors.append("Only SELECT or WITH read-only queries are allowed")
    # Keyword check runs on SQL with literals removed, so values like 'update' or
    # the REPLACE() string function are not mistaken for write operations.
    if UNSAFE.search(syntax_only):errors.append("Unsafe SQL operation detected")
    referenced=None
    try:
        import sqlglot
        from sqlglot import exp
        statements=[s for s in sqlglot.parse(cleaned, read=_dialect()) if s is not None]
        root=statements[0] if len(statements)==1 else None
        # UNION / INTERSECT / EXCEPT are read-only set operations over SELECTs.
        if root is None or not isinstance(root,(exp.Select,exp.Union,exp.Intersect,exp.Except,exp.Subquery)):
            errors.append('SQLGlot parsed a non-read-only statement')
        else:
            write_nodes=(exp.Insert,exp.Update,exp.Delete,exp.Drop,exp.Create,exp.Alter,exp.Command,exp.Merge)
            if any(isinstance(node,write_nodes) for node in root.walk()):
                errors.append('SQLGlot found a write operation inside the query')
            cte_names={cte.alias_or_name.lower() for cte in root.find_all(exp.CTE)}
            referenced={t.name.lower() for t in root.find_all(exp.Table) if t.name}-cte_names
    except ImportError: pass
    except Exception as exc: errors.append(f'SQL parse error: {exc}')
    if schema is not None:
        known={x.lower() for x in schema}
        if referenced is None:  # sqlglot unavailable: regex fallback, excluding CTE names
            ctes={m.group(1).lower() for m in re.finditer(r"(?:\bWITH|,)\s*([A-Za-z_]\w*)\s+AS\s*\(",syntax_only,re.I)}
            referenced={m.group(2).lower() for m in re.finditer(r"\b(FROM|JOIN)\s+([A-Za-z_][\w]*)",syntax_only,re.I)}-ctes
        missing=sorted(referenced-known)
        if missing:errors.append("Unknown table(s): "+", ".join(missing))
    return Validation(not errors,cleaned,list(dict.fromkeys(errors)))

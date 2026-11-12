from core.config import settings

def explain_result_details(question,result):
    if not result.get('success'):return f"The question could not be answered because SQL execution failed: {result.get('error')}"
    rows=result.get('rows',[]); cols=result.get('columns',[])
    if not rows:return f"The query addressed '{question}' but returned zero records."
    first=rows[0]; preview=', '.join(f'{k}={v}' for k,v in list(first.items())[:4]); suffix=' Results were limited to the configured maximum.' if result.get('truncated') else ''
    return f"The query addressed '{question}' and returned {len(rows)} record(s) with columns {', '.join(cols)}. The first result is {preview}.{suffix}"

def explain_result(question,result,sql=None):
    fallback=explain_result_details(question,result)
    if not result.get('success') or settings.llm_provider.lower()!='ollama': return fallback
    from llm.ollama_provider import OllamaProvider, LLMError
    rows=result.get('rows',[])[:20]
    prompt=f"""Explain the actual SQL result concisely and factually.
Question: {question}
SQL: {sql or result.get('sql','')}
Columns: {result.get('columns',[])}
Rows (sample, at most 20): {rows}
State whether zero rows were returned. Do not invent facts or mention unavailable data."""
    try:
        text=OllamaProvider().generate_explanation(prompt,system='You summarize database results. Use only the supplied values. Never say zero/no rows when rows are supplied, and never claim rows exist when the supplied list is empty.').text.strip()
        lowered=text.lower()
        contradiction=(bool(rows) and ('no rows' in lowered or 'zero rows' in lowered or '0 rows' in lowered)) or (not rows and ('returned 5' in lowered or 'returned rows' in lowered))
        return fallback if contradiction or not text else text
    except LLMError: return fallback


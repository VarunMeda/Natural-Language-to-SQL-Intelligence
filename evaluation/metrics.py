import re
def normalize_sql(sql):return re.sub(r'\s+',' ',sql.strip().rstrip(';')).lower()
def exact_match(predicted,reference):return normalize_sql(predicted)==normalize_sql(reference)
def execution_accuracy(predicted_rows,reference_rows):
    def canon(rows):
        values=[]
        for row in rows:
            if hasattr(row,'keys'): values.append(tuple(sorted(dict(row).items())))
            else: values.append(tuple(row))
        return sorted(values)
    return canon(predicted_rows)==canon(reference_rows)
def summarize(records):
    n=len(records); success=sum(r.get('execution_success',False) for r in records); correct=sum(r.get('execution_correct',False) for r in records); exact=sum(r.get('exact_match',False) for r in records)
    return {'total_questions':n,'successful_queries':success,'execution_accuracy_pct':round(correct/n*100,2) if n else None,'exact_match_accuracy_pct':round(exact/n*100,2) if n else None,'average_correction_iterations':round(sum(r.get('correction_iterations',0) for r in records)/n,3) if n else None,'execution_failure_rate_pct':round((n-success)/n*100,2) if n else None,'invalid_sql_rate_pct':round(sum(1 for r in records if r.get('error') and ('SQL' in r.get('error','') or 'Unknown table' in r.get('error','')))/n*100,2) if n else None,'average_latency_ms':round(sum(r.get('latency_ms',0) for r in records)/n,2) if n else None,'total_llm_calls':sum(r.get('llm_calls',0) for r in records),'total_prompt_tokens':sum(r.get('prompt_tokens',0) for r in records),'total_completion_tokens':sum(r.get('completion_tokens',0) for r in records)}


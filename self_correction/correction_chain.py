from sql_generator.generator import generate_sql, correct_sql
from sql_executor.executor import execute_sql
from database.history import record_history


def _tokens(usage):
    return (usage or {}).get('total_tokens') or 0


def provider_metadata(generated):
    """Expose which provider produced the SQL so a silent heuristic fallback is visible."""
    meta={'provider':generated.get('provider'),'model':generated.get('model')}
    if generated.get('provider_error'): meta['provider_error']=generated['provider_error']
    return meta


def run_self_correction(question,strategy='zero-shot',max_attempts=3,initial_sql=None):
    g=generate_sql(question,strategy); current=initial_sql or g['sql']; history=[]
    llm_calls=g.get('llm_calls',0); total_tokens=_tokens(g.get('usage'))
    def outcome(success,result,iterations):
        record_history(question,strategy,current,result,iterations)
        return {'success':success,'question':question,'sql':current,'initial_sql':g['sql'],'result':result,'history':history,
                'correction_iterations':iterations,'llm_calls':llm_calls,'total_tokens':total_tokens or None,**provider_metadata(g)}
    for attempt in range(max_attempts+1):
        result=execute_sql(current); history.append({'attempt':attempt,'sql':current,'error':result.get('error'),'success':result['success']})
        if result['success']: return outcome(True,result,attempt)
        if attempt>=max_attempts: break
        repaired=correct_sql(question,current,result.get('error',''),strategy)
        llm_calls+=repaired.get('llm_calls',0); total_tokens+=_tokens(repaired.get('usage'))
        next_sql=repaired.get('sql',current)
        history[-1]['correction_provider']=repaired.get('provider')
        history[-1]['correction_usage']=repaired.get('usage',{})
        if next_sql.strip()==current.strip(): break
        current=next_sql
    return outcome(False,result,len(history)-1)

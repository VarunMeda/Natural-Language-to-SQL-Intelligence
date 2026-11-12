from sql_generator.generator import generate_sql, correct_sql
from sql_executor.executor import execute_sql
from database.history import record_history
def run_self_correction(question,strategy='zero-shot',max_attempts=3,initial_sql=None):
    g=generate_sql(question,strategy); current=initial_sql or g['sql']; history=[]
    for attempt in range(max_attempts+1):
        result=execute_sql(current); history.append({'attempt':attempt,'sql':current,'error':result.get('error'),'success':result['success']})
        if result['success']:
            outcome={'success':True,'question':question,'sql':current,'initial_sql':g['sql'],'result':result,'history':history,'correction_iterations':attempt}
            record_history(question,strategy,current,result,attempt)
            return outcome
        if attempt>=max_attempts:break
        repaired=correct_sql(question,current,result.get('error',''),strategy)
        next_sql=repaired.get('sql',current)
        history[-1]['correction_provider']=repaired.get('provider')
        history[-1]['correction_usage']=repaired.get('usage',{})
        if next_sql.strip()==current.strip(): break
        current=next_sql
    outcome={'success':False,'question':question,'sql':current,'initial_sql':g['sql'],'result':result,'history':history,'correction_iterations':max_attempts}
    record_history(question,strategy,current,result,max_attempts)
    return outcome


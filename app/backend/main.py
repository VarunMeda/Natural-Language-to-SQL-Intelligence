try:
    from fastapi import FastAPI
    from pydantic import BaseModel
except ImportError: FastAPI=None
from database.init_db import initialize_database
from database.schema_inspector import inspect_schema
from sql_generator.generator import generate_sql
from sql_executor.executor import execute_sql
from self_correction.correction_chain import run_self_correction
from sql_agent.agent import run_agent
from core.config import settings
from llm.ollama_provider import OllamaProvider
from explanation.result_explainer import explain_result
from database.history import get_history, initialize_history
from sql_agent.agent import run_langgraph_agent
if FastAPI:
    app=FastAPI(title='Natural-Language-to-SQL Intelligence',version='1.0.0')
    class Query(BaseModel): question:str; strategy:str='zero-shot'
    class SQL(BaseModel): sql:str
    @app.on_event('startup')
    def startup(): initialize_database(); initialize_history()
    @app.get('/api/health')
    def health():return {'status':'ok','database':'sqlite demo'}
    @app.get('/api/llm/status')
    def llm_status():
        if settings.llm_provider.lower()!='ollama': return {'provider':settings.llm_provider,'model':None,'available':True,'model_available':True}
        status=OllamaProvider().status(); status['provider']='ollama'; return status
    @app.get('/api/database/schema')
    def schema():return inspect_schema()
    @app.get('/api/history')
    def history(limit:int=100):return get_history(limit)
    @app.get('/api/evaluation/results')
    def evaluation_results():return {'status':'not_run','message':'Run the benchmark script after supplying the official Spider dataset.'}
    @app.post('/api/sql/generate')
    def generate(q:Query):return generate_sql(q.question,q.strategy)
    @app.post('/api/sql/execute')
    def execute(q:SQL):return execute_sql(q.sql)
    @app.post('/api/sql/correct')
    def correct(q:Query):return run_self_correction(q.question,q.strategy)
    @app.post('/api/sql/agent')
    def agent(q:Query):return run_agent(q.question)
    @app.post('/api/sql/compare')
    def compare(q:Query):
        import time
        rows=[]
        for strategy in ('zero-shot','few-shot','cot'):
            start=time.perf_counter(); generated=generate_sql(q.question,strategy); result=execute_sql(generated['sql'])
            rows.append({'approach':strategy,'success':result['success'],'latency_ms':round((time.perf_counter()-start)*1000,2),'llm_calls':generated.get('llm_calls',0),'token_usage':None,'sql':generated['sql']})
        return {'question':q.question,'rows':rows}
    @app.post('/api/sql/explain')
    def explain(q:Query):
        g=generate_sql(q.question,q.strategy); r=execute_sql(g['sql']); return {'result':r,'explanation':explain_result(q.question,r),'sql':g['sql']}
else:app=None


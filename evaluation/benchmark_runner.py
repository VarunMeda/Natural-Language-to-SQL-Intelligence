import csv
import importlib.util
import json
import sqlite3
import sys
import time
import re
from pathlib import Path

from evaluation.dataset_loader import load_spider_subset, write_subset_manifest
from evaluation.metrics import summarize
from evaluation.spider_schema import database_path, schema_context
from sql_generator.generator import correct_sql, generate_sql
from sql_validator.validator import validate_sql


def _official_modules():
    root=Path(__file__).resolve().parent/'official_spider'
    if str(root) not in sys.path: sys.path.insert(0,str(root))
    process_spec=importlib.util.spec_from_file_location('spider_process_sql',root/'process_sql.py'); process=importlib.util.module_from_spec(process_spec); sys.modules['process_sql']=process; process_spec.loader.exec_module(process)
    evaluation_spec=importlib.util.spec_from_file_location('spider_official_evaluation',root/'evaluation.py'); official_evaluation=importlib.util.module_from_spec(evaluation_spec); evaluation_spec.loader.exec_module(official_evaluation)
    Schema, get_schema, get_sql=process.Schema, process.get_schema, process.get_sql
    return official_evaluation, Schema, get_schema, get_sql


def official_scores(predicted, gold, db_path, tables_entry):
    """Use the authors' parser and Evaluator, not string normalization."""
    official, Schema, get_schema, get_sql=_official_modules()
    schema=Schema(get_schema(str(db_path))); evaluator=official.Evaluator()
    def evaluator_compatible(sql):
        # The original Spider parser accepts table aliases only when written as
        # `AS`, and does not accept projection aliases. Normalize only the copy
        # passed to the evaluator; execution still uses the model's SQL.
        select_part, sep, rest=sql.partition('FROM')
        select_part=re.sub(r'\s+AS\s+[A-Za-z_][\w]*', '', select_part, flags=re.I)
        rest=re.sub(r'\b(FROM|JOIN)\s+([A-Za-z_][\w]*)\s+(?!AS\b)([A-Za-z_][\w]*)', lambda m:f'{m.group(1)} {m.group(2)} AS {m.group(3)}', sep+rest, flags=re.I)
        return select_part+rest if sep else sql
    try:
        pred_ast=get_sql(schema,evaluator_compatible(predicted)); gold_ast=get_sql(schema,gold)
        exact=bool(evaluator.eval_exact_match(pred_ast,gold_ast))
        hardness=evaluator.eval_hardness(gold_ast)
        return {'exact_match':exact,'complexity':hardness,'official_error':None}
    except Exception as exc:
        return {'exact_match':False,'complexity':'unknown','official_error':str(exc)}


def execute_benchmark_sql(sql, db_path, schema):
    check=validate_sql(sql,schema)
    if not check.valid: return {'success':False,'error':'; '.join(check.errors),'rows':[],'duration_ms':0}
    started=time.perf_counter()
    try:
        with sqlite3.connect(db_path) as con:
            rows=con.execute(check.sql).fetchmany(1000)
        return {'success':True,'error':None,'rows':rows,'duration_ms':round((time.perf_counter()-started)*1000,2)}
    except Exception as exc: return {'success':False,'error':str(exc),'rows':[],'duration_ms':round((time.perf_counter()-started)*1000,2)}


def _empty_record(item,strategy):
    return {'source_index':item['source_index'],'question':item['question'],'db_id':item['db_id'],'reference_sql':item['query'],'strategy':strategy,'generated_sql':None,'execution_success':False,'execution_correct':False,'exact_match':False,'correction_iterations':0,'latency_ms':0,'llm_calls':0,'prompt_tokens':0,'completion_tokens':0,'error':None,'complexity':'unknown'}


def _usage(record, generated):
    usage=generated.get('usage') or {}
    record['llm_calls']+=generated.get('llm_calls',0); record['prompt_tokens']+=(usage.get('prompt_tokens') or 0); record['completion_tokens']+=(usage.get('completion_tokens') or 0)


def evaluate_one(item, db_root, strategy, mode='generation', max_corrections=3):
    db_path=database_path(db_root,item['db_id']); context,schema=schema_context(db_path); record=_empty_record(item,strategy); started=time.perf_counter()
    if mode=='agent':
        return _evaluate_agent(item,db_path,schema,record,started,max_corrections)
    prompt_strategy={'self-correction':'zero-shot'}.get(strategy,strategy)  # self-correction = zero-shot + repair loop
    generated=generate_sql(item['question'],prompt_strategy,schema_context=context); _usage(record,generated); current=generated['sql']; record['generated_sql']=current; record['provider']=generated.get('provider')
    result=execute_benchmark_sql(current,db_path,schema); record['initial_execution_success']=result['success']; record['initial_error']=result.get('error')
    if mode in ('self_correction','agent') and not result['success']:
        for attempt in range(1,max_corrections+1):
            correction=correct_sql(item['question'],current,result.get('error',''),prompt_strategy,schema_context=context); _usage(record,correction); next_sql=correction.get('sql',current)
            record.setdefault('correction_history',[]).append({'attempt':attempt,'sql':next_sql,'error_before':result.get('error'),'provider':correction.get('provider')})
            record['correction_iterations']=attempt
            if next_sql.strip()==current.strip(): break
            current=next_sql; result=execute_benchmark_sql(current,db_path,schema)
            if result['success']: break
    record['generated_sql']=current; record['execution_success']=result['success']; record['error']=result.get('error'); record['latency_ms']=round((time.perf_counter()-started)*1000,2)
    _score(record,current,result,item,db_path,schema)
    return record


def _score(record, predicted_sql, result, item, db_path, schema):
    gold_result=execute_benchmark_sql(item['query'],db_path,schema)
    record['execution_correct']=bool(result['success'] and gold_result['success'] and sorted(map(tuple,result['rows']))==sorted(map(tuple,gold_result['rows'])))
    record.update(official_scores(predicted_sql,item['query'],db_path,None))


def _evaluate_agent(item, db_path, schema, record, started, max_corrections):
    """Run the LangGraph SQL agent with read-only tools bound to this Spider database."""
    from sql_agent.agent import SQLiteFileTools, run_agent_with_tools
    tools=SQLiteFileTools(db_path, lambda sql: execute_benchmark_sql(sql,db_path,schema))
    outcome=run_agent_with_tools(item['question'],tools,max_retries=max_corrections)
    result=outcome['result']
    first_exec=next((a for a in outcome['actions'] if a['tool']=='execute_sql'),{})
    record.update({'generated_sql':outcome['sql'],'initial_sql':outcome.get('initial_sql'),'initial_execution_success':first_exec.get('success'),
                   'execution_success':result['success'],'error':result.get('error'),'correction_iterations':outcome['correction_iterations'],
                   'llm_calls':outcome['llm_calls'],'prompt_tokens':outcome['prompt_tokens'],'completion_tokens':outcome['completion_tokens'],
                   'agent_actions':[a['tool'] for a in outcome['actions']],'agent_framework':outcome['framework'],'provider':outcome.get('provider'),
                   'latency_ms':round((time.perf_counter()-started)*1000,2)})
    _score(record,outcome['sql'],result,item,db_path,schema)
    return record


def run_spider_experiment(dev_json, db_root, output_dir='evaluation/reports', count=100, seed=42, strategies=None, max_corrections=3, resume=True):
    strategies=strategies or ['zero-shot','few-shot','cot','self-correction','agent']; out=Path(output_dir); out.mkdir(parents=True,exist_ok=True)
    records=load_spider_subset(dev_json,count,seed); write_subset_manifest(records,out/'spider_subset_manifest.json',seed,count)
    checkpoint_path=out/'spider_checkpoint.jsonl'; completed={}
    if resume and checkpoint_path.exists():
        for line in checkpoint_path.read_text(encoding='utf-8').splitlines():
            if line:
                row=json.loads(line); completed[(row['source_index'],row['strategy'])]=row
    all_records=[]
    with checkpoint_path.open('a',encoding='utf-8') as checkpoint:
        for strategy in strategies:
            mode='self_correction' if strategy=='self-correction' else 'agent' if strategy=='agent' else 'generation'
            for item in records:
                key=(item['source_index'],strategy)
                if key in completed: row=completed[key]
                else:
                    row=evaluate_one(item,db_root,strategy,mode,max_corrections)
                    if row.get('provider')=='heuristic-fallback':
                        # Never record keyword-fallback SQL as a model result; progress so far is kept.
                        raise RuntimeError(f"LLM unavailable at question {item['source_index']} ({strategy}). Start Ollama and rerun the same command to resume.")
                    checkpoint.write(json.dumps(row)+'\n'); checkpoint.flush()
                all_records.append(row)
    summaries={s:summarize([r for r in all_records if r['strategy']==s]) for s in strategies}
    report={'dataset':'Spider 1.0 official dev split','subset_size':len(records),'selection':{'method':'random.sample then source-index order','seed':seed},'strategies':strategies,'summaries':summaries,'records':all_records}
    (out/'spider_experiment.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    with (out/'spider_experiment.jsonl').open('w',encoding='utf-8') as f:
        for row in all_records:f.write(json.dumps(row)+'\n')
    fields=['source_index','question','db_id','strategy','provider','generated_sql','execution_success','execution_correct','exact_match','correction_iterations','latency_ms','llm_calls','prompt_tokens','completion_tokens','error','complexity']
    with (out/'spider_experiment.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore'); writer.writeheader(); writer.writerows(all_records)
    return report


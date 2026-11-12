from database.schema_inspector import inspect_schema
from sql_generator.generator import generate_sql
from sql_executor.executor import execute_sql
from sql_generator.generator import correct_sql

def _inspect_tool(_state):
    schema=inspect_schema()
    return {'schema':schema,'actions':[{'tool':'inspect_schema','summary':f'Inspected {len(schema)} tables'}]}

def _generate_tool(state):
    generated=generate_sql(state['question'],'cot')
    return {'sql':generated['sql'],'plan':generated['plan'],'actions':state['actions']+[{'tool':'generate_sql','summary':'Generated a concise schema-aware plan'}]}

def _execute_tool(state):
    result=execute_sql(state['sql'])
    actions=state['actions']+[{'tool':'execute_sql','summary':'Executed through controlled read-only database tool','success':result['success']}]
    if not result['success']:
        repaired=correct_sql(state['question'],state['sql'],result.get('error',''),'cot')
        if repaired.get('sql','').strip()!=state['sql'].strip():
            retry=execute_sql(repaired['sql']); actions.append({'tool':'correct_sql','summary':'Regenerated SQL after observed database error','provider':repaired.get('provider')}); actions.append({'tool':'execute_sql_retry','summary':'Executed corrected SQL through controlled tool','success':retry['success']}); return {'sql':repaired['sql'],'result':retry,'actions':actions,'plan':repaired.get('plan',state.get('plan',[]))}
    return {'result':result,'actions':actions}

def run_langgraph_agent(question):
    """Run an explicit LangGraph workflow with bounded, controlled database tools."""
    try:
        from typing import TypedDict
        from langgraph.graph import StateGraph, END
        class AgentState(TypedDict, total=False):
            question:str; schema:dict; sql:str; plan:list; result:dict; actions:list
        graph=StateGraph(AgentState)
        graph.add_node('inspect_schema',_inspect_tool); graph.add_node('generate_sql',_generate_tool); graph.add_node('execute_sql',_execute_tool)
        graph.set_entry_point('inspect_schema'); graph.add_edge('inspect_schema','generate_sql'); graph.add_edge('generate_sql','execute_sql'); graph.add_edge('execute_sql',END)
        state=graph.compile().invoke({'question':question,'actions':[]})
        return {'success':state['result']['success'],'sql':state['sql'],'result':state['result'],'actions':state['actions'],'answer_plan':state.get('plan',[]),'framework':'langgraph'}
    except ImportError:
        return run_agent_fallback(question)

def run_agent_fallback(question):
    actions=[{'tool':'inspect_schema','summary':f"Inspected {len(inspect_schema())} tables"}]; g=generate_sql(question,'cot'); actions.append({'tool':'generate_sql','summary':'Generated a concise query plan'}); result=execute_sql(g['sql']); actions.append({'tool':'execute_sql','summary':'Executed through controlled database tool','success':result['success']})
    return {'success':result['success'],'sql':g['sql'],'result':result,'actions':actions,'answer_plan':g['plan'],'framework':'fallback'}

def run_agent(question):
    return run_langgraph_agent(question)


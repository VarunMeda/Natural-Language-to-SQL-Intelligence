import json
import sys
from pathlib import Path

# Streamlit sets the import root to this script's directory. Add the repository
# root explicitly so the sibling packages (database, sql_agent, etc.) resolve
# regardless of the directory from which `streamlit run` is invoked.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
from database.init_db import initialize_database
from database.schema_inspector import inspect_schema
from database.history import get_history, initialize_history
from self_correction.correction_chain import run_self_correction
from sql_agent.agent import run_agent
from explanation.result_explainer import explain_result
from core.config import settings
from llm.ollama_provider import OllamaProvider
import pandas as pd

initialize_database(); initialize_history()
st.set_page_config(page_title='Natural-Language-to-SQL Intelligence', page_icon='🧠', layout='wide')
st.title('🧠 Natural-Language-to-SQL Intelligence')
st.caption('Schema-aware SQL generation, controlled execution, self-correction, and agent comparison')
llm_status=OllamaProvider().status() if settings.llm_provider.lower()=='ollama' else {'available':True,'model_available':True,'models':[]}
with st.sidebar:
    st.subheader('LLM status'); st.write('Provider:',settings.llm_provider); st.write('Model:',settings.ollama_model or 'qwen2.5-coder:7b'); st.write('Server:', 'Connected' if llm_status.get('available') else 'Unavailable'); st.write('Model:', 'Ready' if llm_status.get('model_available') else 'Not found')
home, explorer, agent_tab, history_tab, eval_tab = st.tabs(['Query workspace','Database explorer','SQL agent','Query history','Evaluation dashboard'])
with home:
    strategy=st.selectbox('Prompt strategy',['zero-shot','few-shot','cot'], format_func=lambda x:{'zero-shot':'Zero-shot','few-shot':'Few-shot','cot':'Structured CoT'}[x])
    question=st.text_area('Natural-language question','How many students are in each department?',height=90)
    if st.button('Generate, validate, execute',type='primary',use_container_width=True): st.session_state['last_outcome']=run_self_correction(question,strategy)
    outcome=st.session_state.get('last_outcome')
    if outcome:
        st.subheader('Generated SQL'); st.code(outcome['sql'],language='sql')
        c1,c2,c3=st.columns(3); c1.metric('Status','Success' if outcome['success'] else 'Failed'); c2.metric('Correction iterations',outcome['correction_iterations']); c3.metric('Execution ms',outcome['result'].get('duration_ms',0))
        if outcome['success']: st.dataframe(outcome['result']['rows'],use_container_width=True); st.info(explain_result(question,outcome['result']))
        else: st.error(outcome['result'].get('error'))
        with st.expander('Self-correction history'): st.json(outcome['history'])
    if st.button('Compare all prompting strategies'):
        comparison=[]
        for name in ('zero-shot','few-shot','cot'):
            started=__import__('time').perf_counter(); result=run_self_correction(question,name); comparison.append({'approach':name,'success':result['success'],'latency_ms':result['result'].get('duration_ms',0),'correction_iterations':result['correction_iterations'],'llm_calls':0,'token_consumption':None})
        st.session_state['comparison']=comparison
    if st.session_state.get('comparison'):
        st.subheader('Prompt strategy comparison'); frame=pd.DataFrame(st.session_state['comparison']); st.dataframe(frame,use_container_width=True); st.bar_chart(frame.set_index('approach')[['latency_ms','correction_iterations']])
with explorer:
    st.subheader('Live database schema'); st.json(inspect_schema())
    if st.button('Refresh schema'): st.rerun()
with agent_tab:
    agent_question=st.text_area('Agent question','List students',key='agent_question')
    if st.button('Run SQL agent',type='primary'): st.session_state['agent_outcome']=run_agent(agent_question)
    agent_outcome=st.session_state.get('agent_outcome')
    if agent_outcome:
        st.write('Framework:',agent_outcome.get('framework')); st.code(agent_outcome['sql'],language='sql'); st.json(agent_outcome['actions'])
        if agent_outcome['success']: st.dataframe(agent_outcome['result']['rows'],use_container_width=True); st.info(explain_result(agent_question,agent_outcome['result']))
        else: st.error(agent_outcome['result'].get('error'))
with history_tab:
    st.subheader('Persistent query history'); rows=get_history(100)
    if rows:
        st.dataframe(rows,use_container_width=True); st.download_button('Download history JSON',json.dumps(rows,indent=2),file_name='query_history.json',mime='application/json')
    else: st.info('No queries recorded yet.')
with eval_tab:
    st.subheader('Evaluation dashboard'); reports=sorted(Path('evaluation/reports').glob('**/spider_experiment.json')) if Path('evaluation/reports').exists() else []
    if not reports: st.info('No benchmark report is available. Supply official Spider data and run scripts/run_evaluation.py; unavailable metrics are not shown as zero.')
    for report in reports:
        payload=json.loads(report.read_text(encoding='utf-8')); st.markdown(f'**{report.parent.name}**'); st.write(f"Dataset: {payload.get('dataset')} | Questions: {payload.get('subset_size')} | Seed: {payload.get('selection',{}).get('seed')}")
        summaries=payload.get('summaries',{}); st.dataframe(pd.DataFrame(summaries).T,use_container_width=True); st.download_button('Download JSON report',report.read_bytes(),file_name=report.name,key=str(report))
        csv_path=report.with_suffix('.csv')
        if csv_path.exists(): st.download_button('Download CSV records',csv_path.read_bytes(),file_name=csv_path.name,key=str(csv_path))

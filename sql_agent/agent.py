"""Tool-using SQL agent built as a LangGraph state machine.

Graph:  inspect_schema -> explore_values -> generate_sql -> execute_sql
                                                  ^              |
                                                  |   error and  |
                                             correct_sql <-------+  retries left
                                                                 |
                                                     success or budget spent -> END

Compared with the plain self-correction chain, the agent (a) calls a
value-exploration tool that reads real column values from the database so
filters use literals that actually exist, (b) plans with the structured CoT
prompt, and (c) routes on execution feedback through a conditional edge. All
database access goes through read-only tools; the model never touches the
connection directly.
"""
import re
import sqlite3

from core.config import settings
from database.schema_inspector import inspect_schema, schema_text
from sql_executor.executor import execute_sql
from sql_generator.generator import generate_sql, correct_sql

_TEXT_TYPES = ('CHAR', 'TEXT', 'CLOB', 'VARCHAR', 'STRING')
_SPLIT = re.compile(r'[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+')


def _name_tokens(name):
    return {t.lower() for t in _SPLIT.findall(name.replace('_', ' '))}


def sample_values_sqlite(db_path, schema, question, per_column=3, budget_chars=1200):
    """Distinct sample values of text columns, most question-relevant columns first."""
    q_tokens = {t for t in re.findall(r'[a-z]+', question.lower()) if len(t) > 2}
    candidates = []
    for table, info in schema.items():
        t_tokens = _name_tokens(table)
        for col in info['columns']:
            ctype = (col.get('type') or '').upper()
            if ctype and not any(t in ctype for t in _TEXT_TYPES):
                continue
            score = len(q_tokens & (t_tokens | _name_tokens(col['name'])))
            candidates.append((score, table, col['name']))
    candidates.sort(key=lambda c: -c[0])
    lines, used = [], 0
    try:
        con = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
        con.text_factory = lambda b: b.decode('utf-8', 'replace')
    except sqlite3.Error:
        return ''
    try:
        for _, table, column in candidates:
            try:
                rows = con.execute(f'SELECT DISTINCT "{column}" FROM "{table}" WHERE "{column}" IS NOT NULL LIMIT {int(per_column)}').fetchall()
            except sqlite3.Error:
                continue
            values = [str(r[0])[:30] for r in rows if str(r[0]).strip()]
            if not values:
                continue
            line = f"{table}.{column}: " + ', '.join(repr(v) for v in values)
            if used + len(line) > budget_chars:
                break
            lines.append(line); used += len(line)
    finally:
        con.close()
    return '\n'.join(lines)


class AppDatabaseTools:
    """Tools bound to the application database configured in .env."""
    name = 'app'

    def inspect(self):
        schema = inspect_schema()
        schema.pop('query_history', None)
        return schema, schema_text(schema)

    def sample_values(self, schema, question):
        if not settings.database_url.startswith('sqlite:///'):
            return ''
        from database.connection import sqlite_path
        return sample_values_sqlite(sqlite_path(), schema, question)

    def execute(self, sql):
        return execute_sql(sql)


class SQLiteFileTools:
    """Tools bound to one SQLite file, e.g. a Spider benchmark database."""
    name = 'sqlite-file'

    def __init__(self, db_path, executor):
        self.db_path, self.executor = db_path, executor

    def inspect(self):
        from evaluation.spider_schema import schema_context
        text, schema = schema_context(self.db_path)
        return schema, text

    def sample_values(self, schema, question):
        return sample_values_sqlite(self.db_path, schema, question)

    def execute(self, sql):
        return self.executor(sql)


def _add_usage(state, generated):
    usage = generated.get('usage') or {}
    return {
        'llm_calls': state.get('llm_calls', 0) + generated.get('llm_calls', 0),
        'prompt_tokens': state.get('prompt_tokens', 0) + (usage.get('prompt_tokens') or 0),
        'completion_tokens': state.get('completion_tokens', 0) + (usage.get('completion_tokens') or 0),
    }


def _values_context(samples):
    return ('Sample values from the database (use these exact spellings in filters):\n' + samples) if samples else None


def build_nodes(tools, max_retries):
    def inspect_node(state):
        schema, text = tools.inspect()
        return {'schema': schema, 'schema_text': text,
                'actions': state['actions'] + [{'tool': 'inspect_schema', 'summary': f'Inspected {len(schema)} tables'}]}

    def explore_node(state):
        samples = tools.sample_values(state['schema'], state['question'])
        n = samples.count('\n') + 1 if samples else 0
        return {'samples': samples,
                'actions': state['actions'] + [{'tool': 'sample_values', 'summary': f'Read sample values for {n} text columns'}]}

    def generate_node(state):
        generated = generate_sql(state['question'], 'cot', schema_context=state['schema_text'],
                                 extra_context=_values_context(state.get('samples')))
        meta = {'provider': generated.get('provider'), 'model': generated.get('model')}
        if generated.get('provider_error'): meta['provider_error'] = generated['provider_error']
        return {'sql': generated['sql'], 'initial_sql': generated['sql'], 'plan': generated.get('plan', []), 'provider_meta': meta,
                **_add_usage(state, generated),
                'actions': state['actions'] + [{'tool': 'generate_sql', 'summary': 'Planned tables, joins, filters, aggregation and nesting, then wrote SQL'}]}

    def execute_node(state):
        result = tools.execute(state['sql'])
        label = 'execute_sql' if not state.get('attempts') else 'execute_sql_retry'
        return {'result': result,
                'actions': state['actions'] + [{'tool': label, 'summary': 'Executed through the read-only database tool',
                                                'success': result['success'], 'error': result.get('error')}]}

    def correct_node(state):
        context = state['schema_text'] + ('\n' + _values_context(state['samples']) if state.get('samples') else '')
        repaired = correct_sql(state['question'], state['sql'], state['result'].get('error', ''), 'cot', schema_context=context)
        attempts = state.get('attempts', 0) + 1
        update = {'attempts': attempts, **_add_usage(state, repaired),
                  'actions': state['actions'] + [{'tool': 'correct_sql', 'summary': f'Repaired SQL from the database error (attempt {attempts})',
                                                  'provider': repaired.get('provider')}]}
        new_sql = repaired.get('sql', state['sql'])
        if new_sql.strip() == state['sql'].strip():
            update['stalled'] = True  # the model could not propose a different query
        else:
            update['sql'] = new_sql
            update['plan'] = repaired.get('plan') or state.get('plan', [])
        return update

    def route_after_execute(state):
        if state['result']['success'] or state.get('stalled') or state.get('attempts', 0) >= max_retries:
            return 'end'
        return 'correct'

    def route_after_correct(state):
        return 'end' if state.get('stalled') else 'execute'

    return inspect_node, explore_node, generate_node, execute_node, correct_node, route_after_execute, route_after_correct


def _run_graph(question, tools, max_retries):
    inspect_node, explore_node, generate_node, execute_node, correct_node, after_exec, after_correct = build_nodes(tools, max_retries)
    initial = {'question': question, 'actions': [], 'attempts': 0, 'llm_calls': 0, 'prompt_tokens': 0, 'completion_tokens': 0}
    try:
        from typing import TypedDict
        from langgraph.graph import StateGraph, END

        class AgentState(TypedDict, total=False):
            question: str; schema: dict; schema_text: str; samples: str; sql: str; initial_sql: str; plan: list
            result: dict; actions: list; attempts: int; stalled: bool; provider_meta: dict
            llm_calls: int; prompt_tokens: int; completion_tokens: int

        graph = StateGraph(AgentState)
        for name, fn in (('inspect_schema', inspect_node), ('explore_values', explore_node), ('generate_sql', generate_node),
                         ('execute_sql', execute_node), ('correct_sql', correct_node)):
            graph.add_node(name, fn)
        graph.set_entry_point('inspect_schema')
        graph.add_edge('inspect_schema', 'explore_values')
        graph.add_edge('explore_values', 'generate_sql')
        graph.add_edge('generate_sql', 'execute_sql')
        graph.add_conditional_edges('execute_sql', after_exec, {'correct': 'correct_sql', 'end': END})
        graph.add_conditional_edges('correct_sql', after_correct, {'execute': 'execute_sql', 'end': END})
        return graph.compile().invoke(initial, {'recursion_limit': 10 + 2 * max_retries}), 'langgraph'
    except ImportError:
        # Same nodes and routing, executed as a plain loop when LangGraph is not installed.
        state = dict(initial)
        for node in (inspect_node, explore_node, generate_node, execute_node):
            state.update(node(state))
        while after_exec(state) == 'correct':
            state.update(correct_node(state))
            if after_correct(state) == 'end':
                break
            state.update(execute_node(state))
        return state, 'fallback'


def run_agent_with_tools(question, tools, max_retries=None):
    max_retries = settings.max_correction_attempts if max_retries is None else max_retries
    state, framework = _run_graph(question, tools, max_retries)
    total = state['prompt_tokens'] + state['completion_tokens']
    return {'success': state['result']['success'], 'question': question, 'sql': state['sql'], 'initial_sql': state.get('initial_sql'),
            'result': state['result'], 'actions': state['actions'], 'answer_plan': state.get('plan', []),
            'correction_iterations': state.get('attempts', 0), 'llm_calls': state['llm_calls'],
            'prompt_tokens': state['prompt_tokens'], 'completion_tokens': state['completion_tokens'],
            'total_tokens': total or None, 'framework': framework, **state.get('provider_meta', {})}


def run_agent(question):
    """Run the agent against the application database and record it in query history."""
    outcome = run_agent_with_tools(question, AppDatabaseTools())
    from database.history import record_history
    record_history(question, 'agent', outcome['sql'], outcome['result'], outcome['correction_iterations'])
    return outcome


# Backwards-compatible names used by the API module.
run_langgraph_agent = run_agent
run_agent_fallback = run_agent

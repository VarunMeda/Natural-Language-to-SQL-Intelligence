from database.schema_inspector import schema_text
from core.config import settings
from llm.ollama_provider import OllamaProvider, LLMError, LLMResponseError
from sql_generator.fewshot import select_examples
EXAMPLE=("How many students are in each department?","SELECT d.name AS department, COUNT(s.student_id) AS student_count FROM departments d LEFT JOIN students s ON s.department_id=d.department_id GROUP BY d.department_id, d.name ORDER BY student_count DESC")
def generate_sql(question,strategy="zero-shot", provider=None, schema_context=None, extra_context=None):
    active_provider=provider or settings.llm_provider
    if active_provider.lower() == 'ollama':
        try:
            prompt=build_prompt(question,strategy,schema_context,extra_context=extra_context)
            result=OllamaProvider().generate_json(prompt, system='You are a careful schema-aware SQL generator. Never invent identifiers. Return only JSON.')
            return {'sql':result['sql'].strip().rstrip(';'),'strategy':strategy,'plan':result.get('plan',[]),'prompt':prompt,'llm_calls':1,'provider':'ollama','model':OllamaProvider().model,'usage':result.get('_usage',{})}
        except LLMResponseError as exc:
            # The model answered but produced nothing usable: score it as invalid output, never as heuristic SQL.
            return {'sql':'','strategy':strategy,'plan':[],'prompt':prompt,'llm_calls':1,'provider':'ollama','model':OllamaProvider().model,'usage':{},'model_output_error':str(exc)}
        except LLMError as exc:
            fallback=_heuristic_sql(question,strategy); fallback.update({'provider':'heuristic-fallback','provider_error':str(exc),'llm_calls':1}); return fallback
    return _heuristic_sql(question,strategy)

def _heuristic_sql(question,strategy="zero-shot"):
    q=question.lower().strip()
    if "how many" in q and "department" in q: sql=EXAMPLE[1]; plan=["departments and students","left join","count and group"]
    elif "average" in q and "course" in q: sql="SELECT c.code, c.title, ROUND(AVG(m.score), 2) AS average_score FROM courses c JOIN examinations e ON e.course_id=c.course_id JOIN marks m ON m.exam_id=e.exam_id GROUP BY c.course_id, c.code, c.title ORDER BY average_score DESC"; plan=["courses, examinations, marks","join","average by course"]
    elif "computer science" in q and "enrolled" in q: sql="SELECT DISTINCT s.name, c.code, c.title FROM students s JOIN enrollments e ON e.student_id=s.student_id JOIN courses c ON c.course_id=e.course_id JOIN departments d ON d.department_id=c.department_id WHERE d.name='Computer Science' ORDER BY s.name"; plan=["four-table join","department filter","distinct"]
    elif "above" in q and "average" in q: sql="SELECT s.name, ROUND(AVG(m.score), 2) AS average_score FROM students s JOIN marks m ON m.student_id=s.student_id GROUP BY s.student_id, s.name HAVING AVG(m.score) > (SELECT AVG(score) FROM marks) ORDER BY average_score DESC"; plan=["student averages","overall-average subquery","HAVING"]
    elif "list" in q and "student" in q: sql="SELECT student_id, name, email, department_id FROM students ORDER BY name"; plan=["students","identity columns","sort"]
    else: sql="SELECT name FROM students ORDER BY name"; plan=["fallback demonstration query"]
    return {"sql":sql,"strategy":strategy,"plan":plan,"prompt":build_prompt(question,strategy),"llm_calls":0,"provider":"heuristic","model":None,"usage":{}}
JSON_CONTRACT='Respond with JSON only, exactly in this shape: {"plan": ["short step", ...], "sql": "one SQL statement"}.'
COT_STEPS=(
    "Before writing SQL, plan it step by step in the plan list:\n"
    "1. Tables: which tables hold the requested columns and conditions.\n"
    "2. Joins: the foreign-key path connecting those tables (join only what is needed).\n"
    "3. Filters: WHERE conditions, with exact literal values.\n"
    "4. Aggregation: GROUP BY / COUNT / AVG / MAX and any HAVING condition.\n"
    "5. Nesting: whether a subquery, NOT IN, EXCEPT, INTERSECT or UNION is required.\n"
    "6. Output: selected columns, ORDER BY and LIMIT.\n"
    "Keep each step to one short line, then write the SQL that follows the plan."
)


def build_prompt(question,strategy,schema_context=None,examples_source=None,extra_context=None):
    base=(f"Question: {question}\nSchema:\n{schema_context or schema_text()}\n"
          + (f"{extra_context}\n" if extra_context else "")
          + "Dialect: SQLite/PostgreSQL-compatible\nReturn one read-only SQL statement. Use only tables and columns from the schema. "
          "Use explicit AS when assigning table aliases; repeat aggregate expressions in ORDER BY instead of ordering by a SELECT alias.")
    if strategy=="few-shot":
        source=examples_source or ('spider' if schema_context else 'demo')
        examples=select_examples(question,k=3,source=source)
        shots="\n\n".join(f"Q: {e['question']}\nSQL: {e['query']}" for e in examples)
        return base+f"\nExamples of similar questions (they may use a different database: copy the SQL pattern, but use only tables and columns from the schema above):\n{shots}\n"+JSON_CONTRACT
    if strategy in ("cot","chain-of-thought"):
        return base+"\n"+COT_STEPS+"\n"+JSON_CONTRACT
    return base+"\nDo not invent tables or columns. Leave plan empty.\n"+JSON_CONTRACT

def correct_sql(question, failed_sql, error, strategy='zero-shot', schema_context=None):
    if settings.llm_provider.lower() != 'ollama':
        return {'sql':failed_sql,'plan':['Mock correction provider enabled'],'provider':'heuristic','llm_calls':0,'usage':{}}
    schema=schema_context or schema_text()
    prompt=f"""Repair one read-only SQL query.
Original question: {question}
Schema:
{schema}
Failed SQL:
{failed_sql}
Database error:
{error}
Return JSON only, in the shape {{"plan": ["what was wrong", "fix"], "sql": "..."}}. The sql value must contain one SELECT or WITH statement; do not explain or expose hidden reasoning."""
    try:
        result=OllamaProvider().generate_json(prompt, system='You repair SQL using only the supplied schema. Return JSON only.')
        return {'sql':result['sql'].strip().rstrip(';'),'plan':result.get('plan',[]),'provider':'ollama','llm_calls':1,'usage':result.get('_usage',{})}
    except LLMResponseError as exc:
        return {'sql':failed_sql,'plan':['Model reply was unusable'],'provider':'ollama','llm_calls':1,'usage':{},'model_output_error':str(exc)}
    except LLMError as exc:
        return {'sql':failed_sql,'plan':['Ollama correction unavailable'], 'provider':'heuristic-fallback','provider_error':str(exc),'llm_calls':1,'usage':{}}


"""Agent, few-shot retrieval and benchmark wiring, tested on a tiny Spider-shaped fixture with a mocked LLM."""
import dataclasses
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.config import settings
from llm.ollama_provider import LLMError

OLLAMA_SETTINGS = dataclasses.replace(settings, llm_provider='ollama')

TRAIN = [
    {'db_id': 'other', 'question': 'Which singers have not performed in any concert?', 'query': 'SELECT name FROM singer WHERE singer_id NOT IN (SELECT singer_id FROM concert)'},
    {'db_id': 'other', 'question': 'How many cars are there for each maker?', 'query': 'SELECT maker, COUNT(*) FROM cars GROUP BY maker'},
    {'db_id': 'other', 'question': 'What is the average age of all dogs?', 'query': 'SELECT AVG(age) FROM dogs'},
    {'db_id': 'other', 'question': 'List the names of pilots older than 30.', 'query': 'SELECT name FROM pilot WHERE age > 30'},
]
DEV = [
    {'db_id': 'pets', 'question': 'How many pets does each owner have?', 'query': 'SELECT owner, COUNT(*) FROM pet GROUP BY owner'},
    {'db_id': 'pets', 'question': 'How many pets are of type Dog?', 'query': "SELECT COUNT(*) FROM pet WHERE pet_type = 'Dog'"},
]


def make_fixture(root):
    data = Path(root) / 'spider_data'; db_dir = data / 'database' / 'pets'; db_dir.mkdir(parents=True)
    (data / 'dev.json').write_text(json.dumps(DEV)); (data / 'train_spider.json').write_text(json.dumps(TRAIN))
    con = sqlite3.connect(db_dir / 'pets.sqlite')
    con.execute('CREATE TABLE pet (pet_id INTEGER PRIMARY KEY, name TEXT, pet_type TEXT, owner TEXT)')
    con.executemany('INSERT INTO pet VALUES (?,?,?,?)', [(1, 'Rex', 'Dog', 'Ana'), (2, 'Tom', 'Cat', 'Ana'), (3, 'Max', 'Dog', 'Bo')])
    con.commit(); con.close()
    return data


def fake_llm(prompts):
    """Scripted model: wrong literal first ('dog'), correct SQL after seeing the error/sample values."""
    def generate_json(prompt, system=None):
        prompts.append(prompt)
        if 'Failed SQL' in prompt:
            sql = "SELECT COUNT(*) FROM pet WHERE pet_type = 'Dog'"
        elif 'each owner' in prompt:
            sql = 'SELECT owner, COUNT(*) FROM pet GROUP BY owner'
        else:
            sql = "SELECT COUNT(*) FROM pets WHERE pet_type = 'Dog'"  # unknown table -> execution error
        return {'sql': sql, 'plan': ['step'], '_usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}}
    return generate_json


class FewShotTests(unittest.TestCase):
    def test_retrieves_structurally_similar_training_examples(self):
        from sql_generator import fewshot
        with tempfile.TemporaryDirectory() as tmp:
            data = make_fixture(tmp)
            with patch.dict('os.environ', {'SPIDER_TRAIN_JSON': str(data / 'train_spider.json')}):
                fewshot._load_bank.cache_clear()
                picked = fewshot.select_examples('Which students have not taken any exam?', k=2, source='spider')
                self.assertEqual(picked[0]['bank'], 'spider-train'); self.assertIn('NOT IN', picked[0]['query'])
                picked = fewshot.select_examples('How many books are there for each author?', k=1, source='spider')
                self.assertIn('GROUP BY', picked[0]['query'])
            fewshot._load_bank.cache_clear()

    def test_demo_bank_used_without_spider(self):
        from sql_generator.fewshot import select_examples
        picked = select_examples('Which students are not enrolled in any course?', k=1, source='demo')
        self.assertEqual(picked[0]['bank'], 'demo'); self.assertIn('NOT IN', picked[0]['query'])

    def test_cot_prompt_plans_joins_aggregation_and_nesting(self):
        from sql_generator.generator import build_prompt
        prompt = build_prompt('q', 'cot', 'TABLE t (id INTEGER)')
        for word in ('Joins', 'Aggregation', 'Nesting', '"plan"', '"sql"'):
            self.assertIn(word, prompt)


class AgentTests(unittest.TestCase):
    def test_agent_explores_values_and_self_corrects_on_spider_db(self):
        from evaluation.benchmark_runner import execute_benchmark_sql
        from evaluation.spider_schema import inspect_spider_database
        from sql_agent.agent import SQLiteFileTools, run_agent_with_tools
        prompts = []
        with tempfile.TemporaryDirectory() as tmp:
            db = make_fixture(tmp) / 'database' / 'pets' / 'pets.sqlite'; schema = inspect_spider_database(db)
            tools = SQLiteFileTools(db, lambda sql: execute_benchmark_sql(sql, db, schema))
            with patch('sql_generator.generator.settings', OLLAMA_SETTINGS), \
                 patch('sql_generator.generator.OllamaProvider.generate_json', side_effect=fake_llm(prompts)):
                out = run_agent_with_tools('How many pets are of type Dog?', tools, max_retries=3)
        self.assertTrue(out['success']); self.assertEqual(out['result']['rows'], [(2,)])
        self.assertEqual(out['correction_iterations'], 1); self.assertEqual(out['llm_calls'], 2); self.assertEqual(out['total_tokens'], 30)
        self.assertEqual([a['tool'] for a in out['actions']],
                         ['inspect_schema', 'sample_values', 'generate_sql', 'execute_sql', 'correct_sql', 'execute_sql_retry'])
        self.assertIn("pet.pet_type: 'Dog', 'Cat'", prompts[0])  # value tool output reached the model
        self.assertIn('Joins', prompts[0])                           # structured CoT prompt

    def test_agent_stops_at_retry_budget(self):
        from sql_agent.agent import SQLiteFileTools, run_agent_with_tools
        calls = {'n': 0}
        def always_bad(prompt, system=None):
            calls['n'] += 1; return {'sql': f'SELECT nope{calls["n"]} FROM pet', 'plan': [], '_usage': {}}
        with tempfile.TemporaryDirectory() as tmp:
            from evaluation.benchmark_runner import execute_benchmark_sql
            from evaluation.spider_schema import inspect_spider_database
            db = make_fixture(tmp) / 'database' / 'pets' / 'pets.sqlite'; schema = inspect_spider_database(db)
            tools = SQLiteFileTools(db, lambda sql: execute_benchmark_sql(sql, db, schema))
            with patch('sql_generator.generator.settings', OLLAMA_SETTINGS), \
                 patch('sql_generator.generator.OllamaProvider.generate_json', side_effect=always_bad):
                out = run_agent_with_tools('anything', tools, max_retries=2)
        self.assertFalse(out['success']); self.assertEqual(out['correction_iterations'], 2); self.assertEqual(calls['n'], 3)

    def test_app_agent_runs_on_demo_database(self):
        from database.init_db import initialize_database
        from sql_agent.agent import run_agent
        initialize_database()
        out = run_agent('List students')
        self.assertTrue(out['success'])
        self.assertIn('sample_values', [a['tool'] for a in out['actions']])


class BenchmarkTests(unittest.TestCase):
    def run_experiment(self, strategies, side_effect):
        from evaluation.benchmark_runner import run_spider_experiment
        from sql_generator import fewshot
        prompts = []
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        data = make_fixture(tmp.name); out = Path(tmp.name) / 'reports'
        with patch.dict('os.environ', {'SPIDER_TRAIN_JSON': str(data / 'train_spider.json')}), \
             patch('sql_generator.generator.settings', OLLAMA_SETTINGS), \
             patch('sql_generator.generator.OllamaProvider.generate_json', side_effect=side_effect or fake_llm(prompts)):
            fewshot._load_bank.cache_clear()
            try:
                report = run_spider_experiment(data / 'dev.json', data / 'database', out, 2, 42, strategies, resume=False)
            finally:
                fewshot._load_bank.cache_clear()
        return report, prompts, out

    def test_agent_mode_uses_real_agent_and_differs_from_self_correction(self):
        report, prompts, _ = self.run_experiment(['few-shot', 'self-correction', 'agent'], None)
        agent = [r for r in report['records'] if r['strategy'] == 'agent']
        selfc = [r for r in report['records'] if r['strategy'] == 'self-correction']
        self.assertTrue(all(r['agent_framework'] == 'langgraph' for r in agent))
        self.assertTrue(all('sample_values' in r['agent_actions'] for r in agent))
        self.assertTrue(all(r['execution_correct'] for r in agent + selfc))
        self.assertEqual(report['summaries']['agent']['execution_accuracy_pct'], 100.0)
        self.assertIn('average_correction_iterations', report['summaries']['self-correction'])
        few_shot_prompts = [p for p in prompts if 'Examples of similar questions' in p]
        self.assertTrue(few_shot_prompts and 'GROUP BY maker' in few_shot_prompts[0])  # retrieved from train split

    def test_run_stops_instead_of_recording_fallback_sql(self):
        def offline(prompt, system=None): raise LLMError('Ollama is unavailable')
        with self.assertRaises(RuntimeError):
            self.run_experiment(['zero-shot'], offline)


if __name__ == '__main__':
    unittest.main()

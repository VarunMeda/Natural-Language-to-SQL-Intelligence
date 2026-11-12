import unittest
from database.init_db import initialize_database
from database.schema_inspector import inspect_schema
from sql_generator.generator import generate_sql
from sql_validator.validator import validate_sql
from sql_executor.executor import execute_sql
from self_correction.correction_chain import run_self_correction
from sql_agent.agent import run_agent
from evaluation.metrics import exact_match,execution_accuracy,summarize
from database.history import get_history,initialize_history
class CoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):initialize_database(reset=True)
    def test_schema(self):self.assertIn('students',inspect_schema())
    def test_strategies(self):
        for s in ('zero-shot','few-shot','cot'):self.assertTrue(generate_sql('How many students are in each department?',s)['sql'].startswith('SELECT'))
    def test_safety(self):self.assertFalse(validate_sql('DROP TABLE students').valid); self.assertFalse(validate_sql('SELECT 1; SELECT 2').valid); self.assertTrue(validate_sql('SELECT * FROM students',inspect_schema()).valid)
    def test_execute(self):
        r=execute_sql('SELECT name FROM students ORDER BY name'); self.assertTrue(r['success']); self.assertEqual(len(r['rows']),5)
    def test_flows(self):self.assertTrue(run_self_correction('How many students are in each department?')['success']); self.assertTrue(run_agent('List students')['success'])
    def test_metrics(self):self.assertTrue(exact_match(' SELECT 1; ','select 1')); self.assertTrue(execution_accuracy([{'a':1}],[{'a':1}])); self.assertEqual(summarize([{'execution_success':True,'execution_correct':True,'exact_match':True}])['execution_accuracy_pct'],100.0)
    def test_history(self):
        before=len(get_history()); self.assertTrue(run_self_correction('List students')['success']); self.assertGreater(len(get_history()),before)
    def test_security_edges(self):
        self.assertFalse(validate_sql('SELECT * FROM not_a_table',inspect_schema()).valid); self.assertFalse(validate_sql('WITH x AS (DELETE FROM students RETURNING *) SELECT * FROM x').valid)

class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        initialize_database(); initialize_history()
    def test_api_routes(self):
        from fastapi.testclient import TestClient
        from app.backend.main import app
        client=TestClient(app)
        self.assertEqual(client.get('/api/health').status_code,200)
        self.assertEqual(client.get('/api/database/schema').status_code,200)
        response=client.post('/api/sql/correct',json={'question':'List students','strategy':'zero-shot'})
        self.assertEqual(response.status_code,200); self.assertTrue(response.json()['success'])
if __name__=='__main__':unittest.main()


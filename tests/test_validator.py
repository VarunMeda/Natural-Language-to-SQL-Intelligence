import unittest
from database.init_db import initialize_database
from database.schema_inspector import inspect_schema
from sql_executor.executor import execute_sql
from sql_validator.validator import validate_sql
from self_correction.correction_chain import run_self_correction


class ValidatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        initialize_database(); cls.schema=inspect_schema()

    def assertValid(self, sql):
        check=validate_sql(sql,self.schema); self.assertTrue(check.valid,check.errors)

    def assertInvalid(self, sql):
        self.assertFalse(validate_sql(sql,self.schema).valid)

    def test_cte_names_are_not_unknown_tables(self):
        self.assertValid('WITH t AS (SELECT * FROM students) SELECT COUNT(*) FROM t')
        self.assertValid('WITH a AS (SELECT student_id FROM students), b AS (SELECT * FROM a) SELECT * FROM b JOIN marks m ON m.student_id=b.student_id')
        result=execute_sql('WITH t AS (SELECT * FROM students) SELECT COUNT(*) AS n FROM t')
        self.assertTrue(result['success'],result['error']); self.assertEqual(result['rows'][0]['n'],5)

    def test_set_operations_are_read_only(self):
        self.assertValid('SELECT name FROM students UNION SELECT name FROM instructors')
        self.assertValid('SELECT student_id FROM students EXCEPT SELECT student_id FROM marks')
        self.assertValid('SELECT student_id FROM students INTERSECT SELECT student_id FROM enrollments')

    def test_safe_functions_and_literals_allowed(self):
        self.assertValid("SELECT REPLACE(name,'a','b') FROM students")
        self.assertValid("SELECT name FROM students WHERE name <> 'update; drop table students'")

    def test_unknown_tables_still_rejected(self):
        self.assertInvalid('WITH t AS (SELECT 1) SELECT * FROM not_a_table')

    def test_writes_still_blocked(self):
        for sql in ('DROP TABLE students','DELETE FROM students','UPDATE students SET name=1',
                    "INSERT INTO students VALUES (9,'x','x',1)","REPLACE INTO students VALUES (9,'x','x',1)",
                    'WITH x AS (DELETE FROM students RETURNING *) SELECT * FROM x',
                    'SELECT 1; DROP TABLE students','PRAGMA table_info(students)','ATTACH DATABASE "x" AS y'):
            self.assertInvalid(sql)


class MetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): initialize_database()

    def test_self_correction_reports_provider_and_calls(self):
        outcome=run_self_correction('How many students are in each department?')
        self.assertIn(outcome['provider'],('ollama','heuristic','heuristic-fallback'))
        self.assertIn('llm_calls',outcome); self.assertIn('total_tokens',outcome)

    def test_llm_timeout_is_separate(self):
        from core.config import settings
        from llm.ollama_provider import OllamaProvider
        self.assertEqual(OllamaProvider().timeout,settings.llm_timeout_seconds)


if __name__=='__main__': unittest.main()

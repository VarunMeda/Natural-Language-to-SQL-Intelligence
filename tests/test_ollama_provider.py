import json
import unittest
from unittest.mock import patch

from llm.ollama_provider import OllamaProvider
from sql_generator.generator import generate_sql


class FakeResponse:
    def __init__(self, payload): self.payload=payload
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self): return json.dumps(self.payload).encode()


class OllamaMockTests(unittest.TestCase):
    @patch('llm.ollama_provider.urllib.request.urlopen')
    def test_structured_generation_response(self, urlopen):
        urlopen.return_value=FakeResponse({'response':'{"sql":"SELECT name FROM students","plan":["students"]}','prompt_eval_count':10,'eval_count':5})
        result=OllamaProvider().generate_json('return SQL')
        self.assertEqual(result['sql'],'SELECT name FROM students'); self.assertEqual(result['_usage']['total_tokens'],15)

    @patch('sql_generator.generator.OllamaProvider.generate_json')
    def test_generator_uses_mocked_ollama(self, generate_json):
        generate_json.return_value={'sql':'SELECT name FROM students','plan':['students'],'_usage':{'total_tokens':3}}
        result=generate_sql('List students', 'zero-shot', provider='ollama')
        self.assertEqual(result['provider'],'ollama'); self.assertEqual(result['sql'],'SELECT name FROM students'); generate_json.assert_called_once()


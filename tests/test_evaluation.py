import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evaluation.dataset_loader import load_spider_subset
from evaluation.benchmark_runner import official_scores, run_spider_experiment
from evaluation.spider_schema import database_path, inspect_spider_database

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'evaluation/datasets/spider_official/spider_data'

class EvaluationTests(unittest.TestCase):
    def test_reproducible_subset(self):
        first=load_spider_subset(DATA/'dev.json',3,42); second=load_spider_subset(DATA/'dev.json',3,42)
        self.assertEqual([x['source_index'] for x in first],[x['source_index'] for x in second]); self.assertEqual(len(first),3)

    def test_database_mapping_and_schema(self):
        item=json.loads((DATA/'dev.json').read_text())[0]; path=database_path(DATA/'database',item['db_id']); schema=inspect_spider_database(path)
        self.assertTrue(schema); self.assertTrue(all('columns' in value for value in schema.values()))

    def test_official_exact_match_gold_against_gold(self):
        item=json.loads((DATA/'dev.json').read_text())[228]; path=database_path(DATA/'database',item['db_id']); result=official_scores(item['query'],item['query'],path,None)
        self.assertTrue(result['exact_match']); self.assertIsNone(result['official_error'])

    @patch('evaluation.benchmark_runner.official_scores',return_value={'exact_match':True,'complexity':'easy','official_error':None})
    @patch('evaluation.benchmark_runner.generate_sql',return_value={'sql':'SELECT 1','llm_calls':0,'usage':{}})
    def test_report_generation_with_mocked_model(self, _generate, _official):
        with tempfile.TemporaryDirectory() as directory:
            report=run_spider_experiment(DATA/'dev.json',DATA/'database',directory,1,42,['zero-shot'],resume=False)
            self.assertEqual(report['subset_size'],1); self.assertTrue((Path(directory)/'spider_experiment.csv').exists()); self.assertTrue((Path(directory)/'spider_checkpoint.jsonl').exists())

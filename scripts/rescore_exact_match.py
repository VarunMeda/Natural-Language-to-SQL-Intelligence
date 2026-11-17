"""Recompute Spider exact-match scores for an existing report without re-running the model.

Usage: python scripts/rescore_exact_match.py [--report-dir evaluation/reports]
"""
import argparse
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from evaluation.benchmark_runner import rescore_report

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report-dir',type=Path,default=ROOT/'evaluation'/'reports')
    parser.add_argument('--data-root',type=Path,default=ROOT/'evaluation'/'datasets'/'spider_official'/'spider_data')
    args=parser.parse_args()
    report,changed=rescore_report(args.report_dir,args.data_root/'database')
    print(f'Rescored {len(report["records"])} records ({changed} changed).')
    for strategy,summary in report['summaries'].items():
        print(strategy,{k:summary[k] for k in ('execution_accuracy_pct','exact_match_accuracy_pct','average_correction_iterations','exact_match_parse_errors')})

if __name__=='__main__': main()

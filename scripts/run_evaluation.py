import argparse
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from evaluation.benchmark_runner import run_spider_experiment

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_DATA=ROOT/'evaluation'/'datasets'/'spider_official'/'spider_data'

def main():
    parser=argparse.ArgumentParser(description='Run the reproducible Spider experiment sequentially with checkpointing.')
    parser.add_argument('--data-root',type=Path,default=DEFAULT_DATA)
    parser.add_argument('--count',type=int,default=100)
    parser.add_argument('--seed',type=int,default=42)
    parser.add_argument('--strategies',nargs='+',default=['zero-shot','few-shot','cot','self-correction','agent'])
    parser.add_argument('--output-dir',type=Path,default=ROOT/'evaluation'/'reports')
    parser.add_argument('--no-resume',action='store_true')
    args=parser.parse_args(); dev=args.data_root/'dev.json'; db=args.data_root/'database'
    if not dev.exists(): raise SystemExit(f'Official Spider dev.json not found: {dev}')
    if not db.exists(): raise SystemExit(f'Official Spider database directory not found: {db}')
    report=run_spider_experiment(dev,db,args.output_dir,args.count,args.seed,args.strategies,resume=not args.no_resume)
    for strategy,summary in report['summaries'].items(): print(strategy,summary)

if __name__=='__main__': main()

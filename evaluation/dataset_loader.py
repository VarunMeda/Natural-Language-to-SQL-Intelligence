import json
import random
from pathlib import Path

def load_spider(path):
    source=Path(path); data=json.loads(source.read_text(encoding='utf-8'))
    if not isinstance(data,list) or not data: raise ValueError(f'Invalid Spider split: {source}')
    return [{**row,'source_index':idx} for idx,row in enumerate(data)]

def load_spider_subset(path,count=100,seed=42):
    data=load_spider(path)
    if count>len(data): raise ValueError(f'Requested {count} questions but Spider split contains only {len(data)}')
    rng=random.Random(seed); selected=rng.sample(data,count)
    return sorted(selected,key=lambda x:x['source_index'])

def write_subset_manifest(records,path,seed,count):
    payload={'dataset':'Spider 1.0','source_split':'dev.json','selection_method':'random.sample followed by source-index ordering','seed':seed,'count':count,'source_indices':[r['source_index'] for r in records],'questions':[{'source_index':r['source_index'],'db_id':r['db_id'],'question':r['question'],'query':r['query']} for r in records]}
    Path(path).write_text(json.dumps(payload,indent=2),encoding='utf-8')

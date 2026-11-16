"""Few-shot example selection.

For the demo university database a small hand-written bank is used. For Spider
evaluation, examples are retrieved from the official *training* split
(train_spider.json), which shares no databases with dev.json, so there is no
test leakage. Retrieval is a dependency-free lexical similarity over the
question text with schema-specific words masked, so the examples teach SQL
*patterns* (joins, grouping, nesting) rather than a particular database.
"""
import json
import math
import os
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPIDER_TRAIN = ROOT / 'evaluation' / 'datasets' / 'spider_official' / 'spider_data' / 'train_spider.json'

DEMO_EXAMPLES = [
    {'question': 'How many students are in each department?',
     'query': 'SELECT d.name AS department, COUNT(s.student_id) AS student_count FROM departments AS d LEFT JOIN students AS s ON s.department_id = d.department_id GROUP BY d.department_id, d.name ORDER BY COUNT(s.student_id) DESC'},
    {'question': 'What is the average mark for each course?',
     'query': 'SELECT c.title, AVG(m.score) AS average_score FROM courses AS c JOIN examinations AS e ON e.course_id = c.course_id JOIN marks AS m ON m.exam_id = e.exam_id GROUP BY c.course_id, c.title'},
    {'question': 'Which students scored above the overall average mark?',
     'query': 'SELECT s.name FROM students AS s JOIN marks AS m ON m.student_id = s.student_id GROUP BY s.student_id, s.name HAVING AVG(m.score) > (SELECT AVG(score) FROM marks)'},
    {'question': 'List the students who are not enrolled in any course.',
     'query': 'SELECT name FROM students WHERE student_id NOT IN (SELECT student_id FROM enrollments)'},
    {'question': 'Which instructor teaches the most courses?',
     'query': 'SELECT i.name FROM instructors AS i JOIN courses AS c ON c.instructor_id = i.instructor_id GROUP BY i.instructor_id, i.name ORDER BY COUNT(*) DESC LIMIT 1'},
]

# Words that signal SQL structure; they are kept even when they look generic.
STRUCTURE_WORDS = {
    'how', 'many', 'number', 'count', 'average', 'mean', 'total', 'sum', 'maximum', 'max', 'minimum', 'min',
    'most', 'least', 'highest', 'lowest', 'largest', 'smallest', 'each', 'every', 'per', 'all', 'both', 'either',
    'not', 'no', 'never', 'without', 'except', 'but', 'and', 'or', 'more', 'less', 'than', 'greater', 'fewer',
    'above', 'below', 'at', 'least', 'distinct', 'different', 'order', 'sorted', 'descending', 'ascending',
    'top', 'first', 'last', 'between', 'same', 'other', 'any', 'only', 'which', 'who', 'what', 'list', 'show',
    'find', 'give', 'return', 'name', 'names', 'id', 'ids', 'average', 'percentage', 'oldest', 'youngest',
}
_WORD = re.compile(r"[a-z]+")


def _tokens(text):
    return _WORD.findall(text.lower())


def _features(question):
    """Bag of structure words plus word bigrams, so 'how many' and 'not in' carry weight."""
    words = _tokens(question)
    feats = Counter(w for w in words if w in STRUCTURE_WORDS)
    feats.update(f'{a}_{b}' for a, b in zip(words, words[1:]) if a in STRUCTURE_WORDS or b in STRUCTURE_WORDS)
    feats.update(f'w:{w}' for w in words if w not in STRUCTURE_WORDS and len(w) > 2)  # weak content signal
    return feats


def _cosine(a, b):
    common = set(a) & set(b)
    if not common:
        return 0.0
    dot = sum(a[k] * b[k] for k in common)
    return dot / (math.sqrt(sum(v * v for v in a.values())) * math.sqrt(sum(v * v for v in b.values())))


@lru_cache(maxsize=2)
def _load_bank(path_str):
    path = Path(path_str)
    if not path.exists():
        return ()
    rows = json.loads(path.read_text(encoding='utf-8'))
    return tuple((row['question'], row['query'], _features(row['question'])) for row in rows)


def spider_train_path():
    return Path(os.getenv('SPIDER_TRAIN_JSON', str(DEFAULT_SPIDER_TRAIN)))


def select_examples(question, k=3, source='demo'):
    """Return up to k {'question','query'} examples most similar to the question.

    source='spider' uses train_spider.json when present and falls back to the
    demo bank otherwise; the returned list says which bank was used.
    """
    bank = ()
    if source == 'spider':
        bank = _load_bank(str(spider_train_path()))
    used = 'spider-train' if bank else 'demo'
    if not bank:
        bank = tuple((e['question'], e['query'], _features(e['question'])) for e in DEMO_EXAMPLES)
    target = _features(question)
    scored = sorted(bank, key=lambda row: _cosine(target, row[2]), reverse=True)
    picked, seen = [], set()
    for q, sql, _ in scored:
        if q.strip().lower() == question.strip().lower() or sql in seen:
            continue
        picked.append({'question': q, 'query': sql, 'bank': used}); seen.add(sql)
        if len(picked) == k:
            break
    return picked

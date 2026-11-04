"""Offline aggregation; never called by request handling."""
from group_watch.utils.time import BEIJING
from group_watch.utils.files import atomic_json, atomic_write
from datetime import datetime
import json
from pathlib import Path

STATS_EVERY = 50

def _review_entry(path):
    try:
        entry = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if not isinstance(entry, dict) or entry.get('scope') != 'automatic-review' or entry.get('status') != 'received':
        return None
    return entry


def _candidate_results(entry):
    messages = (entry.get('input') or {}).get('messages') or []
    prompt = next((m.get('content') for m in messages
                   if isinstance(m, dict) and m.get('role') == 'user'), None)
    if not isinstance(prompt, str):
        return []
    try:
        payload = json.loads(prompt)
    except ValueError:
        return []
    rules = {c.get('id'): c.get('rule') for c in payload.get('candidates') or [] if isinstance(c, dict)}
    choices = (entry.get('output') or {}).get('choices') or []
    content = ((choices[0] or {}).get('message') or {}).get('content') if choices else None
    try:
        results = json.loads(content).get('results') if isinstance(content, str) else []
    except (ValueError, AttributeError):
        return []
    return [(rules.get(row.get('id')), row.get('verdict')) for row in results or []
            if isinstance(row, dict) and rules.get(row.get('id')) and row.get('verdict') in ('clear', 'violation', 'unsure')]


def collect_stats(root):
    """Aggregate per-rule verdicts from successful automatic-review logs."""
    root = Path(root)
    paths = list((root / 'automatic-review').rglob('*.json'))
    requests, rules = 0, {}
    for path in paths:
        entry = _review_entry(path)
        rows = _candidate_results(entry) if entry else []
        if not rows:
            continue
        requests += 1
        for rule, verdict in rows:
            row = rules.setdefault(rule, {'candidates': 0, 'clear': 0, 'violation': 0, 'unsure': 0})
            row['candidates'] += 1
            row[verdict] += 1
    for row in rules.values():
        row['clear_rate'] = round(row['clear'] / row['candidates'], 3) if row['candidates'] else None
    ordered = dict(sorted(rules.items(), key=lambda item: (-item[1]['candidates'], item[0])))
    return {'generated_at': datetime.now(BEIJING).isoformat(timespec='seconds'),
            'requests': requests,
            'candidates': sum(row['candidates'] for row in rules.values()),
            'verdicts': {verdict: sum(row[verdict] for row in rules.values())
                         for verdict in ('clear', 'violation', 'unsure')},
            'rules': ordered}


def write_stats(root):
    stats = collect_stats(root)
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    atomic_json(root / 'ds-stats.json', stats)
    lines = ['# DS 复核统计', '',
             f"- 生成时间：{stats['generated_at']}",
             f"- 自动复核请求：{stats['requests']}",
             f"- 候选：{stats['candidates']}（clear {stats['verdicts']['clear']} / "
             f"violation {stats['verdicts']['violation']} / unsure {stats['verdicts']['unsure']}）",
             '- 统计范围：automatic-review 日期分区；由外部工具读取现有日志生成', '',
             '| rule | 候选 | clear | violation | unsure | clear率 |',
             '| --- | ---: | ---: | ---: | ---: | ---: |']
    for rule, row in stats['rules'].items():
        rate = f"{row['clear_rate'] * 100:.1f}%" if row['clear_rate'] is not None else '-'
        lines.append(f"| {rule} | {row['candidates']} | {row['clear']} | {row['violation']} | {row['unsure']} | {rate} |")
    atomic_write(root / 'ds-stats.md', ('\n'.join(lines) + '\n').encode('utf-8'))
    return stats


def maybe_write_stats(root):
    folder = Path(root) / 'automatic-review'
    total = sum(1 for _ in folder.rglob('*.json')) if folder.exists() else 0
    if total and total % STATS_EVERY == 0:
        write_stats(root)

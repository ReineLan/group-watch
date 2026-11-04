import json

from group_watch.ds.stats import collect_stats
from group_watch.ds.stats import maybe_write_stats


def review_log(candidate_id, rule, verdict):
    prompt = {'messages': [], 'candidates': [{'id': candidate_id, 'rule': rule}]}
    content = json.dumps({'results': [{'id': candidate_id, 'verdict': verdict}]})
    return {'scope': 'automatic-review', 'status': 'received',
            'input': {'messages': [{'role': 'system', 'content': ''},
                                   {'role': 'user', 'content': json.dumps(prompt)}]},
            'output': {'choices': [{'message': {'content': content}}]}}


def test_collect_stats_merges_partitioned_review_logs(tmp_path):
    root = tmp_path / 'logs' / 'ds-requests'
    folder = root / 'automatic-review' / '2026-11-03'
    folder.mkdir(parents=True)
    (folder / 'a.json').write_text(json.dumps(review_log('a', 'ad', 'clear')), encoding='utf-8')
    (folder / 'b.json').write_text(json.dumps(review_log('b', 'ad', 'violation')), encoding='utf-8')
    (root / 'registration.json').write_text(json.dumps(
        {'scope': 'registration', 'status': 'received'}), encoding='utf-8')

    stats = collect_stats(root)

    assert stats['requests'] == 2
    assert stats['candidates'] == 2
    assert stats['verdicts'] == {'clear': 1, 'violation': 1, 'unsure': 0}
    assert stats['rules']['ad'] == {'candidates': 2, 'clear': 1, 'violation': 1,
                                    'unsure': 0, 'clear_rate': 0.5}


def test_stats_are_written_on_every_fiftieth_review(tmp_path):
    root = tmp_path / 'logs' / 'ds-requests'
    folder = root / 'automatic-review' / '2026-11-03'
    folder.mkdir(parents=True)
    for index in range(49):
        (folder / f'{index}.json').write_text('{}', encoding='utf-8')
    maybe_write_stats(root)
    assert not (root / 'ds-stats.json').exists()

    (folder / 'review.json').write_text(json.dumps(review_log('a', 'ad', 'clear')), encoding='utf-8')
    maybe_write_stats(root)

    stats = json.loads((root / 'ds-stats.json').read_text(encoding='utf-8'))
    assert stats['candidates'] == 1 and stats['rules']['ad']['clear'] == 1
    assert '| ad | 1 | 1 | 0 | 0 | 100.0% |' in (root / 'ds-stats.md').read_text(encoding='utf-8')

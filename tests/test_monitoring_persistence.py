"""Exercise actual ingest/review paths; do not seed cases with invented SQL."""
import asyncio
import json
import time

import httpx
import pytest
from pydantic import SecretStr

from group_watch.monitoring.service import Monitor
from group_watch.settings import Settings


def config(tmp_path):
    return Settings(db_path=str(tmp_path / 'watch.sqlite3'), local_env=str(tmp_path / '.env'),
                    settings_file=str(tmp_path / 'rules.json'), groups=[100000001],
                    live_rooms={20: '直播间'}, ds_key=SecretStr('fixture-only'))


def event():
    return dict(post_type='message', message_type='group', group_id=100000001,
                user_id=12345, message_id='own-1', time=time.time(), message='123456',
                sender={'nickname': ''})


def test_unreviewed_candidate_is_not_a_persistent_case(tmp_path):
    monitor = Monitor(config(tmp_path))
    try:
        row = event()
        assert monitor.ingest(row) == 1
        assert monitor.ingest(row) == 0
        assert monitor.store.cases() == []
    finally:
        monitor.store.db.close()


@pytest.mark.parametrize('verdict,confidence,evidence_ids,expected', [
    ('clear', .99, ['own-1'], 0), ('unsure', .99, ['own-1'], 0),
    ('violation', .79, ['own-1'], 0), ('violation', .8, ['own-1'], 1),
    ('violation', .95, ['own-1'], 1), ('violation', .95, [], 0),
    ('violation', .95, ['someone-else'], 0),
])
def test_only_sufficient_validated_violations_are_saved(
        tmp_path, verdict, confidence, evidence_ids, expected):
    async def run():
        calls = []

        def respond(request):
            request_body = json.loads(request.content)
            prompt = json.loads(request_body['messages'][-1]['content'])
            calls.append(prompt)
            results = [dict(id=c['id'], verdict=verdict, confidence=confidence,
                            reason='本条证据的复核理由', evidence_ids=evidence_ids)
                       for c in prompt['candidates']]
            return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {
                'content': json.dumps({'results': results})}}]})

        monitor = Monitor(config(tmp_path), httpx.AsyncClient(transport=httpx.MockTransport(respond)))
        try:
            assert monitor.ingest(event()) == 1
            await monitor.review_once()
            assert len(calls) == 1  # A no-op review must not pass the zero-case assertions.
            cases = monitor.store.cases()
            assert len(cases) == expected
            if expected:
                assert cases[0]['user_id'] == 12345
                assert cases[0]['confidence'] == confidence
                assert cases[0]['reason'] == '本条证据的复核理由'
                assert cases[0]['evidence'] == ['own-1']
                assert cases[0]['context'][0]['message_id'] == 'own-1'
        finally:
            await monitor.stop()

    asyncio.run(run())


def test_network_failure_is_not_a_case_and_still_consumes_budget(tmp_path):
    async def run():
        calls = []

        def respond(request):
            calls.append(request)
            raise httpx.ReadTimeout('offline fixture')

        monitor = Monitor(config(tmp_path), httpx.AsyncClient(transport=httpx.MockTransport(respond)))
        try:
            monitor.ingest(event())
            await monitor.review_once()
            assert len(calls) == 1
            assert monitor.quota.calls_hour(time.time()) == 1
            assert monitor.store.cases() == []
        finally:
            await monitor.stop()

    asyncio.run(run())


def test_directory_persists_only_registered_sources_and_updates_name(tmp_path):
    async def run():
        monitor = Monitor(config(tmp_path))
        group_name = '旧群名'

        async def qq(action, params=None):
            if action == 'get_group_list':
                return [{'group_id': 100000001, 'group_name': group_name},
                        {'group_id': 999999999, 'group_name': '个人群，不应持久化'}]
            if action == 'get_group_member_list':
                return []
            raise AssertionError(action)

        monitor.qq.call = qq
        try:
            await monitor.directory.refresh()
            rows = monitor.store.db.execute('SELECT group_id FROM registered_groups').fetchall()
            assert {r[0] for r in rows} == {100000001, -20}
            assert monitor.directory.name(100000001) == '旧群名'
            group_name = '新群名'
            monitor.directory.checked = 0
            await monitor.directory.refresh()
            assert monitor.directory.name(100000001) == '新群名'
            assert monitor.store.db.execute('SELECT count(*) FROM registered_groups').fetchone()[0] == 2
        finally:
            await monitor.stop()

    asyncio.run(run())

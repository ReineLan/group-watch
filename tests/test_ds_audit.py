import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

from group_watch.ds.client import audited_post
from group_watch.ds.audit import request_log_root


def test_request_logs_live_outside_data(tmp_path):
    assert request_log_root(tmp_path/'data'/'watch.sqlite3') == tmp_path/'logs'/'ds-requests'
    assert request_log_root(tmp_path/'watch.sqlite3') == tmp_path/'logs'/'ds-requests'


def test_model_audit_freezes_input_and_keeps_complete_output_without_credentials(tmp_path):
    async def run():
        payload = {'messages': [{'role': 'user', 'content': '原始中文输入'}]}
        body = {'choices': [{'message': {'content': '完整输出', 'tool_calls': [{'id': 'call-1'}]}}]}

        class Client:
            async def post(self, url, **kwargs):
                payload['messages'].append({'role': 'tool', 'content': '后续修改'})
                return httpx.Response(200, json=body)

        await audited_post(SimpleNamespace(db_path=tmp_path/'watch.db'), 'query', Client(),
                           'https://example.invalid', headers={'Authorization': 'Bearer PRIVATE'}, json=payload)
        files = list((tmp_path/'logs'/'ds-requests').rglob('*.json'))
        assert len(files) == 1
        saved = json.loads(files[0].read_text(encoding='utf-8'))
        assert saved['input']['messages'] == [{'role': 'user', 'content': '原始中文输入'}]
        assert saved['output'] == body and json.loads(saved['output_text']) == body
        assert saved['scope'] == 'query' and saved['status'] == 'received' and saved['http_status'] == 200
        assert 'PRIVATE' not in files[0].read_text(encoding='utf-8')
        assert not list(files[0].parent.glob('*.part'))
    asyncio.run(run())


def test_model_audit_records_failed_request_and_preserves_exception(tmp_path):
    async def run():
        class Client:
            async def post(self, url, **kwargs):
                raise httpx.ReadTimeout('may contain private URL')
        with pytest.raises(httpx.ReadTimeout):
            await audited_post(SimpleNamespace(db_path=tmp_path/'watch.db'), 'registration', Client(),
                               'https://example.invalid', json={'messages': []})
        saved = json.loads(next((tmp_path/'logs'/'ds-requests').rglob('*.json')).read_text(encoding='utf-8'))
        assert saved['status'] == 'failed' and saved['error_type'] == 'ReadTimeout'
        assert saved['output'] is None and saved['finished']
        assert 'private URL' not in json.dumps(saved)
    asyncio.run(run())

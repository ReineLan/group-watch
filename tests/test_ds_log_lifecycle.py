"""Log layout/redaction criteria exercised through the real request wrapper."""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import json
from types import SimpleNamespace

import httpx
import pytest

import group_watch.ds.client as ds_audit


class Clock(datetime):
    instant = datetime(2026, 11, 2, 16, 0, tzinfo=timezone.utc)

    @classmethod
    def now(cls, tz=None):
        return cls.instant.astimezone(tz) if tz else cls.instant.replace(tzinfo=None)


@pytest.mark.parametrize('scope', ['automatic-review', 'registration', 'query', 'feedback'])
def test_log_uses_business_and_beijing_date(tmp_path, monkeypatch, scope):
    async def run():
        class Client:
            async def post(self, url, **kwargs):
                return httpx.Response(200, json={'ok': True})

        await ds_audit.audited_post(SimpleNamespace(db_path=tmp_path / 'watch.sqlite3'), scope,
                                   Client(), 'https://example.invalid', json={'messages': []})
        files = list((tmp_path / 'logs' / 'ds-requests').rglob('*.json'))
        assert len(files) == 1
        assert files[0].parent == tmp_path / 'logs' / 'ds-requests' / scope / '2026-11-03'
        assert not list((tmp_path / 'logs' / 'ds-requests').glob('*.json'))

    monkeypatch.setattr(ds_audit, 'datetime', Clock)
    monkeypatch.setattr(Clock, 'instant', datetime(2026, 11, 2, 16, 0, tzinfo=timezone.utc))
    asyncio.run(run())


def test_image_values_are_redacted_only_in_logged_copy(tmp_path):
    async def run():
        payload = {'messages': [{'role': 'user', 'content': [
            {'type': 'text', 'text': '保留文字'},
            {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,PRIVATE_IMAGE'}},
            {'type': 'image_url', 'image_url': {'url': 'https://qpic.cn/private-image'}},
        ]}]}
        original = deepcopy(payload)
        wire = []

        class Client:
            async def post(self, url, **kwargs):
                wire.append(deepcopy(kwargs['json']))
                return httpx.Response(200, json={'ok': True})

        await ds_audit.audited_post(SimpleNamespace(db_path=tmp_path / 'watch.sqlite3'),
                                   'registration', Client(), 'https://example.invalid',
                                   headers={'Authorization': 'Bearer PRIVATE_TOKEN'}, json=payload)
        assert wire == [original] and payload == original
        files = list((tmp_path / 'logs' / 'ds-requests').rglob('*.json'))
        assert len(files) == 1
        raw = files[0].read_text(encoding='utf-8')
        saved = json.loads(raw)
        assert saved['input']['messages'][0]['content'] == [
            {'type': 'text', 'text': '保留文字'}, {'type': 'image_url'}, {'type': 'image_url'}]
        assert 'PRIVATE_IMAGE' not in raw and 'private-image' not in raw and 'PRIVATE_TOKEN' not in raw

    asyncio.run(run())


def test_pending_log_precedes_io_and_keeps_start_bucket_across_midnight(tmp_path, monkeypatch):
    async def run():
        started_files = []

        class Client:
            async def post(self, url, **kwargs):
                files = list((tmp_path / 'logs' / 'ds-requests').rglob('*.json'))
                assert len(files) == 1
                assert json.loads(files[0].read_text(encoding='utf-8'))['status'] == 'pending'
                assert files[0].parent.name == '2026-11-03'
                started_files.extend(files)
                Clock.instant = datetime(2026, 11, 3, 16, 0, 1, tzinfo=timezone.utc)
                raise httpx.ReadTimeout('fixture')

        with pytest.raises(httpx.ReadTimeout):
            await ds_audit.audited_post(SimpleNamespace(db_path=tmp_path / 'watch.sqlite3'),
                                       'automatic-review', Client(), 'https://example.invalid', json={})
        files = list((tmp_path / 'logs' / 'ds-requests').rglob('*.json'))
        assert files == started_files
        saved = json.loads(files[0].read_text(encoding='utf-8'))
        assert saved['status'] == 'failed' and saved['error_type'] == 'ReadTimeout'
        assert datetime.fromisoformat(saved['finished']) > datetime.fromisoformat(saved['started'])
        assert not list((tmp_path / 'logs' / 'ds-requests').rglob('*.part'))

    monkeypatch.setattr(ds_audit, 'datetime', Clock)
    monkeypatch.setattr(Clock, 'instant', datetime(2026, 11, 3, 15, 59, 59, tzinfo=timezone.utc))
    asyncio.run(run())

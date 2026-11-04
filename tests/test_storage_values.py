"""Stored profile values, resource status constraints and signed identities."""
import sqlite3

import pytest

from group_watch.evidence.store import RecordStore
from group_watch.monitoring.store import Store


@pytest.fixture
def watch(tmp_path):
    store = Store(tmp_path / 'watch.sqlite3')
    try:
        yield store
    finally:
        store.db.close()


@pytest.fixture
def evidence(tmp_path, monkeypatch):
    monkeypatch.setenv('GROUP_EVIDENCE_PROFILES', '0')
    store = RecordStore(tmp_path / 'evidence')
    store.init_db()
    try:
        yield store
    finally:
        store.close()


@pytest.mark.parametrize('nickname,card', [
    (None, None), ('', ''), (' \u3000 ', ' \u3000 '), ('普通昵称', '群名片'),
])
def test_record_validation_preserves_unknown_empty_and_whitespace(evidence, nickname, card):
    body = dict(member_id='12345', group_id=100000001, nickname=nickname, card=card,
                event_date='2026-11-03', reason='辱骂', punishment='警告', penalty_text='警告一次')
    actual = evidence.validate_record(body)
    assert actual['nickname'] == nickname
    assert actual['card'] == card
    assert actual['group_id'] == 100000001
    assert actual['reason'] == '辱骂'
    assert 'group_name' not in actual and 'category' not in actual


def insert_record(db, **overrides):
    # Insert into the real application's schema, never a schema created by the test.
    row = dict(id='record-1', member_id='12345', group_id=100000001,
               nickname=None, card=None, event_date='2026-11-03', reason='辱骂',
               punishment='警告', penalty_text='警告一次', operator='', notes='',
               occurrence='1', images='[]', created_at='2026-11-03T01:00:00',
               updated_at='2026-11-03T01:00:00', nickname_status=0, nickname_at=None,
               avatar_status=0, avatar_at=None, avatar_url=None)
    row.update(overrides)
    db.execute(f'INSERT INTO records ({",".join(row)}) VALUES ({",".join("?" for _ in row)})',
               tuple(row.values()))


@pytest.mark.parametrize('status', [0, 1, 2])
def test_profile_states_and_times_round_trip_in_records(evidence, status):
    at = None if status == 0 else '2026-11-03T01:01:00'
    with evidence.connect() as db:
        insert_record(db, nickname='' if status == 1 else None, nickname_status=status,
                      nickname_at=at, avatar_status=status, avatar_at=at,
                      avatar_url='/avatars/blank.webp' if status == 1 else None)
    row = next(r for r in evidence.get_records() if r['id'] == 'record-1')
    assert row['nickname_status'] == row['avatar_status'] == status
    assert row['nickname_at'] == row['avatar_at'] == at
    if status == 1:
        assert row['nickname'] == ''
        assert row['avatar_url'] == '/avatars/blank.webp'


@pytest.mark.parametrize('field,bad', [('nickname_status', -1), ('nickname_status', 3),
                                       ('avatar_status', -1), ('avatar_status', 3)])
def test_database_rejects_invalid_resource_states(evidence, field, bad):
    with evidence.connect() as db:
        # Establish a valid row first so missing columns cannot masquerade as validation.
        insert_record(db)
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(f'UPDATE records SET {field}=? WHERE id=?', (bad, 'record-1'))


@pytest.mark.parametrize('members,qq_expected,live_expected', [
    ([123456], True, False), ([-123456], False, True),
    ([123456, -123456], True, True), ([], False, False),
])
def test_shared_whitelist_distinguishes_same_digits_on_two_platforms(
        watch, members, qq_expected, live_expected):
    watch.save_whitelist([{'user_id': x, 'nickname': ''} for x in members])
    assert watch.is_whitelisted(100000001, 123456) is qq_expected
    assert watch.is_whitelisted(100000002, 123456) is qq_expected
    assert watch.is_whitelisted(-20, -123456) is live_expected
    assert watch.is_whitelisted(-21, -123456) is live_expected
    assert {r['user_id'] for r in watch.whitelist()} == set(members)

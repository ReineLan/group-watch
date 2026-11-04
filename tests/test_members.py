import asyncio
from concurrent.futures import ThreadPoolExecutor

import pytest

from group_watch.monitoring.store import Store
from group_watch.settings import Settings
from group_watch.sources.members import Members
from group_watch.sources.registry import Sources


def member(user=12345, **fields):
    return dict(user_id=user, nickname='原昵称', card='群名片', level='1',
                join_time=100, last_sent_time=200, **fields)


def directory(tmp_path, qq):
    cfg = Settings(db_path=str(tmp_path/'watch.db'), groups=[100000001, 100000002],
                   live_rooms={}, local_env=str(tmp_path/'.env'))
    store = Store(cfg.db_path)
    return Sources(cfg, qq, store), store


def test_members_retain_absentees_and_exact_values_across_groups(tmp_path):
    store = Store(tmp_path/'watch.db')
    cache = Members(tmp_path/'watch.db')
    try:
        cache.save(100000001, [member(), member(23456)])
        blank = {**member(), 'nickname':'  ', 'card':'', 'level':None}
        cache.save(100000001, [blank])
        cache.save(100000002, [{**member(), 'nickname':None, 'card':'另一群名片'}])
        assert len(cache.rows(100000001)) == 2
        assert cache.get(100000001, 12345)['nickname'] == '  '
        assert cache.get(100000001, 12345)['card'] == ''
        assert cache.get(100000002, 12345)['nickname'] is None
        assert cache.get(100000002, 12345)['card'] == '另一群名片'
        assert cache.get(100000001, 23456)['join_time'] == 100
        assert cache.get(100000001, 12345)['updated_at'].count(':') == 2
        cache.save(100000001, [])
        assert len(cache.rows(100000001)) == 2
    finally:
        store.db.close()


@pytest.mark.parametrize('bad', [[member(0)], [member(-1)], [member(), member()],
                                [member(group_id=100000002)]])
def test_invalid_batch_does_not_partially_replace_members(tmp_path, bad):
    store = Store(tmp_path/'watch.db')
    cache = Members(tmp_path/'watch.db')
    try:
        cache.save(100000001, [member()])
        before = cache.rows(100000001)
        with pytest.raises(ValueError):
            cache.save(100000001, [member(34567)] + bad)
        assert cache.rows(100000001) == before
        with pytest.raises(ValueError):
            cache.save(-1, [member()])
    finally:
        store.db.close()


def test_two_hour_refresh_and_failed_group_retry(tmp_path, monkeypatch):
    async def run():
        stamp = [1000000]
        monkeypatch.setattr('group_watch.sources.qq.time.time', lambda: stamp[0])
        calls, fail = [], [False]

        class QQ:
            async def call(self, action, params=None):
                calls.append((action, params))
                assert params['no_cache'] is True
                if action == 'get_group_list':
                    return [dict(group_id=g, group_name='群', member_count=1) for g in (100000001,100000002)]
                if fail[0] and params['group_id'] == 100000002:
                    raise ValueError('offline')
                return [member()]

        source, store = directory(tmp_path, QQ())
        try:
            await source.refresh()
            stamp[0] += 901
            await source.refresh()
            assert sum(a == 'get_group_member_list' for a, _ in calls) == 2
            stamp[0] += 7200
            fail[0] = True
            with pytest.raises(ValueError):
                await source.refresh()
            assert source.member_store.get(100000002, 12345)['nickname'] == '原昵称'
            fail[0] = False
            await source.refresh()
            queried = [p['group_id'] for a,p in calls if a == 'get_group_member_list']
            assert queried == [100000001,100000002,100000001,100000002,100000002]
        finally:
            store.db.close()
    asyncio.run(run())


def test_restart_resolves_removed_member_offline_and_from_profile_thread(tmp_path):
    class Offline:
        async def call(self, *args, **kwargs):
            raise AssertionError('Known member must not need QQ')

    source, store = directory(tmp_path, Offline())
    source.remember_members(100000001, [member()])
    source.remember_members(100000001, [])  # Member was kicked before registration.
    store.db.close()
    source, store = directory(tmp_path, Offline())
    try:
        found = asyncio.run(source.tool('find_members', {'group_id':'100000001','query':'群名片'}))
        assert found[0]['user_id'] == '12345'
        identity = source.verified_identity(100000001, '12345')
        assert identity['nickname'] == '原昵称'
        assert source.verified_identity(100000002, '12345') is None
        with ThreadPoolExecutor() as executor:
            profile = executor.submit(source.archive_profile, dict(group_id=100000001, member_id='12345'), tmp_path).result()
        assert profile == dict(nickname='原昵称', card='群名片')
    finally:
        store.db.close()


def test_missing_member_still_uses_onebot_and_persists_result(tmp_path):
    class QQ:
        async def call(self, action, params):
            assert action == 'get_group_member_info' and params['no_cache']
            return member(group_id=params['group_id'])

    source, store = directory(tmp_path, QQ())
    try:
        result = asyncio.run(source.tool('find_members', {'group_id':'100000001','query':'12345'}))
        assert result[0]['nickname'] == '原昵称'
        assert source.member_store.get(100000001,12345)['card'] == '群名片'
    finally:
        store.db.close()

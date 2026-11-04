import time

from group_watch.monitoring.service import Monitor
from group_watch.settings import Settings


def test_snowluma_status_confirms_violation_without_review(tmp_path):
    monitor = Monitor(Settings(db_path=str(tmp_path / 'watch.db'),
                               local_env=str(tmp_path / '.env'),
                               settings_file=str(tmp_path / 'rules.json')))
    now = time.time()
    count = monitor.ingest({'post_type': 'message', 'message_type': 'group',
                            'group_id': 100000001, 'user_id': 777, 'message_id': 's1',
                            'time': now,
                            'message': 'SnowLuma 状态\n版本: 2.0.3\n平台: win32-x64\n运行时长: 16小时 34分钟',
                            'sender': {'nickname': 'bot'}}, now)

    assert count == 1
    cases = monitor.store.cases()
    assert [(case['rule'], case['confidence']) for case in cases] == [('snowluma', 1.0)]
    assert not monitor.store.window_state.candidates
    monitor.store.db.close()

import json

import pytest

from group_watch.settings import load_settings


@pytest.mark.parametrize(('address', 'override', 'expected'), [
    ('', '', 'adapter-secret'),
    ('ws://127.0.0.1:3001/', '', 'adapter-secret'),
    ('ws://127.0.0.1:3001', '', 'adapter-secret'),
    ('ws://127.0.0.1:3001/', 'explicit-secret', 'explicit-secret'),
    ('ws://127.0.0.1:3002/', '', ''),
    ('ws://127.0.0.1:3001/other', '', ''),
])
def test_matching_address_inherits_auth_without_overriding_or_leaking(tmp_path, address, override, expected):
    onebot = tmp_path / 'onebot.json'
    onebot.write_text(json.dumps({
        'statusCommand': {'enabled': False},
        'networks': {'wsServers': [
            {'enabled': False, 'host': '127.0.0.1', 'port': 3001, 'accessToken': 'disabled-secret'},
            {'host': '0.0.0.0', 'port': 3001, 'role': 'Universal', 'accessToken': 'adapter-secret'},
        ]},
    }), encoding='utf-8')
    path = tmp_path / 'config.json'
    path.write_text(json.dumps({
        'snowluma_config': str(onebot), 'ws_url': address,
        'ws_token': override, 'local_env': str(tmp_path / '.env'),
    }), encoding='utf-8')
    cfg = load_settings(path)
    assert cfg.ws_token.get_secret_value() == expected
    assert cfg.ws_url == (address or 'ws://127.0.0.1:3001/')

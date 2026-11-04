"""Raw empty values are successful profile data, not errors or placeholders."""
import json
import struct
import zlib

import pytest

from group_watch.evidence import profiles


@pytest.mark.parametrize('nickname', ['', ' ', '\u3000', ' \u3000 ', ' 名称 '])
def test_nickname_parser_returns_exact_string(nickname):
    raw = json.dumps({'code': 200, 'qq': '12345',
                      'data': {'user_info': {'nickname': nickname}}}, ensure_ascii=False).encode()
    assert profiles.nickname_from_json(raw, '12345') == nickname


def test_empty_primary_nickname_does_not_fall_back_to_another_field():
    raw = json.dumps({'code': 200, 'data': {'nickname': '', 'nick': '备用字段'}}).encode()
    assert profiles.nickname_from_json(raw, '12345') == ''


@pytest.mark.parametrize('payload', [{}, {'nickname': None}, {'nickname': 123}])
def test_missing_or_non_string_nickname_is_not_a_success(payload):
    raw = json.dumps({'code': 200, 'data': {'user_info': payload}}).encode()
    with pytest.raises(ValueError):
        profiles.nickname_from_json(raw, '12345')


def transparent_avatar():
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>IIBBBBB', 100, 100, 1, 0, 0, 0, 0))
            + chunk(b'tRNS', b'\0\0') + chunk(b'IDAT', zlib.compress(b'\0' * 1400))
            + chunk(b'IEND', b''))


def test_download_accepts_transparent_s100_without_replacing_it(monkeypatch):
    calls = []
    raw = transparent_avatar()

    def download(url):
        calls.append(url)
        return raw

    monkeypatch.setattr(profiles, 'download', download)
    assert profiles.download_avatar('12345') == (raw, '.png')
    assert len(calls) == 1 and 's=100' in calls[0]

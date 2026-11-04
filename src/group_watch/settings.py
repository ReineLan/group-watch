from group_watch.paths import ROOT, resolve_path
import json
import os
import secrets
import tempfile
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values, set_key
from pydantic import BaseModel, ConfigDict, Field, SecretStr, StringConstraints, model_validator
from typing import Annotated


Word = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class BroadcastTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str = Field("auto", pattern="^(auto|group|private)$")
    id: str = Field(pattern=r"^[1-9]\d{4,11}$")
    name: str = Field("", max_length=100)


class BroadcastSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    targets: list[BroadcastTarget] = Field(default_factory=list, max_length=10)
    confidence: float = Field(.95, ge=.8, le=1)


class PushRecipient(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field('', max_length=64, pattern=r'^[a-zA-Z0-9_-]*$')
    name: str = Field('', max_length=100)
    token: SecretStr = SecretStr('')


class RuleSettings(BaseModel):
    model_config = ConfigDict(extra='forbid')

    query_calls_hour: int = Field(5, ge=1, le=1000)
    flood_count: int = Field(10, ge=3, le=100)
    flood_seconds: int = Field(60, ge=5, le=120)
    batch_seconds: int = Field(0, ge=0, le=300)  # Legacy input; review no longer waits.
    batch_size: int = Field(6, ge=1, le=10)
    repeat_count: int = Field(4, ge=3, le=100)
    retention_days: int = Field(14, ge=1, le=365)
    blocked_words: list[Word] = Field(default_factory=list, max_length=600)
    unrelated_streamers: list[Word] = Field(default_factory=list, max_length=200)
    sensitive_topics: list[Word] = Field(default_factory=list, max_length=200)


class Settings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    groups: list[int] = Field(default_factory=lambda: [100000001, 100000002], min_length=1)
    live_rooms: dict[int, str] = Field(default_factory=dict)
    live_forward_token: SecretStr = SecretStr('')
    broadcast_targets: list[BroadcastTarget] = Field(default_factory=list, max_length=10)
    broadcast_confidence: float = Field(.95, ge=.8, le=1)
    protected_qq: int = 100000003
    protected_groups: list[int] = Field(default_factory=lambda: [123456])
    snowluma_config: str = ''
    ws_url: str = ''
    public_url: str = ''
    ws_token: SecretStr = SecretStr('')
    ds_key: SecretStr = SecretStr('')
    ds_url: str = 'https://api.deepseek.com'
    ds_model: str = 'deepseek-chat'
    pushplus_recipients: list[PushRecipient] = Field(default_factory=list, max_length=10)
    pushplus_enabled: bool = True
    local_env: str = str(ROOT / 'config/.env')
    settings_file: str = str(ROOT / 'config/config.json')
    db_path: str = str(ROOT / 'data/group-watch.sqlite3')
    evidence_data: str = ''
    evidence_tokens: list[SecretStr] = Field(default_factory=list)
    batch_seconds: int = Field(0, ge=0, le=300)
    batch_size: int = Field(6, ge=1, le=10)
    query_calls_hour: int = Field(5, ge=1, le=1000)
    # Compatibility input only; detection uses the built-in interval.
    cooldown_seconds: int = 120
    flood_count: int = Field(10, ge=3, le=100)
    flood_seconds: int = Field(60, ge=5, le=120)
    repeat_count: int = Field(4, ge=3, le=100)
    retention_days: int = Field(14, ge=1, le=365)
    automatic_updates: bool = True
    blocked_words: list[str] = Field(default_factory=list)
    unrelated_streamers: list[str] = Field(default_factory=list)
    sensitive_topics: list[str] = Field(default_factory=list)
    exempt_users: list[int] = Field(default_factory=list)

    @model_validator(mode='after')
    def unify_words(self):
        self.blocked_words = list(dict.fromkeys(self.blocked_words+self.unrelated_streamers+self.sensitive_topics))
        self.unrelated_streamers, self.sensitive_topics = [], []
        self.batch_seconds = 0
        if any(room <= 0 or room > 2**63-1 or not name.strip() for room, name in self.live_rooms.items()):
            raise ValueError('直播间须有正整数房间号与名称')
        if self.public_url:
            address = urlsplit(self.public_url)
            if (address.scheme not in ('http', 'https') or not address.hostname or address.username is not None
                    or address.password is not None or address.path not in ('', '/') or address.query or address.fragment):
                raise ValueError('public_url 必须为完整的 HTTP/HTTPS 站点地址，不含路径、账号或查询参数')
            address.port  # Reject malformed ports before accepting the origin.
            self.public_url = f'{address.scheme}://{address.netloc.lower()}'
        return self


def load_settings(path: Path) -> Settings:
    path = resolve_path(path, base=Path.cwd())
    if not path.exists() and path.name == 'group-watch.json':
        path = path.with_name('config.json')
    raw = json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else {}
    for field in ('local_env', 'db_path', 'evidence_data', 'snowluma_config', 'lan_env'):
        if raw.get(field):
            raw[field] = str(resolve_path(raw[field], base=ROOT))
    raw['settings_file'] = str(path)
    # This project owns its credentials; no implicit dependency on a Lan checkout.
    shared = Path(raw.pop('lan_env', str(ROOT / 'config/.env')))
    env = {**(dotenv_values(shared) if shared.is_file() else {}), **os.environ}
    for key, name in [('ds_key', 'DEEPSEEK_API_KEY'), ('ds_url', 'DEEPSEEK_BASE_URL'),
                      ('ds_model', 'DEEPSEEK_MODEL'),
                      ('live_forward_token', 'LAN_LIVE_FORWARD_TOKEN')]:
        if env.get(name):
            raw[key] = env[name]
    # Notification settings belong to this instance's .env.
    local = Path(raw.get('local_env', str(ROOT / 'config/.env')))
    saved = dotenv_values(local, encoding='utf-8-sig', interpolate=False) if local.is_file() else {}
    if 'PUSHPLUS_ENABLED' in saved:
        raw['pushplus_enabled'] = saved['PUSHPLUS_ENABLED']
    if 'PUSHPLUS_RECIPIENTS' in saved:
        raw['pushplus_recipients'] = json.loads(saved['PUSHPLUS_RECIPIENTS'] or '[]')
    if saved.get('GROUP_EVIDENCE_TOKENS'):
        raw['evidence_tokens'] = saved['GROUP_EVIDENCE_TOKENS'].split(',')
    if saved.get('LAN_LIVE_FORWARD_TOKEN'):
        raw['live_forward_token'] = saved['LAN_LIVE_FORWARD_TOKEN']
    cfg = Settings.model_validate(raw)
    if cfg.snowluma_config:
        onebot = json.loads(Path(cfg.snowluma_config).read_text(encoding='utf-8-sig'))
        if onebot.get('statusCommand', {}).get('enabled') is not False:
            raise ValueError('SnowLuma statusCommand.enabled 必须显式设为 false，禁止 #sl 自动回复')
        adapters = [x for x in onebot.get('networks', {}).get('wsServers', [])
                    if x.get('enabled', True) and str(x.get('role', 'Universal')).lower() in ('event', 'universal')]

        def adapter_url(adapter):
            host = adapter.get('host', '127.0.0.1')
            if host in ('0.0.0.0', '::'):
                host = '127.0.0.1'
            if ':' in host:
                host = f'[{host}]'
            return f"ws://{host}:{adapter.get('port', 3001)}{adapter.get('path', '/')}"

        def endpoint(url):
            parts = urlsplit(url)
            return parts.scheme, parts.hostname, parts.port, parts.path or '/', parts.query

        if not cfg.ws_url:
            adapter = next(iter(adapters), None)
            if not adapter:
                raise ValueError('SnowLuma 未启用 Event/Universal WebSocket')
            cfg.ws_url = adapter_url(adapter)
        else:
            # An explicit address still needs the matching adapter's credentials.
            # Never attach its secret to a different configured endpoint.
            adapter = next((x for x in adapters if endpoint(adapter_url(x)) == endpoint(cfg.ws_url)), None)
        if adapter and not cfg.ws_token.get_secret_value():
            cfg.ws_token = SecretStr(adapter.get('accessToken', ''))
    return cfg


def rule_settings(cfg: Settings) -> dict:
    return {key: getattr(cfg, key) for key in RuleSettings.model_fields}


def save_rules(cfg: Settings, values: dict):
    """Persist editable rules without rewriting credentials or unrelated settings."""
    values = RuleSettings.model_validate(values).model_dump()
    values['blocked_words'] = list(dict.fromkeys(values['blocked_words']+values['unrelated_streamers']+values['sensitive_topics']))
    values['unrelated_streamers'], values['sensitive_topics'], values['batch_seconds'] = [], [], 0
    target = Path(cfg.settings_file)
    previous = json.loads(target.read_text(encoding='utf-8-sig')) if target.exists() else {}
    if not isinstance(previous, dict):
        raise ValueError('配置文件必须是 JSON 对象')
    previous.update(values)
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(prefix='.group-watch-', suffix='.json', dir=target.parent)
    temporary = Path(name)
    try:
        with os.fdopen(handle, 'w', encoding='utf-8', newline='') as output:
            json.dump(previous, output, ensure_ascii=False, indent=2)
            output.write('\n')
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    for key, value in values.items():
        setattr(cfg, key, value)


def push_recipients(cfg):
    return cfg.pushplus_recipients


def save_push_recipients(cfg, rows):
    existing = {row.id:row for row in push_recipients(cfg)}
    prepared, ids, tokens = [], set(), set()
    for row in rows:
        key = row.id or uuid.uuid4().hex
        token = row.token.get_secret_value() or (existing[key].token.get_secret_value() if key in existing else '')
        if not 8 <= len(token) <= 256 or any(ord(x) < 33 or ord(x) > 126 for x in token):
            raise ValueError('每位接收人须有8–256个非空白英文字符的 Token')
        if key in ids or token in tokens:
            raise ValueError('接收人或 Token 重复')
        ids.add(key); tokens.add(token)
        prepared.append(PushRecipient(id=key, name=row.name.strip(), token=SecretStr(token)))
    target = Path(cfg.local_env)
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix='.push-', suffix='.env', dir=target.parent)
    temporary = Path(temporary)
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as output:
            output.write(target.read_text(encoding='utf-8-sig') if target.exists() else '')
        serialized = [dict(id=r.id, name=r.name, token=r.token.get_secret_value()) for r in prepared]
        set_key(str(temporary), 'PUSHPLUS_RECIPIENTS', json.dumps(serialized, ensure_ascii=False), encoding='utf-8')
        set_key(str(temporary), 'PUSHPLUS_ENABLED', 'true', encoding='utf-8')
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    cfg.pushplus_recipients = prepared
    cfg.pushplus_enabled = True


def evidence_tokens(env_file: Path) -> list[str]:
    """Reuse or create the local authentication secret in the owned .env file."""
    values = dotenv_values(env_file, encoding='utf-8-sig', interpolate=False) if env_file.is_file() else {}
    tokens = [x.strip() for x in (values.get('GROUP_EVIDENCE_TOKENS') or '').split(',') if x.strip()]
    if not tokens:
        tokens = [secrets.token_urlsafe(32)]
        env_file.parent.mkdir(parents=True, exist_ok=True)
        env_file.touch(exist_ok=True)
        set_key(str(env_file), 'GROUP_EVIDENCE_TOKENS', ','.join(tokens), encoding='utf-8')
    return tokens


def save_broadcast(cfg, targets, confidence):
    target = Path(cfg.settings_file)
    previous = json.loads(target.read_text(encoding='utf-8-sig')) if target.exists() else {}
    previous.update(broadcast_targets=targets, broadcast_confidence=confidence)
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(prefix='.broadcast-', suffix='.json', dir=target.parent)
    temporary = Path(name)
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as output:
            json.dump(previous, output, ensure_ascii=False, indent=2)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    cfg.broadcast_targets = [BroadcastTarget.model_validate(x) for x in targets]
    cfg.broadcast_confidence = confidence

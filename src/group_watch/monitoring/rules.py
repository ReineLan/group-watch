import html
import json
import re
import unicodedata
from urllib.parse import urlsplit

POLICIES = {
    'flood': ('刷屏', '人工按刷屏程度处理'),
    'repeat': ('重复内容刷屏', '人工按刷屏程度处理'),
    'abuse': ('辱骂、人身攻击 / 用语不文明', '辱骂：禁言7–30天，复犯移出；不文明：警告→禁言1天→7–30天'),
    'lanyin_attack': ('诋毁、侮辱兰音', '移出群聊'),
    'conflict': ('引战、拉踩、挑起矛盾 / 恶意带节奏', '禁言7–30天或移出；严重直接移出'),
    'negative_claim': ('传播未证实负面消息', '警告→禁言7–30天→移出；真实性需另行核实'),
    'sarcasm': ('阴阳怪气、反串贬低', '警告/禁言1天→7–30天→移出'),
    'mention': ('随意@兰音', '警告→禁言7–30天→移出'),
    'unrelated': ('提及无关主播/up主', '警告→禁言1–7天→移出'),
    'ad': ('广告、引流、群邀请、商业推广', '移出群聊'),
    'scam': ('冒充官方、收费、集资、借款、诈骗', '移出群聊；仅提示疑点，不能确认诈骗事实'),
    'vulgar': ('低俗、违规内容', '禁言1–7天→7–30天→移出'),
    'privacy': ('泄露他人隐私 / 开盒', '禁言15–30天或移出；开盒移出'),
    'politics': ('政治相关、键政', '禁言15–30天→移出'),
    'protected_group': ('泄露舰长群号', '禁言3天→移出群聊'),
    'snowluma': ('SnowLuma 状态回复（机器人账号）', '移出群聊'),
    'sensitive': ('敏感话题（不构成涉政）', '禁言1–7天→7–30天→移出'),
    'blocked': ('自定义违禁词', '按群规人工确认'),
}
LIMITATIONS = ['图片/语音/视频不下载、不逐条查看、不发送给 AI 识别；仅记录媒体类型',
               '造谣真实性、私聊骚扰、抢红包外挂、养bot、跨平台搬运、两轮以上争议不能仅凭当前群消息可靠确认',
               '自动筛选有漏检可能；无关主播、敏感话题和违禁词需按实际范围配置',
               'DS 判定仅为管理线索；不自动禁言、撤回、踢人，不自动累计处罚次数']
PATTERNS = {
    'abuse': r'傻[逼比bB]|[操艹肏]你|你[妈麻]死|死(?:妈|全家)|废物|滚出去|脑残|贱[人货]|去死|他妈的|你妈的|(?<![我妈她它老爸死])妈的',
    'lanyin_attack': r'(兰音|兰兰|兰兔|兔兔).{0,20}(垃圾|废物|骗子|去死|滚|贱)|(垃圾|废物|骗子|贱).{0,20}(兰音|兰兰|兰兔)',
    'conflict': r'孝子|结晶|狗粉|脑残粉|粉丝.{0,12}(?:滚|垃圾|废物)',
    'negative_claim': r'(兰音|兰兰|兰兔).{0,30}(黑料|塌房|私联|圈钱|骗钱|实锤|出轨|疑似|听说)',
    'sarcasm': r'急了急了|不会真有人|懂的都懂',
    'ad': r'群号|群聊邀请|扫码(?:进|加)群|刷单|返利|日赚|代充|代购|内部名额|保证收益|稳赚|(?:进群|入群|加群).{0,12}(?:领取|福利|资源|免费|私聊|私信|扫码|\d{5,})|(?:领取|福利|资源|免费|私聊|私信).{0,12}(?:进群|入群|加群)|加(?:微信|[Vv]信|[Vv]x)',
    'scam': r'官方.{0,12}(?:收款|收费|转账)|(?:集资|借[款钱]).{0,10}(?:给我|转我|借我|扫码|群内|大家|私聊|收款)|收款码|内部名额|保证收益|稳赚|验证码.{0,10}(?:给我|发我)',
    'vulgar': r'约炮|裸聊|黄片|卖淫|强奸|做爱|成人视频|(?:发|看|要|求|资源|分享).{0,6}(?:色情|黄片)',
    'privacy': r'人肉|身份证|家庭住址|真实姓名|手机号码|住在.{0,30}(?:小区|栋|室)|开盒.{0,10}(?:你|他|她|@\d+|某人)',
    'snowluma': r'^snowluma状态.{0,12}版本:.{0,24}平台:.{0,24}运行时长:',
    'politics': r'键政|政党|共产党|民进党|国民党|习近平|台独|政变|颠覆政权',
}
COMPILED = {k: re.compile(v, re.I) for k, v in PATTERNS.items()}
AD_LINK_HOSTS = ('bilibili.com', 'b23.tv', 'douyin.com', 'qzone.qq.com', 'qq.com',
                 'xiaohongshu.com', 'xhslink.cn', '114514.tv')
LINK = re.compile(r'(?:https?://|www\.)[^\s]+', re.I)
AD_CTA = re.compile(r'进群|入群|加群|领取|福利|资源|免费|私聊|私信|扫码|加(?:微信|[Vv]信|[Vv]x)')
ABUSE_STRONG = re.compile(r'[操艹肏]你|你[妈麻]死|他妈的|你妈的|(?<![我妈她它老爸死])妈的|贱[人货]')
ABUSE_WEAK = re.compile(r'傻[逼比bB]|死(?:妈|全家)|废物|滚出去|脑残|去死')
ABUSE_TARGET = re.compile(r'你(?!妈)|您|你们|这人|楼上|群友|管理|群主|@\d+')
SYSTEM_PREFIXES = ('生成失败：', '生成失败:')
SYSTEM_MARKERS = ('upstream_text_reply',)
# Some OneBot implementations render media as text segments. They are display
# labels, not message content, so they must never make unrelated media look alike.
MEDIA_PLACEHOLDERS = frozenset({'[图片]'})


def normalize(text):
    text = unicodedata.normalize('NFKC', html.unescape(text)).casefold()
    return ''.join(c for c in text if not c.isspace() and unicodedata.category(c) != 'Cf')


def system_message(msg):
    text = normalize(msg.get('text') or '')
    return text.startswith(SYSTEM_PREFIXES) or any(marker in text for marker in SYSTEM_MARKERS)


def link_hosts(text):
    hosts = set()
    for raw in LINK.findall(text):
        if not raw.lower().startswith(('http://', 'https://')):
            raw = 'http://' + raw
        try:
            host = (urlsplit(raw).hostname or '').lower().strip('.')
        except ValueError:
            continue
        if host:
            hosts.add(host)
    return hosts


def allowed_link(host):
    return any(host == item or host.endswith('.' + item) for item in AD_LINK_HOSTS)


def targeted_abuse(text):
    for match in ABUSE_WEAK.finditer(text):
        window = text[max(0, match.start() - 12):match.end() + 12]
        if ABUSE_TARGET.search(window):
            return True
    return False


def message_content(value):
    """No fetching of attacker-controlled URLs; CQ and array segments supported."""
    mentions, media, pieces = [], [], []
    if isinstance(value, str):
        def segment(match):
            parts = match.group(1).split(',')
            kind = parts[0]
            data = dict(p.split('=', 1) for p in parts[1:] if '=' in p)
            if kind == 'at':
                mentions.append(data.get('qq', ''))
            else:
                media.append(kind)
            if kind in ('json', 'xml'):
                return card_text(html.unescape(data.get('data', '')), kind)
            return ''
        pieces = [re.sub(r'\[CQ:([^\]]*)\]', segment, value)]
    elif isinstance(value, list):
        for segment in value[:200]:
            if not isinstance(segment, dict):
                continue
            kind, data = segment.get('type'), segment.get('data', {})
            if not isinstance(data, dict):
                continue
            if kind == 'text':
                pieces.append(str(data.get('text', '')))
            elif kind == 'at':
                mentions.append(str(data.get('qq', '')))
            else:
                media.append(str(kind))
                if kind in ('json', 'xml'):
                    pieces.append(card_text(str(data.get('data', '')), kind))
    return ''.join(pieces)[:8000], mentions[:100], media[:100]


def card_text(raw, kind='json'):
    """Use visible card titles, never resource URLs or opaque metadata, as evidence."""
    texts = []
    if kind == 'json':
        try:
            value = json.loads(raw)
        except (ValueError, TypeError):
            return '[卡片内容无法解析]'
        if isinstance(value, dict):
            texts.extend(value.get(k) for k in ('prompt', 'title', 'desc'))
            meta = value.get('meta')
            if isinstance(meta, dict):
                for detail in list(meta.values())[:20]:
                    if isinstance(detail, dict):
                        texts.extend(detail.get(k) for k in ('title', 'desc', 'summary'))
    else:
        texts = re.findall(r'<(?:title|summary|des|desc)\b[^>]*>(.*?)</(?:title|summary|des|desc)>', raw[:16000], re.S | re.I)
        texts = [re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', t, flags=re.S) for t in texts]
    cleaned = []
    for text in texts:
        if isinstance(text, str) and text.strip():
            text = re.sub(r'https?://\S+|www\.\S+', '[链接]', html.unescape(text).strip())[:300]
            if text not in cleaned:
                cleaned.append(text)
    return ' · '.join(cleaned)[:1200] or '[卡片，无可读摘要]'


def readable_message(msg):
    """Also adapt snapshots saved before cards were parsed into readable summaries."""
    text = msg.get('text') or ''
    media = msg.get('media', [])
    if 'json' in media and text.lstrip().startswith('{'):
        text = card_text(text)
    elif 'xml' in media and text.lstrip().startswith('<'):
        text = card_text(text, 'xml')
    return {**msg, 'text': text}


def repeat_text(msg):
    """Text used for duplicate detection; empty when the message carries no words.

    Only text segments count as content. Media segments (images, faces, video)
    are never compared: their file ids differ per upload, so equal-looking
    placeholders would otherwise flag unrelated pictures as one repeated message.
    Cards keep their readable summary through the message text fallback.
    """
    segments = msg.get('segments')
    if isinstance(segments, list) and segments:
        pieces = [str(segment['data'].get('text') or '') for segment in segments[:200]
                  if isinstance(segment, dict) and segment.get('type') == 'text'
                  and isinstance(segment.get('data'), dict)]
        value = ''.join(pieces) if pieces else (msg.get('text') or '')
    else:
        value = msg.get('text') or ''
    plain = normalize(value)
    return '' if plain in MEDIA_PLACEHOLDERS else plain


def detect(cfg, msg, recent):
    if system_message(msg):
        return {}
    plain = repeat_text(msg)
    text = normalize(readable_message(msg)['text'])
    own = [x for x in recent if x['user_id'] == msg['user_id']]
    hits = {}
    for kind, pattern in COMPILED.items():
        match = pattern.search(text)
        if match:
            hits[kind] = [msg['message_id']]
    if 'snowluma' in hits:
        return {'snowluma': hits['snowluma']}
    # Untargeted profanity is left out until a target or an explicit second person appears.
    if 'abuse' in hits and ABUSE_WEAK.search(text) and not ABUSE_STRONG.search(text) and not targeted_abuse(text) and not msg.get('mentions'):
        hits.pop('abuse')
    # A normal link is not an ad. Only unknown hosts with a call to action or mass forwarding qualify.
    unknown = {host for host in link_hosts(text) if not allowed_link(host)}
    if unknown and 'ad' not in hits:
        users = {msg['user_id']}
        users.update(x['user_id'] for x in recent
                     if any(host in unknown for host in link_hosts(normalize(readable_message(x)['text']))))
        if AD_CTA.search(text) or len(users) >= 2:
            hits['ad'] = [msg['message_id']]
    fast = [x for x in own if x['time'] >= msg['time'] - cfg.flood_seconds]
    if len(fast) >= cfg.flood_count:
        hits['flood'] = [x['message_id'] for x in fast[-30:]]
    # Media-only messages have no comparable text, so different pictures never look identical.
    repeated = [x for x in own if plain and repeat_text(x) == plain]
    if len(repeated) >= cfg.repeat_count:
        hits['repeat'] = [x['message_id'] for x in repeated[-30:]]
    if str(cfg.protected_qq) in text:
        hits['privacy'] = [msg['message_id']]
    if str(cfg.protected_qq) in msg['mentions']:
        hits['mention'] = [msg['message_id']]
    if any(str(group) in text for group in cfg.protected_groups):
        hits['protected_group'] = [msg['message_id']]
    for key, words in [('blocked', cfg.blocked_words), ('unrelated', cfg.unrelated_streamers), ('sensitive', cfg.sensitive_topics)]:
        if any(normalize(word) in text for word in words if normalize(word)):
            hits[key] = [msg['message_id']]
    return hits

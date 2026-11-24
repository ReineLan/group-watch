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
LIMITATIONS = ['图片/语音/视频不下载、不逐条查看、不发送给 AI 识别；复核只提供媒体类型和重复统计',
               '造谣真实性、私聊骚扰、抢红包外挂、养bot、跨平台搬运、两轮以上争议不能仅凭当前群消息可靠确认',
               '自动筛选有漏检可能；无关主播、敏感话题和违禁词需按实际范围配置',
               'DS 判定仅为管理线索；不自动禁言、撤回、踢人，不自动累计处罚次数']
PATTERNS = {
    'conflict': r'孝子|结晶|狗粉|脑残粉|粉丝.{0,12}(?:滚|垃圾|废物)',
    'negative_claim': r'(兰音|兰兰|兰兔).{0,30}(黑料|塌房|私联|圈钱|骗钱|实锤|出轨|疑似|听说)',
    'ad': r'群号|群聊邀请|扫码(?:进|加)群|刷单|返利|日赚|内部名额|保证收益|稳赚|(?:进群|入群|加群).{0,12}(?:领取|福利|资源|免费|私聊|私信|扫码|\d{5,})|(?:领取|福利|资源|免费|私聊|私信).{0,12}(?:进群|入群|加群)|加(?:微信|[Vv]信|[Vv]x)',
    'scam': r'官方.{0,12}(?:收款|收费|转账)|(?:集资|借[款钱]).{0,10}(?:给我|转我|借我|扫码|群内|大家|私聊|收款)|收款码|内部名额|保证收益|稳赚|验证码.{0,10}(?:给我|发我)',
    'vulgar': r'约炮|裸聊|黄片|卖淫|强奸|做爱|成人视频|(?:发|看|要|求|资源|分享).{0,6}(?:色情|黄片)',
    'snowluma': r'^snowluma状态.{0,12}版本:.{0,24}平台:.{0,24}运行时长:',
    'politics': r'键政|政党|共产党|民进党|国民党|习近平|台独|政变|颠覆政权',
}
COMPILED = {k: re.compile(v, re.I) for k, v in PATTERNS.items()}
AD_LINK_HOSTS = ('bilibili.com', 'b23.tv', 'douyin.com', 'qzone.qq.com', 'qq.com',
                 'xiaohongshu.com', 'xhslink.cn', '114514.tv')
LINK = re.compile(r'(?:https?://|www\.)[^\s]+', re.I)
AD_CTA = re.compile(r'进群|入群|加群|领取|福利|资源|免费|私聊|私信|扫码|加(?:微信|[Vv]信|[Vv]x)')
CLAUSE_BREAK = re.compile(r'[,，。!！?？;；\r\n]')
SENTENCE_BREAK = re.compile(r'[。!！?？;；\r\n]')
TRADE_ACTION = r'接单|下单|报价|收款|扫码付款|加我|私聊我|私信我'
TRADE_AD = re.compile(rf'(?:代充|代购).{{0,12}}(?<!不)(?:{TRADE_ACTION})|(?<!不)(?:{TRADE_ACTION}).{{0,12}}(?:代充|代购)')
ID_FIELD = r'身份证(?:号(?:码)?)?'
PHONE_FIELD = r'手机号(?:码)?'
NAME_FIELD = r'(?:真实姓名|真名)'
ADDRESS_FIELD = r'(?:(?:家庭)?住址|住在)'
PRIVACY_FIELD = re.compile(rf'{ID_FIELD}|{PHONE_FIELD}|{NAME_FIELD}|{ADDRESS_FIELD}')
NAME_VALUE = r'(?!未知|不详|保密|必填|选填|待确认)[\u4e00-\u9fff]{2,4}$'
PRIVACY_VALUES = re.compile(
    rf'{ID_FIELD}(?:[是为]|:)?(?:\d{{17}}[\dx]|\d{{15}})(?![\dx])'
    rf'|{PHONE_FIELD}(?:[是为]|:)?(?:\+?86-?)?1[3-9](?:-?\d){{9}}(?!\d)'
    rf'|{NAME_FIELD}:{NAME_VALUE}'
    rf'|(?:他|她|某人|群友)的?{NAME_FIELD}(?:是|叫){NAME_VALUE}'
    rf'|{ADDRESS_FIELD}(?:[是为]|:)?[\u4e00-\u9fff\d]{{1,20}}(?:路|街|巷|小区|花园|家园|公寓|大厦)'
    r'[\d一二三四五六七八九十百零〇]{1,6}(?:号|栋|室|单元)'
)
PRIVACY_PERSON = re.compile(r'(?:他|她|你|某人|那(?:位|个人)|对方|群友)的|(?:把|查)(?:他|她|对方)|楼上|@\d+')
PRIVACY_ACTION = re.compile(r'谁(?:有|知道)|(?:^|[来请])求|查(?:一)?下|查出|发(?:一下|出来|给我)|贴出来|公布|公开|曝光|泄露|告诉我')
DOXXING = re.compile(r'(?:开盒|人肉)(?:了|一下)?(?:你|他|她|某人|楼上|那个人|@\d+)|'
                     r'(?:把|对).{1,12}(?:开盒|人肉)|(?:一起|来帮我|让人|扬言要)(?:开盒|人肉)')
MENTIONED_DOXXING = re.compile(r'(?:(?:我|我们)(?:要|来)|一起|来帮我|给我)?(?:开盒|人肉)(?:了|一下)?')
PROTECTED_NAME = re.compile(r'^(?:兰音|兰兰|兰兔|兔兔)(?=[,:、]|你|(?:就)?是)')
VOCATIVE = re.compile(r'^([^,:、。!?]{1,30})[,:、]')
PERSONAL_INSULT = re.compile(
    r'^(?:你(?:(?:真|就|还)?是(?:个|一个)?|这(?:个)?))?'
    r'(?:废物|傻[逼比b]|脑残|贱[人货])[啊呀吧呢了]*|'
    r'^你(?:真|就)?是(?:个|一个)?(?:垃圾|骗子)[啊呀吧呢了]*|'
    r'^(?:给我)?去死(?:吧|啊)?$|^(?:[操艹肏]你|你[妈麻]死|死全家)$'
)
HOSTILE_COMPARISON = re.compile(r'^(?:你(?:就)?)?像[^。!?;]{1,25}(?:拖累所有人|趁早闭嘴)')
STOP_REQUEST = re.compile(r'^(?:请|我刚说过|我说过)?(?:别|不要|停止)(?:再)?'
                          r'(?:拿.{1,12}叫我|叫我|(?:这么|这样)叫(?:我)?|这么称呼我|用.{1,12}(?:叫|骂)我|'
                          r'对我这么说|这么说我|骂我|攻击我)')
REPEATED_ADDRESS = re.compile(r'^(?:你(?:真是|就是|是)|又是)?(?!今天|刚才|这个|那个|好的|[你我他她])'
                              r'([\u3400-\u9fff]{2,12}?)(?=今天|又|来[了啦]|也|真|总|怎么|[,:、。!?]|$)')
SYSTEM_PREFIXES = ('生成失败：', '生成失败:')
SYSTEM_MARKERS = ('upstream_text_reply',)
# Some OneBot implementations render media as text segments. They are display
# labels, not message content, so they must never make unrelated media look alike.
MEDIA_PLACEHOLDERS = frozenset({'[图片]'})
REPLY_REACTION = re.compile(r'(?:哇|啊|哦|这|也|真的|看着|看起来|看上去|感觉|好|很|太|真)*'
                            r'(?:好吃|想吃|好香|香|可爱|漂亮|好看|好棒|谢谢(?:你)?|赞|好吃诶)'
                            r'(?:啊|呀|哇|呢|诶|了|欸|喔|捏|哈|耶|哦)*[!！。~～]*')
POST_REFERENCE = re.compile(r'(?:你)?(?:刚才|刚刚|刚|之前|前面|上面)?(?:发|贴|晒|分享)的(?:那[个张份条])?'
                            r'(午饭|晚饭|早饭|午餐|晚餐|早餐|饭|照片|图片|图)')


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


def privacy_signal(clauses, mentions):
    for clause in clauses:
        if DOXXING.search(clause) or PRIVACY_VALUES.search(clause):
            return True
        if mentions and MENTIONED_DOXXING.fullmatch(clause):
            return True
        if (PRIVACY_FIELD.search(clause) and PRIVACY_ACTION.search(clause)
                and (mentions or PRIVACY_PERSON.search(clause))):
            return True
    return False


def reply_ids(msg):
    return {str(segment['data']['id']) for segment in msg.get('segments', [])
            if segment.get('type') == 'reply' and segment.get('data', {}).get('id')}


def attack_target(cfg, msg, text, previous):
    targets = {str(account) for account in msg.get('mentions', [])
               if str(account).isascii() and str(account).isdigit() and str(account) != '0'}
    quoted = reply_ids(msg)
    targets.update(str(row['user_id']) for row in previous if row['message_id'] in quoted)
    name = PROTECTED_NAME.match(text)
    if name:
        targets.add(str(cfg.protected_qq))
        text = text[name.end():].lstrip(',:、')
        if text.startswith(('是', '就是')):
            text = '你' + text
    else:
        vocative = VOCATIVE.match(text)
        if vocative:
            named = {str(row['user_id']) for row in previous if normalize(row.get('name', '')) == vocative[1]}
            if named:
                targets.update(named)
                text = text[vocative.end():]
    if not targets and not quoted and text.startswith('你'):
        own_ids = {row['message_id'] for row in previous if row['user_id'] == msg['user_id']}
        for row in previous[-3:]:
            if row['user_id'] != msg['user_id'] and msg['time'] - row['time'] <= 30:
                if str(msg['user_id']) in row.get('mentions', []) or reply_ids(row) & own_ids:
                    targets.add(str(row['user_id']))
    if len(targets) == 1 and str(msg['user_id']) not in targets:
        return next(iter(targets)), text
    return None, text


def directed_attack(cfg, msg, text, recent):
    quoted = reply_ids(msg)
    if not (quoted or msg.get('mentions') or text.startswith('你') or VOCATIVE.match(text) or PROTECTED_NAME.match(text)):
        return None
    previous = [row for row in recent if row['message_id'] != msg['message_id']]
    target, addressed = attack_target(cfg, msg, text, previous)
    if target is None:
        return None
    rule = 'lanyin_attack' if target == str(cfg.protected_qq) else 'abuse'
    if PERSONAL_INSULT.fullmatch(CLAUSE_BREAK.split(addressed, maxsplit=1)[0]) or HOSTILE_COMPARISON.match(addressed):
        return rule, [msg['message_id']]

    phrase = REPEATED_ADDRESS.match(addressed)
    if not phrase:
        return None
    if len(quoted) != 1:
        return None
    for index, row in enumerate(previous):
        if row['message_id'] in quoted and str(row['user_id']) == target and STOP_REQUEST.match(normalize(row['text'])):
            for earlier in reversed(previous[:index]):
                if earlier['user_id'] != msg['user_id']:
                    continue
                earlier_target, earlier_text = attack_target(cfg, earlier, normalize(earlier['text']), previous[:index])
                earlier_phrase = REPEATED_ADDRESS.match(earlier_text)
                if earlier_target == target and earlier_phrase and earlier_phrase[1] == phrase[1]:
                    return rule, [earlier['message_id'], msg['message_id']]
    return None


def clear_mention_reply(msg, earlier, quoted, references):
    """Recognize short reactions with a verifiable link to the other message."""
    text = normalize(msg['text'])
    if quoted and REPLY_REACTION.fullmatch(text):
        return True
    reference = POST_REFERENCE.match(text)
    if not reference or not REPLY_REACTION.fullmatch(text[reference.end():].lstrip('，,:：')):
        return False
    if references and not quoted:
        return False
    subject = reference[1]
    posts = quoted or earlier
    if any(subject in normalize(row['text']) for row in posts):
        return True
    return sum('image' in row['media'] and not row['text'].strip() for row in posts) == 1


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


def segment_file_id(data):
    return str(data.get('file') or data.get('file_id') or data.get('emoji_id') or data.get('id') or '')


def repeat_text(msg):
    """Signature for duplicate detection; empty when there is nothing comparable.

    Text compares by content. Media segments contribute a type:id token —
    QQ supplies a stable file id for stickers and images, so the same media
    counts as a repeat while id-less media stays invisible as before.
    Cards keep their readable summary through the message text fallback.
    """
    segments = msg.get('segments')
    if isinstance(segments, list) and segments:
        pieces = []
        for segment in segments[:200]:
            if not isinstance(segment, dict):
                continue
            kind, data = segment.get('type'), segment.get('data')
            if not isinstance(data, dict):
                continue
            if kind == 'text':
                pieces.append(str(data.get('text') or ''))
            else:
                fid = segment_file_id(data)
                if fid:
                    pieces.append(f'|{kind}:{fid}|')
        value = ''.join(pieces) if pieces else (msg.get('text') or '')
    else:
        value = msg.get('text') or ''
    plain = normalize(value)
    return '' if plain in MEDIA_PLACEHOLDERS else plain


def detect(cfg, msg, recent):
    if system_message(msg):
        return {}
    plain = repeat_text(msg)
    visible_text = readable_message(msg)['text']
    text = normalize(visible_text)
    clauses = [normalize(clause) for clause in CLAUSE_BREAK.split(visible_text)]
    own = [x for x in recent if x['user_id'] == msg['user_id']]
    hits = {}
    for kind, pattern in COMPILED.items():
        match = pattern.search(text)
        if match:
            hits[kind] = [msg['message_id']]
    if 'snowluma' in hits:
        return {'snowluma': hits['snowluma']}
    attack = directed_attack(cfg, msg, text, recent)
    if attack:
        rule, evidence = attack
        hits[rule] = evidence
    if 'ad' not in hits and any(TRADE_AD.search(normalize(sentence)) for sentence in SENTENCE_BREAK.split(visible_text)):
        hits['ad'] = [msg['message_id']]
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
    # Identical media share a file-id signature; media without ids never look alike.
    repeated = [x for x in own if plain and repeat_text(x) == plain]
    if len(repeated) >= cfg.repeat_count:
        hits['repeat'] = [x['message_id'] for x in repeated[-30:]]
    if str(cfg.protected_qq) in text or privacy_signal(clauses, msg['mentions']):
        hits['privacy'] = [msg['message_id']]
    if str(cfg.protected_qq) in msg['mentions']:
        hits['mention'] = [msg['message_id']]
    if any(str(group) in text for group in cfg.protected_groups):
        hits['protected_group'] = [msg['message_id']]
    for key, words in [('blocked', cfg.blocked_words), ('unrelated', cfg.unrelated_streamers), ('sensitive', cfg.sensitive_topics)]:
        if any(normalize(word) in text for word in words if normalize(word)):
            hits[key] = [msg['message_id']]
    return hits

"""Deterministic record interpretation; never executes a moderation action."""
from group_watch.utils.time import SHANGHAI, now
import re
import math
import unicodedata
from collections import Counter
from datetime import datetime, timedelta


def normalize_account(value):
    text = re.sub(r'\s+', '', unicodedata.normalize('NFKC', str(value or '')))
    return (text.lstrip('0') or '0') if text.isdigit() else text.casefold()


def member_key(record):
    return (record['group_id'], normalize_account(record['member_id']))


def fold(text):
    return re.sub(r'[\s，,。；;、/（）()\-—_]', '', unicodedata.normalize('NFKC', str(text))).casefold()


def rule_for(category, rules):
    wanted = fold(category)
    if not wanted:
        return None
    for rule in rules:
        if wanted == fold(rule['reason']):
            return rule
    aliases = {'提及无关up主': '提及无关主播/up主'}
    for alias, canonical in aliases.items():
        if wanted == fold(alias):
            return next((r for r in rules if r['reason'] == canonical), None)
    for rule in rules:
        if wanted in [fold(x) for x in re.split(r'[、，,；;]', rule['reason']) if x.strip()]:
            return rule
    return None


def is_removal(text):
    return any(x in text for x in ('移出', '踢出', '清出群聊', '请出群聊', '黑名单', '封禁账号')) and not any(x in text for x in ('不移出', '未移出', '无需移出', '不踢出'))


def punishment_type(text):
    return '移出群聊' if is_removal(text) else '禁言' if '禁言' in text else '警告' if '警告' in text else '其他'


def chinese_number(text):
    text = text.replace('个', '').replace('两', '二').replace('半', '0.5')
    try:
        return float(text)
    except ValueError:
        digits = dict(zip('零一二三四五六七八九', range(10)))
        value = part = 0
        for char in text:
            if char in digits:
                part = digits[char]
            elif char in ('十', '百', '千'):
                value += (part or 1) * {'十': 10, '百': 100, '千': 1000}[char]
                part = 0
            else:
                return None
        return float(value + part) if text else None


def duration_delta(text):
    if re.search(r'[\d.零一二两三四五六七八九十]+\s*(?:分钟|小时|天|日|周|星期|个月|月|年)?\s*[-~～至到—–]\s*[\d.零一二两三四五六七八九十]+\s*(分钟|小时|天|日|周|星期|个月|月|年)', text):
        return None
    match = re.search(r'([\d.零一二两三四五六七八九十百千半]+)\s*个?\s*(分钟|小时|天|日|周|星期|个月|月|年)', text)
    if not match:
        return None
    number = chinese_number(match[1])
    if number is None or number <= 0:
        return None
    days = {'分钟': 1/1440, '小时': 1/24, '天': 1, '日': 1, '周': 7, '星期': 7, '个月': 30, '月': 30, '年': 365}
    try:
        return timedelta(days=number * days[match[2]])
    except OverflowError:
        return None


def parse_time(value):
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    return parsed.astimezone(SHANGHAI).replace(tzinfo=None) if parsed.tzinfo else parsed


def ban_info(record, moment=None):
    if record['punishment'] != '禁言':
        return None
    moment = moment or now()
    text = record.get('penalty_text') or ''
    explicit = False
    start = None
    end = None
    basis = '按处理日期与处罚文字推算；起始时刻未核实'
    dates = re.findall(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}(?:[ T]\d{1,2}:\d{2})?',text)
    try:
        def original_time(value):
            year,month,day,*clock = re.split(r'[-/ T]',value)
            return datetime.fromisoformat(f'{int(year):04}-{int(month):02}-{int(day):02}'+('T'+clock[0].zfill(5) if clock else ''))
        start=original_time(dates[0]) if dates else datetime.fromisoformat(record['event_date'])
        if len(dates)>1:
            end=original_time(dates[1])
        if dates:
            explicit='T' in dates[0] or ' ' in dates[0]
            basis='处罚原文写明日期'+('与时刻' if explicit else '；未注明时刻，按零点展示')
    except ValueError:
        pass
    permanent = any(word in text for word in ('永久', '无限期', '无期限'))
    if start and not end and not permanent:
        delta = duration_delta(text)
        if delta:
            try:
                end = start + delta
                if '月' in text or '年' in text:
                    basis += '；月按30天、年按365天估算'
                    explicit = False
            except OverflowError:
                pass
    if end and start and end <= start:
        status = '待核实'
        basis = '结束时间不晚于开始时间，请核实原文'
    elif start and start > moment:
        status = '未开始'
    elif end and end <= moment:
        status = '已结束'
    elif permanent:
        status = '永久禁言'
    elif end:
        status = '进行中'
    else:
        status = '未注明结束'
    remaining = max(1, math.ceil((end-moment).total_seconds()/86400)) if status == '进行中' else None
    return {'status': status, 'remaining_days': remaining, 'start': start.isoformat(timespec='minutes') if start else '',
            'end': end.isoformat(timespec='minutes') if end else '', 'estimated': not explicit, 'basis': basis}


def count_for(records, candidate, rule, rules):
    def same(record):
        if member_key(record) != member_key(candidate) or record['id'] == candidate.get('id'):
            return False
        category = record['reason']
        other = rule_for(category, rules)
        return other['id'] == rule['id'] if other and rule else fold(category) == fold(candidate['reason'])
    return sum(1 for record in records if same(record))


def suggestion(records, rules, candidate):
    rule = rule_for(candidate.get('reason',''), rules)
    previous = count_for(records, candidate, rule, rules)
    steps = rule['steps'] if rule else []
    # An empty later stage is not permission to reuse an earlier sanction.
    penalty = steps[previous] if previous < len(steps) else ''
    return {'previous': previous, 'occurrence': previous + 1, 'penalty': penalty,
            'rule': rule['reason'] if rule else '', 'notes': rule['notes'] if rule else '',
            'message': '按同群、同账号、同类行为的记录条数计算；仅作建议，可手工修改。' if rule else '未匹配到处理规则，请手工决定。'}


def decorate_records(records):
    for record in records:
        record['ban'] = ban_info(record)
    return records


def risk_members(records, rules):
    members = {}
    # Resolve each category once per call. Rules may change between requests.
    resolved = {}
    for record in records:
        members.setdefault(member_key(record), []).append(record)
        category = record['reason']
        if category not in resolved:
            resolved[category] = (rule_for(category, rules) or {}).get('id')
    result = []
    for history in members.values():
        latest = history[0]
        removed = [r for r in history if r['punishment'] == '移出群聊']
        grounds, warnings = [], []
        counts = Counter(resolved[r['reason']] for r in history)
        for rule in rules:
            matching = counts[rule['id']]
            if not matching:
                continue
            level = next((i+1 for i, value in enumerate(rule['steps']) if is_removal(value)), None)
            if level and matching >= level:
                grounds.append(f"{rule['reason']}：{matching} 条，规则第 {level} 次移出")
            elif level and matching == level-1:
                warnings.append(f"{rule['reason']}：已有 {matching} 条，再犯一次达到移出档")
        status = '已记录移出' if removed else '达到移出规则' if grounds else '再犯预警' if warnings else ''
        if status:
            result.append({'nickname': latest['nickname'], 'member_id': latest['member_id'], 'group_id': latest['group_id'],
                           'status': status, 'total': len(history), 'latest': latest['event_date'],
                           'grounds': ([f"{r['event_date']} · {r.get('penalty_text') or r['punishment']}" for r in removed] + grounds + warnings),
                           'record_ids': [r['id'] for r in history]})
    return result

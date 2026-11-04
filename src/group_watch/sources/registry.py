"""The platform boundary: live rooms/members enter the ordinary group workflow."""
from group_watch.sources.qq import Directory
from group_watch.sources.members import Members
import asyncio
import json
import math
import re
import sqlite3
from contextlib import closing
from pathlib import Path


def positive_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[1-9]\d{0,18}', value) or int(value) > 2**63-1:
        raise ValueError('直播房间号或用户号无效')
    return int(value)


class Sources(Directory):
    def __init__(self, cfg, qq, store):
        super().__init__(cfg, qq)
        self.store = store
        self.member_store = Members(cfg.db_path)
        self.members = {g: {str(row['user_id']): self.member_row(row) for row in self.member_store.rows(g)}
                        for g in cfg.groups}
        self.live_members = {}
        self.loop = None
        configured = set(self.group_ids)
        evidence=Path(cfg.evidence_data or Path(cfg.db_path).parent/'group-evidence')/'evidence.sqlite3'
        if evidence.exists():
            with closing(sqlite3.connect(evidence)) as records:
                referenced={r[0] for r in records.execute('SELECT DISTINCT group_id FROM records')}
            if referenced-configured:
                raise ValueError('监控配置仍被正式档案引用，须先处理档案群引用')
        with store.db:
            store.db.executemany('DELETE FROM registered_groups WHERE group_id=?', [(r[0],) for r in store.db.execute('SELECT group_id FROM registered_groups') if r[0] not in configured])
            store.db.executemany('INSERT INTO registered_groups VALUES(?,?,?) ON CONFLICT(group_id) DO NOTHING',
                [(g, 'qq' if g > 0 else 'bilibili', self.cfg.live_rooms.get(-g, '群聊名称待确认')) for g in configured])
        self.groups = {r['group_id']:r['name'] for r in store.db.execute('SELECT * FROM registered_groups')}

    async def refresh(self):
        self.loop = asyncio.get_running_loop()
        try:
            await super().refresh()
        finally:
            self.groups.update({-room:name for room,name in self.cfg.live_rooms.items()})
            with self.store.db:
                self.store.db.executemany('UPDATE registered_groups SET name=? WHERE group_id=?',
                    [(self.groups[g],g) for g in self.group_ids if g in self.groups])

    @property
    def group_ids(self):
        return self.cfg.groups + [-room for room in self.cfg.live_rooms]

    def name(self, group):
        group = int(group)
        return self.cfg.live_rooms.get(-group, '直播间') if group < 0 else super().name(group)

    def account(self, group, user):
        return str(-abs(int(user)) if int(group) < 0 else abs(int(user)))

    def internal_user(self, group, account):
        value = str(account)
        try:
            user = abs(int(value))
            return -user if int(group) < 0 else user
        except ValueError:
            return 0

    def live_member(self, group, user):
        return self.live_members.get((int(group), self.internal_user(group, user)), {})

    def member(self, group, account):
        if int(group) >= 0:
            return super().member(group, account)
        sender = self.live_member(group, account).get('sender', {})
        return str(sender.get('card') or sender.get('nickname') or '')[:100]

    def verified_identity(self, group, account='', name=''):
        """Use a verified account or one exact, unambiguous name in a known room."""
        if group not in self.group_ids:
            return None
        if group < 0:
            rows = []
            for (gid, uid), item in self.live_members.items():
                if gid != group: continue
                row = {'user_id':uid, 'payload':json.dumps(item)}
                sender = json.loads(row['payload']).get('sender', {})
                rows.append(dict(user_id=self.account(group,row['user_id']), name=str(sender.get('card') or sender.get('nickname') or ''),
                                 nickname=sender.get('nickname',''),card=sender.get('card','')))
        else:
            rows = [dict(row,user_id=key) for key,row in self.members.get(group,{}).items()]
        if account:
            verified = self.account(group,self.internal_user(group,account))
            matches = [row for row in rows if row['user_id']==verified]
        else:
            name = str(name).strip().casefold()
            matches = [row for row in rows if name and name in {str(row.get(k,'')).strip().casefold() for k in ('name','nickname','card')}]
        if len(matches)!=1:
            return None
        row = matches[0]
        return dict(group_id=str(group),group_name=self.name(group),member_id=row['user_id'],
                    nickname=row.get('nickname'),card=row.get('card'))

    async def tool(self, name, args):
        if name == 'list_groups' and not args:
            # A disconnected QQ endpoint must not block live identity queries.
            if not all(g in self.groups for g in self.cfg.groups):
                try:
                    async with asyncio.timeout(4):
                        await self.refresh()
                except (ValueError, OSError, TimeoutError):
                    pass
            return [{'group_id':str(g), 'group_name':self.name(g)} for g in self.group_ids]
        if name == 'find_members' and set(args) == {'group_id', 'query'} and int(args['group_id']) < 0:
            group, query = int(args['group_id']), str(args['query']).strip().casefold()
            if group not in self.group_ids or not query or len(query) > 100:
                raise ValueError('仅能查询受监控群的明确成员线索')
            rows = [dict(user_id=uid,payload=json.dumps(item)) for (gid,uid),item in reversed(list(self.live_members.items())) if gid==group]
            found = []
            for row in rows:
                sender = json.loads(row['payload']).get('sender', {})
                nickname = str(sender.get('card') or sender.get('nickname') or '')[:100]
                account = self.account(group, row['user_id'])
                if query in (account, str(abs(row['user_id']))) or query in nickname.casefold():
                    found.append(dict(user_id=account, name=nickname, level=sender.get('level', ''), role=sender.get('role', '')))
                if len(found) == 20:
                    break
            return found
        return await super().tool(name, args)

    def adapt_batch(self, body):
        if not isinstance(body, dict) or body.get('schema_version') != 1 or body.get('source') != 'bilibili_live':
            raise ValueError('直播批次版本或来源无效')
        events = body.get('events')
        if not isinstance(events, list) or not 1 <= len(events) <= 100:
            raise ValueError('直播批次须包含1–100条事件')
        result = []
        for item in events:
            if not isinstance(item, dict) or len(json.dumps(item, ensure_ascii=False).encode()) > 65536:
                raise ValueError('直播事件格式或大小无效')
            room, user = positive_id(item.get('group_id')), positive_id(item.get('user_id'))
            mid = item.get('event_id')
            if (room not in self.cfg.live_rooms or item.get('source') != 'bilibili_live'
                    or item.get('source_id') != f'bilibili:live:{room}'
                    or item.get('event_type') not in ('danmaku', 'super_chat')
                    or not isinstance(mid, str) or not mid.startswith(f'bilibili:live:{room}:') or len(mid) > 512):
                raise ValueError('直播事件来源或标识无效')
            stamp = item.get('time')
            if isinstance(stamp, bool) or not isinstance(stamp, (int, float)) or not math.isfinite(stamp):
                raise ValueError('直播事件时间无效')
            message, sender = item.get('message'), item.get('sender')
            if not isinstance(message, list) or not isinstance(sender, dict) or not isinstance(item.get('assets'), dict) or not isinstance(item.get('bilibili'), dict):
                raise ValueError('直播事件内容无效')
            if any(not isinstance(p, dict) or not isinstance(p.get('data'), dict) for p in message):
                raise ValueError('直播消息段无效')
            result.append(dict(post_type='message', message_type='group', group_id=-room, user_id=-user,
                               time=stamp, message_id=mid, message=message, sender=sender, live=item))
        return result

    def remember(self, event):
        key = (event['group_id'],event['user_id'])
        self.live_members.pop(key, None)
        self.live_members[key] = event['live']
        while len(self.live_members) > 5000:
            self.live_members.pop(next(iter(self.live_members)))

    def archive_profile(self, record, root):
        group, account = int(record['group_id']), str(record['member_id'])
        if group < 0:
            item = self.live_member(group, account)
            sender = item.get('sender', {})
            result = {'card':None, 'avatar_url':item.get('assets',{}).get('avatar_url') or sender.get('avatar_url','')}
            if isinstance(sender.get('nickname'),str): result['nickname'] = sender['nickname']
            return result
        cached = self.member_store.get(group, int(account))
        if cached and isinstance(cached.get('nickname'), str):
            return {k: cached[k] for k in ('nickname', 'card') if isinstance(cached.get(k), str)}
        async def lookup():
            info = await self.qq.call('get_group_member_info', {'group_id':group,'user_id':int(account),'no_cache':True})
            if not isinstance(info,dict) or str(info.get('user_id'))!=account or int(info.get('group_id',group))!=group:
                raise ValueError('未确认群成员身份')
            self.remember_members(group, [info])
            return {k:info[k] for k in ('nickname','card') if isinstance(info.get(k),str)}
        if self.loop is None or not self.loop.is_running():
            raise ValueError('成员资料连接尚未就绪')
        future=asyncio.run_coroutine_threadsafe(lookup(), self.loop)
        try:
            return future.result(timeout=8)
        finally:
            if not future.done(): future.cancel()

    async def presentation(self, case, assets):
        if case['group_id'] >= 0:
            return None
        semaphore = asyncio.Semaphore(4)
        async def render(original):
            async with semaphore:
                live = original.get('live', {})
                sender, links, meta = live.get('sender', {}), live.get('assets', {}), live.get('bilibili', {})
                row = {k:original[k] for k in ('message_id', 'user_id', 'time', 'name')}
                row.update(account=self.account(case['group_id'], original['user_id']),
                           avatar=await assets.image(links.get('avatar_url') or sender.get('avatar_url', '')),
                           pendant=await assets.image(links.get('pendant_url', '')), nameplate=await assets.image(links.get('nameplate_url', '')),
                           level=sender.get('level', ''), role=sender.get('role', ''), medal=meta.get('medal'),
                           guard_level=meta.get('guard_level'), super_chat=meta.get('super_chat') if live.get('event_type') == 'super_chat' else None)
                row['parts'] = []
                for part in original.get('segments', [])[:100]:
                    kind, data = part.get('type'), part.get('data', {})
                    if kind == 'text':
                        row['parts'].append(dict(type='text', text=str(data.get('text', ''))[:8000]))
                    elif kind in ('face', 'image'):
                        row['parts'].append(dict(type=kind, url=await assets.image(data.get('url', '')), text=str(data.get('text') or '表情')[:100]))
                    else:
                        row['parts'].append(dict(type='unsupported', text='附件'))
                return row
        return dict(group_name=self.name(case['group_id']), messages=await asyncio.gather(*(render(m) for m in case['context'][-40:])),
                    decoration_note='头像、等级、勋章与醒目留言取自原始直播消息。')

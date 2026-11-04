"""Bounded OneBot requests; DS gets only the directory's read-only tools."""
import asyncio
import json
import time
import uuid
import websockets

READ_ACTIONS = {'get_group_list', 'get_group_member_list', 'get_group_member_info', 'get_friend_list', 'get_stranger_info', 'get_msg', 'get_image', 'fetch_face_entity', '_get_friend_dress'}


class QQ:
    def __init__(self, cfg):
        self.cfg = cfg

    async def call(self, action, params=None):
        if action not in READ_ACTIONS | {'send_group_msg', 'send_private_msg'}:
            raise ValueError('不允许的 QQ 操作')
        echo = uuid.uuid4().hex
        token = self.cfg.ws_token.get_secret_value()
        async with asyncio.timeout(20):
            async with websockets.connect(self.cfg.ws_url, additional_headers={'Authorization': 'Bearer '+token} if token else {},
                                          proxy=None, max_size=8*1024*1024, max_queue=8) as ws:
                await ws.send(json.dumps({'action': action, 'params': params or {}, 'echo': echo}))
                async for raw in ws:
                    row = json.loads(raw)
                    if row.get('echo') == echo:
                        if row.get('status') != 'ok' or row.get('retcode', 0) != 0:
                            raise ValueError('QQ 未确认操作成功')
                        return row.get('data')
        raise ValueError('QQ 未返回结果')


class Directory:
    def __init__(self, cfg, qq):
        self.cfg, self.qq = cfg, qq
        self.groups, self.members, self.friends = {}, {}, {}
        self.group_counts = {}
        self.checked = 0
        self.member_checked = {}
        self.member_store = None
        self.lock = asyncio.Lock()

    async def refresh(self):
        async with self.lock:
            if time.time()-self.checked < 900:
                return
            groups = await self.qq.call('get_group_list', {'no_cache': True})
            # Missing names or a failed member refresh must not erase known groups.
            self.groups.update({int(x['group_id']): str(x['group_name'])[:100] for x in groups if x.get('group_name') and int(x['group_id']) in self.cfg.groups})
            self.group_counts = {int(x['group_id']): int(x.get('member_count') or 0) for x in groups if int(x['group_id']) in self.cfg.groups}
            async def members(group):
                if time.time() - self.member_checked.get(group, 0) < 7200:
                    return
                rows = await self.qq.call('get_group_member_list', {'group_id': group, 'no_cache': True})
                self.remember_members(group, rows)
                self.member_checked[group] = time.time()
            results = await asyncio.gather(*(members(group) for group in self.cfg.groups), return_exceptions=True)
            if any(isinstance(result, BaseException) for result in results):
                raise ValueError('部分群成员资料暂不可用')
            self.checked = time.time()

    def remember_members(self, group, rows):
        if self.member_store:
            self.member_store.save(group, rows)
        self.members.setdefault(group, {}).update({str(x['user_id']): self.member_row(x) for x in rows})

    @staticmethod
    def member_row(row):
        return {'user_id': str(row['user_id']), 'name': str(row.get('card') or row.get('nickname') or '')[:100],
                **{key: row.get(key) if isinstance(row.get(key), str) else None for key in ('nickname', 'card')},
                **{key: str(row.get(key) or '')[:100] for key in ('level', 'role', 'title')}}

    def name(self, group):
        return self.groups.get(int(group), '群聊名称待确认')

    def member(self, group, account):
        return self.members.get(int(group), {}).get(str(account), {}).get('name', '')

    async def tool(self, name, args):
        if name == 'list_groups' and not args:
            if not all(g in self.groups for g in self.cfg.groups):
                async with asyncio.timeout(4):
                    await self.refresh()
            return [{'group_id': str(g), 'group_name': self.name(g)} for g in self.cfg.groups]
        if name != 'find_members' or set(args) != {'group_id', 'query'}:
            raise ValueError('工具名称或参数无效')
        group, query = int(args['group_id']), str(args['query']).strip().casefold()
        if group not in self.cfg.groups or not query or len(query)>100:
            raise ValueError('仅能查询受监控群的明确成员线索')
        def matches():
            return [x for account,x in self.members.get(group, {}).items() if query == account or
                    any(query in str(x.get(key,'')).casefold() for key in ('name','nickname','card'))][:20]
        found = matches()
        if found:
            return found
        async with asyncio.timeout(4):
            if query.isascii() and query.isdigit() and 5 <= len(query) <= 12:
                info = await self.qq.call('get_group_member_info', {'group_id':group,'user_id':int(query),'no_cache':True})
                if isinstance(info, dict) and str(info.get('user_id'))==query and int(info.get('group_id') or group)==group:
                    self.remember_members(group, [info])
            elif not self.members.get(group):
                await self.refresh()
        return matches()

    async def resolve_targets(self, targets):
        # Explicit user notification settings can select groups or friends, never arbitrary strangers.
        groups = await self.qq.call('get_group_list')
        friends = await self.qq.call('get_friend_list')
        choices = {('group', str(x['group_id'])): str(x.get('group_name') or '') for x in groups}
        choices.update({('private', str(x['user_id'])): str(x.get('remark') or x.get('nickname') or '') for x in friends})
        result = []
        for target in targets:
            ident, kind = str(target['id']), target.get('kind', 'auto')
            matches = [(k, n) for k,n in choices.items() if k[1] == ident and (kind == 'auto' or k[0] == kind)]
            if len(matches) != 1:
                raise ValueError('通知目标不在当前群聊/联系人中，或类型不明确')
            (kind, ident), name = matches[0]
            result.append({'kind': kind, 'id': ident, 'name': name[:100]})
        return result

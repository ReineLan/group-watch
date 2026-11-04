"""Shared QQ exemptions; nickname lookup never delays persisting the list."""
from group_watch.evidence.profiles import DEFAULT_NICKNAME_API, download, nickname_from_json
import asyncio
import contextlib
import os
import time
from urllib.parse import urlparse

from websockets.exceptions import WebSocketException


class Whitelist:
    def __init__(self, monitor):
        self.monitor = monitor
        self.task = None
        self.attempted = {}
        self.nickname_url = os.environ.get('QQ_NICKNAME_API', DEFAULT_NICKNAME_API).strip()
        if self.nickname_url.lower() in ('off', '0'):
            self.nickname_url = ''

    def external_nickname(self, account):
        account = str(account)
        if not self.nickname_url:
            return ''
        if '{qq}' not in self.nickname_url or urlparse(self.nickname_url).scheme != 'https':
            return ''
        raw = download(self.nickname_url.replace('{qq}', account), 65536)
        return nickname_from_json(raw, account)

    def nickname(self, account):
        if int(account)<0:
            for group in self.monitor.directory.group_ids:
                if group<0:
                    sender=self.monitor.directory.live_member(group,account).get('sender',{})
                    if isinstance(sender.get('nickname'),str): return sender['nickname']
            return ''
        return next((str(members.get(str(account), {}).get('nickname') or '')[:100]
                     for group, members in self.monitor.directory.members.items()
                     if group in self.monitor.cfg.groups and members.get(str(account), {}).get('nickname')), '')

    def snapshot(self):
        return dict(members=[dict(user_id=str(row['user_id']), nickname=self.nickname(row['user_id']) or row['nickname'])
                             for row in self.monitor.store.whitelist()])

    def save(self, accounts):
        previous = {str(row['user_id']): row['nickname'] for row in self.monitor.store.whitelist()}
        self.monitor.store.save_whitelist([dict(user_id=account, nickname=self.nickname(account) or previous.get(account, ''))
                                           for account in dict.fromkeys(accounts)])
        self.refresh()
        return self.snapshot()

    def refresh(self):
        if self.task and not self.task.done():
            return
        self.task = asyncio.create_task(self.fill_names())

    async def fill_names(self):
        # Re-read after each batch so additions made during a lookup are included.
        semaphore = asyncio.Semaphore(4)

        async def fill(row):
            account = row['user_id']
            async with semaphore:
                self.attempted[account] = time.monotonic()
                name = self.nickname(account)
                if not name and int(account)>0 and self.monitor.cfg.ws_url:
                    try:
                        async with asyncio.timeout(5):
                            info = await self.monitor.qq.call('get_stranger_info', {'user_id': int(account)})
                        if isinstance(info, dict) and str(info.get('user_id')) == str(account):
                            name = str(info.get('nickname') or '')[:100]
                    except (ValueError, OSError, TimeoutError, WebSocketException):
                        pass
                if not name and int(account)>0 and self.nickname_url:
                    try:
                        async with asyncio.timeout(6):
                            name = await asyncio.to_thread(self.external_nickname, account)
                    except Exception:
                        pass
                if name:
                    # UPDATE cannot restore a member removed during the lookup.
                    self.monitor.store.whitelist_nickname(account, name)

        while True:
            rows = [row for row in self.monitor.store.whitelist()
                    if not row['nickname'] and time.monotonic()-self.attempted.get(row['user_id'], -900) >= 900]
            if not rows:
                return
            await asyncio.gather(*(fill(row) for row in rows))

    async def close(self):
        if self.task:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.task

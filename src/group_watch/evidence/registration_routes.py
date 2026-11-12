from group_watch.evidence.routes import json_body
from group_watch.evidence.registration import analyze, RegistrationUnavailable, recommend_decisions

from fastapi import HTTPException, Request
import asyncio
import httpx
import re


def install(app, monitor, evidence):
    @app.post('/api/registration/resolve-member')
    async def resolve_member(request: Request):
        """Best-effort member lookup inside one monitored group; digits resolve as accounts."""
        try:
            body = await json_body(request)
            name = str(body.get('name') or '').strip()[:100]
            typed = str(body.get('account') or '').strip()
            account = typed if re.fullmatch(r'[1-9]\d{4,11}', typed) else \
                      name if re.fullmatch(r'[1-9]\d{4,11}', name) else ''
            if isinstance(body.get('group_id'), bool):
                raise ValueError('群聊标识无效')
            try:
                group = int(body.get('group_id'))
            except (TypeError, ValueError):
                raise ValueError('群聊标识无效')
            if not group or group not in monitor.directory.group_ids:
                raise ValueError('请选择已登记的群聊或直播间')
            if not name and not account:
                raise ValueError('昵称无效')
            query = account or name
            identity = monitor.directory.verified_identity(group, account, '' if account else name)
            if identity is None:
                try:
                    async with asyncio.timeout(4):
                        await monitor.directory.tool('find_members', {'group_id': str(group), 'query': query})
                    identity = monitor.directory.verified_identity(group, account, '' if account else name)
                except Exception:
                    pass
            return {'member': identity}
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None

    @app.post('/api/registration/analyze')
    async def analyze_registration(request: Request):
        try:
            body = await json_body(request)
            images = body.get('images', [])
            if not isinstance(images, list) or any(not isinstance(x,dict) for x in images):
                raise ValueError('图片格式无效')
            rules = evidence.get_rules()
            result = await analyze(monitor, images, str(body.get('case_id',''))[:100], str(body.get('context',''))[:10000],
                                   categories=[row['reason'] for row in rules],rules=rules)
            return recommend_decisions(result,rules,evidence.get_records())
        except RegistrationUnavailable as exc:
            raise HTTPException(502, str(exc)) from None
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
        except (httpx.HTTPError, KeyError, TypeError, OSError, TimeoutError):
            raise HTTPException(502, 'DS或QQ资料查询失败，已有表单内容保留，可重试或人工填写') from None

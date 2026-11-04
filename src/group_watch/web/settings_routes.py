from group_watch.web.schemas import PushSettings, FeedbackPoint, FeedbackSource, WhitelistSettings
from group_watch.settings import RuleSettings, BroadcastSettings, rule_settings, save_push_recipients, push_recipients, save_rules, save_broadcast
import time
from pathlib import Path

from fastapi import HTTPException
from dotenv import dotenv_values
import httpx

import re


def install(app, cfg, monitor, whitelist):
    test_at = 0
    broadcast_test_at = 0

    @app.get('/api/settings/feedback')
    async def feedback_points():
        return {'points':monitor.feedback.points()}


    @app.post('/api/settings/feedback')
    async def save_feedback_point(body: FeedbackPoint):
        try:
            source = monitor.feedback.edit(body.source,body.rule,body.verdict,body.summary)
            return {'source':source,'points':monitor.feedback.points()}
        except ValueError as exc:
            raise HTTPException(400,str(exc)) from None


    @app.post('/api/settings/feedback/delete')
    async def delete_feedback_point(body: FeedbackSource):
        monitor.feedback.remove(body.source)
        return {'points':monitor.feedback.points()}


    @app.get('/api/settings/notifications')
    async def notification_settings():
        return dict(configured=bool(push_recipients(cfg)), enabled=cfg.pushplus_enabled,
                    recipients=[dict(id=r.id,name=r.name,configured=bool(r.token.get_secret_value())) for r in push_recipients(cfg)],
                    broadcast_targets=[x.model_dump() for x in cfg.broadcast_targets], broadcast_confidence=cfg.broadcast_confidence, saved_locally=Path(cfg.local_env).is_file() and 'PUSHPLUS_RECIPIENTS' in dotenv_values(cfg.local_env, encoding='utf-8-sig', interpolate=False))


    @app.get('/api/settings/rules')
    async def get_rules():
        return rule_settings(cfg)


    @app.get('/api/settings/whitelist')
    async def get_whitelist():
        whitelist.refresh()
        return whitelist.snapshot()


    @app.post('/api/settings/whitelist')
    async def update_whitelist(body: WhitelistSettings):
        if any(not re.fullmatch(r'-?[1-9][0-9]{0,18}', account) or abs(int(account))>2**63-1 for account in body.accounts):
            raise HTTPException(400, '请检查账号：QQ 为正数，Bilibili UID 为负数')
        return dict(ok=True, **whitelist.save(body.accounts))


    @app.post('/api/settings/rules')
    async def update_rules(body: RuleSettings):
        try:
            save_rules(cfg, body.model_dump())
        except (OSError, ValueError):
            raise HTTPException(500, '规则保存失败，请检查本机配置文件格式和写入权限') from None
        return dict(ok=True, **rule_settings(cfg))


    @app.post('/api/settings/notifications')
    async def save_notifications(body: PushSettings):
        try:
            save_push_recipients(cfg, body.recipients)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
        except OSError:
            raise HTTPException(500, '保存失败，请检查本机 .env 文件写入权限') from None
        return dict(ok=True, configured=bool(push_recipients(cfg)), enabled=cfg.pushplus_enabled)


    @app.post('/api/settings/notifications/test')
    async def test_notifications():
        nonlocal test_at
        if not push_recipients(cfg):
            raise HTTPException(400, '请先保存 PushPlus Token')
        if time.time()-test_at < 30:
            raise HTTPException(429, '请等待 30 秒后再测试')
        test_at = time.time()
        try:
            failed = 0
            for recipient in push_recipients(cfg):
                try:
                    response = await monitor.client.post('https://www.pushplus.plus/send', timeout=15,
                        json=dict(token=recipient.token.get_secret_value(), title='Lan 工作台 · 通知测试',
                                  template='html', content='<p>PushPlus 通知测试。这是一条测试消息，不包含群聊内容或违规事件。</p>'))
                    response.raise_for_status()
                    if response.json().get('code') != 200:
                        raise ValueError()
                except (httpx.HTTPError, ValueError, AttributeError):
                    failed += 1
            if failed:
                raise ValueError()
        except (httpx.HTTPError, ValueError, AttributeError):
            raise HTTPException(502, 'PushPlus 未确认受理，请检查 Token 或稍后重试') from None
        return dict(ok=True, message='PushPlus 已受理测试通知，请查看接收端')


    @app.post('/api/settings/broadcast')
    async def broadcast_settings(body: BroadcastSettings):
        try:
            targets = await monitor.directory.resolve_targets([x.model_dump() for x in body.targets]) if body.targets else []
            save_broadcast(cfg, targets, body.confidence)
            return {'ok':True,'targets':targets,'confidence':body.confidence}
        except (ValueError, OSError, TimeoutError):
            raise HTTPException(400, '通知目标核对或保存失败，请确认QQ已连接及群聊/联系人类型') from None


    @app.post('/api/settings/broadcast/test')
    async def test_broadcast():
        nonlocal broadcast_test_at
        if not cfg.broadcast_targets:
            raise HTTPException(400, '请先保存通知目标')
        if time.time()-broadcast_test_at < 30:
            raise HTTPException(429, '请等待 30 秒后再测试')
        broadcast_test_at = time.time()
        sent = 0
        try:
            targets = await monitor.directory.resolve_targets([x.model_dump() for x in cfg.broadcast_targets])
            for target in targets:
                group = target['kind'] == 'group'
                await monitor.qq.call('send_group_msg' if group else 'send_private_msg', {
                    'group_id' if group else 'user_id': int(target['id']),
                    'message': [{'type':'text','data':{'text':'Lan 工作台 · QQ 通知测试。这是一条测试消息，不包含群聊内容或违规事件。'}}],
                })
                sent += 1
        except (ValueError, OSError, TimeoutError):
            raise HTTPException(502, f'QQ 测试已确认发送 {sent} 个目标，其余未确认；请检查连接与接收端') from None
        return dict(ok=True, message=f'QQ 已确认发送到 {sent} 个通知目标，请查看接收端')

from group_watch.web.schemas import Decision, RegisteredCase
from group_watch.settings import ROOT, push_recipients
from group_watch.monitoring.store import MONITORED_CASE
from group_watch.monitoring.rules import LIMITATIONS, POLICIES, readable_message
import secrets
import json
import time
from urllib.parse import urlsplit

from fastapi import HTTPException, Request
from fastapi.responses import Response, FileResponse

import re


def install(app, cfg, monitor, chat, auth, started, evidence=None):
    @app.post('/internal/events/live')
    async def live_events(request: Request):
        token = cfg.live_forward_token.get_secret_value()
        if not token or not secrets.compare_digest(request.headers.get('authorization', '').encode(), ('Bearer '+token).encode()):
            raise HTTPException(401, '直播接入令牌无效')
        payload = bytearray()
        async for chunk in request.stream():
            payload.extend(chunk)
            if len(payload) > 1024*1024:
                raise HTTPException(413, '直播批次过大')
        try:
            monitor.ingest_live(json.loads(payload))
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            raise HTTPException(400, '直播批次格式无效') from exc
        return Response(status_code=204)


    @app.get('/api/status')
    async def status(request: Request):
        if not auth.authenticated(request):
            return {'project_root':str(ROOT), 'counts':{'open':monitor.store.counts().get('open',0)}}
        tasks = [{'done':t.done(), 'cancelled':t.cancelled()} for t in monitor.tasks]
        qq_port = urlsplit(cfg.ws_url).port or (443 if cfg.ws_url.startswith('wss:') else 80) if cfg.ws_url else None
        return dict(project_root=str(ROOT), connected=monitor.connected, qq_port=qq_port, last_event=monitor.last_event, last_message=monitor.last_message,
                    error=monitor.error, review_error=monitor.review_error, notify_error=monitor.notify_error,
                    ds_configured=bool(cfg.ds_key.get_secret_value()), push_configured=bool(push_recipients(cfg)),
                    push_enabled=cfg.pushplus_enabled, started=started, ds_model=cfg.ds_model,
                    group_names={str(g):monitor.directory.name(g) for g in monitor.directory.group_ids},
                    groups=monitor.directory.group_ids, counts=monitor.store.counts(), tasks=tasks,
                    calls_hour=monitor.quota.calls_hour(time.time()), call_limit=cfg.query_calls_hour,
                    policies=POLICIES, limitations=LIMITATIONS,
                    rules=dict(batch_seconds=cfg.batch_seconds, batch_size=cfg.batch_size,
                               flood_count=cfg.flood_count,
                               flood_seconds=cfg.flood_seconds, repeat_count=cfg.repeat_count,
                               retention_days=cfg.retention_days, blocked_words=cfg.blocked_words,
                               unrelated_streamers=cfg.unrelated_streamers, sensitive_topics=cfg.sensitive_topics),
                    activity=[dict(group_id=group, group_name=monitor.directory.name(group), messages=row[0], last_message=row[1])
                              for group in monitor.directory.group_ids
                              for row in [(len(monitor.store.window_state.activity.get(group,())), max((r[1] for r in monitor.store.window_state.activity.get(group,())),default=None))]],
                    open_cases=monitor.store.db.execute(f"SELECT count(*) FROM cases WHERE resolution='' AND {MONITORED_CASE}").fetchone()[0])


    @app.get('/api/cases/{case_id}/context')
    async def chat_context(case_id: str, request: Request):
        if not auth.authenticated(request): raise HTTPException(401, '请刷新工作台')
        rows=monitor.store.cases('id=?',(case_id,),1)
        if not rows: raise HTTPException(404, '线索不存在')
        try: return await chat.context(rows[0])
        except LookupError: raise HTTPException(404, '线索不存在') from None


    @app.get('/api/chat-assets/{name}')
    async def chat_asset(name: str, request: Request):
        if not auth.authenticated(request): raise HTTPException(401, '请刷新工作台')
        if not re.fullmatch(r'[a-f0-9]{64}\.(png|jpg|gif|webp)',name): raise HTTPException(404)
        path=chat.assets.root/name
        if not path.is_file(): raise HTTPException(404)
        return FileResponse(path)


    @app.get('/api/cases')
    async def cases(state: str = '', offset: int = 0, group: int = 0, resolution: str = '', search: str = '', limit: int = 50, summary: bool = False):
        if state not in ('','attention','pending','violation','clear','unsure') or offset < 0 or offset > 1000000 or not 1 <= limit <= 50:
            raise HTTPException(400, '无效筛选参数')
        if (group and group not in monitor.directory.group_ids) or resolution not in ('','open','handled') or len(search)>200:
            raise HTTPException(400, '无效筛选参数')
        where, args = [], []
        if state in ('pending','clear','unsure'):
            return []
        if group:
            where.append('group_id=?')
            args.append(group)
        if resolution:
            where.append("resolution=''" if resolution=='open' else "resolution<>''")
        if search.strip():
            where.append('(instr(context,?)>0 OR instr(reason,?)>0 OR instr(CAST(user_id AS TEXT),?)>0)')
            args.extend([search.strip()]*3)
        if resolution != 'handled':
            where.append(MONITORED_CASE)
        rows = monitor.store.cases(' AND '.join(where) or '1=1', args, limit, offset=offset)
        for case in rows:
            case['group_name'] = monitor.directory.name(case['group_id'])
            case['member_account'] = monitor.directory.account(case['group_id'], case['user_id'])
            case['member_name'] = monitor.directory.member(case['group_id'], case['user_id']) or next((m['name'] for m in case['context'] if m['user_id']==case['user_id']), '成员资料待确认')
            if not summary:
                case['context'] = [readable_message(msg) for msg in case['context']]
        if summary:
            keys = ('id', 'state', 'rule', 'created', 'group_id', 'group_name', 'member_account', 'member_name')
            return [{key:case[key] for key in keys} for case in rows]
        return rows


    @app.post('/api/cases/{case_id}/registered')
    async def registered_case(case_id: str, body: RegisteredCase):
        """Delete the clue only after the saved archive records are confirmed."""
        ids = list(dict.fromkeys(body.record_ids))
        if not ids:
            raise HTTPException(409, '登记结果未确认，线索保留')
        if evidence is not None:
            with evidence.connect() as db:
                found = {row['id'] for row in db.execute(
                    'SELECT id FROM records WHERE id IN (%s)' % ','.join('?' * len(ids)), ids)}
            if found != set(ids):
                raise HTTPException(409, '登记档案未落库，线索保留')
        deleted = await chat.discard_case(case_id)
        return {'ok': True, 'deleted': deleted}

    @app.delete('/api/cases/{case_id}')
    async def delete_case(case_id: str):
        try:
            deleted = await chat.discard_case(case_id,require_handled=True)
        except ValueError as exc:
            raise HTTPException(409,str(exc)) from None
        if not deleted:
            raise HTTPException(404, '线索不存在')
        return {'ok':True}

    @app.post('/api/cases/{case_id}/decision')
    async def decision(case_id: str, body: Decision):
        if body.resolution not in ('confirmed','dismissed','follow_up',''):
            raise HTTPException(400, '无效处理状态')
        if not monitor.store.db.execute('SELECT 1 FROM cases WHERE id=?', (case_id,)).fetchone():
            raise HTTPException(404, '事件不存在')
        with monitor.store.db:
            monitor.store.db.execute('UPDATE cases SET resolution=?,note=COALESCE(?,note),decision_at=? WHERE id=?', (body.resolution,body.note,time.time(),case_id))
        case = monitor.store.cases('id=?',(case_id,),1)[0]
        monitor.feedback.case(case,body.resolution,case['note'])
        return {'ok':True}

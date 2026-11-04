from group_watch.web.schemas import QueryRequest
from group_watch.query.service import QueryError
import secrets
import asyncio
import time

from fastapi import HTTPException, Request


def install(app, queries, auth, maintenance, csrf):
    @app.post('/evidence/query')
    async def query_data(body: QueryRequest, request: Request):
        if not secrets.compare_digest(request.headers.get('x-csrf-token', ''), csrf):
            raise HTTPException(403, '请求令牌无效，请刷新页面')
        if not auth.authenticated(request):
            raise HTTPException(401, '页面会话已过期，请刷新工作台')
        maintenance.last_activity = time.time()
        task = asyncio.create_task(queries.run(body.question.strip()))
        try:
            while not task.done():
                await asyncio.sleep(.2)
                if await request.is_disconnected():
                    task.cancel()
                    raise HTTPException(499, '查询已停止')
            return await task
        except QueryError as exc:
            raise HTTPException(400, str(exc)) from None
        finally:
            if not task.done():
                task.cancel()
            try:
                await task
            except (asyncio.CancelledError, QueryError):
                pass

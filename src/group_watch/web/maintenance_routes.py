import asyncio
import time

from fastapi import HTTPException
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

import re


def install(app, maintenance, queries, csrf):
    @app.get('/api/maintenance')
    async def maintenance_status():
        return maintenance.status(queries)


    @app.post('/api/maintenance/backup')
    async def create_workbench_backup():
        try:
            path = await run_in_threadpool(maintenance.backup)
            return {'url': '/api/maintenance/backups/' + path.name, 'name': path.name}
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None


    @app.get('/api/maintenance/backups/{name}')
    async def download_workbench_backup(name: str):
        path = maintenance.folder / name
        if not re.fullmatch(r'auto-\d{8}-\d{6}-[a-f0-9]{8}\.tar\.zst', name) or path.is_symlink() or not path.is_file():
            raise HTTPException(404, '备份不存在，请重新创建')
        return FileResponse(path, media_type='application/zstd', filename=name)


    @app.post('/api/maintenance/drain')
    async def drain():
        # Supervisor only requests an idle shutdown after the UI has been quiet.
        if queries.active or maintenance.busy or time.time() - maintenance.last_activity < 120:
            raise HTTPException(409, '工作台正在使用，稍后更新')
        maintenance.draining = True
        return {'ok': True}


    @app.get('/api/maintenance/update-token')
    async def update_token():
        # A local supervisor may prepare shutdown without recording a UI visit.
        return {'token': csrf}


    @app.post('/api/maintenance/restart')
    async def restart():
        if not maintenance.draining or queries.active or maintenance.busy:
            raise HTTPException(409, '尚未进入更新状态')
        callback = getattr(app.state, 'shutdown', None)
        if callback is None:
            maintenance.draining = False
            raise HTTPException(409, '当前启动方式不支持自动重启')
        asyncio.get_running_loop().call_later(.5, callback)
        return {'ok': True}


    @app.post('/api/maintenance/shutdown')
    async def shutdown():
        if queries.active or maintenance.busy:
            raise HTTPException(409, '正在完成查询或备份，请稍后停止')
        callback = getattr(app.state, 'shutdown', None)
        if callback is None:
            raise HTTPException(409, '当前启动方式不支持关闭')
        maintenance.draining = True
        asyncio.get_running_loop().call_later(.5, callback)
        return {'ok':True}

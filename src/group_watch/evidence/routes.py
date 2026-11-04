"""Archive endpoints on the shared FastAPI application; storage is injected per app."""
from group_watch.evidence.domain import decorate_records, suggestion
import binascii
import json
import re

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse
from loguru import logger

MAX_BODY = 60 * 1024 * 1024


async def json_body(request):
    if request.headers.get('content-type', '').split(';')[0] != 'application/json':
        raise ValueError('请求格式须为 application/json')
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > MAX_BODY:
            raise ValueError('请求过大，请减少图片或分批提交')
    body = json.loads(raw)
    if not isinstance(body, dict):
        raise ValueError('请求内容应为对象')
    return body


def create_router(store, feedback=None):
    router = APIRouter(prefix='/evidence')

    @router.get('/api/records')
    def records():
        return decorate_records(store.get_records())

    @router.get('/api/rules')
    def rules():
        return store.get_rules()

    @router.get('/api/profiles')
    def profiles():
        cache = store.get_profiles()
        return {'items':cache.snapshot(), **cache.settings()}

    @router.get('/api/profiles/{account}')
    def profile(account: str):
        try:
            cache = store.get_profiles()
            return {'profile':cache.lookup(account), **cache.settings()}
        except ValueError as exc:
            return JSONResponse({'error':str(exc)}, status_code=400)

    @router.post('/api/profiles/{record_id}/retry')
    def retry_profile(record_id: str):
        try:
            store.get_profiles().retry(record_id)
            return {'ok':True}
        except ValueError as exc:
            return JSONResponse({'error':str(exc)},status_code=404)

    @router.get('/api/overview')
    def overview():
        return store.overview()

    @router.get('/api/backup')
    def backup():
        archive = store.backup()
        return FileResponse(archive, media_type='application/zstd', filename=archive.name)

    @router.post('/api/{operation}')
    async def mutate(operation: str, request: Request):
        from starlette.concurrency import run_in_threadpool
        try:
            body = await json_body(request)
            if operation in ('records', 'batch'):
                result = await run_in_threadpool(store.save_records, body, operation == 'batch')
                if feedback:
                    ids = result.get('ids', [result.get('id')])
                    submitted = body.get('records', [body])
                    notes = {key:str(row.get('notes', ''))[:2000] for key,row in zip(ids, submitted)}
                    for row in await run_in_threadpool(store.get_records):
                        if row['id'] in ids:
                            feedback.record(row, notes.get(row['id'], ''))
                return result
            if operation == 'rules':
                return await run_in_threadpool(store.save_rules, body)
            if operation == 'rollback':
                return await run_in_threadpool(store.rollback, body.get('backup'))
            if operation == 'suggest':
                candidate = {key:body.get(key,'') for key in ('id','member_id','group_id','reason')}
                return await run_in_threadpool(lambda:suggestion(store.get_records(), store.get_rules(), candidate))
            return JSONResponse({'error':'接口不存在'}, status_code=404)
        except (ValueError, TypeError, KeyError, AttributeError, binascii.Error) as exc:
            return JSONResponse({'error':str(exc)}, status_code=400)
        except Exception:
            logger.exception('Archive save failed')
            return JSONResponse({'error':'保存失败，请查看服务日志并重试'}, status_code=500)

    @router.delete('/api/records/{record_id}')
    async def delete(record_id: str, request: Request):
        from starlette.concurrency import run_in_threadpool
        try:
            await json_body(request)
            result = await run_in_threadpool(store.delete_record, record_id)
            if result and feedback:
                feedback.remove('record:'+record_id)
            return result or JSONResponse({'error':'记录不存在'}, status_code=404)
        except (ValueError, TypeError) as exc:
            return JSONResponse({'error':str(exc)}, status_code=400)
        except Exception:
            logger.exception('Archive delete failed')
            return JSONResponse({'error':'删除失败，请查看服务日志'}, status_code=500)

    @router.get('/{kind}/{name}')
    def media(kind: str, name: str):
        if kind not in ('avatars', 'uploads') or not re.fullmatch(r'(?:[1-9]\d{4,11}|[a-f0-9]{64})\.webp', name):
            return JSONResponse({'error':'文件不存在'}, status_code=404)
        folder = store.get_profiles().avatars if kind == 'avatars' else store.uploads
        target = (folder / name).resolve()
        if not target.is_relative_to(folder.resolve()) or not target.is_file():
            return JSONResponse({'error':'文件不存在'}, status_code=404)
        filename = None
        if kind == 'uploads':
            filename = next((image['name'] for record in store.get_records() for image in record['images'] if image['url'] == '/uploads/'+name), None)
        return FileResponse(target, filename=filename, content_disposition_type='inline')

    return router

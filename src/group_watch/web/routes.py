from group_watch.evidence.routes import json_body
from group_watch.resources import frontend_dist

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.responses import JSONResponse


def install(app, auth, csrf):
    @app.get('/evidence/')
    async def legacy_evidence():
        return RedirectResponse('/#records', status_code=307)


    @app.post('/api/auth/login')
    @app.post('/evidence/auth/login')
    async def login(request: Request):
        if not auth.allow_login(request.client.host if request.client else ''):
            return JSONResponse({'error':'尝试过于频繁'}, status_code=429)
        try:
            body = await json_body(request)
        except (ValueError, TypeError):
            return JSONResponse({'error':'无效的登录请求'}, status_code=400)
        if not auth.valid(body.get('token')):
            return JSONResponse({'error':'密码不正确，请重新输入'}, status_code=401)
        response = JSONResponse({'ok':True})
        auth.attach(response, secure=request.url.scheme == 'https')
        return response


    @app.get('/api/auth/session')
    async def session(request: Request):
        return {'authenticated':auth.authenticated(request)}


    @app.post('/api/auth/logout')
    @app.post('/evidence/auth/logout')
    async def logout(request: Request):
        auth.revoke(request)
        response = JSONResponse({'ok':True})
        response.delete_cookie('lan_workspace', path='/')
        return response


    @app.get('/', response_class=HTMLResponse)
    async def index(request: Request):
        response = HTMLResponse((frontend_dist() / 'index.html').read_text(encoding='utf-8').replace('__CSRF__', csrf))
        return response

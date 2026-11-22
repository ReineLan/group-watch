import secrets
import time
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from group_watch.paths import ROOT

import re


SUPERVISOR_ROUTES = frozenset({
    '/api/maintenance/update-token', '/api/maintenance/drain',
    '/api/maintenance/restart', '/api/maintenance/shutdown',
})


def direct_local_request(request, local_host):
    return (local_host and request.client is not None and request.client.host in ('127.0.0.1', '::1')
            and not any(header in request.headers for header in (
                'forwarded', 'x-forwarded-for', 'x-forwarded-host', 'x-forwarded-proto', 'x-real-ip')))


def install(app, cfg, auth, maintenance, csrf):
    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        return JSONResponse({'detail':'请求格式无效，请检查输入'}, status_code=422)


    async def guarded_request(request: Request, call_next):
        # Only the configured proxy origin is allowed beyond the local hosts.
        host = request.headers.get('host', '').lower()
        public_host = urlsplit(cfg.public_url).netloc if cfg.public_url else ''
        local_host = host.split(':')[0] in ('127.0.0.1','localhost','testserver')
        if not local_host and (not public_host or host != public_host):
            return HTMLResponse('仅限本机访问', status_code=403)
        expected_origin = cfg.public_url if public_host and host == public_host else str(request.base_url).rstrip('/')
        if request.headers.get('origin') and request.headers['origin'] != expected_origin:
            return JSONResponse({'error':'请求来源不匹配'}, status_code=403)
        path = request.url.path
        if path.rstrip('/') in SUPERVISOR_ROUTES and not direct_local_request(request, local_host):
            return JSONResponse({'error':'仅限本机维护'}, status_code=403)
        is_evidence = path.startswith('/evidence/')
        login = path in ('/evidence/auth/login', '/api/auth/login')
        live_ingest = path == '/internal/events/live'
        public = path == '/api/auth/session' or path in SUPERVISOR_ROUTES
        if (is_evidence or path.startswith('/api/')) and not login and not public and not auth.authenticated(request):
            # An auto-update replaces the worker before the old supervisor is restarted.
            if (path == '/api/status' and request.method == 'GET'
                    and getattr(app.state, 'legacy_supervisor', False) and direct_local_request(request, local_host)):
                return JSONResponse({'project_root': str(ROOT)})
            return JSONResponse({'error':'请输入密码进入工作台'}, status_code=401)
        if request.url.path in ('/', '/api/cases') or (is_evidence and request.url.path != '/evidence/query'):
            maintenance.last_activity = time.time()
        if maintenance.draining and request.method != 'GET' and request.url.path not in ('/api/maintenance/drain', '/api/maintenance/restart', '/api/maintenance/shutdown'):
            return JSONResponse({'detail': '正在更新，请稍后重试'}, status_code=503)
        if request.method not in ('GET', 'HEAD', 'OPTIONS') and not login and not live_ingest and not auth.bearer(request) and not secrets.compare_digest(request.headers.get('x-csrf-token',''), csrf):
            return HTMLResponse('请求令牌无效', status_code=403)
        response = await call_next(request)
        # Vite fingerprints change with file contents. HTML, APIs and mutable
        # avatars must keep their existing no-store policy.
        fingerprinted = re.fullmatch(r'/ui/assets/[^/]+-[A-Za-z0-9_-]{8}\.[a-zA-Z0-9]+', request.url.path)
        response.headers['Cache-Control'] = ('public, max-age=31536000, immutable'
            if fingerprinted and response.status_code in (200, 206, 304) else 'no-store')
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'"
        if is_evidence or request.url.path == '/':
            response.headers['Content-Security-Policy'] += "; img-src 'self' data: blob:; font-src 'self'; object-src 'none'"
        return response


    @app.middleware('http')
    async def local_only(request: Request, call_next):
        response = await guarded_request(request, call_next)
        # Rejected requests return before the normal response headers above.
        response.headers.setdefault('Cache-Control', 'no-store')
        return response

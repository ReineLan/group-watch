from group_watch.monitoring.whitelist import Whitelist
from group_watch.maintenance import Maintenance
from group_watch.query.service import QueryService
from group_watch.web.auth import WorkspaceAuth
from group_watch.evidence.routes import create_router
from group_watch.evidence.store import RecordStore
from group_watch.monitoring.chat import ChatPresentation
from group_watch.settings import evidence_tokens
from group_watch.monitoring.service import Monitor
from group_watch.resources import frontend_dist
from group_watch.query.routes import install as install_query_routes
from group_watch.evidence.registration_routes import install as install_evidence_registration_routes
from group_watch.monitoring.routes import install as install_monitoring_routes
from group_watch.web.settings_routes import install as install_web_settings_routes
from group_watch.web.maintenance_routes import install as install_web_maintenance_routes
from group_watch.web.routes import install as install_web_routes
from group_watch.web.security import install as install_web_security
import secrets
import asyncio
import time
import contextlib
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.middleware.gzip import GZipMiddleware


def create_app(cfg, monitor=None):
    monitor = monitor or Monitor(cfg)
    chat = ChatPresentation(monitor, Path(cfg.db_path).parent / 'chat-assets')
    csrf = secrets.token_urlsafe(32)
    started = time.time()
    evidence = RecordStore(cfg.evidence_data or Path(cfg.db_path).parent / 'group-evidence')
    evidence.source_profile = monitor.directory.archive_profile
    evidence.groups = lambda: monitor.directory.group_ids
    tokens = [token.get_secret_value() for token in cfg.evidence_tokens] or [secrets.token_urlsafe(32)]
    auth = WorkspaceAuth(tokens)
    queries = QueryService(cfg, evidence.data / 'evidence.sqlite3')
    maintenance = Maintenance(cfg, evidence)
    whitelist = Whitelist(monitor)

    @asynccontextmanager
    async def lifespan(app):
        monitor.directory.loop = asyncio.get_running_loop()
        if not cfg.evidence_tokens:
            auth.configure_tokens(evidence_tokens(Path(cfg.local_env)))
        await run_in_threadpool(evidence.initialize, evidence.data)
        try:
            await monitor.start()
            resources_task=asyncio.create_task(chat.loop())
            try:
                yield
            finally:
                try:
                    resources_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await resources_task
                    await chat.close()
                    await maintenance.close()
                finally:
                    await whitelist.close()
                    await monitor.stop()
        finally:
            await run_in_threadpool(evidence.close)

    app = FastAPI(title='群聊监控', lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.monitor = monitor
    app.state.evidence = evidence
    app.state.auth = auth
    app.state.queries = queries
    app.state.maintenance = maintenance
    app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=4)


    app.include_router(create_router(evidence, monitor.feedback))


    install_web_security(app, cfg, auth, maintenance, csrf)
    install_web_routes(app, auth, csrf)
    install_web_maintenance_routes(app, maintenance, queries, csrf)
    install_web_settings_routes(app, cfg, monitor, whitelist)
    install_monitoring_routes(app, cfg, monitor, chat, auth, started, evidence)
    install_evidence_registration_routes(app, monitor, evidence)
    install_query_routes(app, queries, auth, maintenance, csrf)

    app.mount('/ui', StaticFiles(directory=frontend_dist()), name='ui')
    return app

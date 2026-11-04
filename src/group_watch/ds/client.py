"""Send requests and atomically record their lifecycle."""
from group_watch.utils.time import BEIJING
from group_watch.utils.files import atomic_json
from group_watch.ds.audit import request_log_root, sanitize
from datetime import datetime, timezone
import json
import uuid

SCOPES = ('automatic-review', 'registration', 'query', 'feedback')

async def audited_post(cfg, scope, client, url, *, origin=None, **kwargs):
    if scope not in SCOPES:
        raise ValueError('未知请求业务类型')
    origin = origin or ('automatic' if scope=='automatic-review' else 'manual')
    if origin not in ('automatic','manual'):
        raise ValueError('未知请求触发类型')
    started=datetime.now(timezone.utc)
    folder=request_log_root(cfg.db_path)/scope/started.astimezone(BEIJING).date().isoformat()
    folder.mkdir(parents=True,exist_ok=True)
    key=started.strftime('%Y%m%dT%H%M%S%fZ-')+uuid.uuid4().hex
    path=folder/(key+'.json')
    entry=dict(id=key,scope=scope,origin=origin,started=started.isoformat(),
               input=sanitize(kwargs.get('json')),output=None,status='pending')

    def save():
        atomic_json(path,entry)

    save()
    try:
        response=await client.post(url,**kwargs)
        entry['http_status']=response.status_code
        try:
            entry['output']=sanitize(response.json())
            entry['output_text']=json.dumps(entry['output'],ensure_ascii=False)
        except ValueError:
            entry['output_text']=response.text
        entry['status']='received'
        return response
    except BaseException as exc:
        entry.update(status='failed',error_type=type(exc).__name__)
        raise
    finally:
        entry['finished']=datetime.now(timezone.utc).isoformat()
        save()

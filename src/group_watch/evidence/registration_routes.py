from group_watch.evidence.routes import json_body
from group_watch.evidence.registration import analyze, RegistrationUnavailable, recommend_decisions

from fastapi import HTTPException, Request
import httpx


def install(app, monitor, evidence):
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

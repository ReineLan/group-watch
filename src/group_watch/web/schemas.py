"""HTTP request models shared by the workbench routes."""
from group_watch.settings import PushRecipient
from pydantic import BaseModel, Field

class Decision(BaseModel):
    resolution: str
    note: str | None = Field(None, max_length=2000)


class PushSettings(BaseModel):
    model_config = {'extra': 'forbid'}
    recipients: list[PushRecipient] = Field(max_length=10)


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=20000)


class FeedbackPoint(BaseModel):
    source: str = Field('', max_length=200)
    rule: str = Field('', max_length=80)
    verdict: str
    summary: str = Field(min_length=1, max_length=480)


class FeedbackSource(BaseModel):
    source: str = Field(min_length=1, max_length=200)


class WhitelistSettings(BaseModel):
    model_config = {'extra': 'forbid'}
    accounts: list[str] = Field(max_length=200)

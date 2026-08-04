"""Provider 与设置管理 API 的请求/响应模型。"""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models import ProviderType


class ProviderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    type: ProviderType
    base_url: str | None = None
    default_model: str = Field(min_length=1, max_length=128)
    enabled: bool = True
    priority: int = 0


class ProviderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    type: ProviderType | None = None
    base_url: str | None = None
    default_model: str | None = Field(default=None, min_length=1, max_length=128)
    enabled: bool | None = None
    priority: int | None = None


class ProviderOut(BaseModel):
    id: int
    name: str
    type: ProviderType
    base_url: str | None
    default_model: str
    enabled: bool
    priority: int
    updated_at: datetime


class LLMSettingsIn(BaseModel):
    default_provider_id: int | None = None
    fallback_provider_ids: list[int] = Field(default_factory=list)
    node_routing: dict[str, int] = Field(default_factory=dict)


class LLMSettingsOut(LLMSettingsIn):
    pass


class TestRequest(BaseModel):
    api_key: str = Field(min_length=1, max_length=512)


class TestResult(BaseModel):
    ok: bool
    message: str


class GenerateRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=500)
    keyword: str = Field(default="", max_length=200)
    provider: str | int | None = None
    model: str | None = Field(default=None, max_length=128)
    # 前端本地保存的密钥映射（provider_id -> api_key），仅本次请求使用，不落库
    provider_api_keys: dict[int, str] = Field(default_factory=dict)


class GenerateResponse(BaseModel):
    article: str
    provider_name: str
    model: str


class ResearchRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=500)
    keyword: str = Field(default="", max_length=200)
    provider: str | int | None = None
    model: str | None = Field(default=None, max_length=128)
    # 前端本地保存的密钥映射，仅本次请求使用。
    provider_api_keys: dict[int, str] = Field(default_factory=dict)

    @field_validator("topic")
    @classmethod
    def topic_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("topic 不能为空")
        return value


class ResearchResponse(BaseModel):
    topic: str
    keyword: str
    audience: str
    search_intent: str
    content_angles: list[str]
    related_questions: list[str]
    competitor_gaps: list[str]
    recommended_title: str
    outline: list[str]
    provider_name: str
    model: str


class LLMCallOut(BaseModel):
    provider_name: str
    model: str
    node: str | None
    thread_id: str | None
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: int
    success: bool
    error: str | None
    failover_from: list[int]
    created_at: datetime


class ProviderStat(BaseModel):
    provider_name: str
    calls: int
    success_rate: float
    total_tokens: int
    avg_latency_ms: float
    failovers: int


class NodeStat(BaseModel):
    node: str
    calls: int
    success_rate: float
    total_tokens: int
    avg_latency_ms: float


class StatsOut(BaseModel):
    by_provider: list[ProviderStat]
    by_node: list[NodeStat]

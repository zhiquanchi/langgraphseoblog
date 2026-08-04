"""Provider 与设置管理 API 的请求/响应模型。"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.models import ProviderType


def mask_api_key(api_key: str) -> str:
    """掩码 api_key：长度 >= 8 保留前 3 后 4，其余全掩。"""
    if len(api_key) >= 8:
        return f"{api_key[:3]}****{api_key[-4:]}"
    return "****"


class ProviderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    type: ProviderType
    base_url: str | None = None
    api_key: str = Field(min_length=1, max_length=512)
    default_model: str = Field(min_length=1, max_length=128)
    enabled: bool = True
    priority: int = 0


class ProviderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    type: ProviderType | None = None
    base_url: str | None = None
    api_key: str | None = Field(default=None, max_length=512)
    default_model: str | None = Field(default=None, min_length=1, max_length=128)
    enabled: bool | None = None
    priority: int | None = None


class ProviderOut(BaseModel):
    id: int
    name: str
    type: ProviderType
    base_url: str | None
    api_key_masked: str
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


class TestResult(BaseModel):
    ok: bool
    message: str


class GenerateRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=500)
    keyword: str = Field(default="", max_length=200)
    provider: str | int | None = None
    model: str | None = Field(default=None, max_length=128)


class GenerateResponse(BaseModel):
    article: str
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

"""REST 路由：Provider 管理、全局 LLM 设置、调用统计。"""

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, Response
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.llm.factory import get_chat_model
from app.llm.fallback import build_fallback_model
from app.llm.resolver import ProviderNotFoundError
from app.llm.stats import mask_sensitive
from app.models import AppSettings, LLMCall, Provider
from app.research import build_research_prompt, parse_research_result
from app.research import collect_topic_sources
from app.search import SearchProviderNotConfiguredError, get_search_provider
from app.search.tavily import TavilySearchError

from . import schemas

router = APIRouter(prefix="/api")

KNOWN_NODES = {
    "research",
    "retrieve",
    "outline",
    "draft_section",
    "assemble",
    "seo_optimize",
    "review",
    "publish",
}


def _get_provider_or_404(db: Session, provider_id: int) -> Provider:
    provider = db.get(Provider, provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail=f"Provider {provider_id} 不存在")
    return provider


def _provider_out(provider: Provider) -> schemas.ProviderOut:
    return schemas.ProviderOut(
        id=provider.id,
        name=provider.name,
        type=provider.type,
        base_url=provider.base_url,
        default_model=provider.default_model,
        enabled=provider.enabled,
        priority=provider.priority,
        updated_at=provider.updated_at,
    )


def _validate_base_url(provider_type: str, base_url: str | None) -> None:
    if provider_type in ("ark", "openai-compatible") and not base_url:
        raise HTTPException(status_code=400, detail=f"{provider_type} 类型必须提供 base_url")


def _settings_out(settings: AppSettings) -> schemas.LLMSettingsOut:
    return schemas.LLMSettingsOut(
        default_provider_id=settings.default_provider_id,
        fallback_provider_ids=json.loads(settings.fallback_provider_ids or "[]"),
        node_routing=json.loads(settings.node_routing or "{}"),
    )


def _get_settings_or_default(db: Session) -> AppSettings:
    settings = db.get(AppSettings, 1)
    if settings is None:
        settings = AppSettings(id=1, fallback_provider_ids="[]", node_routing="{}")
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


def _validate_settings_refs(db: Session, payload: schemas.LLMSettingsIn) -> None:
    referenced_ids = set()
    if payload.default_provider_id is not None:
        referenced_ids.add(payload.default_provider_id)
    referenced_ids.update(payload.fallback_provider_ids)
    referenced_ids.update(payload.node_routing.values())
    for provider_id in referenced_ids:
        provider = db.get(Provider, provider_id)
        if provider is None or not provider.enabled:
            raise HTTPException(
                status_code=400, detail=f"引用的 provider {provider_id} 不存在或已禁用"
            )
    unknown_nodes = set(payload.node_routing) - KNOWN_NODES
    if unknown_nodes:
        raise HTTPException(status_code=400, detail=f"未知的节点名: {sorted(unknown_nodes)}")


@router.post("/providers", response_model=schemas.ProviderOut, status_code=201)
def create_provider(payload: schemas.ProviderCreate, db: Session = Depends(get_db)) -> schemas.ProviderOut:
    _validate_base_url(payload.type, payload.base_url)
    exists = db.scalar(select(Provider).where(Provider.name == payload.name))
    if exists is not None:
        raise HTTPException(status_code=409, detail=f"Provider 名称 '{payload.name}' 已存在")
    provider = Provider(**payload.model_dump())
    db.add(provider)
    db.commit()
    db.refresh(provider)
    return _provider_out(provider)


@router.get("/providers", response_model=list[schemas.ProviderOut])
def list_providers(
    enabled: bool | None = None, db: Session = Depends(get_db)
) -> list[schemas.ProviderOut]:
    query = select(Provider).order_by(Provider.priority.desc(), Provider.id)
    if enabled is not None:
        query = query.where(Provider.enabled == enabled)
    providers = db.scalars(query).all()
    return [_provider_out(p) for p in providers]


@router.get("/providers/{provider_id}", response_model=schemas.ProviderOut)
def get_provider(provider_id: int, db: Session = Depends(get_db)) -> schemas.ProviderOut:
    return _provider_out(_get_provider_or_404(db, provider_id))


@router.patch("/providers/{provider_id}", response_model=schemas.ProviderOut)
def update_provider(
    provider_id: int, payload: schemas.ProviderUpdate, db: Session = Depends(get_db)
) -> schemas.ProviderOut:
    provider = _get_provider_or_404(db, provider_id)
    data = payload.model_dump(exclude_unset=True)

    if "name" in data and data["name"] != provider.name:
        exists = db.scalar(
            select(Provider).where(Provider.name == data["name"], Provider.id != provider_id)
        )
        if exists is not None:
            raise HTTPException(status_code=409, detail=f"Provider 名称 '{data['name']}' 已存在")

    new_type = data.get("type", provider.type)
    _validate_base_url(new_type, data.get("base_url", provider.base_url))

    for field, value in data.items():
        setattr(provider, field, value)
    db.commit()
    db.refresh(provider)
    return _provider_out(provider)


@router.delete("/providers/{provider_id}", status_code=204)
def delete_provider(provider_id: int, db: Session = Depends(get_db)) -> Response:
    provider = _get_provider_or_404(db, provider_id)
    settings = db.get(AppSettings, 1)
    if settings is not None:
        if settings.default_provider_id == provider_id:
            raise HTTPException(status_code=409, detail=f"Provider {provider_id} 正被引用为默认 Provider，无法删除")
        fallbacks = json.loads(settings.fallback_provider_ids or "[]")
        if provider_id in fallbacks:
            raise HTTPException(status_code=409, detail=f"Provider {provider_id} 正被引用为 fallback 链成员，无法删除")
        routing = json.loads(settings.node_routing or "{}")
        if provider_id in routing.values():
            raise HTTPException(status_code=409, detail=f"Provider {provider_id} 正被引用为节点路由，无法删除")
    db.delete(provider)
    db.commit()
    return Response(status_code=204)


@router.post("/providers/{provider_id}/test", response_model=schemas.TestResult)
def test_provider(
    provider_id: int, payload: schemas.TestRequest, db: Session = Depends(get_db)
) -> schemas.TestResult:
    """测试连接：使用请求携带的 api_key（前端本地保存），后端不持久化。"""
    _get_provider_or_404(db, provider_id)
    try:
        model = get_chat_model(provider_id, api_key=payload.api_key)
        model.invoke("ping")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        return JSONResponse(
            status_code=502, content={"ok": False, "message": mask_sensitive(str(exc))}
        )
    return schemas.TestResult(ok=True, message="连接成功")


@router.get("/settings/llm", response_model=schemas.LLMSettingsOut)
def get_llm_settings(db: Session = Depends(get_db)) -> schemas.LLMSettingsOut:
    return _settings_out(_get_settings_or_default(db))


@router.put("/settings/llm", response_model=schemas.LLMSettingsOut)
def update_llm_settings(
    payload: schemas.LLMSettingsIn, db: Session = Depends(get_db)
) -> schemas.LLMSettingsOut:
    _validate_settings_refs(db, payload)
    settings = _get_settings_or_default(db)
    settings.default_provider_id = payload.default_provider_id
    settings.fallback_provider_ids = json.dumps(payload.fallback_provider_ids)
    settings.node_routing = json.dumps(payload.node_routing)
    db.commit()
    db.refresh(settings)
    return _settings_out(settings)


@router.get("/llm/stats", response_model=schemas.StatsOut)
def llm_stats(db: Session = Depends(get_db)) -> schemas.StatsOut:
    failover_count = func.coalesce(
        func.sum(case((LLMCall.failover_from != "[]", 1), else_=0)), 0
    )
    by_provider_rows = db.execute(
        select(
            LLMCall.provider_name,
            func.count().label("calls"),
            func.avg(LLMCall.success).label("success_rate"),
            func.coalesce(func.sum(LLMCall.total_tokens), 0).label("total_tokens"),
            func.avg(LLMCall.latency_ms).label("avg_latency_ms"),
            failover_count.label("failovers"),
        ).group_by(LLMCall.provider_name)
    ).all()

    by_node_rows = db.execute(
        select(
            LLMCall.node,
            func.count().label("calls"),
            func.avg(LLMCall.success).label("success_rate"),
            func.coalesce(func.sum(LLMCall.total_tokens), 0).label("total_tokens"),
            func.avg(LLMCall.latency_ms).label("avg_latency_ms"),
        ).group_by(LLMCall.node)
    ).all()

    by_provider = [
        schemas.ProviderStat(
            provider_name=row.provider_name,
            calls=row.calls,
            success_rate=float(row.success_rate or 0),
            total_tokens=row.total_tokens,
            avg_latency_ms=float(row.avg_latency_ms or 0),
            failovers=row.failovers,
        )
        for row in by_provider_rows
    ]
    by_node = [
        schemas.NodeStat(
            node=row.node or "unknown",
            calls=row.calls,
            success_rate=float(row.success_rate or 0),
            total_tokens=row.total_tokens,
            avg_latency_ms=float(row.avg_latency_ms or 0),
        )
        for row in by_node_rows
    ]
    return schemas.StatsOut(by_provider=by_provider, by_node=by_node)


@router.get("/llm/calls", response_model=list[schemas.LLMCallOut])
def list_llm_calls(
    limit: int = Query(default=50, ge=1, le=200), db: Session = Depends(get_db)
) -> list[schemas.LLMCallOut]:
    calls = db.scalars(
        select(LLMCall).order_by(LLMCall.created_at.desc()).limit(limit)
    ).all()
    return [
        schemas.LLMCallOut(
            provider_name=call.provider_name,
            model=call.model,
            node=call.node,
            thread_id=call.thread_id,
            prompt_tokens=call.prompt_tokens,
            completion_tokens=call.completion_tokens,
            total_tokens=call.total_tokens,
            latency_ms=call.latency_ms,
            success=call.success,
            error=call.error,
            failover_from=json.loads(call.failover_from or "[]"),
            created_at=call.created_at,
        )
        for call in calls
    ]


@router.post("/blog/generate", response_model=schemas.GenerateResponse)
def generate_blog(payload: schemas.GenerateRequest) -> schemas.GenerateResponse:
    """触发博客生成：解析 provider（请求指定 > 节点映射 > 默认 > fallback 链）后调用模型撰写。

    工作流节点接入的统一入口为 app.llm.fallback.build_fallback_model(node, request_provider)。
    """
    request_provider = str(payload.provider) if payload.provider is not None else None
    try:
        wrapper = build_fallback_model(
            "generate",
            request_provider,
            model_override=payload.model,
            provider_api_keys=payload.provider_api_keys,
        )
    except ProviderNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    keyword_section = f"目标关键词：{payload.keyword}\n" if payload.keyword else ""
    prompt = (
        f"请围绕主题「{payload.topic}」撰写一篇 SEO 优化的博客文章。\n"
        f"{keyword_section}"
        "要求：Markdown 格式，包含 H1 标题、2-3 个 H2 小节、结论；"
        "标题与正文自然融入目标关键词；输出完整文章正文。"
    )
    article = wrapper.invoke(prompt, node="generate")
    provider_id, provider_name, model = wrapper.last_used or (None, "env", "env")
    return schemas.GenerateResponse(article=article, provider_name=provider_name, model=model)


@router.post("/research/topic", response_model=schemas.ResearchResponse)
def research_topic(payload: schemas.ResearchRequest) -> schemas.ResearchResponse:
    """研究主题并返回结构化简报，供用户确认后进入文章生成。"""
    request_provider = str(payload.provider) if payload.provider is not None else None
    try:
        search_provider = get_search_provider()
        sources = collect_topic_sources(
            search_provider, payload.topic.strip(), payload.keyword.strip()
        )
        wrapper = build_fallback_model(
            "research",
            request_provider,
            model_override=payload.model,
            provider_api_keys=payload.provider_api_keys,
        )
        raw_result = wrapper.invoke(
            build_research_prompt(payload.topic.strip(), payload.keyword.strip(), sources),
            node="research",
        )
        brief = parse_research_result(raw_result)
    except ProviderNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (SearchProviderNotConfiguredError, TavilySearchError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    _, provider_name, model = wrapper.last_used or (None, "env", "env")
    return schemas.ResearchResponse(
        topic=payload.topic.strip(),
        keyword=payload.keyword.strip(),
        provider_name=provider_name,
        model=model,
        sources=[
            schemas.ResearchSource(
                title=source.title,
                url=source.url,
                published_at=source.published_at,
            )
            for source in sources
        ],
        **brief,
    )

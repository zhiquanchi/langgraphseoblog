"""Provider 解析链：调用方上下文 → 有序 provider_id 候选列表。

优先级：请求指定 > 节点映射 > 全局默认 + fallback 链；全部为空返回空列表，
调用方据此回退环境变量模式。
"""

import json

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import AppSettings, Provider


class ProviderNotFoundError(Exception):
    """请求指定的 provider 不存在或已禁用。"""

    def __init__(self, identifier: str | int) -> None:
        self.identifier = identifier
        super().__init__(f"provider {identifier!r} 不存在或已禁用")


def _load_json_object(raw: str) -> dict:
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _load_json_int_list(raw: str) -> list[int]:
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, int)]


def _find_enabled_provider(session: Session, provider_id: int) -> Provider | None:
    provider = session.get(Provider, provider_id)
    if provider is None or not provider.enabled:
        return None
    return provider


def _find_provider_by_identifier(session: Session, identifier: str) -> Provider | None:
    if identifier.isdigit():
        provider = session.get(Provider, int(identifier))
        if provider is not None:
            return provider
    return session.scalar(select(Provider).where(Provider.name == identifier))


def _resolve_requested_provider(session: Session, identifier: str) -> Provider:
    provider = _find_provider_by_identifier(session, identifier)
    if provider is None or not provider.enabled:
        raise ProviderNotFoundError(identifier)
    return provider


def _resolve_node_mapping(session: Session, node: str) -> int | None:
    settings = session.get(AppSettings, 1)
    if settings is None:
        return None
    provider_id = _load_json_object(settings.node_routing).get(node)
    if not isinstance(provider_id, int):
        return None
    if _find_enabled_provider(session, provider_id) is None:
        return None
    return provider_id


def resolve_provider_ids(node: str | None, request_provider: str | None) -> list[int]:
    """解析候选 provider_id 列表：首个为主 provider，其余为降级链。

    全部为空时返回 []，调用方据此回退环境变量模式。
    """
    try:
        with SessionLocal() as session:
            if request_provider is not None:
                candidates: list[int] = [_resolve_requested_provider(session, request_provider).id]
            elif node:
                mapped_id = _resolve_node_mapping(session, node)
                candidates = [mapped_id] if mapped_id is not None else []
            else:
                candidates = []

            settings = session.get(AppSettings, 1)
            default_id = settings.default_provider_id if settings is not None else None
            if (
                default_id is not None
                and default_id not in candidates
                and _find_enabled_provider(session, default_id) is not None
            ):
                candidates.append(default_id)

            if settings is not None:
                fallback_ids = [
                    fid
                    for fid in _load_json_int_list(settings.fallback_provider_ids)
                    if fid not in candidates
                ]
                fallback_ids = list(dict.fromkeys(fallback_ids))
                if fallback_ids:
                    providers = session.scalars(
                        select(Provider).where(Provider.id.in_(fallback_ids))
                    ).all()
                    providers_by_id = {p.id: p for p in providers}
                    enabled_fallbacks: list[Provider] = []
                    for fid in fallback_ids:
                        provider = providers_by_id.get(fid)
                        if provider is not None and provider.enabled:
                            enabled_fallbacks.append(provider)
                    candidates.extend(
                        p.id
                        for p in sorted(enabled_fallbacks, key=lambda p: p.priority, reverse=True)
                    )

            return candidates
    except SQLAlchemyError:
        return []


def resolve_node_provider_id(node: str) -> int | None:
    """返回节点映射的 provider_id；未映射或映射 provider 禁用时返回 None。"""
    try:
        with SessionLocal() as session:
            return _resolve_node_mapping(session, node)
    except SQLAlchemyError:
        return None

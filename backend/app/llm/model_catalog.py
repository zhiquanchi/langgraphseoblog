"""从各官方 Provider 的模型接口读取可用模型。"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class ProviderCatalog:
    type: str
    label: str
    homepage: str
    models_url: str


CATALOG: dict[str, ProviderCatalog] = {
    "openai": ProviderCatalog(
        "openai", "OpenAI", "https://platform.openai.com/docs/models", "https://api.openai.com/v1/models"
    ),
    "anthropic": ProviderCatalog(
        "anthropic", "Anthropic", "https://docs.anthropic.com/en/docs/about-claude/models", "https://api.anthropic.com/v1/models"
    ),
    "ark": ProviderCatalog(
        "ark", "火山方舟 (Ark)", "https://www.volcengine.com/docs/82379/1330310", "https://ark.cn-beijing.volces.com/api/v3/models"
    ),
}

MAX_ATTEMPTS = 3


class ModelDiscoveryError(RuntimeError):
    """模型接口连续请求失败或返回空数据。"""


def discover_models(provider_type: str, api_key: str) -> list[dict[str, str]]:
    catalog = CATALOG.get(provider_type)
    if catalog is None:
        raise ModelDiscoveryError(f"不支持自动获取 {provider_type} 的模型列表")
    if not api_key.strip():
        raise ModelDiscoveryError("API Key 不能为空")

    last_error = "模型接口没有返回数据"
    for attempt in range(MAX_ATTEMPTS):
        try:
            models = _request_models(catalog, api_key)
            if models:
                return models
            last_error = "模型接口返回空列表"
        except Exception as exc:  # noqa: BLE001 - 对外只暴露脱敏后的重试结果
            last_error = _safe_error(exc)
        if attempt < MAX_ATTEMPTS - 1:
            time.sleep(0.15)
    raise ModelDiscoveryError(f"连续 {MAX_ATTEMPTS} 次获取模型失败：{last_error}")


def _request_models(catalog: ProviderCatalog, api_key: str) -> list[dict[str, str]]:
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    if catalog.type == "anthropic":
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Accept": "application/json",
        }
    request = Request(catalog.models_url, headers=headers, method="GET")
    with urlopen(request, timeout=8) as response:  # noqa: S310 - URL 来自固定官方目录
        payload = json.loads(response.read().decode("utf-8"))
    raw_models = payload.get("data", payload.get("models", [])) if isinstance(payload, dict) else []
    if not isinstance(raw_models, list):
        return []
    result: list[dict[str, str]] = []
    for item in raw_models:
        if isinstance(item, str) and item.strip():
            result.append({"id": item.strip(), "name": item.strip()})
        elif isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"].strip():
            model_id = item["id"].strip()
            result.append({"id": model_id, "name": str(item.get("display_name") or model_id)})
    return result


def _safe_error(exc: Exception) -> str:
    if isinstance(exc, HTTPError):
        return f"模型接口 HTTP {exc.code}"
    if isinstance(exc, URLError):
        return "模型接口网络不可达"
    return "模型接口响应异常"

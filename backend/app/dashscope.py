"""阿里云百炼（DashScope）接入常量：LLM 与 embedding 共用同一个 OpenAI 兼容端点。"""

import os

DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_CHAT_MODEL = "qwen-plus"
DEFAULT_EMBEDDING_MODEL = "text-embedding-v4"

# embeddings 接口单次请求最多 10 条文本，超出直接 400
MAX_EMBED_BATCH = 10

# 环境变量的几种叫法等价（LLM_PROVIDER / EMBEDDING_PROVIDER 均可填）
PROVIDER_ALIASES = frozenset({"dashscope", "aliyun", "bailian"})


def resolve_base_url() -> str:
    """取 DASHSCOPE_BASE_URL，缺省用北京区兼容模式地址。"""
    return os.environ.get("DASHSCOPE_BASE_URL", DEFAULT_BASE_URL).strip().rstrip("/")

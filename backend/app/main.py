from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app import models  # noqa: F401  — 确保模型在 create_all 前注册
from app.api.routes import router
from app.db import Base, engine


def _migrate_drop_provider_api_key() -> None:
    """启动迁移：移除旧版 providers.api_key 列。

    密钥改为前端本地保存，后端仅在使用时接收、不落库。SQLite 3.35+ 支持
    DROP COLUMN；旧列无索引/约束，可安全删除。
    """
    with engine.begin() as conn:
        columns = conn.exec_driver_sql("PRAGMA table_info(providers)").fetchall()
        if any(row[1] == "api_key" for row in columns):
            conn.exec_driver_sql("ALTER TABLE providers DROP COLUMN api_key")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _migrate_drop_provider_api_key()
    yield


app = FastAPI(
    title="langgraphseoblog backend",
    description="LangGraph-powered SEO blog generator API",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

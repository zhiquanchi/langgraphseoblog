from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import models  # noqa: F401  — 确保模型在 create_all 前注册
from app.api.routes import router
from app.db import Base, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
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

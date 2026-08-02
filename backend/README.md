# langgraphseoblog backend

FastAPI 服务，承载 LangGraph 驱动的 SEO 博客生成流水线。

## 本地开发

```bash
uv sync          # 安装依赖
uv run uvicorn app.main:app --reload
```

服务启动后访问 `http://localhost:8000/docs` 查看 OpenAPI 文档。

## 测试

```bash
uv run pytest
```

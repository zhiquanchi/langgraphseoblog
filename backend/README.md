# langgraphseoblog backend

FastAPI 服务，承载 LangGraph 驱动的 SEO 博客生成流水线。

## 本地开发

```bash
uv sync          # 安装依赖
uv run uvicorn app.main:app --reload
```

服务启动后访问 `http://localhost:8000/docs` 查看 OpenAPI 文档。

## 选题研究

选题研究默认使用 Tavily 实时搜索，再由项目配置的 LLM 汇总研究结果。配置环境变量后即可使用：

```bash
export SEARCH_PROVIDER=tavily
export TAVILY_API_KEY=tvly-...
```

也可以在前端生成页填写 Tavily Key。前端只将 Key 保存在浏览器本地，并在研究请求中临时发送；服务端优先使用请求中的 Key，否则回退到 `TAVILY_API_KEY`。接口为 `POST /api/research/topic`。返回结果包含研究简报和参考来源；系统不会使用 Tavily 的 `include_answer`，也不会把 Tavily API Key 写入数据库。

## RAG 知识库

不配置任何 RAG 环境变量时功能整体关闭，生成主流程不受影响；配置后 `retrieve` 节点自动检索知识库并注入撰写 prompt：

```bash
export EMBEDDING_PROVIDER=openai        # openai / ark（OpenAI 兼容协议）
export EMBEDDING_MODEL=text-embedding-3-small
export VECTOR_STORE=memory              # memory（默认，零依赖）/ chroma（uv sync --extra chroma）
```

文档与分块的权威数据存 SQLite，向量索引是可重建的缓存（memory 索引重启后首次检索自动重建）。启动后调 `POST /api/rag/seed` 幂等导入 `data/corpus/` 内置语料，或在前端「知识库」页管理文档、测试检索。

## 测试

```bash
uv run pytest
```

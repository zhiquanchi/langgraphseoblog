# AGENTS.md

基于 LangGraph 的 AI SEO 博客生成器（monorepo）：`backend/`（FastAPI + SQLAlchemy + LangGraph，Python ≥ 3.11，uv 管理）与 `frontend/`（React 19 + antd 6 + @ant-design/x + Vite，Node ≥ 20）。工作流为 retrieve(RAG) → outline → review_outline(interrupt 人工确认) → draft → seo_score ⇄ seo_optimize，全程 SSE 推送。

**本仓库是用户求职 AI 应用岗的核心简历项目**：README 必须与真实实现保持一致，改功能时同步更新 README/`.env.example`；不要虚标未实现的能力。

## 常用命令

```bash
# 后端（在 backend/ 下）
uv sync                          # Qdrant 为主依赖，无可选 extras
uv run uvicorn app.main:app --reload   # 端口 8000
uv run pytest                    # 全部测试（47 个 + 1 个服务端冒烟按需 skip）
uv run pytest tests/test_seo_loop.py::test_xxx   # 单个测试

# 前端（在 frontend/ 下）
npm run dev                      # 端口 5173，/api 已代理到 8000
npm run build                    # tsc -b 类型检查 + vite 构建
npm run lint                     # oxlint
```

## 架构与关键约束

- **图定义在 `backend/app/graph.py`**：`BlogState` 为 `TypedDict(total=False)`；条件边路由 `route_after_review`（修订自循环）与 `route_after_seo_score`（SEO 重写循环，阈值 0.8、上限 2 次，杜绝死循环）。checkpointer 用 `MemorySaver`，按 `thread_id` 恢复。
- **SSE 自定义事件**：graph 节点经 `StreamWriter` 发 `outline_token / article_token / seo_token / seo_score / rag_context`，由 `app/api/routes.py` 直通 SSE；前端 `src/api/blog.ts` 解析。新增流式内容要同时改这三处。
- **LLM 层（`app/llm/`）**：`FallbackChatModel` 只在认证失败/限流/超时/5xx 时切换候选，其余 4xx 立即抛出；**流式仅首 token 产生前允许切换**。候选链优先级：请求指定 Provider > 节点路由 > 全局默认 > fallback 链 > 环境变量模式。
- **API Key 不落地后端**：Key 只存浏览器 localStorage，随请求传入、仅本次构建使用（工厂缓存键只含 Key 哈希）。任何改动都不得把 Key 持久化到数据库或日志；统计入库前错误信息需脱敏。
- **RAG（`app/rag/`）**：SQLite（`knowledge_docs`/`knowledge_chunks`）是权威数据，向量索引唯一实现为 **Qdrant**（默认本地嵌入式文件模式，配 `QDRANT_URL` 连服务端），只是可重建缓存：集合为空但有分块时首次检索自动重建。`EMBEDDING_PROVIDER` 未配置或向量库故障时 retrieve 节点**静默降级跳过，不得阻塞生成主流程**（有测试覆盖）。
- **embedding 维度不通用**（OpenAI 1536 vs 百炼 text-embedding-v4 1024）：切换 provider 需删掉 `data/qdrant` 或对应集合，首次检索自动用新模型重建；百炼 embeddings 单请求上限 10 条，入库已分批；百炼/方舟兼容端点只接受字符串输入，构建 `OpenAIEmbeddings` 必须 `check_embedding_ctx_length=False`（默认会发 token 整数数组导致 400，有测试锁定）。
- **数据库**：SQLite，路径可用 `SQLITE_PATH` 覆盖。`tests/conftest.py` 在导入 app 前设置临时 `SQLITE_PATH`——新测试文件不要绕过 conftest 直接先导入 app。
- **测试无需真实 API Key**：工作流测试用 FakeWrapper 模拟逐 token 流式（按节点与调用次序返回不同结果，如 SEO 首评 0.5、复评 0.9）；RAG 测试用确定性假 embedding 跑真嵌入式 Qdrant（每用例独立 tmp 目录）。
- `docker-compose.yml` 仅用于可选的 Qdrant 服务端模式；默认嵌入式文件模式（`backend/data/qdrant`）零外部进程。
- `backend/app.db` 是本地运行数据，不要提交改动或用它做测试。

## 约定

- 代码注释、文档、错误提示、commit message 均用中文；commit 遵循 `feat(backend): ...` / `fix(frontend): ...` 风格。
- 前端统一走 `src/api/client.ts` 的 `http` 封装（相对路径 `/api`，错误取 `detail`/`message`）；页面在 `src/pages/`（生成/知识库/Provider/统计四页）。

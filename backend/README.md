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
export EMBEDDING_PROVIDER=openai        # openai / ark / dashscope（OpenAI 兼容协议）
export EMBEDDING_MODEL=text-embedding-3-small
export VECTOR_STORE=qdrant              # memory（零依赖）/ chroma / qdrant（需对应 --extra）
```

改用阿里云百炼：

```bash
export EMBEDDING_PROVIDER=dashscope     # 等价写法 aliyun / bailian
export EMBEDDING_MODEL=text-embedding-v4
export DASHSCOPE_API_KEY=sk-...
# export DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1  # 缺省即此地址
```

百炼 embeddings 单次请求最多 10 条文本，入库时会按 10 条一批自动切分；`text-embedding-v4` 默认 1024 维，与 `text-embedding-3-small`（1536 维）不兼容，换模型需清掉 `data/chroma` / `data/qdrant`（或删掉对应集合）后重新导入语料，SQLite 里的文档与分块不受影响。

## 向量库选型

三种实现共用同一套「SQLite 为权威、向量索引为缓存」的契约，按 `VECTOR_STORE` 切换：

| 取值 | 依赖 | 持久化 | 适用 |
| --- | --- | --- | --- |
| `memory` | 无 | 否（重启后首次检索自动重建） | 默认、CI、演示 |
| `chroma` | `uv sync --extra chroma` | `data/chroma` 本地文件 | 单机轻量持久化 |
| `qdrant` | `uv sync --extra qdrant` | `data/qdrant` 本地嵌入式，或 `QDRANT_URL` 指向服务端 | 需要正式向量库/服务端实例、后续上生产 |

Qdrant 相关环境变量：

```bash
export VECTOR_STORE=qdrant
export QDRANT_DIR=./data/qdrant          # 本地嵌入式文件模式，免起服务（默认）
export QDRANT_COLLECTION=seo_knowledge   # 集合名，默认 seo_knowledge
# export QDRANT_URL=http://localhost:6333   # 填了就优先连服务端实例
# export QDRANT_API_KEY=...
```

首次使用会按当前 embedding 的维度自动创建 cosine 集合；分块主键 `{doc_id}:{seq}` 以 uuid5 形式作为点位 id，删除文档时同步删点位。

### 用 Docker 起 Qdrant 实例

仓库根目录带 `docker-compose.yml`（镜像 `qdrant/qdrant:v1.19.1`，向量数据存 named volume `qdrant_data`）：

```bash
docker compose up -d qdrant            # 启动
curl http://localhost:6333/readyz      # 期望：all shards are ready
# http://localhost:6333/dashboard      # 内置 Web 控制台，可直接看集合与点位
```

后端切到服务端模式（`QDRANT_URL` 优先于本地嵌入式目录）：

```bash
export VECTOR_STORE=qdrant
export QDRANT_URL=http://localhost:6333
# export QDRANT_API_KEY=...            # compose 里启用 QDRANT__SERVICE__API_KEY 后需同步
```

其余常用命令：`docker compose logs -f qdrant`；`docker compose down` 停止但保留数据；`docker compose down -v` 连向量数据一起清（SQLite 文档不受影响，重新 `POST /api/rag/seed` 即可重建索引）。集合仍由后端按当前 embedding 维度自动创建，名字取 `QDRANT_COLLECTION`（默认 `seo_knowledge`）。

文档与分块的权威数据存 SQLite，向量索引是可重建的缓存（memory 索引重启后首次检索自动重建）。启动后调 `POST /api/rag/seed` 幂等导入 `data/corpus/` 内置语料，或在前端「知识库」页管理文档、测试检索。

## 测试

```bash
uv run pytest
```

Qdrant 默认只跑本地嵌入式文件模式（无需任何外部服务）。想在真实实例上验一遍服务端分支，先 `docker compose up -d qdrant`，再：

```bash
QDRANT_SMOKE_URL=http://localhost:6333 uv run pytest
```

该用例自建随机集合、跑完即删，不影响 `seo_knowledge` 正式集合；未设置环境变量时自动 skip。

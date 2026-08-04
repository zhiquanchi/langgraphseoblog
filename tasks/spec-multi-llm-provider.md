# SPEC: 多 LLM Provider 管理

> 技术规格源自: [tasks/prd-multi-llm-provider.md](../tasks/prd-multi-llm-provider.md)
> 生成日期: 2026-08-03 | 目标分支: master | Commit: 321756a

## 1. Summary

### 1.1 What This SPEC Covers

将 SEO 博客生成器的 LLM Provider 从「静态环境变量」升级为「数据库动态管理的多 Provider 体系」。后端新增 SQLite 持久化（Provider 配置、全局 LLM 设置、调用统计）、Provider 注册表与模型工厂、优先级解析链与自封装故障降级、管理/统计 REST API；前端新增 react-router 路由与 antd 组件库，提供 Provider 管理页、生成页 Provider 选择与统计展示。

### 1.2 PRD Reference

- 来源: `tasks/prd-multi-llm-provider.md`
- 覆盖 User Stories: US-001 ~ US-009
- 覆盖 Functional Requirements: FR-1 ~ FR-12

### 1.3 Design Decisions Summary

| Decision | Choice | Rationale |
|----------|--------|-----------|
| 持久化 | SQLite + SQLAlchemy 2.0 | 项目零数据库基础；SQLAlchemy 生态成熟、类型安全，后续可平滑迁移其他数据库 |
| 模型接口 | langchain-core `BaseChatModel` 统一接口 | 与 README 的 LangChain 架构一致；OpenAI/Ark/兼容端点共用 `ChatOpenAI`（base_url 区分），Anthropic 用 `ChatAnthropic` |
| Fallback | factory 内自封装降级（`FallbackChatModel`） | 可控性强，可记录 failover_from 与触发原因；不采用 `RunnableWithFallbacks`（流式链路定制受限） |
| 前端 | react-router-dom + antd | 快速搭建管理界面（Form/Table/Modal）；与用户 antd 技能栈一致 |
| 配置热更新 | 模型实例按 provider 缓存，配置变更后失效重建 | 新调用用新配置；进行中的调用继续用旧实例（先获取先完成） |
| 环境变量回退 | 无任何动态配置时走 `LLM_PROVIDER` 路径 | 保证向后兼容，未迁移部署不受影响 |

---

## 2. Architecture

### 2.1 System Context

```
┌────────────────────────────── Backend (FastAPI) ──────────────────────────────┐
│                                                                               │
│  REST API ──► api/routes.py ──► llm/resolver.py ──► llm/factory.py            │
│    │                              │                 │  (ProviderRegistry)     │
│    │                              │                 ▼                        │
│    │                          providers/settings   llm/fallback.py           │
│    │                              │  (SQLite)       │  FallbackChatModel      │
│    │                              ▼                 ▼                        │
│  blog generate ──► 工作流节点 ──► get_chat_model ──► ChatOpenAI / ChatAnthropic│
│                                                      │                        │
│  llm/stats.py ──► llm_calls 表 ◄────────────────────┘ (调用统计埋点)          │
│                                                                               │
└───────────────────────────────────────────────────────────────────────────────┘
                                    ▲
                    react-router + antd 前端（管理页 / 生成页 / 统计页）
```

### 2.2 Component Design

| 组件 | 职责 |
|------|------|
| `db.py` | SQLAlchemy engine / Session 管理，启动时 `create_all` 建表 |
| `models.py` | ORM 实体：`Provider`、`AppSettings`、`LLMCall` |
| `llm/factory.py` | `ProviderRegistry`：按 provider 配置构建 `BaseChatModel`，带缓存与环境变量回退 |
| `llm/resolver.py` | 解析调用方上下文 → 有序 provider_id 列表（请求指定 > 节点映射 > 全局默认 + fallback 链） |
| `llm/fallback.py` | `FallbackChatModel`：包装候选模型链，按序尝试、失败降级、全链失败才抛错 |
| `llm/stats.py` | `LLMCallRecorder`：每次调用写入 `llm_calls` 记录（含 failover 信息） |
| `api/routes.py` | REST 路由：providers CRUD / settings / stats / blog.generate 扩展 |
| `api/schemas.py` | Pydantic 请求/响应模型（api_key 掩码规则在此落地） |

### 2.3 Module Interactions

```
调用方（节点 / API handler）
  → resolver.resolve(node, request_provider)          # 返回 [p1, p2, p3]（p1 主，其余降级链）
  → factory.get_fallback_model([p1, p2, p3])          # 构建或取缓存 FallbackChatModel
  → FallbackChatModel.invoke/astream                  # 按序尝试，失败降级
  → stats.record(...)                                  # 每次尝试/最终结果写入 llm_calls
```

配置变更流程：管理 API 写库 → 使 `ProviderRegistry` 中对应 provider_id 缓存失效 → 下次调用重建模型实例。`resolver` 每次从 DB 读 settings 与 enabled 状态（量小，直读不缓存）。

### 2.4 File Structure

```
backend/
├── pyproject.toml                    [MODIFY: +sqlalchemy, +langchain-core, +langchain-openai, +langchain-anthropic]
├── app/
│   ├── main.py                       [MODIFY: 挂载路由, create_all]
│   ├── db.py                         [NEW: engine/session/get_db]
│   ├── models.py                     [NEW: ORM 模型]
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── factory.py                [MODIFY: ProviderRegistry + 缓存 + 环境变量回退]
│   │   ├── resolver.py               [NEW: 优先级解析链]
│   │   ├── fallback.py               [NEW: FallbackChatModel]
│   │   └── stats.py                  [NEW: LLMCallRecorder]
│   └── api/
│   │   ├── __init__.py
│   │   ├── routes.py                 [NEW: /api/providers, /api/settings/llm, /api/llm/*, blog.generate 扩展]
│   │   └── schemas.py                [NEW: Pydantic 模型]
│   └── (未来 graphs/nodes 接入点: 各节点 get_chat_model 调用替换为 resolver)
└── tests/
    ├── test_factory.py               [NEW]
    ├── test_resolver.py              [NEW]
    ├── test_fallback.py              [NEW]
    ├── test_providers_api.py         [NEW]
    └── test_stats.py                 [NEW]

frontend/
├── package.json                      [MODIFY: +react-router-dom, +antd]
└── src/
    ├── main.tsx                      [MODIFY: 挂 BrowserRouter + antd ConfigProvider]
    ├── App.tsx                       [MODIFY: 路由定义]
    ├── api/client.ts                 [NEW: fetch 封装]
    ├── api/providers.ts              [NEW: Provider API 类型与方法]
    ├── api/stats.ts                  [NEW: 统计 API 类型与方法]
    └── pages/
        ├── GeneratePage.tsx          [MODIFY: Provider 下拉 + 生效展示]
        ├── ProvidersPage.tsx         [NEW: 管理页]
        └── StatsPage.tsx             [NEW: 统计页]
```

---

## 3. Data Model

### 3.1 Schema Changes

SQLite 三张新表（`Base.metadata.create_all` 启动建表；数据结构稳定后再评估 alembic 迁移）：

```sql
CREATE TABLE providers (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL UNIQUE,          -- 显示名，全局唯一
    type          TEXT NOT NULL,                 -- openai | anthropic | ark | openai-compatible
    base_url      TEXT,                          -- ark/openai-compatible 必填；openai/anthropic 可空（官方端点）
    api_key       TEXT NOT NULL,
    default_model TEXT NOT NULL,
    enabled       BOOLEAN NOT NULL DEFAULT 1,
    priority      INTEGER NOT NULL DEFAULT 0,    -- 越大越优先，fallback 链排序依据
    created_at    DATETIME NOT NULL,
    updated_at    DATETIME NOT NULL
);

CREATE TABLE app_settings (                      -- 单行全局配置 (id=1)
    id                 INTEGER PRIMARY KEY CHECK (id = 1),
    default_provider_id INTEGER,                 -- FK providers.id, 可为 NULL（NULL=回退环境变量）
    fallback_provider_ids TEXT NOT NULL DEFAULT '[]',  -- JSON 数组，有序降级链（不含 default）
    node_routing       TEXT NOT NULL DEFAULT '{}',      -- JSON: {节点名: provider_id}
    updated_at         DATETIME NOT NULL
);

CREATE TABLE llm_calls (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_id       INTEGER,                   -- 实际生效 provider（冗余，可空：环境变量回退路径无 id）
    provider_name     TEXT NOT NULL,             -- 冗余存储，provider 删除后统计仍可读
    model             TEXT NOT NULL,
    node              TEXT,                      -- 工作流节点名；API 直调为 NULL
    thread_id         TEXT,                      -- 关联生成请求（可选）
    prompt_tokens     INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens      INTEGER NOT NULL DEFAULT 0,
    latency_ms        INTEGER NOT NULL DEFAULT 0,
    success           BOOLEAN NOT NULL,
    error             TEXT,                      -- 失败原因摘要（不含 api_key）
    failover_from     TEXT NOT NULL DEFAULT '[]',-- JSON: 降级前已失败的 provider_id 列表
    created_at        DATETIME NOT NULL
);

CREATE INDEX idx_llm_calls_created ON llm_calls(created_at);
CREATE INDEX idx_llm_calls_provider ON llm_calls(provider_id);
```

### 3.2 Entity Definitions

```python
# app/models.py
class ProviderType(StrEnum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    ARK = "ark"
    OPENAI_COMPATIBLE = "openai-compatible"

class Provider(Base):
    __tablename__ = "providers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    type: Mapped[str] = mapped_column(String)
    base_url: Mapped[str | None] = mapped_column(String, nullable=True)
    api_key: Mapped[str] = mapped_column(String)
    default_model: Mapped[str] = mapped_column(String)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    created_at / updated_at: Mapped[datetime]

class AppSettings(Base):
    __tablename__ = "app_settings"
    id: Mapped[int] = mapped_column(primary_key=True)   # 恒为 1
    default_provider_id: Mapped[int | None]
    fallback_provider_ids: Mapped[str]  # JSON 字符串
    node_routing: Mapped[str]           # JSON 字符串
    updated_at: Mapped[datetime]

class LLMCall(Base):
    __tablename__ = "llm_calls"
    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id / provider_name / model / node / thread_id
    prompt_tokens / completion_tokens / total_tokens
    latency_ms / success / error / failover_from  # failover_from 为 JSON 字符串
    created_at: Mapped[datetime]
```

### 3.3 Relationships

- `AppSettings.default_provider_id` → `Provider.id`（软引用，不设强 FK 约束；删除时校验兜底）
- `LLMCall.provider_id` → `Provider.id`（软引用；Provider 删除后保留历史记录，靠冗余 `provider_name` 展示）
- 约束规则：`default_provider_id` 与 `fallback_provider_ids`、`node_routing` 中引用的 provider 必须存在且 enabled；删除被引用 provider 时拒绝（409）

### 3.4 Migration Plan

- 初期：启动时 `Base.metadata.create_all()`（项目无迁移基础设施，表结构由模型定义驱动）
- 回滚：删除三张表即回退到环境变量模式（代码内所有读取带「表/数据缺失 → 环境变量回退」分支）
- 后续：表结构稳定后引入 alembic 管理版本化迁移（本期不做）

---

## 4. API Design

### 4.1 Endpoints

| Method | Path | Description | Auth | Request | Response |
|--------|------|-------------|------|---------|----------|
| GET | `/api/health` | 健康检查 | 无 | — | `{status: "ok"}` |
| POST | `/api/providers` | 创建 Provider | 无* | `ProviderCreate` | `ProviderOut` (201) |
| GET | `/api/providers` | Provider 列表（key 掩码） | 无* | `?enabled=true` | `ProviderOut[]` |
| GET | `/api/providers/{id}` | Provider 详情 | 无* | — | `ProviderOut` |
| PATCH | `/api/providers/{id}` | 更新（api_key 传空串=不更新） | 无* | `ProviderUpdate` | `ProviderOut` |
| DELETE | `/api/providers/{id}` | 删除（被引用时 409） | 无* | — | 204 |
| POST | `/api/providers/{id}/test` | 测试连通性（最小请求） | 无* | — | `{ok: bool, message: str}` |
| GET | `/api/settings/llm` | 全局 LLM 设置 | 无* | — | `LLMSettingsOut` |
| PUT | `/api/settings/llm` | 更新全局 LLM 设置 | 无* | `LLMSettingsIn` | `LLMSettingsOut` |
| GET | `/api/llm/stats` | 聚合统计 | 无* | `?days=7` | `StatsOut` |
| GET | `/api/llm/calls` | 最近调用明细 | 无* | `?limit=50` | `LLMCallOut[]` |
| POST | `/api/blog/generate` | 触发生成（扩展可选参数） | 无* | `+provider?/model?` | 同现有 |

> *与现有 API 一致，本期不加鉴权（认证体系不在本 SPEC 范围，见 7.1）

### 4.2 Request/Response Schemas

```python
# app/api/schemas.py
class ProviderCreate(BaseModel):
    name: str                       # 1-64 字符，唯一
    type: ProviderType
    base_url: str | None = None     # ark / openai-compatible 必填；校验必填规则见 5.2
    api_key: str                    # 1-512，不落日志
    default_model: str              # 1-128
    enabled: bool = True
    priority: int = 0

class ProviderUpdate(BaseModel):
    name / type / base_url: 可选，规则同创建
    api_key: str | None = None      # None/空串 = 保持不变
    default_model / enabled / priority: 可选

class ProviderOut(BaseModel):
    id: int
    name: str
    type: ProviderType
    base_url: str | None
    api_key_masked: str             # 形如 "sk-****abcd"（后 4 位）
    default_model: str
    enabled: bool
    priority: int
    updated_at: datetime

class LLMSettingsIn(BaseModel):
    default_provider_id: int | None = None       # None = 回退环境变量
    fallback_provider_ids: list[int] = []
    node_routing: dict[str, int] = {}

class LLMSettingsOut(LLMSettingsIn): ...

class StatsOut(BaseModel):
    by_provider: list[ProviderStat]   # provider_name, calls, success_rate, total_tokens, avg_latency_ms, failovers
    by_node: list[NodeStat]           # node, calls, success_rate, total_tokens, avg_latency_ms

class LLMCallOut(BaseModel):
    provider_name, model, node, thread_id, prompt_tokens, completion_tokens,
    total_tokens, latency_ms, success, error, failover_from, created_at
```

`POST /api/blog/generate` 扩展请求体：

```json
{
  "topic": "LangGraph 最佳实践",
  "keyword": "langgraph tutorial",
  "provider": "openai-gpt4o",        // 可选：provider 名称（name）或 id；不传走默认
  "model": "gpt-4o"                  // 可选：覆盖该 provider 的 default_model（需与 provider 同传）
}
```

### 4.3 Error Responses

统一错误体 `{"detail": "..."}`（FastAPI 默认风格）：

| HTTP | 场景 | detail 示例 |
|------|------|-------------|
| 400 | 创建/更新校验失败 | `"ark 类型必须提供 base_url"` |
| 400 | 请求指定 provider 无效 | `"provider 'foo' 不存在或已禁用"` |
| 404 | provider 不存在 | `"Provider 1 不存在"` |
| 409 | 删除被引用 provider | `"Provider 1 正被引用为默认/fallback/节点路由，无法删除"` |
| 409 | 名称冲突 | `"Provider 名称 'openai-gpt4o' 已存在"` |
| 422 | 参数类型错误 | FastAPI 默认校验错误 |
| 502 | test 连接失败 | `"连接失败: 401 AuthenticationError ..."`（不含 key） |
| 503 | 全 fallback 链失败 | `"所有 Provider 均调用失败: [p1: 超时, p2: 认证失败]"` |

### 4.4 Breaking Changes

- `POST /api/blog/generate` 为**向后兼容扩展**：新增可选字段，不传时行为不变
- 无破坏性变更；环境变量路径完整保留

---

## 5. Business Logic

### 5.1 Core Algorithms

**Provider 解析链（resolver.py）：**

```
resolve(node, request_provider) -> list[provider_id]:
  1. 若有 request_provider：p = 查库（name 或 id），不存在/禁用 → 400
     候选链 = [p.id]
  2. 否则若有 node_routing[node]：候选链 = [该 provider_id]
  3. 否则：候选链 = []
  4. 若 settings.default_provider_id 存在且 enabled：
     候选链.append(default_provider_id)
  5. 候选链 += [f for f in settings.fallback_provider_ids if f 存在且 enabled 且不在候选链]
  6. 若候选链为空 → 回退环境变量模式（构建 env ChatModel，无降级）
  7. 去重后返回
```

**FallbackChatModel（fallback.py）：**

```
invoke(input):
  errors = []
  for provider_id, model in candidates:
    try:
      result = model.invoke(input)
      stats.record(provider=..., success=True, failover_from=errors.map(provider_id))
      return result
    except 判定为可降级异常 (AuthenticationError / RateLimitError / Timeout / InternalServerError):
      errors.append((provider_id, 摘要)); continue
    except 其他 (如 4xx 业务错误 / 内容过滤):
      stats.record(provider=..., success=False, error=...); raise   # 不降级，直接失败
  stats.record(all_attempts, success=False, error=汇总)
  raise 503 "所有 Provider 均调用失败: ..."
```

**可降级异常判定：** 基于 langchain-core 异常类型（`langchain_core.exceptions` 的 `AuthenticationError`、`RateLimitError`、`TimeoutError` 与底层 HTTP 5xx 包装），映射规则集中在一个函数 `is_failover_eligible(e)` 内，便于维护。

**流式（astream）约束：** 降级仅允许发生在「首个 token 产生之前」的失败；一旦任 provider 开始产出 token，其后续错误直接向调用方抛出（无法安全回退）。SPEC 明确此为已知限制。

**统计埋点（stats.py）：**

```
record(provider, model, node, thread_id, latency_ms, success, error, failover_from):
  从模型响应 usage 取 token（ChatOpenAI/ChatAnthropic 均带 usage_metadata；无则记 0）
  写入 llm_calls 表
```

### 5.2 Validation Rules

| 字段 | 规则 |
|------|------|
| `type = ark` 或 `openai-compatible` | `base_url` 必填，且为合法 http(s) URL |
| `type = openai` / `anthropic` | `base_url` 留空走官方端点；提供则作为自定义端点 |
| `name` | 1-64 字符，创建时唯一 |
| `api_key` | 1-512 字符；PATCH 传空串视为不更新 |
| `priority` | 整数，越大越优先 |
| `fallback_provider_ids` / `node_routing` 引用的 provider | 必须存在且 enabled，否则 400 |
| `node_routing` 键 | 限工作流已知节点名集合（outline/review/draft_section 等），未知键 400 |

### 5.3 State Machine

Provider 生命周期：`disabled ⇄ enabled`（PATCH 切换）；删除仅允许未被引用的 provider（409 保护）。fallback 链与节点映射的引用完整性在每次 PUT settings 与 DELETE provider 时双向校验。

### 5.4 Edge Cases

| 场景 | 处理 |
|------|------|
| 无任何 provider 记录 / settings 为空 | 环境变量回退（现有行为不变） |
| 请求指定 provider 但该 provider 失败 | 仍按全局 fallback 链降级（保证工作流完成率）；全链失败报 503 |
| 配置热更新时进行中的调用 | 已获取实例继续完成；新调用取新配置（缓存按 provider_id + updated_at 失效） |
| provider 被删除后历史统计 | llm_calls 冗余 provider_name，删除不影响展示 |
| 流式中途失败 | 不降级，向调用方抛错（首 token 前才可降级） |
| 全部 fallback 均禁用 | 候选链只剩启用项；为空则环境变量回退 |
| token 统计缺失（模型未返回 usage） | 记 0，不阻塞调用 |

---

## 6. Error Handling

### 6.1 Error Taxonomy

| Error Code | HTTP | Condition | User Message |
|------------|------|-----------|--------------|
| `PROVIDER_NOT_FOUND` | 404 | provider id 不存在 | `Provider {id} 不存在` |
| `PROVIDER_NAME_CONFLICT` | 409 | name 唯一冲突 | `Provider 名称 '{name}' 已存在` |
| `PROVIDER_REFERENCED` | 409 | 删除被引用 provider | `Provider {id} 正被引用为默认/fallback/节点路由，无法删除` |
| `PROVIDER_INVALID` | 400 | 请求指定不存在/禁用 | `provider '{x}' 不存在或已禁用` |
| `VALIDATION_ERROR` | 400 | 配置校验失败 | 见 5.2 各规则 |
| `TEST_FAILED` | 502 | test 连接失败 | 失败原因（不含 key） |
| `ALL_PROVIDERS_FAILED` | 503 | 全 fallback 链失败 | 各 provider 失败摘要 |

### 6.2 Retry Strategy

- 同一 provider 内不自动重试（由降级链承担容错）；全链失败直接报错
- test 连接不做重试，单次请求即时反馈
- 超时阈值：模型调用默认 `request_timeout=60s`（ChatOpenAI/ChatAnthropic 参数），可后续配置化

### 6.3 Failure Modes

| 依赖 | 失败表现 | 降级路径 |
|------|----------|----------|
| 数据库不可用 | 管理 API 500；模型解析回退环境变量 | settings/providers 读取包 try 分支，失败走 env 模式并记日志 |
| 主 provider 故障 | 自动切换 | fallback 链按序接管 |
| 全链故障 | 工作流节点报错 | 异常向调用方抛出（503）；调用统计记录全失败 |
| 模型未返回 usage | token 计 0 | 不阻塞，仅统计不完整 |

---

## 7. Security

### 7.1 Authentication & Authorization

- 本期无鉴权（与现有 `/api/health` 一致）；Provider 管理 API 与生成 API 同层暴露
- **风险已记录（见 11.2）**：管理 API 含 api_key 写入能力，生产部署必须前置网关鉴权或内网隔离

### 7.2 Input Validation

- 所有请求体走 Pydantic 校验（类型/长度/枚举）
- `base_url` 校验为 http/https，防 SSRF 类自定义端点滥用（提示性校验，不做域名白名单）
- `node_routing` 键限定已知节点名集合
- 错误信息与日志不得包含 api_key 明文

### 7.3 Data Protection

- API 响应仅返回 `api_key_masked`（后 4 位，形如 `sk-****abcd`），任何接口不回传完整 key
- api_key 在 SQLite 中明文存储（本期无加密基础设施），列为风险；后续可引入加密列迭代
- `llm_calls.error` 字段写入前剥离疑似 key（长度>16 的连续 token 片段掩码）

---

## 8. Performance

### 8.1 Expected Load

- 单用户/小团队工具场景：Provider 配置量 < 50 条；调用统计日增量 < 1k 条
- 管理 API QPS < 10；生成 API 与模型调用延迟同 LLM 服务端（秒级）

### 8.2 Optimization Strategy

- 模型实例缓存：`ProviderRegistry` 按 provider_id 缓存 `BaseChatModel`，键含 `updated_at` 实现热更新失效
- settings/providers 每次解析直读 DB（量小，无缓存一致性问题）
- 统计列表接口 `?limit=` 分页上限 200；聚合统计按 created_at 时间窗过滤

### 8.3 Database Considerations

- `idx_llm_calls_created`、`idx_llm_calls_provider` 覆盖明细查询与聚合
- 统计聚合走 SQL（GROUP BY provider_id/node），不引入额外 OLAP 组件
- 明细表长期膨胀策略见 11.1（留存清理未定）

---

## 9. Testing Strategy

### 9.1 Unit Tests

| 目标 | 用例 |
|------|------|
| `factory.py` | 各 type 映射正确（openai/anthropic/ark/openai-compatible 构建出对应类且参数正确）；缓存命中与 updated_at 失效；无动态配置回退 env |
| `resolver.py` | 四层优先级：请求指定 > 节点映射 > 默认 > fallback；去重；禁用项跳过；全空回退 env |
| `fallback.py` | 首候选成功即返回；首候选可降级异常 → 备选接管且 failover_from 正确；不可降级异常直接抛出不降级；全链失败抛 503；流式首 token 前失败可降级 |
| `stats.py` | 成功/失败记录字段完整；usage 缺失记 0 |

### 9.2 Integration Tests

- Provider CRUD + settings + delete 引用保护（临时 SQLite，`tmp_path` fixture）
- test 连接：mock ChatModel.invoke 抛/成，断言响应与 502 分支
- `POST /api/blog/generate` 新增参数：传 provider 生效；传不存在 provider 得 400
- stats 聚合与明细接口：插入样例 llm_calls 断言聚合结果

### 9.3 Edge Case Tests

覆盖 5.4 全部场景：env 回退、请求指定失败仍降级、热更新进行中调用、删除后统计保留、全 fallback 禁用、token 缺失。

### 9.4 Acceptance Criteria Mapping

| US/FR | Test | Type | Description |
|-------|------|------|-------------|
| US-001 / FR-1 | 数据模型建表与字段 | integration | providers/app_settings/llm_calls 创建成功，字段与约束符合 3.1 |
| US-002 / FR-2 | CRUD + test API | integration | 全端点行为 + 校验 + 409/404 分支 |
| US-003 / FR-3,4,10 | factory 构建与回退 | unit | 四类型映射 + env 回退 |
| US-004 / FR-5,6 | 默认 + fallback | unit | 降级链行为 + 全链失败 |
| US-005 / FR-7 | 节点路由 | unit | 映射命中/未命中 + 优先级 |
| US-006 / FR-8 | 请求指定 | integration | generate 参数覆盖 + 400 分支 |
| US-007 / FR-9 | 统计 | integration | 记录 + 聚合正确性 |
| US-008 / FR-11 | 前端管理页 | build + 浏览器 | `npm run build` 通过；浏览器走通 CRUD/测试/启停用 |
| US-009 / FR-12 | 生成页集成 | build + 浏览器 | `npm run build` 通过；浏览器指定 provider 生成并查看统计 |

---

## 10. Implementation Plan

### 10.1 Phases

1. **数据层**：SQLAlchemy 接入 + 三表模型 + create_all + 依赖写入 pyproject
2. **工厂**：langchain 依赖 + ProviderRegistry + env 回退（US-003 后端部分）
3. **解析与降级**：resolver + fallback + stats 埋点（US-004/US-005/US-007 后端部分）
4. **管理 API**：providers CRUD / settings / test / stats 端点 + 校验与错误码（US-001/US-002）
5. **生成集成**：blog.generate 可选参数 + 节点接入 resolver（US-006）
6. **前端**：路由 + antd + 管理页 → 生成页 → 统计页（US-008/US-009）

### 10.2 Issue Mapping

| Issue | SPEC Sections | Priority | Depends On |
|-------|--------------|----------|------------|
| #1 数据层与 ORM | 3, 2.4 | high | — |
| #2 LLM 工厂与环境变量回退 | 2.2, 5.1 | high | #1 |
| #3 解析链与故障降级 | 5.1, 6 | high | #2 |
| #4 调用统计埋点与接口 | 4, 5.1 | medium | #3 |
| #5 Provider/设置管理 API | 4, 5.2 | high | #1 |
| #6 生成接口扩展与节点接入 | 4.4, 5.1 | medium | #3, #5 |
| #7 前端管理页 | 2.4, 4 | medium | #5 |
| #8 前端生成页与统计页 | 2.4, 4 | medium | #6, #7 |

### 10.3 Incremental Delivery

- 阶段 1-2 完成后即可在保留 env 模式的前提下切换默认 provider（静态切换先行）
- 阶段 3 完成即具备降级能力，无需前端改动即可验证
- 前端两页可独立交付；管理页先行，生成页下拉后置
- 全程向后兼容：任何阶段回退 = 清空三张表

---

## 11. Open Questions & Risks

### 11.1 Unresolved Questions

- `llm_calls` 明细留存策略：保留多久 / 是否定期清理？（PRD Open Question 4）
- 节点路由是否需要 UI 配置界面（本期仅 API 配置）
- 请求指定 provider 失败时是否总是走全局 fallback（本期设计为「是」，如需「严格指定不降级」需改 5.1）
- Ark 的 base_url 是否需要内置默认值（本期要求用户配置 base_url，虽 Ark 官方有固定端点）

### 11.2 Technical Risks

| Risk | Impact | Mitigation |
|------|--------|-----------|
| 管理 API 无鉴权即可写 api_key | 高 | 记录风险；生产部署前置网关鉴权；本项目为本地/内网工具场景 |
| api_key 明文存 SQLite | 高 | 掩码展示 + 日志剥离；后续引入加密列迭代 |
| 流式 + fallback 冲突 | 中 | 明确「首 token 前才可降级」限制并写入文档 |
| langchain 依赖版本行为差异 | 中 | 锁定 langchain-core/openai/anthropic 主版本，测试覆盖关键调用 |
| antd + react-router 引入增大 bundle | 低 | Vite 构建默认 code-split；本期规模可接受 |

### 11.3 Assumptions

- langchain-openai / langchain-anthropic / langchain-core 当前主版本可用且 API 兼容（实现时以锁定版本为准）
- 工作流节点将在本 SPEC 落地时接入 resolver（README 规划的 nodes 尚为实现，节点名集合以届时实现为准）
- 前端 antd 使用默认主题与简体中文 locale
- 单实例部署，无水平扩展需求（SQLite 适用）

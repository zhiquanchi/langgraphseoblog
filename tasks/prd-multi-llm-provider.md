# PRD: 多 LLM Provider 管理

## 1. Introduction

当前 SEO 博客生成器计划通过单一环境变量（`LLM_PROVIDER`）指定一个 LLM Provider。本功能将 Provider 从「静态环境变量」升级为「动态可管理的多 Provider 体系」：

- 在数据库中持久化管理多个 Provider 配置（OpenAI、Anthropic、火山方舟及任意 OpenAI 兼容端点）
- 支持四种使用模式：全局静态切换、故障自动降级、按工作流节点路由、按 API 请求指定
- 提供管理 API 与前端界面，无需重启即可增删改 Provider、测试连通性、查看调用统计

## 2. Goals

- 在不重启服务的前提下动态管理多个 Provider（增、删、改、启停用、测试连接）
- 支持 OpenAI 兼容协议泛化：任何提供 base_url + api_key 的兼容服务（DeepSeek、Ollama、通义等）开箱即用
- 覆盖四种使用模式：静态切换 / 故障自动切换 / 按节点路由 / 按请求指定
- 前端提供 Provider 管理、生成时选择 Provider、调用统计展示
- 保持向后兼容：未配置动态 Provider 时回退到环境变量行为

## 3. User Stories

### US-001: Provider 数据模型与存储
**Description:** As a developer, I need a persistence layer for provider configs so that provider settings survive restarts and can be managed at runtime.

**Acceptance Criteria:**
- [ ] 新增 `providers` 表：id、name、type（openai/anthropic/ark/openai-compatible）、base_url、api_key、default_model、enabled、priority、created_at、updated_at
- [ ] SQLite 持久化实现（与项目零依赖风格一致，或用 SQLAlchemy 2.0 轻量接入）
- [ ] API key 不落日志、管理接口不回传完整 key（仅掩码）
- [ ] 后端测试通过（pytest）

### US-002: Provider 管理 API
**Description:** As a backend operator, I want REST APIs to manage providers so that I can add/update/remove providers without editing code or restarting.

**Acceptance Criteria:**
- [ ] `POST /api/providers` 创建 Provider（重名校验）
- [ ] `GET /api/providers` 列表（api_key 仅返回掩码）
- [ ] `PATCH /api/providers/{id}` 更新（可改模型、优先级、启停用）
- [ ] `DELETE /api/providers/{id}` 删除（被引用为默认或 fallback 链成员时拒绝并提示）
- [ ] `POST /api/providers/{id}/test` 发送最小 LLM 请求验证连通性，返回成功或失败原因
- [ ] 后端测试通过（pytest）

### US-003: LLM 工厂：OpenAI 兼容泛化
**Description:** As a developer, I want a provider registry that builds chat models from config so that all nodes use a unified model interface.

**Acceptance Criteria:**
- [ ] `app/llm/factory.py` 重构为注册表：按 type 构建对应 ChatModel（openai/anthropic/ark 专用适配 + openai-compatible 通用 base_url 接入）
- [ ] openai-compatible 类型只需 base_url + api_key + model 即可创建可用客户端
- [ ] 所有工作流节点统一通过模型解析器获取实例，不再直接读环境变量
- [ ] 无动态配置时回退到现有 `LLM_PROVIDER` / `*_API_KEY` 环境变量路径
- [ ] 后端测试通过（pytest）

### US-004: 全局默认 Provider 与故障自动切换
**Description:** As a backend operator, I want a global default provider with an automatic failover chain so that generation continues when the primary provider fails.

**Acceptance Criteria:**
- [ ] 可配置全局默认 Provider（静态切换模式生效）
- [ ] 可为默认 Provider 配置 fallback 链（按 priority 排序的备选列表）
- [ ] 主 Provider 调用失败（认证失败、5xx、超时、rate limit）时自动按序降级到备选，全链失败才报错
- [ ] 降级结果在调用统计中记录 `failover_from`（实际用到的 provider）
- [ ] 后端测试覆盖「主失败 → 备选接管」场景（pytest）

### US-005: 按节点路由
**Description:** As a backend operator, I want to map workflow nodes to specific providers so that cheap models handle outline generation while strong models handle final review.

**Acceptance Criteria:**
- [ ] 支持节点 → Provider 映射配置（如 outline → provider A，review → provider B）
- [ ] 路由解析优先级：请求指定 > 节点映射 > 全局默认（fallback 链最后兜底）
- [ ] 未映射的节点走全局默认 Provider
- [ ] 实际生效的节点与 provider 记录在调用统计中
- [ ] 后端测试通过（pytest）

### US-006: 按请求指定 Provider
**Description:** As an API user, I want to pick the provider/model per request so that I can compare outputs or use a specific model for a one-off generation.

**Acceptance Criteria:**
- [ ] `POST /api/blog/generate` 增加可选参数 `provider` / `model`，显式指定时覆盖节点路由与全局默认
- [ ] 指定的 provider 不存在或被禁用时返回 400 及明确错误信息
- [ ] 不传参数时行为与当前一致（走默认 Provider）
- [ ] 后端测试通过（pytest）

### US-007: 调用统计
**Description:** As an operator, I want per-call LLM usage records so that I can see which provider is actually used, token consumption, latency, and failures.

**Acceptance Criteria:**
- [ ] 每次 LLM 调用记录：provider、model、node、输入/输出 token、耗时、成功/失败、failover_from
- [ ] `GET /api/llm/stats` 聚合统计：按 Provider / 节点维度的调用次数、成功率、总 token、平均耗时
- [ ] 提供最近 N 次调用明细接口
- [ ] 后端测试通过（pytest）

### US-008: 前端 Provider 管理页
**Description:** As an admin user, I want a provider management page in the frontend so that I can configure providers without touching the server.

**Acceptance Criteria:**
- [ ] 页面列表展示所有 Provider（名称、类型、模型、启停用、优先级、key 掩码）
- [ ] 支持新建/编辑表单（type 选择、base_url、api_key、default_model、priority、enabled）
- [ ] 支持启停用开关与删除操作；删除被引用 Provider 时给出错误提示
- [ ] 「测试连接」按钮调用 test 接口并展示结果
- [ ] TypeScript 类型检查与构建通过（npm run build）
- [ ] 浏览器验证：完整走一遍「新建 → 测试 → 启用 → 生成」流程

### US-009: 前端生成页集成与统计展示
**Description:** As an end user, I want to optionally choose a provider on the generation page and see provider usage stats so that I control which backend powers my blog.

**Acceptance Criteria:**
- [ ] 生成页增加 Provider 下拉（默认「系统默认」），可选指定本次生成使用的 Provider/模型
- [ ] 生成结果/进度中展示实际使用的 Provider 与模型
- [ ] 新增 Provider 状态/统计页面（或区块）：调用次数、成功率、平均耗时、最近调用明细
- [ ] TypeScript 类型检查与构建通过（npm run build）
- [ ] 浏览器验证：选择 Provider 生成一篇文章并查看统计

## 4. Functional Requirements

- FR-1: 系统必须支持在数据库中持久化管理多个 Provider 配置（名称、类型、base_url、api_key、默认模型、启用状态、优先级）
- FR-2: 系统必须提供 Provider 的增删改查与连通性测试 REST API
- FR-3: 系统必须支持 OpenAI 兼容协议泛化接入（base_url + api_key + model 即可创建可用模型客户端）
- FR-4: 系统必须内置 OpenAI、Anthropic、火山方舟三类专用适配器
- FR-5: 系统必须支持指定一个全局默认 Provider（静态切换模式）
- FR-6: 系统必须支持为默认 Provider 配置 fallback 链，主 Provider 调用失败时自动按优先级降级，全链失败才报错
- FR-7: 系统必须支持节点级 Provider 路由映射，未映射节点使用全局默认
- FR-8: 系统必须支持 API 请求参数显式指定 Provider/模型，且优先级高于节点路由与全局默认
- FR-9: 系统必须记录每次 LLM 调用的 provider、model、node、token、耗时与成败，并提供聚合统计接口
- FR-10: 系统必须在无任何动态配置时回退到环境变量（`LLM_PROVIDER` 等）路径，保证向后兼容
- FR-11: 前端必须提供 Provider 管理页面（CRUD、启停用、测试连接）
- FR-12: 前端生成页必须支持可选指定本次生成所用的 Provider/模型，并展示实际生效的 Provider

## 5. Non-Goals

- 不做 Embedding 模型的多 Provider 管理（`EMBEDDING_PROVIDER` 维持环境变量切换现状）
- 不做智能成本调度（按价格/延迟自动择优路由），fallback 仅按配置顺序降级
- 不做调用配额、限流与计费金额统计
- 不做多租户隔离（不同用户各自管理 Provider 配置）
- 不做 API key 的 KMS/加密托管（仅掩码展示与防泄露，存储加密可后续迭代）

## 6. Design Considerations

- `app/llm/factory.py` 从单例工厂改造为「注册表 + 缓存」：按 provider_id 构建并缓存 ChatModel 实例，配置变更时失效缓存
- 工作流节点从「读环境变量」改为「通过模型解析器获取模型」，改动集中在 factory 与各节点的模型获取处
- 前端沿用现有 React 组件风格；管理页优先复用项目已引入的组件库（Form/Table/Modal 类）
- 配置优先级在 UI 与 API 文档中明示：请求指定 > 节点映射 > 全局默认 > fallback 链

## 7. Technical Considerations

- 持久化：项目当前无数据库层，建议引入 SQLite（与 LangGraph Checkpointer 的 SQLite 规划一致）；ORM 可选 SQLAlchemy 2.0 或 SQLModel，避免过度依赖
- fallback 实现：可基于 langchain `RunnableWithFallbacks`，或在 factory 内自封装重试 + 降级逻辑（后者更可控，便于记录 failover_from）
- 流式输出兼容：fallback 与节点路由不得破坏现有 `astream_events` 流式链路
- API key 安全：列表/详情接口仅返回掩码（如 `sk-****1234`），test 接口错误信息不泄露 key
- 并发安全：配置热更新需处理「更新时正在进行的调用」——已获取的模型实例继续完成，新调用使用新配置

## 8. Success Metrics

- 任一 Provider 故障时，工作流整体完成率不因故障下降（fallback 生效率 100%）
- Provider 增删改/启停用全程无需重启服务
- 前端可独立完成「新建 Provider → 测试连接 → 启用 → 指定生成」全流程
- 调用统计可回答「每个 Provider 的实际使用量、成功率、耗时」

## 9. Open Questions

- 数据库选型与 ORM 偏好：SQLite + SQLAlchemy 2.0？SQLModel？还是标准库 sqlite3？
- 节点路由是否需要 UI 配置界面（本期默认只有 API 配置）？
- fallback 判定标准确认：认证失败、5xx、超时、rate limit 触发降级；4xx 业务错误不触发——是否认可？
- 统计明细留存策略：保留多久，是否需要定期清理？

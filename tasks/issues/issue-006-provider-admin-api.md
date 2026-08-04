# Provider 与设置管理 API

## Description

Provider CRUD（含 api_key 掩码、连通性测试）与全局 LLM 设置读写（默认 Provider、fallback 链、节点路由），并做引用完整性校验。（对应 US-002）

## Acceptance Criteria

- [ ] POST /api/providers 创建（name 1-64 唯一；type 枚举校验；ark/openai-compatible 必填 base_url）
- [ ] GET /api/providers 列表与 GET /api/providers/{id} 详情，api_key 仅返回掩码（形如 sk-****abcd）
- [ ] PATCH /api/providers/{id} 更新（api_key 空串视为不更新）
- [ ] DELETE /api/providers/{id}：被 default/fallback/节点路由引用时返回 409
- [ ] POST /api/providers/{id}/test 通过工厂发最小请求验证连通性，成功返回 ok，失败返回原因（502，不含 key）
- [ ] GET/PUT /api/settings/llm：默认 provider、fallback 链、节点路由读写；引用必须存在且启用（否则 400）
- [ ] 名称冲突 409；错误响应统一 {"detail": ...}
- [ ] 后端集成测试覆盖 CRUD、掩码、409/400/404 分支、test 成功与失败（pytest）

## Dependencies

Issue #1, #2

## Type

backend

## Priority

high

## SPEC Reference

SPEC 4.1, 4.2, 4.3, 5.2

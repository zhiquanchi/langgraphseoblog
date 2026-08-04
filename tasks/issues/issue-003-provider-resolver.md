# Provider 解析链与节点路由

## Description

实现「请求指定 > 节点映射 > 全局默认 > fallback 链」四层优先级解析，输出去重、有序、跳过禁用项的 provider_id 候选链；全部为空时回退环境变量模式。未映射节点走全局默认。（对应 US-005）

## Acceptance Criteria

- [ ] app/llm/resolver.py 实现 resolve(node, request_provider) -> list[provider_id]
- [ ] 请求指定 provider 不存在或禁用时抛出 400 语义错误
- [ ] 节点映射命中优先于全局默认；未映射节点走全局默认
- [ ] fallback 链按 priority 降序拼接、去重、跳过禁用项
- [ ] 全部为空时返回空列表（调用方据此回退环境变量模式）
- [ ] 单元测试覆盖四层优先级组合、去重、禁用跳过、空回退（pytest）

## Dependencies

Issue #1

## Type

backend

## Priority

high

## SPEC Reference

SPEC 5.1

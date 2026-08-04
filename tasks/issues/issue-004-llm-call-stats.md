# 调用统计：LLMCallRecorder 与统计接口

## Description

每次 LLM 调用落库 llm_calls（含降级信息），提供按 Provider / 节点的聚合统计接口与最近调用明细接口。（对应 US-007）

## Acceptance Criteria

- [ ] app/llm/stats.py 实现 LLMCallRecorder：成功/失败记录 provider_id、provider_name、model、node、thread_id、token、耗时、error、failover_from
- [ ] token 从模型响应 usage_metadata 提取，缺失记 0
- [ ] error 字段写入前剥离疑似 API key 片段
- [ ] GET /api/llm/stats 按 Provider 与节点维度聚合：调用次数、成功率、总 token、平均耗时、failover 次数
- [ ] GET /api/llm/calls?limit=N 返回最近调用明细（上限 200）
- [ ] 后端测试覆盖记录字段完整性、聚合正确性、usage 缺失（pytest）

## Dependencies

Issue #1

## Type

backend

## Priority

medium

## SPEC Reference

SPEC 3.1, 4.1

# 故障自动切换：FallbackChatModel 自封装降级

## Description

实现自封装 FallbackChatModel：按候选链序尝试调用，可降级异常（认证失败、5xx、超时、限流）自动切换到备选，全链失败才报错；每次尝试写入调用统计并记录 failover_from。4xx 业务错误不降级直接抛出。（对应 US-004）

## Acceptance Criteria

- [ ] app/llm/fallback.py 实现 FallbackChatModel（invoke + astream）
- [ ] 认证失败 / 5xx / 超时 / 限流异常触发降级；其余异常（如 4xx 业务错误）直接抛出不降级
- [ ] 每次尝试调用 LLMCallRecorder 记录，降级时 failover_from 记录已失败候选
- [ ] 全链失败抛 503 语义错误，汇总各候选失败摘要（不含 key）
- [ ] 流式模式仅允许首个 token 产生前的失败触发降级，之后错误直接抛出
- [ ] 单元测试 mock 模型覆盖「主失败→备选接管」「不可降级异常直抛」「全链失败」三类场景（pytest）

## Dependencies

Issue #2, #3, #4

## Type

backend

## Priority

high

## SPEC Reference

SPEC 5.1, 6

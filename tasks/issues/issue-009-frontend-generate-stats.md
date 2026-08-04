# 前端生成页与统计页集成

## Description

生成页增加 Provider 下拉（可选指定本次生成所用 Provider/模型）并展示实际生效 Provider；新增统计页展示调用指标与最近明细。（对应 US-009）

## Acceptance Criteria

- [ ] 生成页增加 Provider 下拉（默认「系统默认」），数据源 GET /api/providers 的启用项
- [ ] 生成进度/结果中展示实际使用的 Provider 与模型
- [ ] 统计页：Statistic 卡片（调用次数、成功率、平均耗时、总 token）+ 按 Provider/节点表格 + 最近调用明细
- [ ] npm run build（tsc + vite）通过
- [ ] 浏览器验证：选择 Provider 生成一篇文章并查看统计页数据

## Dependencies

Issue #7, #8

## Type

frontend

## Priority

medium

## SPEC Reference

SPEC 2.4, 4.1

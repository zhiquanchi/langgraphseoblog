# 生成接口扩展与工作流节点接入

## Description

POST /api/blog/generate 增加可选 provider / model 参数（不传时行为不变）；工作流各节点统一经 resolver + factory 获取模型，不再直接读环境变量。（对应 US-006）

## Acceptance Criteria

- [ ] POST /api/blog/generate 请求体增加可选 provider（名称或 id）与 model 字段
- [ ] 不传参数时行为与当前一致（走默认解析链）
- [ ] 传 provider 时覆盖节点映射与全局默认；不存在/禁用返回 400
- [ ] model 与 provider 同传时覆盖该 provider 的 default_model
- [ ] 各工作流节点模型获取改为经 resolver + factory
- [ ] 后端测试覆盖参数生效、400 分支、缺省行为（pytest）

## Dependencies

Issue #3, #6

## Type

backend

## Priority

medium

## SPEC Reference

SPEC 4.4, 5.1

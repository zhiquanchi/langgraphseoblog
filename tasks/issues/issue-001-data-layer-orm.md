# 数据层与 ORM：SQLAlchemy + SQLite 三表

## Description

建立动态配置持久化基础，支撑后续所有 Provider 管理功能。新增 SQLAlchemy 2.0 + SQLite 数据层，定义 Provider 配置、全局 LLM 设置、调用统计三张表，启动时自动建表。（对应 US-001）

## Acceptance Criteria

- [ ] pyproject.toml 增加 sqlalchemy>=2.0 依赖并完成依赖安装
- [ ] app/db.py 提供 engine / Session 管理（SQLite 文件库，路径可配置）
- [ ] app/models.py 定义 Provider、AppSettings、LLMCall 三张表（字段与索引见 SPEC 3.1/3.2，AppSettings 为单行约束 id=1）
- [ ] app/main.py 启动时执行 Base.metadata.create_all() 建表
- [ ] API key 不落日志；测试断言日志输出不含 api_key 明文
- [ ] 后端测试通过（uv run pytest）

## Dependencies

None — 可以立即开始

## Type

backend

## Priority

high

## SPEC Reference

SPEC 3.1, 3.2, 2.4

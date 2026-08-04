# LLM 工厂：ProviderRegistry 与环境变量回退

## Description

把模型构建收敛为统一注册表（ProviderRegistry），支持四种 Provider 类型映射、按配置热更新缓存；无动态配置时回退到现有 LLM_PROVIDER 环境变量路径，保证向后兼容。（对应 US-003）

## Acceptance Criteria

- [ ] pyproject.toml 增加 langchain-core / langchain-openai / langchain-anthropic 依赖并锁定主版本
- [ ] app/llm/factory.py 实现 ProviderRegistry：openai→ChatOpenAI、anthropic→ChatAnthropic、ark/openai-compatible→ChatOpenAI(base_url=配置值)
- [ ] openai-compatible 类型仅凭 base_url + api_key + default_model 即可构建可用实例
- [ ] 模型实例按 provider_id + updated_at 缓存，配置更新后失效重建
- [ ] 无动态配置时回退 LLM_PROVIDER / *_API_KEY / *_MODEL 环境变量路径构建
- [ ] 单元测试覆盖四类型映射、缓存命中与失效、env 回退（pytest）

## Dependencies

Issue #1

## Type

backend

## Priority

high

## SPEC Reference

SPEC 2.2, 5.1

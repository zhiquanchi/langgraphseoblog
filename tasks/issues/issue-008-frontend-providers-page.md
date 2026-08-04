# 前端 Provider 管理页

## Description

引入 react-router 与 antd，搭建路由骨架并落地 Provider 管理界面：列表、新建/编辑、启停用、删除（引用保护提示）、测试连接。（对应 US-008）

## Acceptance Criteria

- [ ] package.json 增加 react-router-dom 与 antd；main.tsx 挂 BrowserRouter + antd ConfigProvider（中文 locale）
- [ ] App.tsx 定义路由：/（生成页）、/providers（管理页）、/stats（统计页）
- [ ] 管理页 Table 展示所有 Provider：名称、类型、模型、启停用、优先级、key 掩码
- [ ] 新建/编辑 Modal 表单：type 选择、base_url、api_key、default_model、priority、enabled
- [ ] 启停用 Switch 与删除按钮；删除被引用 Provider 时展示 409 错误提示
- [ ] 「测试连接」按钮调用 POST /api/providers/{id}/test 并展示结果
- [ ] npm run build（tsc + vite）通过
- [ ] 浏览器验证：完整走一遍「新建→测试→启用→生成」

## Dependencies

Issue #6

## Type

frontend

## Priority

medium

## SPEC Reference

SPEC 2.4, 4.1

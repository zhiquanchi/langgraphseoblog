# LangGraph SEO Blog

基于 LangGraph 的 SEO 博客生成器，前后端分离的 monorepo：

```
├── backend/    # FastAPI + LangGraph API 服务
└── frontend/   # React + Vite + TypeScript 前端
```

## 本地开发

**后端**（端口 8000）

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload
```

**前端**（端口 5173，已配置 `/api` 代理到后端）

```bash
cd frontend
npm install
npm run dev
```

访问 http://localhost:5173 ，页面会通过代理请求 `/api/health` 显示后端状态。

## 测试

```bash
cd backend && uv run pytest   # 后端测试
cd frontend && npm run build  # 前端类型检查 + 构建
```

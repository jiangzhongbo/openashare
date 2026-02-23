# 部署检查清单

使用本清单确保所有部署步骤都已完成。

---

## ☑️ 部署前检查

- [ ] 已有 Cloudflare 账号（免费版）
- [ ] 已有 GitHub 账号
- [ ] 本地已安装 wrangler CLI (`npm install -g wrangler`)
- [ ] 本地测试通过（`wrangler dev` + `python3 main.py`）

---

## ☑️ Cloudflare Worker 部署

- [ ] 1. 登录 Cloudflare (`wrangler login`)
- [ ] 2. 创建 D1 数据库 (`wrangler d1 create ashare-screener-db`)
- [ ] 3. 记录 `database_id`
- [ ] 4. 更新 `worker/wrangler.toml` 中的 `database_id`
- [ ] 5. 执行数据库迁移 (`wrangler d1 execute ashare-screener-db --remote --file=../migrations/0001_initial_schema.sql`)
- [ ] 6. 生成 WORKER_WRITE_TOKEN (`openssl rand -hex 32`)
- [ ] 7. 设置 Worker secret (`wrangler secret put WORKER_WRITE_TOKEN`)
- [ ] 8. 部署 Worker (`wrangler deploy`)
- [ ] 9. 记录 Worker URL (例如: `https://ashare-screener.xxx.workers.dev`)
- [ ] 10. 测试 API (`curl https://your-worker-url/api/combinations`)

---

## ☑️ Cloudflare Pages 部署

- [ ] 1. 更新 `web/index.html` 中的 `API_BASE` 为生产 Worker URL
- [ ] 2. 提交代码到 GitHub
- [ ] 3. 登录 Cloudflare Dashboard
- [ ] 4. 创建 Pages 项目，连接 GitHub 仓库
- [ ] 5. 配置构建设置：
  - Build command: 留空
  - Build output directory: `web`
  - Root directory: `openashare`
- [ ] 6. 部署完成，记录 Pages URL (例如: `https://ashare-screener.pages.dev`)
- [ ] 7. 访问 Pages URL，确认前端正常显示

---

## ☑️ GitHub Actions 配置

- [ ] 1. 进入 GitHub 仓库 Settings → Secrets and variables → Actions
- [ ] 2. 添加 Secret: `WORKER_URL` = Worker URL
- [ ] 3. 添加 Secret: `WORKER_WRITE_TOKEN` = 步骤 6 中生成的 token
- [ ] 4. 手动触发 workflow (Actions → Daily Stock Screening → Run workflow)
- [ ] 5. 查看运行日志，确认成功
- [ ] 6. 检查 Worker API 是否有数据 (`curl https://your-worker-url/api/screening/latest`)
- [ ] 7. 刷新前端，确认显示最新数据

---

## ☑️ CORS 配置（可选）

如果前端和 Worker 在不同域名，需要配置 CORS：

- [ ] 1. 编辑 `worker/src/index.ts`
- [ ] 2. 在 `jsonResponse()` 函数中添加 CORS 头
- [ ] 3. 设置 `Access-Control-Allow-Origin` 为 Pages URL
- [ ] 4. 重新部署 Worker (`wrangler deploy`)
- [ ] 5. 测试前端是否能正常加载数据

---

## ☑️ 验证部署

- [ ] Worker API 可访问
  - [ ] `GET /api/combinations` 返回组合列表
  - [ ] `GET /api/screening/latest` 返回筛选结果
  - [ ] `GET /api/screening/history` 返回历史记录
- [ ] 前端可访问
  - [ ] 显示组合 Tab
  - [ ] 显示筛选结果表格
  - [ ] 显示历史记录
  - [ ] 点击股票代码可跳转东方财富
- [ ] GitHub Actions 正常运行
  - [ ] 每日 16:30 自动触发
  - [ ] 测试通过
  - [ ] 筛选成功
  - [ ] 数据上传成功
  - [ ] SQLite 缓存生效

---

## ☑️ 后续维护

- [ ] 监控 GitHub Actions 运行状态
- [ ] 定期检查 Cloudflare 免费额度使用情况
- [ ] 根据需要添加新因子或调整组合
- [ ] 定期查看筛选结果，验证因子有效性

---

## 🎉 部署完成！

所有步骤完成后，你的 A 股选股工具已经成功部署到生产环境，每日自动运行。

**访问地址：**
- 前端：`https://ashare-screener.pages.dev`
- API：`https://ashare-screener.xxx.workers.dev`

**下一步：**
- 查看 [README.md](../README.md) 了解如何添加新因子
- 查看 [Plan 文档](./plans/0001-stock-screener.md) 了解系统架构


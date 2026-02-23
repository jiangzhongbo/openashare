# A股选股工具 - 部署指南

本文档说明如何将系统部署到生产环境（Cloudflare）。

---

## 前置条件

1. **Cloudflare 账号**（免费版即可）
2. **GitHub 账号**
3. **本地已安装**：
   - Node.js 18+
   - Python 3.11+
   - wrangler CLI (`npm install -g wrangler`)

---

## 部署步骤

### 1. 部署 Cloudflare Worker

#### 1.1 登录 Cloudflare
```bash
wrangler login
```

#### 1.2 创建生产 D1 数据库
```bash
cd worker
wrangler d1 create ashare-screener-db
```

记录输出中的 `database_id`，例如：
```
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
```

#### 1.3 更新 wrangler.toml
编辑 `worker/wrangler.toml`，将 `[[d1_databases]]` 部分的 `database_id` 替换为上一步的值。

#### 1.4 执行数据库迁移
```bash
wrangler d1 execute ashare-screener-db --remote --file=../migrations/0001_initial_schema.sql
```

#### 1.5 设置 Worker 环境变量
```bash
# 生成一个随机 token（用于 Python 写入鉴权）
openssl rand -hex 32

# 设置为 Worker secret
wrangler secret put WORKER_WRITE_TOKEN
# 粘贴上面生成的 token
```

#### 1.6 部署 Worker
```bash
wrangler deploy
```

记录输出中的 Worker URL，例如：
```
https://ashare-screener.your-subdomain.workers.dev
```

---

### 2. 部署 Cloudflare Pages（前端）

#### 2.1 修改前端 API 配置
编辑 `web/index.html`，将 API_BASE 改为生产 Worker URL：

```javascript
const API_BASE = window.location.hostname === 'localhost' || window.location.protocol === 'file:'
  ? 'http://localhost:8787'
  : 'https://ashare-screener.your-subdomain.workers.dev';  // 改为你的 Worker URL
```

#### 2.2 通过 Cloudflare Dashboard 部署
1. 登录 [Cloudflare Dashboard](https://dash.cloudflare.com/)
2. 进入 **Pages** → **Create a project**
3. 选择 **Connect to Git** → 选择你的 GitHub 仓库
4. 配置构建设置：
   - **Build command**: 留空（纯静态）
   - **Build output directory**: `web`
   - **Root directory**: `openashare`
5. 点击 **Save and Deploy**

记录 Pages URL，例如：
```
https://ashare-screener.pages.dev
```

---

### 3. 配置 GitHub Actions

#### 3.1 设置 GitHub Secrets
在 GitHub 仓库中设置以下 Secrets：

1. 进入仓库 → **Settings** → **Secrets and variables** → **Actions**
2. 点击 **New repository secret**，添加：

| Secret Name | Value |
|------------|-------|
| `WORKER_URL` | `https://ashare-screener.your-subdomain.workers.dev` |
| `WORKER_WRITE_TOKEN` | 步骤 1.5 中生成的 token |

#### 3.2 测试 GitHub Actions
```bash
# 手动触发 workflow
gh workflow run daily-screening.yml
# 或者在 GitHub 网页上：Actions → Daily Stock Screening → Run workflow
```

查看运行日志，确保成功。

---

### 4. 配置 Worker CORS（可选）

如果前端和 Worker 在不同域名，需要在 Worker 中配置 CORS。

编辑 `worker/src/index.ts`，在 `jsonResponse()` 函数中添加 CORS 头：

```typescript
function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      'Content-Type': 'application/json',
      'Access-Control-Allow-Origin': 'https://ashare-screener.pages.dev',  // 你的 Pages URL
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    },
  });
}
```

重新部署 Worker：
```bash
wrangler deploy
```

---

## 验证部署

### 1. 验证 Worker API
```bash
# 获取组合列表
curl https://ashare-screener.your-subdomain.workers.dev/api/combinations

# 获取最新筛选结果
curl https://ashare-screener.your-subdomain.workers.dev/api/screening/latest
```

### 2. 验证前端
访问 `https://ashare-screener.pages.dev`，应该能看到：
- 组合 Tab（MA60支撑反弹+趋势向上）
- 筛选结果表格
- 历史记录区域

### 3. 验证 GitHub Actions
等待每日 16:30（北京时间），或手动触发 workflow，检查：
- Actions 运行成功
- Worker API 返回当日数据
- 前端显示最新结果

---

## 常见问题

### Q1: GitHub Actions 运行失败，提示 "Unauthorized"
**A**: 检查 `WORKER_WRITE_TOKEN` secret 是否正确设置，与 Worker 中的 token 一致。

### Q2: 前端显示 "加载失败: Failed to fetch"
**A**: 检查：
1. Worker 是否已部署
2. 前端 `API_BASE` 配置是否正确
3. 是否需要配置 CORS

### Q3: GitHub Actions Cache 不生效，每次都全量下载
**A**: 这是正常的，第一次运行会全量下载。后续运行会复用缓存，只增量更新。

### Q4: BaoStock 登录失败
**A**: BaoStock 偶尔会不稳定，重试即可。GitHub Actions 会自动重试失败的 workflow。

---

## 成本估算（免费额度）

| 服务 | 免费额度 | 预计使用 | 是否足够 |
|------|---------|---------|---------|
| CF Worker | 10万请求/天 | ~100请求/天 | ✅ 足够 |
| CF D1 | 500万行读取/天 | ~1000行读取/天 | ✅ 足够 |
| CF Pages | 500次构建/月 | 1次构建/月 | ✅ 足够 |
| GitHub Actions | 2000分钟/月 | ~30分钟/月 | ✅ 足够 |

**结论：完全免费，无需付费。**

---

## 下一步

部署完成后，你可以：

1. **添加新因子** - 在 `openashare/pipeline/factors/` 创建新文件
2. **调整组合** - 修改 `openashare/pipeline/factors/registry.py`
3. **调整参数** - 在 GitHub Actions 中设置环境变量（格式：`FACTOR_<ID>_<PARAM>`）
4. **查看历史数据** - 访问前端的历史记录区域

详见 [Plan 文档](./plans/0001-stock-screener.md)。


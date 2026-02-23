# A股选股工具

基于技术指标的 A 股自动筛选系统，每日自动运行并展示符合条件的股票。

---

## 🎯 功能特性

- **自动化运行** - GitHub Actions 每日 16:30 自动执行
- **因子系统** - 可扩展的技术指标因子框架
- **组合筛选** - 支持多因子组合，灵活配置
- **历史记录** - 永久保存每日筛选结果
- **增量更新** - 智能缓存，只下载新数据
- **完全免费** - 基于 Cloudflare 免费服务

---

## 📁 项目结构

```
openashare/                    # 项目根目录
├── pipeline/                  # Python 数据管道
│   ├── data/                 # 数据获取和本地缓存
│   ├── factors/              # 因子定义和组合注册
│   ├── screening/            # 筛选引擎
│   ├── sync/                 # Worker 客户端
│   └── main.py               # 主入口
├── worker/                    # Cloudflare Worker API
│   └── src/index.ts          # API 端点实现
├── web/                       # 静态前端
│   └── index.html            # 单页应用
├── migrations/                # 数据库迁移脚本
├── .github/workflows/         # GitHub Actions
│   └── daily-screening.yml   # 每日筛选任务
└── docs/                      # 文档
    ├── plans/                # 设计文档
    └── deployment.md         # 部署指南
```

---

## 🚀 快速开始

### 本地开发

#### 1. 安装依赖

**Python 依赖：**
```bash
cd pipeline
pip install -r requirements.txt
```

**Worker 依赖：**
```bash
cd worker
npm install
```

#### 2. 启动本地 Worker
```bash
cd worker
npx wrangler dev --port 8787
```

#### 3. 运行数据管道
```bash
cd pipeline
export WORKER_URL=http://localhost:8787
export WORKER_WRITE_TOKEN=test-token-local
python3 main.py
```

#### 4. 查看前端
在浏览器中打开 `web/index.html`

---

## 📦 生产部署

详见 [部署指南](./docs/deployment.md)

**简要步骤：**
1. 部署 Cloudflare Worker（API + 数据库）
2. 部署 Cloudflare Pages（前端）
3. 配置 GitHub Actions Secrets
4. 等待每日自动运行或手动触发

---

## 🔧 添加新因子

### 1. 创建因子文件
在 `pipeline/factors/` 创建新文件，例如 `my_factor.py`：

```python
from .base import Factor, FactorResult
import pandas as pd

class MyFactor(Factor):
    def __init__(self, threshold: float = 10.0):
        super().__init__(
            id="my_factor",
            label="我的因子",
            params={"threshold": threshold}
        )
    
    def compute(self, df: pd.DataFrame) -> FactorResult:
        # df 包含列：date, open, high, low, close, volume, amount, turn, pct_chg
        # 以及计算好的 MA5, MA10, MA20, MA60
        
        if len(df) < 10:
            return FactorResult(passed=False, reason="数据不足")
        
        latest = df.iloc[-1]
        
        # 你的逻辑
        if latest['close'] > latest['MA60'] * (1 + self.params['threshold'] / 100):
            return FactorResult(
                passed=True,
                value=latest['close'] / latest['MA60'] * 100 - 100,
                detail=f"价格高于MA60 {self.params['threshold']}%"
            )
        
        return FactorResult(passed=False, reason="未达到阈值")
```

### 2. 注册因子
在 `pipeline/factors/registry.py` 中注册：

```python
from .my_factor import MyFactor

# 注册因子
register_factor(MyFactor())

# 添加到组合
COMBINATIONS = [
    Combination(
        id="my_combination",
        label="我的组合",
        description="使用我的因子筛选",
        factors=["my_factor", "ma60_recent_uptrend"]  # 可以组合多个因子
    ),
]
```

### 3. 测试
```bash
cd pipeline
python3 test_factors.py --factor my_factor --stock 000001
```

---

## 📊 当前因子

| 因子 ID | 名称 | 说明 |
|---------|------|------|
| `ma60_bounce_with_volume` | MA60支撑反弹 | 检测跌破MA60后带量反弹 |
| `ma60_recent_uptrend` | MA60近期上升 | 检查最近N天MA60严格向上 |

---

## 🔐 环境变量

### GitHub Actions Secrets
| 变量名 | 说明 |
|--------|------|
| `WORKER_URL` | Worker API 地址 |
| `WORKER_WRITE_TOKEN` | Worker 写入鉴权 token |

### 因子参数覆盖（可选）
格式：`FACTOR_<因子ID>_<参数名>`

例如：
```bash
FACTOR_MA60_BOUNCE_WITH_VOLUME_MIN_GAIN=8.0
FACTOR_MA60_RECENT_UPTREND_LOOKBACK_DAYS=15
```

---

## 📖 文档

- [AI 开发方法论](./docs/ai-development-methodology.md)
- [Plan 0001: 股票筛选工具](./docs/plans/0001-stock-screener.md)
- [部署指南](./docs/deployment.md)

---

## 📝 License

MIT


# 全球财经新闻聚合 Agent

每天自动抓取全球财经 RSS → 去重 → DeepSeek 中文摘要 → SQLite 存储 → Markdown 日报。

## 项目结构

```
news-agent/
├── config.py       # 配置中心（RSS 源、分类、阈值、API 端点）
├── fetcher.py      # RSS 抓取 + News API 预留接口
├── dedup.py        # URL hash 去重 + embedding 相似度聚类
├── summarizer.py   # DeepSeek batch 摘要 + 分类
├── storage.py      # SQLite 读写
├── report.py       # 生成 daily_YYYY-MM-DD.md
├── main.py         # 主流水线入口
├── requirements.txt
├── .env.example
└── .github/workflows/daily.yml   # GitHub Actions 定时任务
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

> 首次运行会从 Hugging Face 下载 `paraphrase-multilingual-MiniLM-L12-v2`（约 120 MB）。
> 如果网络受限或不需要语义去重，可在 `requirements.txt` 中删除 `sentence-transformers` 和 `numpy`，流水线会自动降级为纯 URL 去重。

### 2. 配置密钥

```bash
cp .env.example .env
# 编辑 .env，填入你的 DeepSeek API Key
```

`.env` 文件示例：

```
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx
```

其余变量均有默认值，可按需修改。

### 3. 本地运行

```bash
python main.py
```

生成的日报保存在 `reports/daily_YYYY-MM-DD.md`。

#### 其他选项

```bash
# 指定日期（重新生成历史日报，不重新抓取）
python main.py --date 2025-06-01 --skip-fetch

# 跳过抓取，只从数据库重新生成今日报告
python main.py --skip-fetch
```

## GitHub Actions 自动化

### 配置 Secrets

在仓库 **Settings → Secrets and variables → Actions** 中添加：

| Secret 名称 | 说明 |
|---|---|
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥（必填） |
| `FINNHUB_API_KEY` | Finnhub 密钥（选填，留空则跳过） |
| `MARKETAUX_API_KEY` | MarketAux 密钥（选填，留空则跳过） |

### 触发方式

- **定时**：每天 UTC 23:00（北京时间次日 07:00）自动触发。
- **手动**：Actions 页面点击 "Run workflow"。

生成的日报会自动 commit 到仓库的 `reports/` 目录。

## 增删新闻源

编辑 `config.py` 中的 `RSS_FEEDS` 列表，每条记录格式如下：

```python
{
    "url":    "https://example.com/rss",   # RSS feed URL
    "source": "示例媒体",                   # 来源名称（显示在日报中）
    "lang":   "zh",                         # "en" 或 "zh"
},
```

保存后下次运行即生效，无需改动其他文件。

## 调整去重阈值

在 `config.py` 中修改：

```python
SIMILARITY_THRESHOLD = 0.85   # 0.0–1.0，越高越严格（保留更多文章）
```

## 分类标签

默认分类（可在 `config.py` 的 `CATEGORIES` 列表中增删）：

`货币政策` / `贸易` / `能源` / `股市` / `地缘政治` / `宏观数据` / `其他`

## 版权说明

日报只输出我方改写的中文摘要和原文链接，不整段转载原文，规避版权风险。

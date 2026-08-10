# RepoTrace

RepoTrace 是一个面向 GitHub 项目的历史故障调查工具。

开发者遇到 Bug 时，经常需要在 Issue、Pull Request、Commit 和项目文档之间来回搜索：这个问题以前出现过吗？当时是什么原因？最后改了哪里？RepoTrace 把这条调查链路放到一个地方完成，并把每一步使用的证据保留下来。

当前版本聚焦一个场景：**历史故障调查**。它不会自动修改代码，也不会把一次检索结果包装成“确定结论”。如果证据不足，系统会明确降低置信度。

## 能做什么

- 导入公开 GitHub 仓库的 Issue、PR、Commit、README 和部分 `docs/` 文档
- 使用 BM25 + 字符向量检索，并通过 RRF 合并两路结果
- 对错误码、函数名、Issue 编号和“怎么修”这类修复意图做领域重排
- 通过 LangGraph 编排 `检索 → 重排 → 回答 → 证据检查`
- 支持 OpenAI-compatible LLM；未配置 LLM 时会自动退化为可追溯的证据摘要
- 每次调查都记录本地 Trace，可查看各阶段耗时和命中数量
- 可选接入 Langfuse，把 Agent / Retrieval / Generation 链路导出到外部观测平台
- 同时维护人工回归集和真实 GitHub Golden Dataset，检索改动必须用指标验证

## V0.2：真实 GitHub Benchmark

当前冻结集 `github_issue_pr_v1` 包含 **34 条真实 Issue → merged PR**，来自：

- `langchain-ai/langchain`：8 条
- `pydantic/pydantic`：26 条

Ground Truth 只接受 PR 正文中明确的 `Fixes / Closes / Resolves` 关系，并确认 PR 已 merged。冻结集使用 GitHub 原始 Issue 标题和 PR 标题，不加入人工改写文本，closure evidence 也不会进入检索候选。

Repo scope 结果：

| 方案 | Recall@1 | Recall@5 | MRR | nDCG@5 |
|---|---:|---:|---:|---:|
| BM25 | 55.88% | 67.65% | 0.6099 | 0.6215 |
| BM25 + 字符向量 RRF | 61.76% | **79.41%** | 0.7098 | 0.7134 |
| Dense LSA baseline | 61.76% | 73.53% | 0.6776 | 0.6750 |
| BM25 + Dense LSA RRF | 58.82% | 73.53% | 0.6654 | 0.6674 |
| Hybrid + Evidence Reranker | **64.71%** | **79.41%** | **0.7246** | **0.7242** |

这里的 Dense LSA 是 `TF-IDF → TruncatedSVD` 的离线 dense baseline，和 neural sentence embedding 分开统计。

完整数据构造、消融、global stress test 和失败分析见 [`docs/evaluation/GITHUB_BENCHMARK_V02.md`](docs/evaluation/GITHUB_BENCHMARK_V02.md)。下一轮实验见 [`docs/evaluation/NEXT_EXPERIMENTS.md`](docs/evaluation/NEXT_EXPERIMENTS.md)。

## 小型回归集

`demo_incidents_v1` 仍保留 8 个故障查询，用于 CI 快速发现检索逻辑退化。它是人工工程回归集，不当作真实公开仓库效果。

| 方案 | Hit Rate@5 | MRR |
|---|---:|---:|
| BM25 基线 | 87.5% | 0.6292 |
| BM25 + 字符向量 RRF | 100% | 0.7604 |
| Hybrid + 证据重排 | 100% | 1.0000 |

V0.1 的优化过程见 [`docs/evaluation/EVALUATION.md`](docs/evaluation/EVALUATION.md)。

## 架构

```mermaid
flowchart LR
    UI[React UI] --> API[FastAPI]
    API --> GH[GitHub REST API]
    GH --> DB[(SQLite)]
    API --> G[LangGraph Investigation]
    G --> R[Hybrid Retrieval]
    R --> RR[Evidence Rerank]
    RR --> LLM[LLM / Extractive Fallback]
    LLM --> V[Evidence Check]
    V --> UI
    G --> T[Local Trace]
    G -. optional .-> LF[Langfuse]
```

V1 使用 SQLite 和本地检索索引，先把故障调查、评估和证据链做扎实。代码关系图、增量索引、neural embedding、跨仓库调查等能力继续通过真实 benchmark 推进。

## 快速开始

### 1. 后端

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

API 文档：`http://localhost:8000/docs`

### 2. 前端

```bash
cd frontend
npm install
npm run dev
```

浏览器打开：`http://localhost:5173`

Vite 会把 `/api` 请求代理到 `localhost:8000`。

### 3. 配置 LLM

复制环境变量模板：

```bash
cp .env.example .env
```

至少设置：

```env
REPO_TRACE_LLM_ENABLED=true
REPO_TRACE_LLM_BASE_URL=https://opencode.ai/zen/go/v1
REPO_TRACE_LLM_API_KEY=your-key
REPO_TRACE_LLM_MODEL=deepseek-v4-flash
```

`REPO_TRACE_LLM_BASE_URL` 需要填写到 `/v1` 层级，RepoTrace 会调用 `${base_url}/chat/completions`。

不配置 LLM 也能运行。此时系统会展示检索到的证据和 Trace，只跳过生成式归纳。

### 4. GitHub Token（推荐）

公开仓库在不带 Token 的情况下也能访问，但 GitHub REST API 的匿名限额比较低。建议设置：

```env
REPO_TRACE_GITHUB_TOKEN=github_pat_xxx
```

Token 只通过运行时环境变量读取，不应提交到仓库。

## 运行测试与评估

```bash
cd backend
pytest -q
python -m scripts.run_benchmark
python -m scripts.run_github_benchmark --scope repo
python -m scripts.run_github_benchmark --scope global
```

重新构造真实 GitHub 数据集：

```bash
python -m scripts.build_github_benchmark \
  --repo langchain-ai/langchain \
  --repo pydantic/pydantic \
  --limit-per-repo 50 \
  --output benchmarks/github_issue_pr_regenerated.jsonl
```

CI 会执行 Ruff、pytest coverage、人工回归 benchmark、真实 GitHub 冻结集 benchmark 和前端 build。

## 项目结构

```text
RepoTrace/
├── backend/
│   ├── app/
│   │   ├── api/              # FastAPI 路由
│   │   ├── core/             # 配置
│   │   ├── models/           # 领域模型
│   │   ├── services/         # GitHub、检索、LLM、Agent、评估
│   │   ├── storage/          # SQLite
│   │   └── support/          # demo + real benchmark support
│   ├── benchmarks/           # 冻结 Golden Dataset
│   ├── scripts/              # benchmark / dataset builder / LLM smoke test
│   └── tests/
├── frontend/                 # React + TypeScript + Vite
├── docs/
│   ├── design/
│   ├── engineering/
│   ├── evaluation/
│   ├── guide/
│   └── roadmap/
└── .github/workflows/ci.yml
```

## 文档

- [产品问题与边界](docs/design/PRODUCT.md)
- [系统设计](docs/design/SYSTEM_DESIGN.md)
- [UI 设计说明](docs/design/UI_DESIGN.md)
- [技术选择与取舍](docs/engineering/TECH_DECISIONS.md)
- [V0.1 评估与优化记录](docs/evaluation/EVALUATION.md)
- [V0.2 真实 GitHub Benchmark](docs/evaluation/GITHUB_BENCHMARK_V02.md)
- [下一轮实验清单](docs/evaluation/NEXT_EXPERIMENTS.md)
- [从代码理解 RepoTrace](docs/guide/UNDERSTANDING_REPOTRACE.md)
- [后续路线](docs/roadmap/ROADMAP.md)

## License

[MIT](LICENSE)

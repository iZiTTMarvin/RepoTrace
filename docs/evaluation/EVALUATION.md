# 检索评估与第一轮优化记录

这份文档保留 RepoTrace V0.1 的小型回归实验。V0.2 已经加入真实 GitHub `Issue → merged PR` Golden Dataset，真实结果见 [`GITHUB_BENCHMARK_V02.md`](GITHUB_BENCHMARK_V02.md)。

## V0.1 数据集

`demo_incidents_v1`：8 个故障查询，15 条候选证据。

包含几类常见软件故障：

- token refresh 并发导致 401；
- webhook 大请求导致 502；
- Windows 路径分隔符导致 ignore 失效；
- SSE 被 Nginx buffering；
- logout 后 profile cache 没清；
- 代理 body size 配置；
- `X-Accel-Buffering` header。

候选文档模拟 GitHub 中的 Issue、merged PR、Commit 和 docs。

它是人工整理的回归集，作用是：

1. 每次改检索逻辑后快速发现退化；
2. 用消融验证一个改动有没有帮助；
3. CI 不依赖外部 API 和模型。

真实公开仓库效果不再用这 8 条数据证明。

## 指标

### Hit Rate@5

正确证据是否至少有一条出现在 Top 5。

### MRR

第一条正确证据排得越靠前，分数越高：

```text
rank 1 -> 1.0
rank 2 -> 0.5
rank 3 -> 0.333...
```

## V0：BM25 基线

最开始只有 BM25。

| Metric | Result |
|---|---:|
| Hit Rate@5 | 0.8750 |
| MRR | 0.6292 |

主要暴露两个问题。

第一类是中英文词面完全对不上。例如：

```text
查询：退出登录以后还短暂显示上一个用户头像
Issue：Logout leaves cached profile
```

第二类是 Issue 和 merged PR 都召回了，但用户问“最后怎么修”时，描述现象的 Issue 容易排在修复 PR 前面。

## V0.2：Query Expansion + 双路检索 + RRF

先用少量调试词做中英扩展：

```text
退出登录 -> logout / sign out
头像     -> avatar / profile
缓存     -> cache / stale
并发     -> concurrent / race
路径     -> path / separator
卡住     -> stuck / buffering
```

第二路使用 char 3–5 gram TF-IDF，再和 BM25 做 RRF。

| Metric | BM25 | Hybrid |
|---|---:|---:|
| Hit Rate@5 | 0.8750 | **1.0000** |
| MRR | 0.6292 | **0.7604** |

## V0.3：Evidence Reranker

最早的重排信号包括：

- 函数名、错误码、配置项精确命中；
- `#123` 明确编号；
- merged PR；
- “怎么修 / fix / resolve”修复意图。

小回归集上：

| Metric | BM25 | Hybrid | Hybrid + Rerank |
|---|---:|---:|---:|
| Hit Rate@5 | 0.8750 | 1.0000 | **1.0000** |
| MRR | 0.6292 | 0.7604 | **1.0000** |

8 条数据上的 1.0 只表示这些已知回归样例全部排对，不能当成真实准确率。

## V0.2 真实 Benchmark 带来的修正

真实 Golden Dataset 上发现：如果候选池本身全部是 merged PR，那么“PR 类型”和“已 merged”对每个候选都一样，几乎没有区分能力。

因此 Evidence Reranker 现在会先对当前候选集的 Hybrid、BM25、字符向量分数做归一化，再使用标题 overlap、全文 overlap 和精确标识符作为 tie-break signal，同时保留明确 Issue 编号和修复意图的领域信号。

改完以后，小回归集仍保持：

```text
Hit Rate@5 = 1.0000
MRR        = 1.0000
```

真实 `github_issue_pr_v1` repo-scope 则从 Hybrid 的：

```text
Recall@1 = 0.6176
MRR      = 0.7098
```

提升到：

```text
Recall@1 = 0.6471
MRR      = 0.7246
```

这组数字来自 34 条真实 GitHub closure relation。完整实验、Dense LSA 对比、global stress test、数据构造规则见 [`GITHUB_BENCHMARK_V02.md`](GITHUB_BENCHMARK_V02.md)。

## 如何复现

V0.1 小回归集：

```bash
cd backend
python -m scripts.run_benchmark
```

V0.2 真实冻结集：

```bash
python -m scripts.run_github_benchmark --scope repo
python -m scripts.run_github_benchmark --scope global
```

下一轮 neural embedding、cross-encoder、100–300 条多仓库数据等实验统一记录在 [`NEXT_EXPERIMENTS.md`](NEXT_EXPERIMENTS.md)。

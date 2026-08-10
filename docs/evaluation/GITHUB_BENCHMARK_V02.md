# V0.2：真实 GitHub Issue → merged PR Benchmark

V0.1 的 8 条 demo 数据主要用来做检索回归，数据是人工构造的，适合 CI，但不能拿来证明 RepoTrace 在真实仓库里也有效。

V0.2 换成真实 GitHub 修复关系。

## Golden Dataset

当前冻结集：`backend/benchmarks/github_issue_pr_v1.jsonl`

共 34 条真实 `Issue → merged PR`：

- `langchain-ai/langchain`：8 条
- `pydantic/pydantic`：26 条

每条关系都满足两个条件：

1. PR 已经 merged；
2. PR 正文明确出现 `Fixes / Closes / Resolves` 指向对应 Issue。

不会根据标题相似度猜关联，也不会把普通 related issue 当成答案。

冻结集只保存 GitHub 上的原始 Issue 标题、PR 标题、URL、编号和 closure evidence。V0.2 的主结果使用 `Issue title → PR title`，没有加入人工改写的描述文本。这样做出来的分数不依赖我们自己写的“摘要”，也不会把答案关系偷偷塞进候选文本。

例如：

```text
langchain-ai/langchain
Issue #38713
`convert_runnable_to_tool` wraps TypedDict input in `RootModel` causing OpenAI tool calls to fail

PR #39307
fix(core): preserve flat tool args schema for `RootModel` runnables

Relation
Closes #38713
```

关系证据只用于确定 Ground Truth，不进入检索文本。

## 评估方式

一个 Issue 对应一个正确 merged PR，因此这里的 `Recall@K` 可以直接理解成：正确 PR 有没有出现在前 K 个结果里。

主要看：

- `Recall@1 / @3 / @5`
- `MRR`：正确 PR 越靠前越好
- `nDCG@5`：同样奖励靠前的正确结果
- `mean_rank`：正确 PR 的平均名次；没有召回时按候选数 + 1 计入

主结果使用 `repo` scope：每个 Issue 只在它所属仓库的 PR 池里检索。这和 RepoTrace 实际工作方式一致。

另外保留 `global` scope，把两个仓库的 34 个 PR 混在一起，作为额外压力测试。

## 实验结果

### Repo scope：真实产品场景

| 方法 | Recall@1 | Recall@3 | Recall@5 | MRR | nDCG@5 | Mean Rank |
|---|---:|---:|---:|---:|---:|---:|
| BM25 | 0.5588 | 0.6765 | 0.6765 | 0.6099 | 0.6215 | 8.0000 |
| BM25 + char TF-IDF RRF | 0.6176 | 0.7353 | **0.7941** | 0.7098 | 0.7134 | 3.1176 |
| Dense LSA baseline | 0.6176 | 0.6765 | 0.7353 | 0.6776 | 0.6750 | 5.1176 |
| BM25 + Dense LSA RRF | 0.5882 | 0.7059 | 0.7353 | 0.6654 | 0.6674 | 5.2059 |
| Hybrid + Evidence Reranker | **0.6471** | **0.7353** | **0.7941** | **0.7246** | **0.7242** | **3.0882** |

几个结论比较清楚。

BM25 在真实标题上没有 demo 集那么好。Recall@5 只有 67.65%，说明词面匹配一旦对不上，正确 PR 直接进不了候选区。

字符 TF-IDF 与 BM25 做 RRF 后，Recall@5 提升到 79.41%，MRR 从 0.6099 提升到 0.7098。这个提升来自真实数据，所以 V1 保留字符向量通道是合理的。

Dense LSA 单独使用时 Recall@1 与 Hybrid 一样，但 Recall@5 和 MRR 都低于字符 Hybrid。直接把 BM25 与 LSA 做 RRF 也没有继续提升。这说明“再加一个 dense channel”本身不会自动变好，融合方式和表示模型都要单独验证。

Reranker 优化后，Recall@1 从 Hybrid 的 61.76% 提升到 64.71%，MRR 从 0.7098 提升到 0.7246，同时没有损失 Recall@5。

### Global scope：混合仓库压力测试

| 方法 | Recall@1 | Recall@3 | Recall@5 | MRR | nDCG@5 | Mean Rank |
|---|---:|---:|---:|---:|---:|---:|
| BM25 | 0.5000 | 0.6471 | 0.6765 | 0.5766 | 0.5965 | 10.7647 |
| BM25 + char TF-IDF RRF | 0.5882 | 0.6765 | **0.7647** | 0.6760 | 0.6819 | 3.9412 |
| Dense LSA baseline | 0.5588 | 0.6471 | 0.7059 | 0.6305 | 0.6334 | 6.8824 |
| BM25 + Dense LSA RRF | 0.5588 | 0.6471 | 0.7059 | 0.6236 | 0.6308 | 7.4412 |
| Hybrid + Evidence Reranker | **0.6176** | **0.7059** | **0.7647** | **0.6932** | **0.6948** | **3.8824** |

混合仓库后整体下降是正常现象：候选更多，而且不同项目会重复出现 `schema`、`model`、`generic`、`tool`、`validation` 这类高频词。

Reranker 在压力池中仍然保持正收益，说明这次改动没有只记住单个仓库的排序。

## Reranker 这轮改了什么

旧版主要依赖：

- merged PR 类型加分；
- 查询里出现“怎么修 / fix”时提高 PR 权重；
- 错误码、函数名、配置项精确命中。

真实 benchmark 暴露了一个问题：当候选池本身全是 merged PR 时，前两类信号对所有候选都一样，几乎没有排序能力。

新版保留修复意图和文档类型信号，但先对当前候选集里的 Hybrid、BM25、字符向量分数分别归一化，再加入：

- PR 标题与查询标题的 token overlap；
- 全文 token overlap；
- 函数名、错误名、配置项等精确标识符命中。

检索分数仍占主要权重，额外规则只负责把非常接近的候选拉开。

这套改动在原来的 8 条 demo 回归集上仍保持：

```text
Hit Rate@5 = 1.0000
MRR        = 1.0000
```

也就是说，新排序没有为了真实 benchmark 把旧回归样例改坏。

## 目前最难的样例

失败样例集中在几类很相似的问题中：

- LangChain middleware / structured output / tool selection 之间的相邻修复；
- Pydantic generic、RootModel、Mypy 相关修复；
- experimental pipeline 的多个 constraint 修复；
- PR 标题比 Issue 更抽象，例如 Issue 描述具体异常，而 PR 标题写成更底层的内部修复。

这些 case 很适合继续验证真正的 neural embedding 和 cross-encoder，因为它们已经超出简单词面重合能稳定解决的范围。

## LSA 的命名

仓库里把这一组明确写成 `Dense LSA baseline`。

实现是：

```text
word TF-IDF
    ↓
TruncatedSVD
    ↓
L2 normalize
    ↓
cosine / dot-product ranking
```

它会得到 dense vector，但它不是神经网络训练出来的 sentence embedding，所以结果表不会把它写成 neural embedding。

## 如何复现

主 benchmark：

```bash
cd backend
python -m scripts.run_github_benchmark --scope repo
```

压力测试：

```bash
python -m scripts.run_github_benchmark --scope global
```

重新从 GitHub 构造数据：

```bash
python -m scripts.build_github_benchmark \
  --repo langchain-ai/langchain \
  --repo pydantic/pydantic \
  --limit-per-repo 50 \
  --output benchmarks/github_issue_pr_regenerated.jsonl
```

构造脚本会重新验证 PR 的 merged 状态、解析 closure relation、跳过 bot / dependency PR，并把 relation 语句从 PR 检索正文中清掉。

CI 使用冻结 snapshot，因此不会因为 GitHub 网络、仓库新提交或搜索排序变化导致回归指标漂移。

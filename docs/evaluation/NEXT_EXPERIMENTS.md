# RepoTrace 下一轮实验清单

这份文档只记录后续要执行的实验。每项实验都需要保留配置、数据版本和实际指标，结果出来后再决定是否进入主检索链路。

## 1. Neural Sentence Embedding Benchmark

### 目标

测真正的神经语义向量在 `Issue → merged PR` 检索上的收益，重点看词面差异大、语义接近的 case。

### 方法

在同一份 Golden Dataset 上增加 neural embedding 通道，模型通过配置项注入，至少比较：

- 一个轻量英文 sentence embedding；
- 一个 multilingual embedding；
- 一个偏 retrieval 的 embedding。

统一使用同一套候选池和 Query，不改变 Ground Truth。

需要分别测：

```text
Embedding only
BM25 + Embedding RRF
BM25 + char TF-IDF + Embedding RRF
Hybrid + Embedding + Evidence Reranker
```

### 指标

- Recall@1 / @3 / @5 / @10
- MRR
- nDCG@5 / @10
- 单 Query embedding 延迟
- 索引构建时间
- 索引内存 / 磁盘体积

### 完成标准

至少一个 neural embedding 方案在 repo scope 上稳定超过当前 Hybrid 的 MRR，并通过重复运行确认结果一致，再考虑进入默认链路。

## 2. Cross-Encoder Reranker

### 目标

验证“正确 PR 已经召回，但排序靠后”的 case 能否通过 pairwise rerank 提升。

### 方法

固定第一阶段召回 Top 20，分别用：

```text
Hybrid Top20
Hybrid + 当前 Evidence Reranker
Hybrid + Cross Encoder
Hybrid + Evidence Reranker + Cross Encoder
```

Cross Encoder 输入统一为：

```text
query = Issue title/body
candidate = PR title/body
```

### 指标

- MRR
- Recall@1 / @3 / @5
- nDCG@5
- P50 / P95 rerank 延迟
- 每次 rerank 的候选数量与总推理耗时

### 完成标准

MRR 和 Recall@1 有稳定增益，并且延迟能控制在 RepoTrace 调查链路可接受范围内。

## 3. Body-aware Benchmark

### 目标

比较只使用标题与使用真实 Issue/PR 正文时，检索表现有什么变化。

### 方法

用 `build_github_benchmark.py` 重新生成带清洗正文的冻结集，建立两套完全相同的关系：

```text
A: Issue title -> PR title
B: Issue title + body -> PR title + body
```

正文只做机械清洗：GitHub template、HTML comment、图片、system info、closure relation。禁止人工改写正文。

### 指标

对 BM25、Hybrid、Dense LSA、Neural Embedding、Reranker 全部重新计算 Recall、MRR、nDCG。

### 完成标准

确认正文带来的收益和噪声，并确定 RepoTrace 索引 PR / Issue 时默认保留哪些字段。

## 4. 100–300 条多仓库 Golden Dataset

### 目标

把当前几十条数据扩展到能观察跨项目泛化的规模。

### 方法

增加 5–10 个维护活跃、Issue/PR 关系清晰的开源项目，统一使用：

```text
merged PR
+ explicit Fixes / Closes / Resolves
+ non-bot
+ non-dependency-only change
```

按仓库、语言、问题类型统计分布，避免某一个仓库占绝大多数样本。

### 指标

除了整体指标，还要输出 per-repo 指标和 macro average，防止大仓库掩盖小仓库退化。

### 完成标准

至少 100 条高置信关系，并且任意单仓库不超过总数据的 40%。

## 5. Hard Negative Benchmark

### 目标

专门测“几个 PR 都很像，但只有一个真的修这个 Issue”的排序能力。

### 方法

为每条 Query 加入相似 hard negatives：

- 同模块相邻 bugfix PR；
- 标题共享同一函数名 / 类名的 PR；
- 同一个错误类型的其他修复；
- 同一时间窗口内的相关 PR。

Ground Truth 仍只来自 explicit closure relation。

### 指标

重点看 Recall@1、MRR、pairwise accuracy。

### 完成标准

在 hard-negative 子集上建立独立基线，并验证 reranker 的收益明显高于简单 Hybrid。

## 6. Temporal Split

### 目标

确认调出来的权重对未来修复记录仍然有效。

### 方法

按 merged 时间切分：

```text
较早数据 -> 调参 / 开发
较新数据 -> 最终测试
```

测试集不参与权重选择。

### 指标

比较开发集与时间外测试集的 Recall@K、MRR、nDCG 差距。

### 完成标准

新数据上没有明显崩塌，Reranker 相对 Hybrid 的收益仍为正。

## 7. 中英跨语言 Query

### 目标

模拟中文开发者描述英文 GitHub bug 的实际使用方式。

### 方法

从 Golden Dataset 抽取 Issue，构造只保留原意的中文症状 Query，并与英文原 Query 分开统计。

比较：

```text
BM25 + 手工 debug glossary
Multilingual embedding
LLM query rewrite + BM25
LLM query rewrite + Hybrid
Multilingual embedding + Reranker
```

### 指标

- 中文 Recall@K / MRR
- 相对英文原 Query 的性能下降
- Query rewrite 延迟与调用成本

### 完成标准

找到一条对中文 Query 有明显提升，同时不破坏英文检索的默认路径。

## 8. Query Rewrite 消融

### 目标

确认 LLM query rewrite 到底解决哪些 case，避免把一次额外模型调用当成默认动作。

### 方法

同一 Query 生成：

```text
raw query
keyword extraction
bug symptom rewrite
likely code identifiers
```

分别送入同一个 retriever，单独记录收益和失败样例。

### 指标

Recall@K、MRR、额外 token、额外延迟、改写失败率。

### 完成标准

只有在明确的 query 类型上有稳定收益时，才做条件触发；不做无条件 rewrite。

## 9. Bootstrap Confidence Interval

### 目标

让“提升 2–3 个百分点”有统计意义，不被少数样例偶然翻转。

### 方法

对 case 做 bootstrap resampling，至少 1000 次，计算各方案 MRR、Recall@1 的 95% confidence interval，同时计算方案差值的区间。

### 完成标准

报告中同时出现 point estimate 和 confidence interval；小改动只有在差值足够稳定时才进入默认配置。

## 10. Retrieval Latency / Memory Profile

### 目标

把准确率收益和真实运行成本一起看。

### 方法

数据规模按 100、1k、10k、50k candidate 分档，分别测：

- index build time
- cold query latency
- warm P50 / P95 latency
- resident memory
- serialized index size

对 BM25、char TF-IDF、LSA、neural embedding、cross-encoder 分开记录。

### 完成标准

形成一张 accuracy / latency / memory 对照表，RepoTrace 默认方案由这张表决定，而不是只看单一准确率。

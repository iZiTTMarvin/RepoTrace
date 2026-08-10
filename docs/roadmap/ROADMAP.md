# Roadmap

这份路线图按“先证明价值，再增加系统复杂度”排序。

## V0.1 — 当前版本

目标：跑通一次完整历史故障调查。

已完成：

- GitHub Issue / PR / Commit / docs 导入；
- SQLite 本地持久化；
- BM25；
- char TF-IDF vector；
- Query Expansion；
- RRF；
- Evidence Rerank；
- LangGraph 调查流程；
- OpenAI-compatible LLM；
- LLM fallback；
- 本地 Trace；
- 可选 Langfuse；
- React 中文 UI；
- 检索回归集和 CI。

## V0.2 — 真实数据评估

这是下一阶段最高优先级。

准备从真实 GitHub 仓库构造：

```text
Issue -> merged PR
```

Golden pair，并增加：

- Recall@1 / 5 / 10；
- MRR；
- nDCG；
- query type 分组；
- failure viewer。

只有这一步完成后，才有资格判断当前 char vector 是否应该替换。

## V0.3 — 多语语义检索

候选：

- multilingual-e5-small；
- BGE-M3；
- 其他可本地部署的多语 embedding。

实验必须和 V0.2 数据集绑定，比较准确率、索引成本和延迟。

## V0.4 — 二阶段证据拉取

当前初次导入不抓所有评论和 PR diff。

计划变成：

```text
粗检索找到 Top Issue / PR
        ↓
按需拉 comments / changed files / review discussion
        ↓
建立更完整 evidence bundle
```

这样 API 调用量和上下文大小都更可控。

## V0.5 — 条件式 Agent 调查

LangGraph 增加条件边：

- 低召回置信度 → Query Rewrite；
- 找到 Issue 但没有修复证据 → 搜索关联 PR；
- 找到 PR → 拉 changed files；
- 证据冲突 → verifier 标记 uncertain。

这一阶段才开始真正出现“Agent 根据中间结果决定下一步”的行为。

## V0.6 — Code Graph / Change Impact

把 RepoTrace 从“历史故障调查”扩到：

```text
历史发生过什么
+
当前代码可能受哪里影响
```

候选能力：

- symbol / import graph；
- changed file impact；
- Git blame；
- call relationship；
- PR diff evidence。

这部分复杂度高，所以不放在 V1。

## V1.0 的完成标准

我希望正式 1.0 至少满足：

- 一个公开、可复现的真实 GitHub benchmark；
- 对 3 个以上不同技术栈仓库测试；
- 检索和回答失败可以在 Trace 中定位；
- 用户能从 Issue 问题一路追到 merged PR / changed files；
- 有真实人工对照的调查耗时数据；
- 关键路径有稳定自动测试。

到那时再讨论跨仓库、多人协作或自动修复，会更踏实。

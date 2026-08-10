# 检索评估与第一轮优化记录

这是 RepoTrace V1 最重要的一份文档。

如果一个 RAG / Agent 项目只展示最终页面，却没有回答“检索为什么这样设计、加了以后到底有没有变好”，我自己也很难相信这个系统真的被调过。

所以第一版从一个很小但完全可重复的 benchmark 开始。

## 数据集

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

这里必须强调：**它是人工整理的回归集，不是公开真实仓库 benchmark。**

它现在的作用是：

1. 每次改检索逻辑后能快速发现退化；
2. 用消融方式验证一个改动有没有帮助；
3. CI 不依赖外部 API 和模型。

## 指标

### Hit Rate@5

正确证据是否至少有一条出现在 Top 5。

对于故障调查，第一步先保证“找得到”。

### MRR

第一条正确证据排得越靠前，分数越高：

```text
rank 1 -> 1.0
rank 2 -> 0.5
rank 3 -> 0.333...
```

这个指标很适合验证 rerank。

## V0：BM25 基线

最开始只有 BM25。

结果：

| Metric | Result |
|---|---:|
| Hit Rate@5 | 0.8750 |
| MRR | 0.6292 |

这个结果暴露了两个问题。

### 问题 1：中文查询对不上英文历史记录

失败 case：

```text
查询：退出登录以后还短暂显示上一个用户头像

Issue：Logout leaves cached profile
Body：User profile cache remains after sign out...
```

中文 Query 和英文 Issue 几乎没有共享 token，BM25 找不到它。

### 问题 2：找到了问题，但“修复记录”排得不够靠前

比如用户问：

```text
登录后偶发 401，最后怎么修？
```

BM25 很容易把描述现象的 Issue 放在第一位，而用户此时更想看到 merged PR。

这两个问题分别属于召回和排序，不能用同一个补丁解决。

## V0.2：Query Expansion + 双路检索 + RRF

第一步先解决召回。

我没有立刻上更大的 Embedding 模型，先做了两件便宜的改动：

### 中英调试词扩展

给少量高频调试词补充英文表达：

```text
退出登录 -> logout / sign out
头像     -> avatar / profile
缓存     -> cache / stale
并发     -> concurrent / race
路径     -> path / separator
卡住     -> stuck / buffering
```

这不是完整翻译系统，只负责明显的调试词差异。

### 第二路字符向量

使用 char 3~5 gram TF-IDF 做第二路检索，然后与 BM25 通过 RRF 融合。

结果：

| Metric | BM25 | Hybrid |
|---|---:|---:|
| Hit Rate@5 | 0.8750 | **1.0000** |
| MRR | 0.6292 | **0.7604** |

Hit Rate@5 从 87.5% 到 100%，说明之前漏掉的 case 被召回了。

但 MRR 只有 0.7604，说明正确证据虽然进了 Top 5，第一位还不够稳定。

所以接下来该优化排序，而不是继续堆召回策略。

## V0.3：Evidence Reranker

Reranker 使用几个和 GitHub 故障调查直接相关的信号：

- 函数名、错误码、配置项精确命中；
- `#123` 这类明确编号；
- merged PR；
- 查询出现“怎么修 / 如何解决 / fix / resolve”时，提高 merged PR 的权重。

结果：

| Metric | BM25 | Hybrid | Hybrid + Rerank |
|---|---:|---:|---:|
| Hit Rate@5 | 0.8750 | 1.0000 | **1.0000** |
| MRR | 0.6292 | 0.7604 | **1.0000** |

这个小数据集上 MRR 到 1.0，意味着 8 个 case 的第一条正确证据都排在了首位。

这不是“系统已经 100% 准确”。8 个样例太小，而且数据是我们自己整理的。它只能证明当前几条检索规则确实解决了这 8 个已知问题，并且 CI 能防止以后把它们改坏。

## 当前实际 Trace

在本地、15 条 demo 文档、LLM 关闭的情况下，一次 `401 + refresh token` 调查记录为：

| Step | Duration |
|---|---:|
| hybrid_retrieval | 5.04 ms |
| evidence_rerank | 0.22 ms |
| answer_synthesis (fallback) | 0.02 ms |
| evidence_check | 0.04 ms |

这组数据只说明本地小索引的执行量级。真实 GitHub 仓库会随着文档数量、LLM 调用和网络请求增加而变化。

## 为什么这次没有继续加 Cross Encoder

因为目前 benchmark 给出的信号很明确：规则重排已经把已知样例排对了。

此时再上 Cross Encoder，指标没有空间证明它的价值，只会增加：

- 模型下载；
- 推理延迟；
- 内存占用；
- CI 复杂度。

合理的顺序应该是先做真实 benchmark。如果真实数据出现：

```text
正确 PR 已经在 Top 20
但总是排不到 Top 5
```

那时 Cross Encoder 才有非常明确的任务。

## 下一阶段：真实 GitHub Benchmark

真正能写进项目结果里的数据，应该来自真实开源仓库。

准备按下面方式构造：

1. 找有清晰 `Fixes #123 / Closes #123` 关系的 merged PR；
2. 把 Issue 标题 + Body 作为 Query 来源；
3. 把对应 PR 作为 Ground Truth；
4. 隐藏 PR 信息后跑检索；
5. 统计 Recall@K、MRR、nDCG；
6. 人工抽样检查根因回答是否被证据支持。

为了避免 benchmark 被“记住”，查询还需要做 paraphrase，并分出：

- exact error / identifier query；
- natural-language symptom query；
- Chinese query against English repo；
- repair-intent query。

到这一步，才能真正比较：

```text
BM25
Hybrid char vector
Multilingual embedding
Cross-encoder rerank
LLM query rewrite
```

## 如何复现当前结果

```bash
cd backend
python -m scripts.run_benchmark
```

输出由代码实时计算，README 里的数字不应该手动“维护成更好看”。修改检索后，先跑 benchmark，再决定文档里的结论要不要变。

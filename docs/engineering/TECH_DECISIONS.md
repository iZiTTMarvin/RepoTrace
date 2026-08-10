# 技术选择与取舍

这份文档记录第一版为什么选这些技术。以后替换技术时，也应该把原因补回来，不要只改 `pyproject.toml`。

## 后端：FastAPI

选择原因很直接：

- Pydantic 模型和 API Schema 配合顺手；
- 异步 / 流式接口后面容易扩；
- Python 的检索、评估、Agent 生态最完整；
- Swagger 对调接口很方便。

V1 还没有做 SSE。调查任务目前同步执行，等 GitHub 二次拉取、LLM 多轮工具调用变多后，再把执行方式改成后台 Run + SSE 状态推送。

## Agent 编排：LangGraph

RepoTrace 当前流程有明确步骤和共享状态：

```text
question
  ↓
hits
  ↓
reranked hits
  ↓
answer
  ↓
confidence
```

这正适合 `StateGraph`。

我没有直接用 LangChain `create_agent`，因为这里不需要让模型自由决定每一步；检索、重排和证据检查应该是确定性流程。

我也没有使用 DeepAgents。它提供的 Todo、虚拟文件系统、子 Agent、上下文压缩，在 V1 里没有对应需求。等未来加入代码阅读和多工具调查时再评估。

## 存储：SQLite

第一版的数据量目标是单仓库几百到几千条证据。SQLite 足够，而且有两个很实际的好处：

- `git clone` 后不需要再起数据库容器；
- 测试可以用临时文件，完全隔离。

如果以后要同时维护很多大仓库、做增量同步和并发任务，再考虑 PostgreSQL。

## Retrieval：自己维护一层薄实现

没有直接把整个检索交给 LangChain Retriever。

原因是 RepoTrace 很需要看清楚每个分数是怎么来的。当前实现自己维护：

- BM25；
- char TF-IDF vector；
- RRF；
- domain rerank。

代码量不大，评估时却能单独切换 `bm25 / hybrid / hybrid_rerank`，方便做消融实验。

## 为什么暂时没有向量数据库

V1 的 vector channel 用 scikit-learn 在当前仓库文档上建索引。

这不是最终形态，但现在加 Qdrant / Milvus 的收益有限：数据规模小，真正需要验证的是召回策略和故障场景。

后续切语义 Embedding 时，如果索引量明显上升，再把 VectorStore 抽象接到 Qdrant 或 pgvector。

## 为什么第二路先用 char TF-IDF

理想状态下，中文问题和英文 Issue 应该使用多语 Embedding。但第一版先用了 char n-gram：

- 没有模型下载；
- CI 可重复；
- 标识符、路径、错误码表现稳定；
- 可以先验证 RRF 和评估基础设施。

它的弱点也明显：真正的跨语言语义能力有限，所以目前还有一个很小的中英调试词表。

下一阶段真正值得做的实验是：

```text
char TF-IDF
vs
multilingual-e5-small / bge-m3
```

然后看真实仓库 Recall@K 和延迟，再决定是否替换默认方案。

## Reranker：规则先行

没有第一版就上 Cross Encoder。

故障调查里有一些很便宜又很强的信号：

- `401`、`refreshAccessToken` 精确命中；
- `#184` 明确编号；
- merged PR；
- “怎么修”表示用户更想看最终落地方案。

先把这些信号利用起来，收益可以直接从 MRR 里看到。

如果真实 benchmark 发现 Top 20 候选里经常有正确答案，但规则无法把它排上去，再上 Cross Encoder 会更有理由。

## LLM：OpenAI-compatible HTTP

这里没有依赖某一家官方 SDK。`httpx` 直接调用 `chat/completions`，配置：

```text
base_url
api_key
model
reasoning_effort(optional)
```

这样 OpenCode Go、兼容 OpenAI API 的自建网关或其他服务都可以接。

同时保留 extractive fallback。LLM 是回答增强，不是检索系统的单点故障。

## Observability：本地 Trace + 可选 Langfuse

只接 Langfuse 会让本地开发依赖第三方服务；只做本地日志又不够直观。

所以两层都留：

- 本地 Trace：永远存在，直接给 UI；
- Langfuse：有配置时导出，用于更完整的 Agent / LLM 观测。

这也避免“观测平台宕机导致业务接口不可用”这种反向依赖。

## 前端：React + TypeScript + Vite

V1 页面状态并不复杂，没有引入 Zustand。

组件内状态已经够用：

```text
repositories
selected repository
question
investigation result
evaluation summary
```

等后面有多会话、长任务流和实时 Trace，再引入全局 store。

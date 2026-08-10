# RepoTrace 文档

这里记录 RepoTrace 的产品判断、系统设计、检索实验和开发过程。README 负责告诉使用者“怎么跑”，`docs/` 更关心“为什么这么做”和“当前实现还有哪些不确定”。

## 设计

- [`design/PRODUCT.md`](design/PRODUCT.md)：项目解决什么问题，哪些事暂时不做
- [`design/SYSTEM_DESIGN.md`](design/SYSTEM_DESIGN.md)：数据流、模块边界、Agent 工作流
- [`design/UI_DESIGN.md`](design/UI_DESIGN.md)：页面为什么这样排，界面如何表达“证据优先”

## 工程

- [`engineering/TECH_DECISIONS.md`](engineering/TECH_DECISIONS.md)：技术栈选择和取舍

## 评估

- [`evaluation/EVALUATION.md`](evaluation/EVALUATION.md)：从 BM25 基线到 Hybrid + Rerank 的真实回归过程

## 上手与阅读

- [`guide/UNDERSTANDING_REPOTRACE.md`](guide/UNDERSTANDING_REPOTRACE.md)：按调用链读代码，适合第一次接触项目时使用

## 路线

- [`roadmap/ROADMAP.md`](roadmap/ROADMAP.md)：V1 之后准备做什么，以及为什么没有现在就做

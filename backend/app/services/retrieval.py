from __future__ import annotations

import math
import re
from collections import Counter

from sklearn.feature_extraction.text import TfidfVectorizer

from app.models.domain import EvidenceDocument, SearchHit


TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_./:-]*|\d{3,}|[\u4e00-\u9fff]+")
CODE_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_./:-]{2,}|\b\d{3,}\b")

DEBUG_GLOSSARY = {
    "退出登录": "logout sign out",
    "登录": "login auth authentication",
    "用户头像": "user avatar profile",
    "头像": "avatar profile",
    "缓存": "cache cached stale",
    "并发": "concurrent race",
    "路径": "path separator",
    "分隔符": "separator slash backslash",
    "卡住": "freeze stuck buffered buffering",
    "一次性返回": "buffered buffering flush",
    "大请求": "large payload body size",
    "请求失败": "request failed error",
    "错误": "error failure",
}


def expand_debug_query(query: str) -> str:
    extras = [english for chinese, english in DEBUG_GLOSSARY.items() if chinese in query]
    if not extras:
        return query
    return f"{query} {' '.join(extras)}"


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text)]


class BM25Index:
    def __init__(self, documents: list[EvidenceDocument], k1: float = 1.5, b: float = 0.75):
        self.documents = documents
        self.k1 = k1
        self.b = b
        self.tokens = [tokenize(doc.searchable_text) for doc in documents]
        self.lengths = [len(tokens) for tokens in self.tokens]
        self.avg_len = sum(self.lengths) / max(len(self.lengths), 1)
        self.term_freqs = [Counter(tokens) for tokens in self.tokens]
        document_frequency: Counter[str] = Counter()
        for tokens in self.tokens:
            document_frequency.update(set(tokens))
        n = max(len(documents), 1)
        self.idf = {
            term: math.log(1 + (n - freq + 0.5) / (freq + 0.5))
            for term, freq in document_frequency.items()
        }

    def score(self, query: str) -> list[float]:
        query_terms = tokenize(query)
        scores = []
        for tf, doc_len in zip(self.term_freqs, self.lengths, strict=True):
            score = 0.0
            for term in query_terms:
                frequency = tf.get(term, 0)
                if not frequency:
                    continue
                denominator = frequency + self.k1 * (
                    1 - self.b + self.b * doc_len / max(self.avg_len, 1)
                )
                score += self.idf.get(term, 0.0) * frequency * (self.k1 + 1) / denominator
            scores.append(score)
        return scores


class TfidfVectorIndex:
    """Small, dependency-light vector channel used by V1.

    It is deliberately local and reproducible. The interface is isolated so a sentence
    embedding backend can replace it later without touching fusion or evaluation code.
    """

    def __init__(self, documents: list[EvidenceDocument]):
        self.documents = documents
        self.vectorizer = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(3, 5),
            min_df=1,
            sublinear_tf=True,
            max_features=30_000,
        )
        corpus = [doc.searchable_text for doc in documents]
        self.matrix = self.vectorizer.fit_transform(corpus) if corpus else None

    def score(self, query: str) -> list[float]:
        if self.matrix is None:
            return []
        query_vector = self.vectorizer.transform([query])
        scores = (self.matrix @ query_vector.T).toarray().ravel()
        return scores.astype(float).tolist()


class HybridRetriever:
    def __init__(self, documents: list[EvidenceDocument]):
        self.documents = documents
        self.bm25 = BM25Index(documents)
        self.vector = TfidfVectorIndex(documents)

    def search(self, query: str, top_k: int = 12, variant: str = "hybrid") -> list[SearchHit]:
        retrieval_query = query if variant == "bm25" else expand_debug_query(query)
        bm25_scores = self.bm25.score(retrieval_query)
        vector_scores = self.vector.score(retrieval_query)

        if variant == "bm25":
            order = sorted(range(len(self.documents)), key=lambda i: bm25_scores[i], reverse=True)
            return [
                SearchHit(
                    document=self.documents[i],
                    score=bm25_scores[i],
                    bm25_score=bm25_scores[i],
                )
                for i in order[:top_k]
                if bm25_scores[i] > 0
            ]

        fused = reciprocal_rank_fusion(bm25_scores, vector_scores)
        order = sorted(range(len(self.documents)), key=lambda i: fused[i], reverse=True)
        return [
            SearchHit(
                document=self.documents[i],
                score=fused[i],
                bm25_score=bm25_scores[i],
                vector_score=vector_scores[i],
            )
            for i in order[:top_k]
            if fused[i] > 0
        ]


def reciprocal_rank_fusion(*channels: list[float], k: int = 60) -> list[float]:
    if not channels:
        return []
    size = len(channels[0])
    fused = [0.0] * size
    for scores in channels:
        ranked = sorted(range(size), key=lambda i: scores[i], reverse=True)
        for rank, index in enumerate(ranked, start=1):
            if scores[index] <= 0:
                continue
            fused[index] += 1 / (k + rank)
    return fused


class EvidenceReranker:
    KIND_PRIOR = {
        "issue": 0.06,
        "pull_request": 0.05,
        "commit": 0.03,
        "doc": 0.01,
    }

    def rerank(self, query: str, hits: list[SearchHit], top_k: int = 6) -> list[SearchHit]:
        expanded_query = expand_debug_query(query)
        exact_tokens = {token.lower() for token in CODE_TOKEN_RE.findall(expanded_query)}
        issue_refs = set(re.findall(r"#(\d+)", query))
        repair_intent = bool(re.search(r"怎么修|如何修|修复|解决|处理|fix|resolve|patch", query, re.I))

        for hit in hits:
            searchable = hit.document.searchable_text.lower()
            boost = self.KIND_PRIOR.get(hit.document.kind.value, 0.0)
            reasons: list[str] = []

            matched = sorted(token for token in exact_tokens if token in searchable)
            if matched:
                boost += min(0.12, 0.025 * len(matched))
                reasons.append("精确命中: " + ", ".join(matched[:4]))

            if hit.document.number is not None and str(hit.document.number) in issue_refs:
                boost += 0.2
                reasons.append("命中明确编号")

            if hit.document.kind.value == "pull_request" and hit.document.metadata.get("merged_at"):
                boost += 0.02
                reasons.append("已合并修复候选")
                if repair_intent:
                    boost += 0.12
                    reasons.append("查询包含修复意图")

            normalized_source = min(1.0, hit.score * 25)
            hit.rerank_score = normalized_source + boost
            hit.score = hit.rerank_score
            hit.reasons.extend(reasons)

        return sorted(hits, key=lambda item: item.score, reverse=True)[:top_k]

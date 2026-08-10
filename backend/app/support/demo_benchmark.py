from __future__ import annotations

from app.models.domain import DocumentType, EvidenceDocument
from app.services.evaluation import EvalCase, evaluate_retrieval


def demo_documents() -> list[EvidenceDocument]:
    repo = "demo/checkout"
    rows = [
        ("issue:1", DocumentType.ISSUE, "Intermittent 401 after token refresh", "Concurrent API calls can reuse the old access token while refresh is still in flight. Login succeeds but the next request sometimes returns 401 unauthorized.", 184),
        ("pr:2", DocumentType.PULL_REQUEST, "Serialize refresh token requests", "Fixes #184 by adding a single-flight lock around refreshAccessToken and retrying waiting requests with the new token.", 201),
        ("commit:3", DocumentType.COMMIT, "fix auth retry race", "Guard refreshAccessToken with a shared promise and clear it after completion.", None),
        ("issue:4", DocumentType.ISSUE, "Logout leaves cached profile", "User profile cache remains after sign out and briefly shows the previous avatar.", 77),
        ("pr:5", DocumentType.PULL_REQUEST, "Clear profile cache on logout", "Invalidate user profile query when the session is cleared.", 81),
        ("issue:6", DocumentType.ISSUE, "502 when webhook body is large", "Reverse proxy returns 502 bad gateway for webhook payloads larger than 1 MB. The app server is healthy.", 302),
        ("pr:7", DocumentType.PULL_REQUEST, "Raise webhook proxy body limit", "Increase client_max_body_size for /webhooks and document the deployment setting. Fixes #302.", 309),
        ("issue:8", DocumentType.ISSUE, "Windows path breaks repository scan", "Backslash paths are compared with slash-normalized ignore patterns, so node_modules is accidentally scanned on Windows.", 411),
        ("pr:9", DocumentType.PULL_REQUEST, "Normalize paths before ignore matching", "Convert Windows separators before glob matching and add regression coverage. Resolves #411.", 419),
        ("issue:10", DocumentType.ISSUE, "SSE stream stops behind nginx", "Streaming response is buffered by nginx and appears to freeze until the request completes.", 520),
        ("pr:11", DocumentType.PULL_REQUEST, "Disable proxy buffering for SSE", "Set X-Accel-Buffering: no on the event stream response and add nginx example config. Fixes #520.", 531),
        ("doc:12", DocumentType.DOC, "docs/authentication.md", "Authentication uses rotating access tokens. refreshAccessToken is shared by concurrent requests to avoid duplicate refresh calls.", None),
        ("doc:13", DocumentType.DOC, "docs/deployment.md", "For SSE endpoints disable reverse proxy buffering. Webhook payload size is controlled at the proxy layer.", None),
        ("issue:14", DocumentType.ISSUE, "Refresh button does not update settings", "The settings screen keeps stale form values after manual refresh.", 91),
        ("commit:15", DocumentType.COMMIT, "refactor token parser", "Rename parse_token to decode_access_token without changing refresh behavior.", None),
    ]
    docs = []
    for doc_id, kind, title, body, number in rows:
        docs.append(
            EvidenceDocument(
                id=doc_id,
                repo=repo,
                kind=kind,
                title=title,
                body=body,
                url=f"https://example.invalid/{doc_id}",
                number=number,
                state="closed" if kind == DocumentType.ISSUE else None,
                metadata={"merged_at": "2026-01-01"} if kind == DocumentType.PULL_REQUEST else {},
            )
        )
    return docs


def demo_cases() -> list[EvalCase]:
    return [
        EvalCase("auth-401", "登录后偶发 401，refresh token 并发时更明显，最后怎么修？", {"pr:2"}),
        EvalCase("auth-race", "refreshAccessToken race condition old token reused", {"issue:1", "pr:2", "commit:3"}),
        EvalCase("webhook-502", "大 webhook 请求经过 nginx 出现 502，如何解决？", {"pr:7"}),
        EvalCase("windows-scan", "Windows 上 node_modules 没有被 ignore，路径分隔符可能有问题", {"issue:8", "pr:9"}),
        EvalCase("sse-buffer", "SSE 看起来卡住，nginx 直到最后才一次性返回，怎么修复？", {"pr:11"}),
        EvalCase("logout-cache", "退出登录以后还短暂显示上一个用户头像", {"issue:4", "pr:5"}),
        EvalCase("proxy-limit", "client_max_body_size 导致请求失败", {"issue:6", "pr:7", "doc:13"}),
        EvalCase("stream-header", "X-Accel-Buffering event stream", {"pr:11", "doc:13"}),
    ]


def run_demo_benchmark() -> dict:
    documents = demo_documents()
    cases = demo_cases()
    variants = []
    for variant, label in [
        ("bm25", "BM25 基线"),
        ("hybrid", "BM25 + 字符向量 RRF"),
        ("hybrid_rerank", "Hybrid + 证据重排"),
    ]:
        metrics = evaluate_retrieval(documents, cases, variant=variant, top_k=5)
        variants.append({"id": variant, "label": label, **metrics})
    best = variants[-1]
    return {
        "dataset": "demo_incidents_v1",
        "cases": len(cases),
        "metrics": {"hit_rate@5": best["hit_rate@5"], "mrr": best["mrr"]},
        "variants": variants,
        "note": "内置可重复基准，用于验证检索逻辑和回归；它不是公开真实仓库 benchmark。",
    }

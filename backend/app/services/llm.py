from __future__ import annotations

import json
from dataclasses import dataclass

import httpx

from app.core.config import Settings
from app.models.domain import SearchHit


@dataclass(slots=True)
class LLMResult:
    answer: str
    used_llm: bool
    usage: dict
    warning: str | None = None


class OpenAICompatibleLLM:
    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def available(self) -> bool:
        return bool(
            self.settings.llm_enabled
            and self.settings.llm_api_key
            and self.settings.llm_base_url
        )

    def answer(self, question: str, hits: list[SearchHit]) -> LLMResult:
        if not self.available:
            return self._extractive_fallback(question, hits)

        evidence = "\n\n".join(
            f"[E{i}] {hit.document.kind.value} {hit.document.title}\n"
            f"URL: {hit.document.url}\n"
            f"内容: {hit.document.body[:3500]}"
            for i, hit in enumerate(hits, start=1)
        )
        system = (
            "你是 RepoTrace 的故障调查助手。只能根据给出的 GitHub 证据回答。"
            "你的目标是帮助开发者判断：是否存在相似历史问题、当时的原因是什么、最后怎么处理。"
            "如果证据不足就明确说不足，不允许把猜测写成事实。引用证据时使用 [E1] 这种编号。"
            "输出中文，结构简洁，包含：调查结论、可能根因、历史处理、建议检查、证据局限。"
        )
        payload = {
            "model": self.settings.llm_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": f"问题：{question}\n\n证据：\n{evidence}"},
            ],
            "temperature": 0.1,
        }
        if self.settings.llm_reasoning_effort:
            payload["reasoning_effort"] = self.settings.llm_reasoning_effort

        url = self.settings.llm_base_url.rstrip("/") + "/chat/completions"
        headers = {"Authorization": f"Bearer {self.settings.llm_api_key}"}
        try:
            response = httpx.post(
                url,
                headers=headers,
                json=payload,
                timeout=self.settings.llm_timeout_seconds,
            )
            if response.status_code == 400 and "reasoning_effort" in payload:
                payload.pop("reasoning_effort", None)
                response = httpx.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=self.settings.llm_timeout_seconds,
                )
            response.raise_for_status()
            data = response.json()
            answer = data["choices"][0]["message"]["content"]
            return LLMResult(answer=answer, used_llm=True, usage=data.get("usage", {}))
        except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError) as exc:
            fallback = self._extractive_fallback(question, hits)
            fallback.warning = f"LLM 调用失败，已降级为证据摘要：{type(exc).__name__}"
            return fallback

    @staticmethod
    def _extractive_fallback(question: str, hits: list[SearchHit]) -> LLMResult:
        if not hits:
            return LLMResult(
                answer="当前仓库中没有检索到足够相关的历史证据。建议换一个更具体的错误信息、函数名或异常栈再试。",
                used_llm=False,
                usage={},
            )
        lines = ["当前未启用 LLM，先给出可追溯的检索结果：", ""]
        for index, hit in enumerate(hits[:4], start=1):
            excerpt = " ".join(hit.document.body.split())[:220]
            lines.append(f"[E{index}] {hit.document.title}")
            if excerpt:
                lines.append(f"{excerpt}…")
        lines.append("")
        lines.append("可以先从排名最靠前的 Issue / PR 开始核对根因和修复记录。")
        return LLMResult(answer="\n".join(lines), used_llm=False, usage={})

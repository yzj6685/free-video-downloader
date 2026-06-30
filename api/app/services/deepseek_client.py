from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
from fastapi import HTTPException

from app.config import get_settings


class DeepSeekClient:
    async def complete_json(self, messages: list[dict[str, str]], max_tokens: int = 4096) -> dict[str, Any]:
        content = await self._complete(messages, response_format={"type": "json_object"}, max_tokens=max_tokens)
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=502, detail="AI 返回格式异常，请稍后重试。") from exc
        if not isinstance(payload, dict):
            raise HTTPException(status_code=502, detail="AI 返回格式异常，请稍后重试。")
        return payload

    async def complete_text(self, messages: list[dict[str, str]], max_tokens: int = 2048) -> str:
        return await self._complete(messages, response_format={"type": "text"}, max_tokens=max_tokens)

    async def stream_text(self, messages: list[dict[str, str]], max_tokens: int = 2048) -> AsyncIterator[str]:
        settings = get_settings()
        if not settings.deepseek_api_key:
            raise HTTPException(
                status_code=503,
                detail="AI 分析需要配置 DEEPSEEK_API_KEY，请配置后重启后端。",
            )

        url = settings.deepseek_base_url.rstrip("/") + "/chat/completions"
        body: dict[str, Any] = {
            "model": settings.deepseek_model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": max_tokens,
            "response_format": {"type": "text"},
            "stream": True,
        }

        try:
            async with httpx.AsyncClient(timeout=90) as client:
                async with client.stream(
                    "POST",
                    url,
                    headers={
                        "Authorization": f"Bearer {settings.deepseek_api_key}",
                        "Content-Type": "application/json",
                        "Accept": "text/event-stream",
                    },
                    json=body,
                ) as response:
                    if response.status_code in {401, 403}:
                        raise HTTPException(status_code=503, detail="DeepSeek API Key 无效或无权限，请检查配置。")
                    if response.status_code >= 400:
                        raise HTTPException(status_code=502, detail="AI 服务返回异常，请稍后重试。")

                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line or not line.startswith("data:"):
                            continue
                        data = line.removeprefix("data:").strip()
                        if data == "[DONE]":
                            break
                        try:
                            payload = json.loads(data)
                            content = payload["choices"][0].get("delta", {}).get("content")
                        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
                            raise HTTPException(status_code=502, detail="AI 服务返回格式异常，请稍后重试。") from exc
                        if isinstance(content, str) and content:
                            yield content
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail="AI 服务暂时不可用，请稍后重试。") from exc

    async def _complete(
        self,
        messages: list[dict[str, str]],
        response_format: dict[str, str],
        max_tokens: int,
    ) -> str:
        settings = get_settings()
        if not settings.deepseek_api_key:
            raise HTTPException(
                status_code=503,
                detail="AI 分析需要配置 DEEPSEEK_API_KEY，请配置后重启后端。",
            )

        url = settings.deepseek_base_url.rstrip("/") + "/chat/completions"
        body: dict[str, Any] = {
            "model": settings.deepseek_model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": max_tokens,
            "response_format": response_format,
            "stream": False,
        }

        try:
            async with httpx.AsyncClient(timeout=90) as client:
                response = await client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {settings.deepseek_api_key}",
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    json=body,
                )
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail="AI 服务暂时不可用，请稍后重试。") from exc

        if response.status_code in {401, 403}:
            raise HTTPException(status_code=503, detail="DeepSeek API Key 无效或无权限，请检查配置。")
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail="AI 服务返回异常，请稍后重试。")

        payload = response.json()
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise HTTPException(status_code=502, detail="AI 服务返回格式异常，请稍后重试。") from exc

        if not isinstance(content, str) or not content.strip():
            raise HTTPException(status_code=502, detail="AI 服务没有返回有效内容，请稍后重试。")
        return content.strip()


deepseek_client = DeepSeekClient()

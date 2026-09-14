"""Web tools: search (Tavily/DuckDuckGo fallback), fetch page as text, HTTP request."""

from __future__ import annotations

import json
from typing import Any

import httpx
from selectolax.parser import HTMLParser

from app.core.config import settings
from app.tools.base import Permission, Tool, ToolResult, tool_schema

UA = "Mozilla/5.0 (compatible; BhatiAgent/2.0; +https://github.com/vmeducatedlucifer-commits)"


async def web_search(query: str, max_results: int = 5) -> ToolResult:
    if settings.tavily_api_key:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": settings.tavily_api_key,
                    "query": query,
                    "max_results": max_results,
                    "include_answer": True,
                },
            )
        if response.status_code < 400:
            payload = response.json()
            lines = [f"Answer: {payload.get('answer', '')}".strip()]
            for item in payload.get("results", []):
                lines.append(f"- {item.get('title')} — {item.get('url')}\n  {item.get('content', '')[:300]}")
            return ToolResult.success("\n".join(lines), provider="tavily")

    async with httpx.AsyncClient(timeout=30, headers={"User-Agent": UA}) as client:
        response = await client.get(
            "https://duckduckgo.com/html/", params={"q": query}, follow_redirects=True
        )
    tree = HTMLParser(response.text)
    results = []
    for node in tree.css("a.result__a")[:max_results]:
        results.append(f"- {node.text(strip=True)} — {node.attributes.get('href', '')}")
    return ToolResult.success("\n".join(results) or "No results", provider="duckduckgo")


async def fetch_url(url: str, max_chars: int = 8000) -> ToolResult:
    async with httpx.AsyncClient(timeout=45, headers={"User-Agent": UA}, follow_redirects=True) as client:
        response = await client.get(url)
    if response.status_code >= 400:
        return ToolResult.failure(f"HTTP {response.status_code} for {url}")
    content_type = response.headers.get("content-type", "")
    if "html" in content_type:
        tree = HTMLParser(response.text)
        for tag in tree.css("script, style, nav, footer, noscript"):
            tag.decompose()
        body = tree.body
        text = body.text(separator="\n", strip=True) if body else response.text
    else:
        text = response.text
    return ToolResult.success(text[:max_chars], url=url, content_type=content_type)


async def http_request(
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: str | None = None,
    timeout: int = 45,
) -> ToolResult:
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.request(
            method.upper(), url, headers=headers or {}, content=body
        )
    preview: Any = response.text[:6000]
    try:
        preview = json.dumps(response.json(), indent=2)[:6000]
    except Exception:
        pass
    return ToolResult.success(f"HTTP {response.status_code}\n{preview}", status=response.status_code)


WEB_TOOLS = [
    Tool(
        name="web_search",
        description="Search the public web and return ranked results with snippets.",
        parameters=tool_schema(
            query={"type": "string", "required": True},
            max_results={"type": "integer", "default": 5},
        ),
        handler=web_search,
        permission=Permission.SAFE,
        tags=["web", "research"],
    ),
    Tool(
        name="fetch_url",
        description="Fetch a URL and return readable text content.",
        parameters=tool_schema(
            url={"type": "string", "required": True}, max_chars={"type": "integer", "default": 8000}
        ),
        handler=fetch_url,
        permission=Permission.SAFE,
        tags=["web", "research"],
    ),
    Tool(
        name="http_request",
        description="Make an arbitrary HTTP request (REST API calls, webhooks).",
        parameters=tool_schema(
            url={"type": "string", "required": True},
            method={"type": "string", "default": "GET"},
            headers={"type": "object", "default": {}},
            body={"type": "string"},
            timeout={"type": "integer", "default": 45},
        ),
        handler=http_request,
        permission=Permission.DANGEROUS,
        tags=["web", "ops"],
    ),
]

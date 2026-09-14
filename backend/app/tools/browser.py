"""Browser-use tools backed by Playwright (lazy import so it stays optional)."""

from __future__ import annotations

import asyncio
from typing import Any

from app.core.config import settings
from app.tools.base import Permission, Tool, ToolContext, ToolResult, tool_schema

_lock = asyncio.Lock()
_state: dict[str, Any] = {"playwright": None, "browser": None, "page": None}


async def _ensure_page(headless: bool = True):
    async with _lock:
        if _state["page"] is not None:
            return _state["page"]
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "Playwright not installed. Run: pip install playwright && playwright install chromium"
            ) from exc
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=headless)
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        _state.update({"playwright": playwright, "browser": browser, "page": page})
        return page


async def browser_navigate(url: str, headless: bool = True) -> ToolResult:
    page = await _ensure_page(headless)
    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    title = await page.title()
    return ToolResult.success(f"Opened {url}\nTitle: {title}", url=url, title=title)


async def browser_snapshot(max_chars: int = 6000) -> ToolResult:
    page = await _ensure_page()
    text = await page.inner_text("body")
    links = await page.eval_on_selector_all(
        "a[href]", "els => els.slice(0,40).map(e => e.innerText.trim() + ' -> ' + e.href)"
    )
    body = text[:max_chars] + "\n\nLINKS:\n" + "\n".join(links)
    return ToolResult.success(body, url=page.url)


async def browser_act(
    action: str, selector: str = "", text: str = "", key: str = ""
) -> ToolResult:
    page = await _ensure_page()
    if action == "click":
        await page.click(selector, timeout=20000)
    elif action == "type":
        await page.fill(selector, text)
    elif action == "press":
        await page.keyboard.press(key or "Enter")
    elif action == "scroll":
        await page.mouse.wheel(0, 800)
    elif action == "back":
        await page.go_back()
    else:
        return ToolResult.failure(f"Unknown action: {action}")
    await page.wait_for_timeout(500)
    return ToolResult.success(f"{action} done on '{selector or key}' (url: {page.url})")


async def browser_screenshot(ctx: ToolContext, path: str = "screenshot.png") -> ToolResult:
    page = await _ensure_page()
    target = ctx.resolve(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    await page.screenshot(path=str(target), full_page=True)
    return ToolResult.success(f"Screenshot saved to {path}", path=str(target))


async def browser_close() -> ToolResult:
    if _state["browser"]:
        await _state["browser"].close()
    if _state["playwright"]:
        await _state["playwright"].stop()
    _state.update({"playwright": None, "browser": None, "page": None})
    return ToolResult.success("Browser closed")


BROWSER_TOOLS = [
    Tool(
        name="browser_navigate",
        description="Open a URL in the controlled browser session.",
        parameters=tool_schema(
            url={"type": "string", "required": True},
            headless={"type": "boolean", "default": not settings.is_production},
        ),
        handler=browser_navigate,
        permission=Permission.DANGEROUS,
        tags=["browser", "computer"],
    ),
    Tool(
        name="browser_snapshot",
        description="Read the current page: visible text plus the main links.",
        parameters=tool_schema(max_chars={"type": "integer", "default": 6000}),
        handler=browser_snapshot,
        permission=Permission.SAFE,
        tags=["browser", "computer"],
    ),
    Tool(
        name="browser_act",
        description="Interact with the page: click, type, press, scroll or back.",
        parameters=tool_schema(
            action={"type": "string", "enum": ["click", "type", "press", "scroll", "back"], "required": True},
            selector={"type": "string"},
            text={"type": "string"},
            key={"type": "string"},
        ),
        handler=browser_act,
        permission=Permission.DANGEROUS,
        tags=["browser", "computer"],
    ),
    Tool(
        name="browser_screenshot",
        description="Capture a full-page screenshot into the workspace.",
        parameters=tool_schema(path={"type": "string", "default": "screenshot.png"}),
        handler=browser_screenshot,
        permission=Permission.WRITE,
        tags=["browser", "computer"],
    ),
    Tool(
        name="browser_close",
        description="Close the browser session and free resources.",
        parameters=tool_schema(),
        handler=browser_close,
        permission=Permission.SAFE,
        tags=["browser", "computer"],
    ),
]

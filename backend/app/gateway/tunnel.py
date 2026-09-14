"""Keyless Gemini web-tunnel client (ported from Bhati-Ai-Agent v1).

Real browser emulation + TLS impersonation (curl_cffi when available) with a
rotating pool of warmed sessions. Works with **zero API keys and zero cookies**.
If official `GEMINI_API_KEY`s are present they are tried first (round-robin with
cooldown), otherwise everything goes through the web tunnel.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import random
import re
import time
import urllib.parse
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

import httpx

try:  # optional: much better fingerprinting when installed
    from curl_cffi.requests import AsyncSession as CurlAsyncSession

    CURL_CFFI_AVAILABLE = True
except Exception:  # pragma: no cover - depends on wheel availability
    CurlAsyncSession = None  # type: ignore[assignment]
    CURL_CFFI_AVAILABLE = False

from app.gateway.config import settings

logger = logging.getLogger("app.gateway.tunnel")

BROWSER_PROFILES: List[Dict[str, str]] = [
    {
        "name": "chrome_windows",
        "impersonate": "chrome124",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Not(A:Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"',
        "sec_ch_ua_mobile": "?0",
        "sec_ch_ua_platform": '"Windows"',
    },
    {
        "name": "chrome_mac",
        "impersonate": "chrome124",
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Not(A:Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"',
        "sec_ch_ua_mobile": "?0",
        "sec_ch_ua_platform": '"macOS"',
    },
    {
        "name": "chrome_linux",
        "impersonate": "chrome124",
        "user_agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Not(A:Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"',
        "sec_ch_ua_mobile": "?0",
        "sec_ch_ua_platform": '"Linux"',
    },
    {
        "name": "chrome_android",
        "impersonate": "chrome124",
        "user_agent": "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Mobile Safari/537.36",
        "sec_ch_ua": '"Not(A:Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"',
        "sec_ch_ua_mobile": "?1",
        "sec_ch_ua_platform": '"Android"',
    },
]

USER_AGENTS = [p["user_agent"] for p in BROWSER_PROFILES]
DEFAULT_STREAM_URL = (
    "https://gemini.google.com/_/BardChatUi/data/"
    "assistant.lamda.BardFrontendService/StreamGenerate"
)
WARMUP_URL = "https://gemini.google.com/app"
OFFICIAL_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class RateLimitError(Exception):
    """Raised when an API key or tunnel session hits a rate limit / quota wall."""


def resolve_model(model_name: Optional[str]) -> str:
    """Normalize any model string to a Gemini model the tunnel understands."""
    if not model_name:
        return settings.default_model
    m = model_name.lower().strip()
    if m.startswith("builtin/"):
        m = m.split("/", 1)[1]
    if m.startswith("gemini-"):
        return m
    if "flash-lite" in m:
        return "gemini-2.0-flash-lite"
    if "flash" in m:
        return "gemini-2.0-flash"
    if "pro" in m:
        return "gemini-1.5-pro"
    if any(k in m for k in ("claude", "sonnet", "gpt-4", "gpt-3", "o1", "o3")):
        return "gemini-2.0-flash"
    return settings.default_model


def _reqid() -> int:
    return random.randint(100000, 999999)


@dataclass
class BrowserWarmSession:
    id: str = field(default_factory=lambda: f"sess_{uuid.uuid4().hex[:10]}")
    profile: Dict[str, str] = field(default_factory=dict)
    bl: str = ""
    f_sid: str = ""
    at: str = ""
    cookies: Dict[str, str] = field(default_factory=dict)
    custom_cookie: Optional[str] = None
    sapisid: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    last_used_at: float = field(default_factory=time.time)
    request_count: int = 0
    rate_limited_until: float = 0.0

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > settings.session_ttl

    @property
    def is_rate_limited(self) -> bool:
        return time.time() < self.rate_limited_until

    @property
    def is_exhausted(self) -> bool:
        return self.request_count >= settings.max_requests_per_session

    @property
    def is_available(self) -> bool:
        return not self.is_expired and not self.is_rate_limited and not self.is_exhausted


class ApiKeyPool:
    """Round-robin pool of official Gemini API keys with cooldown tracking."""

    def __init__(self) -> None:
        self._keys: List[str] = []
        self._cooldowns: Dict[str, float] = {}
        self._current_idx = 0
        self._lock = asyncio.Lock()
        self.reload_keys()

    def reload_keys(self) -> None:
        self._keys = settings.get_api_keys()

    async def get_key(self, explicit_key: Optional[str] = None) -> Optional[str]:
        if explicit_key and explicit_key.startswith("AIza"):
            return explicit_key
        async with self._lock:
            if not self._keys:
                self.reload_keys()
            if not self._keys:
                return None
            now = time.time()
            available = [k for k in self._keys if self._cooldowns.get(k, 0) <= now]
            if not available:
                return None
            self._current_idx = (self._current_idx + 1) % len(available)
            return available[self._current_idx]

    async def mark_rate_limited(self, key: str, cooldown_seconds: Optional[int] = None) -> None:
        async with self._lock:
            cd = cooldown_seconds or settings.session_cooldown_seconds
            self._cooldowns[key] = time.time() + cd
            logger.warning("gemini api key %s... cooling down for %ss", key[:8], cd)

    async def get_status(self) -> Dict[str, Any]:
        async with self._lock:
            now = time.time()
            return {
                "total_keys": len(self._keys),
                "active_keys": len([k for k in self._keys if self._cooldowns.get(k, 0) <= now]),
                "cooldown_keys": len([k for k in self._keys if self._cooldowns.get(k, 0) > now]),
            }


api_key_pool = ApiKeyPool()


class BrowserSessionPool:
    """Pool of pre-warmed browser sessions with rotation and quarantine."""

    def __init__(self) -> None:
        self._pool: List[BrowserWarmSession] = []
        self._current_index = 0
        self._lock = asyncio.Lock()
        self._total_requests = 0
        self._rotations_count = 0

    def _pick_profile(self) -> Dict[str, str]:
        return random.choice(BROWSER_PROFILES)

    async def _create_warm_session(self, custom_cookie: Optional[str] = None) -> BrowserWarmSession:
        profile = self._pick_profile()
        bl = settings.stream_bl or "boq_assistant-bard-web-server_20260907.07_p0"
        f_sid = ""
        at_token = settings.gemini_at or ""
        cookies: Dict[str, str] = {}
        cookie_to_use = custom_cookie or settings.gemini_cookie

        headers = {
            "User-Agent": profile["user_agent"],
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-Ch-Ua": profile["sec_ch_ua"],
            "Sec-Ch-Ua-Mobile": profile["sec_ch_ua_mobile"],
            "Sec-Ch-Ua-Platform": profile["sec_ch_ua_platform"],
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }
        if cookie_to_use:
            headers["Cookie"] = cookie_to_use

        proxy_url = settings.upstream_proxy or None
        body = ""
        try:
            if CURL_CFFI_AVAILABLE:
                impersonate = settings.browser_impersonate or profile.get("impersonate", "chrome124")
                async with CurlAsyncSession(impersonate=impersonate, proxy=proxy_url) as client:
                    resp = await client.get(WARMUP_URL, headers=headers, timeout=15)
                    if resp.status_code == 200:
                        body = resp.text
                        cookies = dict(client.cookies)
            else:
                async with httpx.AsyncClient(
                    follow_redirects=True, timeout=15.0, proxy=proxy_url
                ) as client:
                    resp = await client.get(WARMUP_URL, headers=headers)
                    if resp.status_code == 200:
                        body = resp.text
                        cookies = dict(resp.cookies)
        except Exception as exc:
            logger.warning("browser warm-up probe failed (using defaults): %s", exc)

        if body:
            m_bl = re.search(r'"cfb2h":"([^"]+)"', body)
            if m_bl:
                bl = m_bl.group(1)
            m_sid = re.search(r'"FdrFJe":"([^"]+)"', body)
            if m_sid:
                f_sid = m_sid.group(1)
            m_at = re.search(r'"SNlM0e":"([^"]+)"', body)
            if m_at:
                at_token = m_at.group(1)

        return BrowserWarmSession(
            profile=profile,
            bl=bl,
            f_sid=f_sid,
            at=at_token,
            cookies=cookies,
            custom_cookie=cookie_to_use,
        )

    def _cleanup_pool_locked(self) -> None:
        self._pool = [
            s for s in self._pool if not s.is_expired and not (s.is_exhausted and not s.is_rate_limited)
        ]

    async def get_session(
        self,
        force_refresh: bool = False,
        force_new: bool = False,
        exclude_session_id: Optional[str] = None,
    ) -> BrowserWarmSession:
        need_new = force_refresh or force_new
        async with self._lock:
            self._cleanup_pool_locked()
            available = [
                s
                for s in self._pool
                if s.is_available and (not exclude_session_id or s.id != exclude_session_id)
            ]
            if not need_new and available:
                if settings.rotate_session_every_request:
                    self._current_index = (self._current_index + 1) % len(available)
                    sess = available[self._current_index]
                    self._rotations_count += 1
                else:
                    sess = min(available, key=lambda s: (s.request_count, s.last_used_at))
                sess.last_used_at = time.time()
                self._total_requests += 1
                return sess

            cookie_pool = settings.get_cookies()
            chosen_cookie = random.choice(cookie_pool) if cookie_pool else None

        new_sess = await self._create_warm_session(custom_cookie=chosen_cookie)

        async with self._lock:
            max_cap = max(settings.session_pool_size * 2, 10)
            if len(self._pool) < max_cap:
                self._pool.append(new_sess)
            else:
                self._pool.sort(key=lambda s: s.last_used_at)
                self._pool[0] = new_sess
            new_sess.last_used_at = time.time()
            self._total_requests += 1
            self._rotations_count += 1
        return new_sess

    async def mark_rate_limited(self, session_id: str, cooldown_seconds: Optional[int] = None) -> None:
        async with self._lock:
            cd = cooldown_seconds or settings.session_cooldown_seconds
            for s in self._pool:
                if s.id == session_id:
                    s.rate_limited_until = time.time() + cd
                    break

    async def mark_exhausted(self, session_id: str) -> None:
        async with self._lock:
            for s in self._pool:
                if s.id == session_id:
                    s.request_count = settings.max_requests_per_session + 1
                    break

    async def record_success(self, session_id: str) -> None:
        async with self._lock:
            for s in self._pool:
                if s.id == session_id:
                    s.request_count += 1
                    s.last_used_at = time.time()
                    break

    def invalidate(self, session_id: Optional[str] = None) -> None:
        if session_id:
            self._pool = [s for s in self._pool if s.id != session_id]
        else:
            self._pool.clear()

    async def get_pool_status(self) -> Dict[str, Any]:
        async with self._lock:
            self._cleanup_pool_locked()
            return {
                "pool_size": len(self._pool),
                "healthy_sessions": len([s for s in self._pool if s.is_available]),
                "cooling_sessions": len([s for s in self._pool if s.is_rate_limited]),
                "target_pool_size": settings.session_pool_size,
                "rotate_every_request": settings.rotate_session_every_request,
                "total_requests": self._total_requests,
                "rotations_count": self._rotations_count,
                "curl_cffi": CURL_CFFI_AVAILABLE,
            }


BrowserSessionManager = BrowserSessionPool
session_pool = BrowserSessionPool()
session_manager = session_pool


class GeminiTunnel:
    """Web tunnel with session rotation; official keys used first when present."""

    def __init__(self) -> None:
        self._client: Optional[httpx.AsyncClient] = None
        self._build_label = settings.stream_bl or "boq_assistant-bard-web-server_20260907.07_p0"

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(settings.request_timeout, connect=15.0),
                follow_redirects=True,
                http2=False,
                proxy=settings.upstream_proxy or None,
            )
        return self._client

    async def aclose(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ------------------------------------------------------------- helpers
    def _generate_sapisid_auth(self, sapisid: Optional[str] = None) -> Tuple[str, str]:
        sid = sapisid or ""
        ts = int(time.time())
        h_data = f"{ts} {sid} https://gemini.google.com" if sid else f"{ts}  https://gemini.google.com"
        sha1 = hashlib.sha1(h_data.encode("utf-8")).hexdigest()
        return sid, f"SAPISIDHASH {ts}_{sha1}"

    def _build_payload(
        self,
        prompt: Optional[str],
        session_id: str = "",
        response_id: str = "",
        choice_id: str = "",
        thinking_mode: int = 0,
        at_token: str = "",
    ) -> str:
        """Build the 102-element nested payload the web tunnel expects."""
        lst: List[Any] = [None] * 102
        lst[0] = [prompt or "", 0, None, None, None, None, 0]
        lst[2] = [session_id or "", response_id or "", choice_id or "", None, None, []]
        lst[10] = thinking_mode
        lst[101] = [None, None, None, None, []]

        inner_json = json.dumps(lst, separators=(",", ":"))
        outer_json = json.dumps([None, inner_json], separators=(",", ":"))
        at_param = urllib.parse.quote(at_token or settings.gemini_at or "")
        return f"f.req={urllib.parse.quote(outer_json)}&at={at_param}"

    def _build_headers(
        self,
        auth_header: str,
        custom_cookie: Optional[str] = None,
        profile: Optional[Dict[str, str]] = None,
    ) -> Dict[str, str]:
        prof = profile or BROWSER_PROFILES[0]
        headers = {
            "User-Agent": prof["user_agent"],
            "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
            "Origin": "https://gemini.google.com",
            "Referer": WARMUP_URL,
            "X-Same-Domain": "1",
            "Sec-Ch-Ua": prof.get("sec_ch_ua", BROWSER_PROFILES[0]["sec_ch_ua"]),
            "Sec-Ch-Ua-Mobile": prof.get("sec_ch_ua_mobile", "?0"),
            "Sec-Ch-Ua-Platform": prof.get("sec_ch_ua_platform", '"Windows"'),
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
        }
        if auth_header and "SAPISIDHASH" in auth_header:
            headers["Authorization"] = auth_header
        cookie_str = custom_cookie or settings.gemini_cookie
        if cookie_str:
            headers["Cookie"] = cookie_str
        return headers

    def _parse_wrb_blocks(self, text: str) -> List[Any]:
        """Extract every balanced `[["wrb.fr"...]]` block from the raw body."""
        blocks: List[Any] = []
        idx = 0
        target = '[["wrb.fr"'
        while True:
            pos = text.find(target, idx)
            if pos == -1:
                break
            depth = 0
            in_string = False
            escape = False
            end_pos = -1
            for i in range(pos, len(text)):
                c = text[i]
                if escape:
                    escape = False
                    continue
                if c == "\\":
                    escape = True
                    continue
                if c == '"':
                    in_string = not in_string
                    continue
                if not in_string:
                    if c == "[":
                        depth += 1
                    elif c == "]":
                        depth -= 1
                        if depth == 0:
                            end_pos = i + 1
                            break
            if end_pos == -1:
                break
            try:
                blocks.append(json.loads(text[pos:end_pos]))
            except Exception:
                pass
            idx = end_pos
        return blocks

    @staticmethod
    def _is_html_response(text: str) -> bool:
        if not text:
            return False
        stripped = text.lstrip()[:500].lower()
        return bool(
            stripped.startswith("<!doctype")
            or stripped.startswith("<html")
            or "<head>" in stripped
            or "<body" in stripped
        )

    def _candidate_text(self, accumulated: str) -> str:
        """Longest candidate text found across all parsed wrb.fr blocks."""
        best = ""
        for block in self._parse_wrb_blocks(accumulated):
            if not (isinstance(block, list) and block and block[0] and block[0][0] == "wrb.fr"):
                continue
            inner_str = block[0][2] if len(block[0]) > 2 else None
            if not inner_str:
                continue
            try:
                inner_obj = json.loads(inner_str)
            except Exception:
                continue
            if isinstance(inner_obj, list) and len(inner_obj) > 4 and inner_obj[4]:
                cand = inner_obj[4][0]
                if len(cand) > 1 and cand[1]:
                    text = cand[1][0]
                    if isinstance(text, str) and len(text) > len(best):
                        best = text
        return best

    def _clean_response_text(self, text: str) -> str:
        if not text:
            return ""
        text = re.sub(r"```([a-zA-Z0-9_-]+)\?[^\n\r]*", r"```\1", text)
        text = re.sub(r"https?://googleusercontent\.com/[^\s\n\r]*", "", text)
        text = re.sub(r"\n{2,}[A-Za-z0-9_]{10,}\s*$", "", text)
        return text.strip()

    def _clean_stream_chunk(self, text: str) -> str:
        if not text:
            return ""
        text = re.sub(r"```([a-zA-Z0-9_-]+)\?[^\n\r]*", r"```\1", text)
        return re.sub(r"https?://googleusercontent\.com/[^\s\n\r]*", "", text)

    def _extract_stream_text(self, raw: str) -> str:
        if self._is_html_response(raw):
            logger.warning("tunnel returned HTML (login/consent/captcha) instead of data")
            return ""
        full_text = self._candidate_text(raw)
        if self._is_html_response(full_text):
            return ""
        return self._clean_response_text(full_text)

    def _tunnel_url(self, warm: BrowserWarmSession) -> str:
        bl = warm.bl or self._build_label
        url = f"{DEFAULT_STREAM_URL}?bl={bl}&_reqid={_reqid()}&rt=c"
        if warm.f_sid:
            url += f"&f.sid={warm.f_sid}"
        return url

    # ------------------------------------------------------- transport glue
    async def _post(
        self, warm: BrowserWarmSession, url: str, headers: Dict[str, str], payload: str
    ) -> Tuple[int, str]:
        proxy_url = settings.upstream_proxy or None
        if CURL_CFFI_AVAILABLE:
            impersonate = settings.browser_impersonate or warm.profile.get("impersonate", "chrome124")
            async with CurlAsyncSession(
                impersonate=impersonate, cookies=warm.cookies, proxy=proxy_url
            ) as client:
                resp = await client.post(
                    url, headers=headers, data=payload, timeout=settings.request_timeout
                )
                return resp.status_code, resp.text
        resp = await self.client.post(url, headers=headers, content=payload, cookies=warm.cookies)
        return resp.status_code, resp.text

    @asynccontextmanager
    async def _post_stream(
        self, warm: BrowserWarmSession, url: str, headers: Dict[str, str], payload: str
    ):
        """Yield `(status_code, async text-chunk iterator)` for either transport."""
        proxy_url = settings.upstream_proxy or None
        if CURL_CFFI_AVAILABLE:
            impersonate = settings.browser_impersonate or warm.profile.get("impersonate", "chrome124")
            async with CurlAsyncSession(
                impersonate=impersonate, cookies=warm.cookies, proxy=proxy_url
            ) as client:
                resp = await client.post(
                    url,
                    headers=headers,
                    data=payload,
                    stream=True,
                    timeout=settings.request_timeout,
                )

                async def _curl_chunks() -> AsyncIterator[str]:
                    async for chunk in resp.aiter_content():
                        if chunk:
                            yield chunk.decode("utf-8", errors="replace")

                yield resp.status_code, _curl_chunks()
            return

        async with self.client.stream(
            "POST", url, headers=headers, content=payload, cookies=warm.cookies
        ) as response:

            async def _httpx_chunks() -> AsyncIterator[str]:
                async for chunk in response.aiter_text():
                    if chunk:
                        yield chunk

            yield response.status_code, _httpx_chunks()

    # ------------------------------------------------- official REST (keys)
    async def _official_gemini_complete(
        self,
        api_key: str,
        model: str,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        system: Optional[str] = None,
    ) -> str:
        url = f"{OFFICIAL_API_BASE}/{resolve_model(model)}:generateContent?key={api_key}"
        payload: Dict[str, Any] = {"contents": [{"parts": [{"text": prompt}], "role": "user"}]}
        if system:
            payload["system_instruction"] = {"parts": [{"text": system}]}
        gen_config: Dict[str, Any] = {}
        if temperature is not None:
            gen_config["temperature"] = temperature
        if max_tokens:
            gen_config["maxOutputTokens"] = max_tokens
        if gen_config:
            payload["generationConfig"] = gen_config

        async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 429 or "RESOURCE_EXHAUSTED" in resp.text:
                await api_key_pool.mark_rate_limited(api_key)
                raise RateLimitError("official gemini api quota exceeded")
            if resp.status_code in (401, 403):
                await api_key_pool.mark_rate_limited(api_key)
                raise RateLimitError(f"official gemini api auth error {resp.status_code}")
            if resp.status_code != 200:
                raise RuntimeError(f"official gemini api error {resp.status_code}: {resp.text[:200]}")
            data = resp.json()
            candidates = data.get("candidates", [])
            if candidates and "content" in candidates[0]:
                parts = candidates[0]["content"].get("parts", [])
                return "".join(p.get("text", "") for p in parts)
            raise RuntimeError("empty official gemini response")

    async def _official_gemini_stream(
        self,
        api_key: str,
        model: str,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        system: Optional[str] = None,
    ) -> AsyncIterator[str]:
        url = (
            f"{OFFICIAL_API_BASE}/{resolve_model(model)}:streamGenerateContent"
            f"?alt=sse&key={api_key}"
        )
        payload: Dict[str, Any] = {"contents": [{"parts": [{"text": prompt}], "role": "user"}]}
        if system:
            payload["system_instruction"] = {"parts": [{"text": system}]}
        gen_config: Dict[str, Any] = {}
        if temperature is not None:
            gen_config["temperature"] = temperature
        if max_tokens:
            gen_config["maxOutputTokens"] = max_tokens
        if gen_config:
            payload["generationConfig"] = gen_config

        async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
            async with client.stream("POST", url, json=payload) as response:
                if response.status_code in (401, 403, 429):
                    await api_key_pool.mark_rate_limited(api_key)
                    raise RateLimitError(f"official gemini stream {response.status_code}")
                if response.status_code != 200:
                    body = await response.aread()
                    raise RuntimeError(
                        f"official gemini stream error {response.status_code}: "
                        f"{body.decode(errors='replace')[:200]}"
                    )
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    if not data_str:
                        continue
                    try:
                        data = json.loads(data_str)
                    except Exception:
                        continue
                    for cand in data.get("candidates", []):
                        for p in cand.get("content", {}).get("parts", []):
                            if p.get("text"):
                                yield p["text"]

    # --------------------------------------------------------------- public
    @staticmethod
    def _flatten(
        prompt: Optional[str], messages: Optional[List[Dict[str, Any]]], system: Optional[str]
    ) -> str:
        if not prompt and messages:
            parts = []
            if system:
                parts.append(f"System: {system}")
            for m in messages:
                parts.append(f"{m.get('role', 'user')}: {m.get('content', '')}")
            return "\n".join(parts)
        if system and prompt:
            return f"System: {system}\n{prompt}"
        return prompt or "hello"

    async def stream_tokens(
        self,
        prompt: Optional[str] = None,
        session_id: str = "",
        response_id: str = "",
        choice_id: str = "",
        thinking_mode: int = 0,
        model: Optional[str] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        api_key: Optional[str] = None,
        system: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """Stream text deltas, rotating sessions/keys on failure."""
        prompt_text = self._flatten(prompt, messages, system)

        # 1. explicit key
        if api_key and api_key.startswith("AIza"):
            try:
                async for token in self._official_gemini_stream(
                    api_key, model or settings.default_model, prompt_text, temperature, max_tokens, system
                ):
                    yield token
                return
            except Exception as exc:
                logger.warning("explicit key stream failed (%s), falling back to tunnel", exc)

        # 2. configured key pool
        for _ in range(len(settings.get_api_keys())):
            pool_key = await api_key_pool.get_key()
            if not pool_key:
                break
            try:
                async for token in self._official_gemini_stream(
                    pool_key, model or settings.default_model, prompt_text, temperature, max_tokens, system
                ):
                    yield token
                return
            except Exception as exc:
                logger.warning("pooled key stream failed (%s), rotating", exc)
                continue

        # 3. keyless web tunnel with session rotation
        max_attempts = max(settings.max_retries, 3)
        excluded_id: Optional[str] = None

        for attempt in range(max_attempts):
            warm = await session_pool.get_session(
                force_new=(attempt > 0), exclude_session_id=excluded_id
            )
            excluded_id = warm.id
            _, auth_hdr = self._generate_sapisid_auth(warm.sapisid or settings.gemini_sapisid)
            payload = self._build_payload(
                prompt=prompt_text,
                session_id=session_id,
                response_id=response_id,
                choice_id=choice_id,
                thinking_mode=thinking_mode,
                at_token=warm.at,
            )
            headers = self._build_headers(auth_hdr, warm.custom_cookie, warm.profile)
            url = self._tunnel_url(warm)

            accumulated = ""
            last_len = 0
            emitted_any = False
            html_detected = False
            retryable = False

            try:
                async with self._post_stream(warm, url, headers, payload) as (status, chunks):
                    if status in (401, 403, 429, 503):
                        logger.warning("tunnel stream HTTP %s on %s, rotating", status, warm.id)
                        await session_pool.mark_rate_limited(warm.id)
                        retryable = True
                    elif status != 200:
                        await session_pool.mark_exhausted(warm.id)
                        retryable = True
                    else:
                        async for text_chunk in chunks:
                            accumulated += text_chunk
                            if not emitted_any and self._is_html_response(accumulated):
                                html_detected = True
                                break
                            clean_txt = self._clean_stream_chunk(self._candidate_text(accumulated))
                            if len(clean_txt) > last_len:
                                delta = clean_txt[last_len:]
                                last_len = len(clean_txt)
                                emitted_any = True
                                yield delta
            except Exception as exc:
                if emitted_any:
                    return
                logger.warning("tunnel stream error on %s: %s, rotating", warm.id, exc)
                await session_pool.mark_rate_limited(warm.id, cooldown_seconds=30)
                continue

            if retryable:
                continue
            if html_detected:
                await session_pool.mark_rate_limited(warm.id, cooldown_seconds=60)
                continue
            if emitted_any:
                await session_pool.record_success(warm.id)
                return

            logger.warning("session %s produced 0 tokens, rotating", warm.id)
            await session_pool.mark_rate_limited(warm.id, cooldown_seconds=30)

        logger.error("web tunnel stream exhausted after %s rotations", max_attempts)

    async def complete(
        self,
        prompt: Optional[str] = None,
        session_id: str = "",
        response_id: str = "",
        choice_id: str = "",
        thinking_mode: int = 0,
        model: Optional[str] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        api_key: Optional[str] = None,
        system: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        """One-shot completion with key-pool then session-pool fallback."""
        prompt_text = self._flatten(prompt, messages, system)

        if api_key and api_key.startswith("AIza"):
            try:
                return await self._official_gemini_complete(
                    api_key, model or settings.default_model, prompt_text, temperature, max_tokens, system
                )
            except Exception as exc:
                logger.warning("explicit key failed (%s), falling back to tunnel", exc)

        for _ in range(len(settings.get_api_keys())):
            pool_key = await api_key_pool.get_key()
            if not pool_key:
                break
            try:
                return await self._official_gemini_complete(
                    pool_key, model or settings.default_model, prompt_text, temperature, max_tokens, system
                )
            except Exception as exc:
                logger.warning("pooled key failed (%s), rotating", exc)
                continue

        max_attempts = max(settings.max_retries, 3)
        last_err: Optional[Exception] = None
        excluded_id: Optional[str] = None

        for attempt in range(max_attempts):
            warm = await session_pool.get_session(
                force_new=(attempt > 0), exclude_session_id=excluded_id
            )
            excluded_id = warm.id
            _, auth_hdr = self._generate_sapisid_auth(warm.sapisid or settings.gemini_sapisid)
            payload = self._build_payload(
                prompt=prompt_text,
                session_id=session_id,
                response_id=response_id,
                choice_id=choice_id,
                thinking_mode=thinking_mode,
                at_token=warm.at,
            )
            headers = self._build_headers(auth_hdr, warm.custom_cookie, warm.profile)
            url = self._tunnel_url(warm)

            try:
                status, raw_resp = await self._post(warm, url, headers, payload)
            except Exception as exc:
                logger.warning("tunnel error on %s: %s, rotating", warm.id, exc)
                await session_pool.mark_rate_limited(warm.id, cooldown_seconds=30)
                last_err = exc
                continue

            if status in (401, 403, 429, 503):
                await session_pool.mark_rate_limited(warm.id)
                last_err = RuntimeError(f"tunnel HTTP {status}")
                continue
            if status != 200:
                await session_pool.mark_exhausted(warm.id)
                last_err = RuntimeError(f"tunnel HTTP {status}")
                continue
            if self._is_html_response(raw_resp):
                await session_pool.mark_rate_limited(warm.id, cooldown_seconds=60)
                last_err = RuntimeError("tunnel returned an HTML page")
                continue

            lowered = raw_resp.lower()
            if "RESOURCE_EXHAUSTED" in raw_resp or "quota exceeded" in lowered or "limit reached" in lowered:
                await session_pool.mark_rate_limited(warm.id)
                last_err = RuntimeError("tunnel quota/rate limit")
                continue

            text = self._extract_stream_text(raw_resp)
            if text:
                await session_pool.record_success(warm.id)
                return text

            await session_pool.mark_rate_limited(warm.id, cooldown_seconds=30)
            last_err = RuntimeError("empty tunnel response")

        raise RuntimeError(
            f"built-in model failed after {max_attempts} session rotations. Last error: {last_err}"
        )


tunnel = GeminiTunnel()


async def prewarm_sessions(count: int | None = None) -> int:
    """Warm a few sessions in the background so the first request is fast."""
    target = count if count is not None else settings.prewarm_sessions
    target = max(0, min(target, settings.session_pool_size))
    warmed = 0
    for _ in range(target):
        try:
            await session_pool.get_session(force_new=True)
            warmed += 1
        except Exception as exc:  # pragma: no cover - network dependent
            logger.warning("session pre-warm failed: %s", exc)
            break
    return warmed

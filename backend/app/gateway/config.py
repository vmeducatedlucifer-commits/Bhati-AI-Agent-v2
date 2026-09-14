"""Built-in (keyless) model gateway configuration.

Ported from Bhati-Ai-Agent v1. In v2 the gateway is *in-process*: there is no
separate loopback HTTP server, the provider in `app/llm/builtin.py` calls the
tunnel directly. That keeps it working on Render free tier (single port, single
worker) and locally.

Everything here is optional. With zero environment variables and zero API keys
the tunnel still works — that is the whole point of the built-in model.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List

# Model ids the built-in gateway serves. The UI shows friendly aliases
# ("General" / "Pro"); these raw ids are what the tunnel understands.
BUILTIN_GENERAL_MODEL = "gemini-2.0-flash"
BUILTIN_PRO_MODEL = "gemini-1.5-pro"
BUILTIN_MODELS: tuple[str, ...] = (BUILTIN_GENERAL_MODEL, BUILTIN_PRO_MODEL)

BUILTIN_LABELS: dict[str, str] = {
    BUILTIN_GENERAL_MODEL: "Built-in General",
    BUILTIN_PRO_MODEL: "Built-in Pro",
}


def _flag(name: str, default: str = "1") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class GatewaySettings:
    # Master switch. BUILTIN_MODEL_ENABLED=0 disables the keyless provider.
    enabled: bool = _flag("BUILTIN_MODEL_ENABLED", "1")

    # ---- upstream (Google web tunnel, keyless) ---------------------------
    stream_bl: str = os.getenv("STREAM_BL", "boq_assistant-bard-web-server_20260716.08_p0")
    gemini_api_key: str = os.getenv(
        "GEMINI_API_KEY", os.getenv("GEMINI_API_KEYS", os.getenv("GEMINI_KEYS", ""))
    )
    gemini_cookie: str = os.getenv(
        "GEMINI_COOKIE", os.getenv("GEMINI_COOKIES", os.getenv("GEMINI_COOKIE_POOL", ""))
    )
    gemini_sapisid: str = os.getenv("GEMINI_SAPISID", "")
    gemini_at: str = os.getenv("GEMINI_AT", "")
    user_agent: str = os.getenv(
        "USER_AGENT",
        "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/133.0.0.0 Mobile Safari/537.36",
    )
    default_model: str = os.getenv("BUILTIN_DEFAULT_MODEL", BUILTIN_GENERAL_MODEL)
    request_timeout: float = float(os.getenv("REQUEST_TIMEOUT", "180"))
    upstream_proxy: str = os.getenv(
        "UPSTREAM_PROXY", os.getenv("HTTPS_PROXY", os.getenv("HTTP_PROXY", ""))
    )
    browser_impersonate: str = os.getenv("BROWSER_IMPERSONATE", "chrome124")
    session_ttl: int = int(os.getenv("SESSION_TTL", "1800"))
    session_pool_size: int = int(os.getenv("SESSION_POOL_SIZE", "5"))
    rotate_session_every_request: bool = _flag("ROTATE_SESSION", "1")
    max_requests_per_session: int = int(os.getenv("MAX_REQUESTS_PER_SESSION", "15"))
    session_cooldown_seconds: int = int(os.getenv("SESSION_COOLDOWN_SECONDS", "60"))
    max_retries: int = int(os.getenv("MAX_RETRIES", "3"))
    prewarm_sessions: int = int(os.getenv("BUILTIN_PREWARM_SESSIONS", "1"))

    def get_api_keys(self) -> List[str]:
        raw = self.gemini_api_key or ""
        return [k.strip() for k in raw.replace("\n", ",").split(",") if k.strip()]

    def get_cookies(self) -> List[str]:
        raw = self.gemini_cookie or ""
        if "|||" in raw:
            cookies = [c.strip() for c in raw.split("|||") if c.strip()]
        elif "\n" in raw:
            cookies = [c.strip() for c in raw.split("\n") if c.strip()]
        else:
            cookies = [raw.strip()] if raw.strip() else []
        return cookies


settings = GatewaySettings()

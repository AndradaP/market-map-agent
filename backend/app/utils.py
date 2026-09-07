from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlparse


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def host_of(url: str) -> str:
    try:
        netloc = urlparse(url if "//" in url else f"//{url}", scheme="https").netloc.lower()
        return netloc[4:] if netloc.startswith("www.") else netloc
    except Exception:
        return ""

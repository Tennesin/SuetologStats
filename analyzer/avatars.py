"""Загрузка аватарок с CDN Discord (необязательно; без сети отчёты строятся с буквой-заглушкой)."""

import base64
import os
import urllib.request
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

ALLOWED_HOSTS = {"cdn.discordapp.com", "media.discordapp.net"}
MAX_BYTES = 1_000_000


def _normalize(url: str) -> Optional[str]:
    """Только https и только CDN Discord; всегда статичный png размером 128 px."""
    try:
        p = urlsplit(url)
    except ValueError:
        return None
    if p.scheme != "https" or p.hostname not in ALLOWED_HOSTS:
        return None
    root, _ext = os.path.splitext(p.path)
    return urlunsplit((p.scheme, p.netloc, root + ".png", "size=128", ""))


def fetch_avatar(url: str, timeout: float = 8.0) -> Optional[str]:
    """Возвращает data:-URI или None, если скачать не удалось."""
    if not url:
        return None
    norm = _normalize(url)
    if not norm:
        return None
    try:
        req = urllib.request.Request(norm, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ctype = resp.headers.get_content_type() or ""
            data = resp.read(MAX_BYTES)
    except Exception:
        return None
    if not ctype.startswith("image/") or not data:
        return None
    return f"data:{ctype};base64,{base64.b64encode(data).decode('ascii')}"
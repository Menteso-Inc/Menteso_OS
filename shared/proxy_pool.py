"""Proxy rotation pool — feeds Playwright's `proxy=` launch option.

Sources, in priority order:
  1. PROXY_POOL_URLS — comma-separated list, format `http://user:pass@host:port`
     (or `socks5://host:port`). User-supplied; nothing if blank.
  2. TOR_ENABLED=true — falls back to the local Tor SOCKS5 endpoint.

Returns dicts in the shape Playwright expects:
    {"server": "http://host:port", "username": "...", "password": "..."}

A burn-cooldown is honored so a proxy that just failed isn't picked again
immediately.
"""
import random
import threading
import time
from urllib.parse import urlparse

from .config import get_env


def _read_int(key, fallback):
    raw = get_env(key)
    if not raw:
        return fallback
    try:
        return int(raw)
    except (TypeError, ValueError):
        return fallback


def _parse_proxy_url(url):
    """Convert a URL string into Playwright's proxy dict shape."""
    if not url:
        return None
    parsed = urlparse(url.strip())
    if not parsed.scheme or not parsed.hostname:
        return None
    server = f"{parsed.scheme}://{parsed.hostname}"
    if parsed.port:
        server += f":{parsed.port}"
    proxy = {"server": server}
    if parsed.username:
        proxy["username"] = parsed.username
    if parsed.password:
        proxy["password"] = parsed.password
    return proxy


def _load_pool_from_env():
    raw = get_env("PROXY_POOL_URLS") or ""
    urls = [u.strip() for u in raw.split(",") if u.strip()]
    return [_parse_proxy_url(u) for u in urls if _parse_proxy_url(u)]


def _tor_proxy():
    if (get_env("TOR_ENABLED") or "").lower() not in ("1", "true", "yes"):
        return None
    server = get_env("TOR_SOCKS_PROXY") or "socks5://127.0.0.1:9050"
    return _parse_proxy_url(server)


class _Pool:
    def __init__(self):
        self._lock = threading.Lock()
        self._proxies = _load_pool_from_env()
        self._tor = _tor_proxy()
        self._burned = {}  # server -> expiry timestamp
        self._cooldown = _read_int("PROXY_POOL_BURN_COOLDOWN_SECONDS", 300)

    def reload(self):
        """Re-read env (useful in tests or after the user edits .env)."""
        with self._lock:
            self._proxies = _load_pool_from_env()
            self._tor = _tor_proxy()
            self._burned.clear()

    def available_count(self):
        with self._lock:
            now = time.time()
            return sum(1 for p in self._proxies if self._burned.get(p["server"], 0) < now)

    def get(self):
        """Pick a fresh proxy. Falls back to Tor if the explicit pool is empty
        or fully burned. Returns None when no rotation source is configured.
        """
        with self._lock:
            now = time.time()
            available = [
                p for p in self._proxies
                if self._burned.get(p["server"], 0) < now
            ]
            if available:
                return random.choice(available)
            if self._tor:
                return dict(self._tor)
            return None

    def mark_burned(self, proxy):
        if not proxy or "server" not in proxy:
            return
        with self._lock:
            self._burned[proxy["server"]] = time.time() + self._cooldown


_default_pool = _Pool()


def get_proxy():
    """Module-level convenience — returns a Playwright proxy dict or None."""
    return _default_pool.get()


def mark_burned(proxy):
    _default_pool.mark_burned(proxy)


def available_count():
    return _default_pool.available_count()


def reload():
    _default_pool.reload()

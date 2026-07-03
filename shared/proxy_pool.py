"""Proxy rotation pool — feeds Playwright's `proxy=` option.

Goal: give every browser worker its OWN egress IP so WIPO's per-IP
throttling is spread across many IPs instead of hammering one. This is what
lets the parallel pipeline scale toward the 2000-rows/hour target.

Sources, in priority order:
  1. PROXY_POOL_URLS — comma-separated list, format `http://user:pass@host:port`
     (or `socks5://host:port`). Paid residential/datacenter proxies go here.
  2. TOR — free fallback. Either:
       - TOR_SOCKS_PORTS = "9050,9052,9054,..."  (explicit list), or
       - TOR_SOCKS_BASE_PORT + TOR_SOCKS_PORT_COUNT (e.g. 9050 + 20), or
       - TOR_SOCKS_PROXY (single endpoint, back-compat).
     Enabled when TOR_ENABLED=true. Each distinct SOCKS port is a distinct Tor
     circuit → a distinct exit IP, so N ports ≈ N concurrent IPs.

Per-worker assignment:
    get_proxy_for_worker(i)  → the i-th worker always maps to a stable proxy
                               (round-robin over the pool), so tabs don't all
                               share one IP. Pass `rotation` to jump to a fresh
                               proxy for that worker after a captcha/block.

Returns dicts in the shape Playwright expects:
    {"server": "socks5://host:port"}  or
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


def _is_truthy(key):
    return (get_env(key) or "").strip().lower() in ("1", "true", "yes", "on")


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


def _tor_host():
    # Allow overriding the Tor host; default local.
    raw = get_env("TOR_SOCKS_HOST") or "127.0.0.1"
    return raw.strip() or "127.0.0.1"


def _load_tor_proxies():
    """Build the list of Tor SOCKS endpoints (one per circuit/port).

    Each distinct SOCKS port maps to an independent Tor circuit, so pointing
    different browser contexts at different ports yields different exit IPs
    concurrently — the free alternative to a paid proxy pool.
    """
    if not _is_truthy("TOR_ENABLED"):
        return []

    host = _tor_host()

    # 1. Explicit port list wins.
    raw_ports = get_env("TOR_SOCKS_PORTS") or ""
    ports = []
    for chunk in raw_ports.split(","):
        chunk = chunk.strip()
        if chunk.isdigit():
            ports.append(int(chunk))

    # 2. Base + count range.
    if not ports:
        base = _read_int("TOR_SOCKS_BASE_PORT", 0)
        count = _read_int("TOR_SOCKS_PORT_COUNT", 0)
        if base and count > 0:
            ports = [base + i for i in range(count)]

    # 3. Single endpoint (back-compat).
    if not ports:
        single = _parse_proxy_url(get_env("TOR_SOCKS_PROXY") or "socks5://127.0.0.1:9050")
        return [single] if single else []

    return [{"server": f"socks5://{host}:{port}"} for port in ports]


class _Pool:
    def __init__(self):
        self._lock = threading.Lock()
        self._proxies = _load_pool_from_env()
        self._tor = _load_tor_proxies()
        self._burned = {}  # server -> expiry timestamp
        self._cooldown = _read_int("PROXY_POOL_BURN_COOLDOWN_SECONDS", 300)

    # -- lifecycle -------------------------------------------------------
    def reload(self):
        """Re-read env (useful in tests or after the user edits .env)."""
        with self._lock:
            self._proxies = _load_pool_from_env()
            self._tor = _load_tor_proxies()
            self._burned.clear()

    def _all(self):
        """Every configured proxy: explicit pool first, then Tor circuits."""
        return list(self._proxies) + list(self._tor)

    def enabled(self):
        with self._lock:
            return bool(self._all())

    def size(self):
        with self._lock:
            return len(self._all())

    def available_count(self):
        with self._lock:
            now = time.time()
            return sum(1 for p in self._all() if self._burned.get(p["server"], 0) < now)

    # -- selection -------------------------------------------------------
    def get(self):
        """Pick a random fresh proxy (any worker). Back-compat entry point.

        Returns None when no rotation source is configured, so callers stay
        on their direct connection unless the user opts in.
        """
        with self._lock:
            now = time.time()
            available = [
                p for p in self._all()
                if self._burned.get(p["server"], 0) < now
            ]
            if available:
                return dict(random.choice(available))
            # Everything burned — fall back to any Tor circuit rather than
            # dropping to a bare (single-IP) connection mid-run.
            if self._tor:
                return dict(random.choice(self._tor))
            return None

    def get_for_worker(self, index, rotation=0):
        """Stable per-worker mapping so each of the N contexts gets its own IP.

        worker `index` maps to `pool[(index + rotation) % N]`. Bump `rotation`
        (e.g. after a captcha) to move that one worker to a fresh proxy without
        disturbing the others. Skips burned proxies where possible.
        """
        with self._lock:
            pool = self._all()
            if not pool:
                return None
            now = time.time()
            n = len(pool)
            # Try up to n offsets starting at the requested slot, preferring a
            # non-burned proxy.
            for step in range(n):
                candidate = pool[(index + rotation + step) % n]
                if self._burned.get(candidate["server"], 0) < now:
                    return dict(candidate)
            # All burned — return the nominally-assigned one anyway.
            return dict(pool[(index + rotation) % n])

    def mark_burned(self, proxy):
        if not proxy or "server" not in proxy:
            return
        with self._lock:
            self._burned[proxy["server"]] = time.time() + self._cooldown


_default_pool = _Pool()


def get_proxy():
    """Module-level convenience — returns a random Playwright proxy dict or None."""
    return _default_pool.get()


def get_proxy_for_worker(index, rotation=0):
    """Return the stable proxy for browser worker `index` (or None)."""
    return _default_pool.get_for_worker(index, rotation)


def enabled():
    """True when any rotation source (proxy pool or Tor) is configured."""
    return _default_pool.enabled()


def size():
    """How many distinct proxies/circuits are configured."""
    return _default_pool.size()


def mark_burned(proxy):
    _default_pool.mark_burned(proxy)


def available_count():
    return _default_pool.available_count()


def reload():
    _default_pool.reload()

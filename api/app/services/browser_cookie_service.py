from __future__ import annotations

from http.cookiejar import CookieJar


class BrowserCookieService:
    def __init__(self) -> None:
        self._cache: dict[str, CookieJar] = {}

    def bilibili_cookie_header(self, browsers: list[str]) -> str:
        pairs: dict[str, str] = {}
        for browser in browsers:
            jar = self._load_browser(browser)
            if not jar:
                continue
            for cookie in jar:
                if "bilibili.com" not in cookie.domain or not cookie.name or not cookie.value:
                    continue
                pairs[cookie.name] = cookie.value
        return "; ".join(f"{name}={value}" for name, value in pairs.items())

    def _load_browser(self, browser: str) -> CookieJar | None:
        cached = self._cache.get(browser)
        if cached:
            return cached
        try:
            from yt_dlp.cookies import extract_cookies_from_browser

            jar = extract_cookies_from_browser(browser)
            self._cache[browser] = jar
            return jar
        except Exception:
            return None


browser_cookie_service = BrowserCookieService()

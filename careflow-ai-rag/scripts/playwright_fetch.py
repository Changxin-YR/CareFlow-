"""CareFlow 康脉智护 —— 官方站点抓取工具（已实测突破 WZWS 风控）。

背景
----
``www.nhc.gov.cn`` 全站挂的是 WZWS（网宿）JS 挑战：任何非浏览器客户端
（httpx / requests / curl，无论 UA 怎么伪装）都会拿到 **HTTP 412**，
响应体里是一段需要执行的 JS。**只有真实浏览器执行完挑战后会自动重新导航，
才能拿到正文。**

关键坑（必须避开）
------------------
1. **绝对不能因为 `response.status == 412` 就判定失败** —— 412 是这个页面
   的正常第一步，几秒后页面会自己跳到真正的正文。
2. 不能用 `wait_until="load"` / `"networkidle"` 等：挑战期间这些会超时或抛
   "page is navigating and changing the content"。
   **用 `wait_until="commit"`，然后自己轮询。**
3. 轮询判据不能只看 `len(html)`：挑战页本身也有几 KB。
   要用 **`inner_text("body")` 的长度 + 期望关键词** 判断。
4. 下载 PDF 时，必须复用**同一个 BrowserContext**（`ctx.request.get(...)`），
   否则 WAF cookie 不在，照样 412。

用法
----
::

    from scripts.playwright_fetch import fetch_html, fetch_bytes, html_to_text

    html = await fetch_html("https://www.nhc.gov.cn/...")
    data = await fetch_bytes("https://www.nhc.gov.cn/.../xxx.pdf")
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)

DEFAULT_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-dev-shm-usage",
    "--no-sandbox",
]

#: 挑战页特征（出现这些说明还在 WAF 页面上）
CHALLENGE_MARKERS = ("$_ts", "wzws", "请稍候", "安全验证", "Checking your browser")


@dataclass
class FetchResult:
    url: str
    status: int | None = None
    html: str = ""
    text: str = ""
    title: str = ""
    ok: bool = False
    challenge_solved: bool = False
    attempts: int = 0
    error: str = ""
    warnings: list[str] = field(default_factory=list)


def looks_like_challenge(html: str, text: str) -> bool:
    if len(text) > 800 and "wzws" not in html[:2000].lower():
        return False
    lowered = html[:4000].lower()
    return any(marker.lower() in lowered for marker in CHALLENGE_MARKERS) or len(text) < 200


async def fetch_html(
    url: str,
    *,
    expect_keywords: tuple[str, ...] = (),
    min_text_chars: int = 800,
    max_wait_seconds: float = 45.0,
    poll_interval: float = 2.0,
    timeout_ms: int = 60000,
    browser=None,
    context=None,
) -> FetchResult:
    """抓取页面 HTML，自动等待 WZWS 挑战通过。

    :param expect_keywords: 正文里应当出现的关键词（任一中即算成功），可空
    """
    result = FetchResult(url=url)
    owns_browser = browser is None
    owns_context = context is None
    launched = None
    ctx = context

    from playwright.async_api import async_playwright

    playwright = None
    try:
        if owns_browser:
            playwright = await async_playwright().start()
            launched = await playwright.chromium.launch(headless=True, args=DEFAULT_ARGS)
            browser = launched
        if owns_context:
            ctx = await browser.new_context(
                locale="zh-CN",
                user_agent=DEFAULT_UA,
                viewport={"width": 1366, "height": 900},
                extra_http_headers={"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"},
            )

        for attempt in range(1, 4):
            result.attempts = attempt
            page = await ctx.new_page()
            try:
                response = await page.goto(url, timeout=timeout_ms, wait_until="commit")
                result.status = response.status if response else None
                # 注意：status 可能是 412 —— 这正是挑战的第一步，不能据此退出。

                deadline = asyncio.get_event_loop().time() + max_wait_seconds
                text = ""
                html = ""
                while asyncio.get_event_loop().time() < deadline:
                    await asyncio.sleep(poll_interval)
                    try:
                        text = await page.inner_text("body")
                        html = await page.content()
                        title = await page.title()
                    except Exception as exc:  # 页面正在跳转
                        result.warnings.append(f"read_retry:{type(exc).__name__}")
                        continue
                    if len(text) >= min_text_chars and not looks_like_challenge(html, text):
                        if not expect_keywords or any(k in text for k in expect_keywords):
                            result.html = html
                            result.text = text
                            result.title = title
                            result.ok = True
                            result.challenge_solved = True
                            return result
                    result.title = title
            except Exception as exc:  # noqa: BLE001
                result.error = f"{type(exc).__name__}: {exc}"[:300]
            finally:
                try:
                    await page.close()
                except Exception:  # noqa: BLE001
                    pass
            await asyncio.sleep(1.5 * attempt)

        result.error = result.error or (
            f"challenge_not_passed status={result.status} text_len={len(result.text)}"
        )
        return result
    finally:
        if owns_context and ctx is not None:
            try:
                await ctx.close()
            except Exception:  # noqa: BLE001
                pass
        if owns_browser and launched is not None:
            try:
                await launched.close()
            except Exception:  # noqa: BLE001
                pass
        if playwright is not None:
            try:
                await playwright.stop()
            except Exception:  # noqa: BLE001
                pass


async def fetch_bytes(
    url: str,
    *,
    context=None,
    referer: str = "",
    timeout_ms: int = 90000,
) -> tuple[bytes, int, str]:
    """用**同一个浏览器上下文**下载附件（PDF 等）。

    返回 ``(content, status, error)``。
    """
    from playwright.async_api import async_playwright

    owns_context = context is None
    playwright = None
    launched = None
    if owns_context:
        playwright = await async_playwright().start()
        launched = await playwright.chromium.launch(headless=True, args=DEFAULT_ARGS)
        context = await launched.new_context(
            locale="zh-CN", user_agent=DEFAULT_UA, accept_downloads=True
        )
    try:
        headers = {"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}
        if referer:
            headers["Referer"] = referer
        response = await context.request.get(url, headers=headers, timeout=timeout_ms)
        body = await response.body()
        return body, response.status, ""
    except Exception as exc:  # noqa: BLE001
        return b"", 0, f"{type(exc).__name__}: {exc}"[:300]
    finally:
        if owns_context:
            try:
                await context.close()
            except Exception:  # noqa: BLE001
                pass
            if launched is not None:
                try:
                    await launched.close()
                except Exception:  # noqa: BLE001
                    pass
            if playwright is not None:
                try:
                    await playwright.stop()
                except Exception:  # noqa: BLE001
                    pass


def html_to_text(html: str) -> str:
    """粗略的 HTML 转文本（正式清洗请用 scripts/preprocess_documents.py）。"""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "iframe"]):
        tag.decompose()
    return "\n".join(
        line.strip() for line in soup.get_text("\n").splitlines() if line.strip()
    )


async def _selftest(urls: list[str]) -> None:
    for url in urls:
        result = await fetch_html(url, expect_keywords=("国家", "健康", "管理", "指南", "规范"))
        status = "OK  " if result.ok else "FAIL"
        print(f"[{status}] status={result.status} len={len(result.text)} {url}")
        if result.ok:
            print("        title:", result.title)
            print("        text :", result.text[:120].replace("\n", " "))
        else:
            print("        error:", result.error)


if __name__ == "__main__":
    import sys

    targets = sys.argv[1:] or [
        "https://www.nhc.gov.cn/jws/s3578/201703/d20c37e23e1f4c7db7b8e25f34473e1b.shtml"
    ]
    asyncio.run(_selftest(targets))

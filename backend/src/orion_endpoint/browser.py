"""One isolated process-local browser context; no user profile or JS RPC."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from orion_endpoint.policy import Policy


class Browser:
    def __init__(self, policy: Policy) -> None:
        self.policy = policy
        self.playwright: Any = None
        self.browser: Any = None
        self.context: Any = None
        self.page: Any = None

    async def available(self) -> bool:
        if not self.policy.browser:
            return False
        from playwright.async_api import async_playwright

        async with async_playwright() as runtime:
            return Path(runtime.chromium.executable_path).is_file()

    async def execute(self, operation: str, args: dict[str, Any]) -> dict[str, Any]:
        if not self.policy.browser:
            raise PermissionError("policy_denied")
        if operation == "close":
            await self.close()
            return {"closed": True}
        if operation == "open":
            if self.page is not None:
                raise FileExistsError("conflict")
            from playwright.async_api import async_playwright

            self.playwright = await async_playwright().start()
            try:
                self.browser = await self.playwright.chromium.launch(headless=True)
                self.context = await self.browser.new_context(accept_downloads=False)
                # Downloads are denied; no browser-origin files leave the controlled context.
                self.page = await self.context.new_page()
                self.context.on("page", lambda page: page.close())
                self.page.set_default_timeout(10_000)
            except BaseException:
                await self.close()
                raise
        if self.page is None:
            raise RuntimeError("unavailable")
        if operation in {"open", "navigate"}:
            parsed = urlsplit(args["url"])
            if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
                raise ValueError("invalid_input")
            await self.page.goto(args["url"], wait_until="domcontentloaded")
        elif operation == "click":
            await self.page.locator(args["selector"]).click()
        elif operation == "type":
            await self.page.locator(args["selector"]).fill(args["text"])
        elif operation == "key":
            key = {
                "ctrl": "Control",
                "alt": "Alt",
                "escape": "Escape",
                "up": "ArrowUp",
                "down": "ArrowDown",
                "left": "ArrowLeft",
                "right": "ArrowRight",
            }.get(args["key"], args["key"] if len(args["key"]) == 1 else args["key"].capitalize())
            await self.page.keyboard.press(key)
        snapshot = await self.page.locator("body").aria_snapshot(timeout=10_000)
        return {
            "url": self.page.url[:2048],
            "title": (await self.page.title())[:256],
            "snapshot": snapshot[:24000],
            "untrusted_external_content": True,
        }

    async def close(self) -> None:
        try:
            if self.browser is not None:
                await self.browser.close()
        finally:
            if self.playwright is not None:
                await self.playwright.stop()
            self.page = self.context = self.browser = self.playwright = None

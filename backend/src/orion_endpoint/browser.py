"""One isolated process-local browser context; no user profile or JS RPC."""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from orion_endpoint.policy import Policy
from orion_endpoint.protocol import MAX_TRANSFER


class Browser:
    def __init__(self, policy: Policy) -> None:
        self.policy = policy
        self.playwright: Any = None
        self.browser: Any = None
        self.context: Any = None
        self.page: Any = None
        self.download_tasks: set[asyncio.Task[None]] = set()
        self.download_count = 0
        self.download_limit_task: asyncio.Task[None] | None = None

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
                directory = None
                if self.policy.browser_download_directory:
                    directory = Path(self.policy.browser_download_directory).resolve(strict=True)
                    self.policy.path(str(directory / ".download-check"), write=True)
                self.browser = await self.playwright.chromium.launch(
                    headless=True, downloads_path=str(directory) if directory else None
                )
                self.context = await self.browser.new_context(
                    accept_downloads=directory is not None
                )
                self.page = await self.context.new_page()
                self.page.on("download", self.download)
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

    def download(self, download: Any) -> None:
        if self.download_count >= 2 or not self.policy.browser_download_directory:
            # Close once instead of allocating one cancellation task per hostile download.
            if self.download_limit_task is None:
                self.download_limit_task = asyncio.create_task(self.context.close())
            return
        self.download_count += 1

        async def save() -> None:
            assert self.policy.browser_download_directory is not None
            directory = Path(self.policy.browser_download_directory)
            try:
                async with asyncio.timeout(30):
                    pending = asyncio.create_task(download.path())
                    try:
                        while not pending.done():
                            if (
                                sum(
                                    path.stat().st_size
                                    for path in directory.iterdir()
                                    if path.is_file()
                                )
                                > MAX_TRANSFER
                            ):
                                await download.cancel()
                                return
                            await asyncio.sleep(0.1)
                        downloaded = await pending
                        if downloaded is None or downloaded.stat().st_size > MAX_TRANSFER:
                            await download.cancel()
                            return
                        destination = self.policy.path(
                            str(directory / f"download-{uuid.uuid4().hex}"), write=True
                        )
                        await download.save_as(destination)
                        await download.delete()
                    finally:
                        pending.cancel()
                        await asyncio.gather(pending, return_exceptions=True)
            except Exception:
                with contextlib.suppress(Exception):
                    await download.cancel()

        task = asyncio.create_task(save())
        self.download_tasks.add(task)
        task.add_done_callback(self.download_tasks.discard)

    async def close(self) -> None:
        try:
            for task in self.download_tasks:
                task.cancel()
            await asyncio.gather(*self.download_tasks, return_exceptions=True)
            self.download_tasks.clear()
            self.download_count = 0
            if self.download_limit_task is not None:
                await asyncio.gather(self.download_limit_task, return_exceptions=True)
                self.download_limit_task = None
            if self.browser is not None:
                await self.browser.close()
        finally:
            if self.playwright is not None:
                await self.playwright.stop()
            self.page = self.context = self.browser = self.playwright = None

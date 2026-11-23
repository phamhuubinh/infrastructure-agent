"""Packaged UI regression using browser contexts and one isolated Host."""

from __future__ import annotations

import os
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import expect, sync_playwright

from orion.api.app import create_app
from orion.bootstrap import build_application
from orion.contracts import AssistantMessage, ModelTurn, ModelTurnCompleted
from orion.models.backend import ModelBackend

pytestmark = pytest.mark.skipif(
    os.getenv("ORION_MOBILE_BROWSER_TESTS") != "1",
    reason="requires a built UI and Playwright browsers",
)


class FixtureModel(ModelBackend):
    async def stream(self, messages, tools, settings, cancellation):
        yield ModelTurnCompleted(
            turn=ModelTurn(assistant=AssistantMessage(content="Fixture reply"))
        )


@pytest.fixture
def fixture_host(tmp_path):
    root = Path(__file__).resolve().parents[2]
    bundle = root / "ui" / "dist" / "client"
    assert (bundle / "_shell.html").is_file()
    application = build_application(
        tmp_path / "test.db",
        FixtureModel(),
        endpoint_enabled=False,
        seed_model_from_environment=False,
    )
    application.store.upsert_model_config(
        "openai_compatible", "http://fixture.test/v1", "fixture", None
    )
    asgi = create_app(application=application, ui_directory=bundle)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        origin = f"http://127.0.0.1:{listener.getsockname()[1]}"
        server = uvicorn.Server(uvicorn.Config(asgi, log_level="warning"))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 10
            while not server.started and thread.is_alive() and time.monotonic() < deadline:
                time.sleep(0.05)
            assert server.started
            yield origin
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            assert not thread.is_alive()
            application.store.close()


@pytest.mark.parametrize("engine,device", [("chromium", "Pixel 7"), ("webkit", "iPhone 13")])
def test_shared_chat_sidebar_composer_and_host_sync_on_mobile(fixture_host, engine, device):
    with sync_playwright() as playwright:
        browser = getattr(playwright, engine).launch()
        desktop = browser.new_context(viewport={"width": 1280, "height": 800}).new_page()
        mobile = browser.new_context(**playwright.devices[device]).new_page()
        for page in (desktop, mobile):
            page.goto(fixture_host)
            expect(page.get_by_role("textbox", name="Chat input")).to_be_visible()
        sidebar = mobile.get_by_role("complementary", name="Thanh bên Orion")
        desktop_sidebar = desktop.get_by_role("complementary", name="Thanh bên Orion")
        menu = mobile.get_by_role("button", name="Menu", exact=True)
        expect(sidebar).to_be_hidden()
        expect(desktop_sidebar).to_be_visible()
        expect(desktop.get_by_role("button", name="Menu", exact=True)).to_be_hidden()

        def send(page, text):
            composer = page.get_by_role("textbox", name="Chat input")
            composer.fill(text)
            page.get_by_role("button", name="Send message").click()
            expect(page.get_by_text("Fixture reply", exact=True)).to_be_visible(timeout=12000)

        send(desktop, "Desktop shared history")
        mobile.get_by_role("link", name="Chat mới", exact=True).click()
        send(mobile, "Mobile shared history")
        expect(
            desktop_sidebar.get_by_role("button", name="Mobile shared history", exact=True)
        ).to_be_visible(timeout=15000)

        menu.click()
        expect(sidebar).to_be_visible()
        for label in ("Trò chuyện", "Projects", "Remote Control", "Commands", "Cài đặt"):
            expect(sidebar.get_by_role("link", name=label)).to_be_visible()
        older = sidebar.get_by_role("button", name="Desktop shared history", exact=True)
        expect(older).to_be_visible(timeout=15000)
        recent = sidebar.get_by_role("button", name="Mobile shared history", exact=True)
        assert recent.evaluate(
            "(row, other) => !!(row.compareDocumentPosition(other) & 4)", older.element_handle()
        )
        older.click()
        expect(sidebar).to_be_hidden()
        expect(
            mobile.get_by_test_id("conversation-scroll-area").get_by_text(
                "Desktop shared history", exact=True
            )
        ).to_be_visible()
        menu.click()
        assert recent.evaluate(
            "(row, other) => !!(row.compareDocumentPosition(other) & 4)", older.element_handle()
        )
        sidebar.get_by_role("button", name="Đóng thanh bên").click()

        mobile.get_by_role("button", name="Mở bảng chi tiết").click()
        expect(mobile.get_by_role("complementary", name="Hoạt động runtime")).to_be_visible()
        mobile.get_by_role("button", name="Đóng bảng chi tiết").click()
        mobile.get_by_role("textbox", name="Chat input").focus()
        mobile.evaluate(
            """() => {
                const vp = window.visualViewport;
                Object.defineProperty(vp, 'height', { configurable: true, value: 345 });
                vp.dispatchEvent(new Event('resize'));
            }"""
        )
        send_button = mobile.get_by_role("button", name="Send message")
        composer = mobile.get_by_role("textbox", name="Chat input")
        for control in (composer, send_button):
            box = control.bounding_box()
            assert box is not None and 0 <= box["y"] < box["y"] + box["height"] <= 346
        assert mobile.evaluate("document.documentElement.scrollWidth === window.innerWidth")

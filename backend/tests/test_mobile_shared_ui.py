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

LONG_VALUE = "PowerShellResult" * 55
OVERFLOW_REPLY = (
    f"Identifier: {LONG_VALUE}\n\n"
    f"```powershell\nWrite-Output '{LONG_VALUE}'\n```\n\n"
    "| Hostname | WindowsVersion | IPv4 | DNS | DefaultGateway |\n"
    "| --- | --- | --- | --- | --- |\n"
    f"| {LONG_VALUE} | 10.0.12345 | 192.0.2.20 | 192.0.2.53 | 192.0.2.1 |"
)


class FixtureModel(ModelBackend):
    async def stream(self, messages, tools, settings, cancellation):
        content = (
            OVERFLOW_REPLY
            if any(LONG_VALUE in (message.content or "") for message in messages)
            else "Fixture reply"
        )
        yield ModelTurnCompleted(turn=ModelTurn(assistant=AssistantMessage(content=content)))


def assert_long_chat_stays_in_viewport(page, origin):
    page.goto(origin)
    page.get_by_role("textbox", name="Chat input").fill(LONG_VALUE)
    page.get_by_role("button", name="Send message").click()
    table = page.get_by_role("region", name="Bảng kết quả")
    pre = page.locator("pre").filter(has_text="Write-Output")
    expect(table).to_be_visible(timeout=15000)
    expect(pre).to_be_visible(timeout=15000)
    page.wait_for_function(
        """() => [...document.querySelectorAll('pre, [aria-label="Bảng kết quả"]')]
            .every(element => element.clientWidth > 0 &&
                element.scrollWidth > element.clientWidth)"""
    )
    for scroll_area in (table, pre):
        sizes = scroll_area.evaluate(
            """element => {
                element.scrollLeft = element.scrollWidth;
                return [element.clientWidth, element.scrollWidth, element.scrollLeft];
            }"""
        )
        assert 0 < sizes[0] < sizes[1] and sizes[2] > 0, sizes
    assert page.evaluate(
        """() => {
            const track = document.querySelector('[data-testid="conversation-scroll-area"]');
            return document.documentElement.scrollWidth <= window.innerWidth + 1 &&
                track.scrollWidth <= track.clientWidth + 1 && window.scrollX == 0;
        }"""
    )
    assert table.evaluate(
        """element => {
            element.scrollLeft = element.scrollWidth;
            const frame = element.getBoundingClientRect();
            const cell = element.querySelector('tr:last-child td:last-child');
            const last = cell.getBoundingClientRect();
            return last.right > frame.left && last.left < frame.right;
        }"""
    )


@pytest.mark.parametrize("engine,device", [("chromium", "Pixel 7"), ("webkit", "iPhone 13")])
def test_wide_powershell_result_scrolls_inside_its_components(fixture_host, engine, device):
    with sync_playwright() as playwright:
        browser = getattr(playwright, engine).launch()
        page = browser.new_context(**playwright.devices[device]).new_page()
        assert_long_chat_stays_in_viewport(page, fixture_host)


def test_update_notice_is_visible_on_desktop_and_mobile(fixture_host):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        desktop = browser.new_context().new_page()
        mobile = browser.new_context(**playwright.devices["Pixel 7"]).new_page()
        for page in (desktop, mobile):
            page.route(
                "**/api/updates",
                lambda route: route.fulfill(
                    json={"host_version": "0.1.5", "available_host_version": "0.1.6"}
                ),
            )
            page.goto(fixture_host)
        for page in (desktop, mobile):
            expect(page.get_by_text("Orion Host có bản 0.1.6.")).to_be_visible()
            expect(page.get_by_text("Cài đặt bản cập nhật trên máy Host.")).to_be_visible()
        mobile.get_by_role("button", name="Ẩn").click()
        expect(mobile.get_by_text("Orion Host có bản 0.1.6.")).to_be_hidden()
        expect(desktop.get_by_text("Orion Host có bản 0.1.6.")).to_be_visible()


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

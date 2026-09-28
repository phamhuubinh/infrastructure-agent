from __future__ import annotations

import os
import sys

import pytest

from orion import cli, paths, ui_package
from orion.ui_package import replace_ui_bundle


def test_source_checkout_detection_uses_package_location_not_cwd(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    package = tmp_path / "backend" / "src" / "orion" / "paths.py"
    package.parent.mkdir(parents=True)
    package.write_text("", encoding="utf-8")
    (tmp_path / "backend" / "pyproject.toml").write_text("", encoding="utf-8")
    (tmp_path / "ui").mkdir()
    (tmp_path / "ui" / "package.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(paths, "__file__", str(package))
    monkeypatch.setattr(sys, "prefix", str(tmp_path / ".venv"))
    monkeypatch.chdir(tmp_path / "ui")

    assert paths.source_checkout_root() == tmp_path
    monkeypatch.delenv("ORION_UI_DIR", raising=False)
    assert paths.packaged_ui_directory() == tmp_path / ".orion-ui"

    monkeypatch.setattr(sys, "prefix", str(tmp_path / "installed" / ".venv"))
    assert paths.source_checkout_root() is None
    assert paths.packaged_ui_directory() == tmp_path / "installed" / ".orion-ui"

    monkeypatch.setattr(sys, "prefix", str(tmp_path / ".venv"))
    (tmp_path / "ui" / "package.json").unlink()
    assert paths.source_checkout_root() is None


def test_dev_web_builds_bundle_before_reusing_healthy_server(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    destination = tmp_path / ".orion-ui"
    built: list[tuple[object, object]] = []

    def build(repository, frontend) -> None:  # type: ignore[no-untyped-def]
        built.append((repository, frontend))
        frontend.mkdir()
        (frontend / "_shell.html").write_text("current", encoding="utf-8")

    monkeypatch.delenv("ORION_UI_DIR", raising=False)
    monkeypatch.setattr(cli, "source_checkout_root", lambda: tmp_path)
    monkeypatch.setattr(cli, "packaged_ui_directory", lambda: destination)
    monkeypatch.setattr(cli, "build_and_package_ui", build)
    monkeypatch.setattr(cli, "_orion_is_healthy", lambda: True)
    monkeypatch.setattr(cli, "_open_desktop_url", lambda url: None)
    monkeypatch.setattr(cli.uvicorn, "Server", lambda config: pytest.fail("must not start"))

    cli._run_web()

    assert built == [(tmp_path, destination)]


def test_installed_web_never_builds_with_npm(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    destination = tmp_path / ".orion-ui"
    destination.mkdir()
    (destination / "_shell.html").write_text("installed", encoding="utf-8")
    monkeypatch.setattr(cli, "source_checkout_root", lambda: None)
    monkeypatch.setattr(cli, "packaged_ui_directory", lambda: destination)
    monkeypatch.setattr(
        cli, "build_and_package_ui", lambda *args: pytest.fail("installed runtime invoked npm")
    )
    monkeypatch.setattr(cli, "_orion_is_healthy", lambda: True)
    monkeypatch.setattr(cli, "_open_desktop_url", lambda url: None)

    cli._run_web()


def test_bundle_replacement_removes_old_hashed_assets(tmp_path) -> None:  # type: ignore[no-untyped-def]
    source = tmp_path / "dist" / "client"
    source.mkdir(parents=True)
    (source / "_shell.html").write_text("<script src='/new.js'></script>", encoding="utf-8")
    (source / "new.js").write_text("current", encoding="utf-8")
    destination = tmp_path / ".orion-ui"
    destination.mkdir()
    (destination / "_shell.html").write_text("<script src='/old.js'></script>", encoding="utf-8")
    (destination / "old.js").write_text("stale", encoding="utf-8")

    replace_ui_bundle(source, destination)

    assert (destination / "_shell.html").read_text(encoding="utf-8") == (
        "<script src='/new.js'></script>"
    )
    assert (destination / "new.js").read_text(encoding="utf-8") == "current"
    assert not (destination / "old.js").exists()


def test_build_and_package_uses_npm_then_syncs_the_new_bundle(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    repository = tmp_path / "checkout"
    source = repository / "ui" / "dist" / "client"
    source.mkdir(parents=True)
    (source / "_shell.html").write_text("new shell", encoding="utf-8")
    destination = repository / ".orion-ui"
    commands: list[list[str]] = []
    monkeypatch.setattr(ui_package, "_run_npm", commands.append)

    ui_package.build_and_package_ui(repository, destination)

    assert commands == [["npm", "run", "build", "--prefix", str(repository / "ui")]]
    assert (destination / "_shell.html").read_text(encoding="utf-8") == "new shell"


def test_failed_swap_restores_previous_complete_bundle(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    source = tmp_path / "dist" / "client"
    source.mkdir(parents=True)
    (source / "_shell.html").write_text("new", encoding="utf-8")
    destination = tmp_path / ".orion-ui"
    destination.mkdir()
    (destination / "_shell.html").write_text("old", encoding="utf-8")
    replace = os.replace
    calls = 0

    def fail_second_replace(src, dst) -> None:  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("swap failed")
        replace(src, dst)

    monkeypatch.setattr(ui_package.os, "replace", fail_second_replace)

    with pytest.raises(OSError, match="swap failed"):
        replace_ui_bundle(source, destination)
    assert (destination / "_shell.html").read_text(encoding="utf-8") == "old"


def test_dev_web_reports_swap_failure_and_never_serves_stale_bundle(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    source = tmp_path / "ui" / "dist" / "client"
    source.mkdir(parents=True)
    (source / "_shell.html").write_text("new", encoding="utf-8")
    destination = tmp_path / ".orion-ui"
    destination.mkdir()
    (destination / "_shell.html").write_text("old", encoding="utf-8")
    replace = os.replace
    calls = 0

    def fail_swap(src, dst) -> None:  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated disk error")
        replace(src, dst)

    monkeypatch.setattr(ui_package, "_run_npm", lambda command: None)
    monkeypatch.setattr(ui_package.os, "replace", fail_swap)
    monkeypatch.setattr(cli, "source_checkout_root", lambda: tmp_path)
    monkeypatch.setattr(cli, "packaged_ui_directory", lambda: destination)
    monkeypatch.setattr(cli, "_orion_is_healthy", lambda: pytest.fail("must not serve"))
    monkeypatch.setattr(cli.uvicorn, "Server", lambda config: pytest.fail("must not start"))

    with pytest.raises(SystemExit) as failure:
        cli._run_web()
    assert str(destination) in str(failure.value)
    assert "Check write permissions and free disk space" in str(failure.value)
    assert (destination / "_shell.html").read_text(encoding="utf-8") == "old"


def test_dev_build_failure_cannot_start_with_stale_bundle(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    destination = tmp_path / ".orion-ui"
    destination.mkdir()
    (destination / "_shell.html").write_text("stale", encoding="utf-8")
    monkeypatch.setattr(cli, "source_checkout_root", lambda: tmp_path)
    monkeypatch.setattr(cli, "packaged_ui_directory", lambda: destination)
    monkeypatch.setattr(
        cli,
        "build_and_package_ui",
        lambda *args: (_ for _ in ()).throw(RuntimeError("UI build failed; run npm ci")),
    )
    monkeypatch.setattr(cli.uvicorn, "Server", lambda config: pytest.fail("must not start"))

    with pytest.raises(SystemExit, match="UI build failed; run npm ci"):
        cli._run_web()
    assert (destination / "_shell.html").read_text(encoding="utf-8") == "stale"

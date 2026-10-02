"""Visible foreground portable support session using the ordinary worker executor."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import getpass
import json
import logging
import os
import sys
import tempfile
import threading
from pathlib import Path

import httpx

from orion_endpoint.cli import Identity, PairIdentity, data_path, private_write
from orion_endpoint.executor import Executor
from orion_endpoint.policy import Policy
from orion_endpoint.protocol import validate_url
from orion_endpoint.worker import run


def pair(server: str, token: str, name: str, remember: bool) -> Identity:
    with httpx.Client(timeout=15, follow_redirects=False) as client:
        with client.stream(
            "POST",
            server + "/api/endpoints/pair",
            json={
                "token": token,
                "name": name,
                "temporary": not remember,
            },
        ) as response:
            response.raise_for_status()
            data = bytearray()
            for chunk in response.iter_bytes():
                if len(data) + len(chunk) > 2048:
                    raise ValueError("pairing_response")
                data.extend(chunk)
    identity = PairIdentity.model_validate_json(data)
    return Identity(server=server, **identity.model_dump())


async def session(identity: Identity, policy: Policy, temporary: bool) -> None:
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()

    def console() -> None:
        while True:
            try:
                command = input().strip().lower()
            except (EOFError, OSError):
                command = "exit"
            if command in {"exit", "disconnect"}:
                with contextlib.suppress(RuntimeError):
                    loop.call_soon_threadsafe(stopped.set)
                return
            print("Enter Disconnect or Exit to stop the session.", flush=True)

    reader = threading.Thread(target=console, daemon=True)
    reader.start()
    task = asyncio.create_task(
        run(identity.server, identity.endpoint_id, identity.credential, Executor(policy))
    )
    print("Session active in foreground. Enter Disconnect or Exit. Ctrl+C also exits.", flush=True)
    try:
        await stopped.wait()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        if temporary:
            try:
                async with httpx.AsyncClient(timeout=5, follow_redirects=False) as client:
                    response = await client.post(
                        f"{identity.server}/api/endpoints/{identity.endpoint_id}/end",
                        headers={"Authorization": f"Bearer {identity.credential}"},
                    )
                    response.raise_for_status()
                print("Temporary device credential invalidated.", flush=True)
            except Exception:
                print(
                    "Server unreachable; temporary credential expires within two minutes.",
                    flush=True,
                )


def install_browser() -> None:
    # The bundled Playwright driver runs directly; never invoke a host Python interpreter.
    from playwright.__main__ import main as playwright_main

    previous = sys.argv
    try:
        sys.argv = ["playwright", "install", "chromium"]
        playwright_main()
    finally:
        sys.argv = previous


def main() -> None:
    parser = argparse.ArgumentParser(prog="OrionRemote")
    parser.add_argument("--server")
    parser.add_argument("--name")
    parser.add_argument("--remember", action="store_true", help="Explicit persistent device mode")
    parser.add_argument("--data", type=Path, default=data_path())
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("command", nargs="?", choices=["browser"])
    parser.add_argument("action", nargs="?", choices=["install"])
    args = parser.parse_args()
    # Frozen Playwright otherwise looks inside its bundle while its install command
    # uses a user cache. Bind both paths explicitly, without implicit provisioning.
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(data_path() / "browsers"))
    try:
        if args.self_test:
            hello = asyncio.run(Executor(Policy()).hello())
            print(
                json.dumps(
                    {
                        "portable": bool(getattr(sys, "frozen", False)),
                        "version": hello.worker_version,
                        "platform": hello.platform,
                        "capabilities": hello.capabilities,
                    }
                )
            )
            return
        if args.command == "browser" and args.action == "install":
            install_browser()
            return
        print("Orion Remote · visible outbound support session", flush=True)
        print(
            "Temporary session is the default. --remember explicitly remembers this device.",
            flush=True,
        )
        policy = Policy.load(args.policy) if args.policy else Policy()
        if args.policy is None:
            root = input("Optional allowed folder (blank disables files): ").strip()
            if root:
                root = str(Path(root).resolve(strict=True))
                policy.read_roots = [root]
                if input("Permit file writes in this folder? [y/N]: ").lower() == "y":
                    policy.write_roots = [root]
            policy.desktop_capture = input("Permit screen viewing? [y/N]: ").lower() == "y"
            if policy.desktop_capture:
                policy.desktop_control = (
                    input("Permit keyboard/mouse control? [y/N]: ").lower() == "y"
                )
            policy.browser = input("Permit isolated browser automation? [y/N]: ").lower() == "y"
        state = args.data / "identity.json"
        if args.remember and state.exists():
            if state.stat().st_size > 4096:
                raise ValueError("identity_size")
            identity = Identity.model_validate_json(state.read_text(encoding="utf-8"))
        else:
            server = validate_url(args.server or input("Orion HTTPS server URL: ").strip())
            name = args.name or input("Display name: ").strip()
            token = os.environ.pop("ORION_PAIRING_TOKEN", None) or getpass.getpass(
                "One-time pairing code: "
            )
            identity = pair(server, token, name, args.remember)
            if args.remember:
                private_write(state, identity.model_dump())
        logging.basicConfig(level=logging.INFO, format="%(name)s %(message)s")
        # Only state owned by this run is removed. No OS/security/audit history is touched.
        with tempfile.TemporaryDirectory(prefix="orion-remote-session-") as temporary:
            if policy.browser and policy.browser_download_directory is None:
                directory = Path(temporary) / "downloads"
                directory.mkdir()
                policy.browser_download_directory = str(directory)
                policy.write_roots.append(str(directory))
            asyncio.run(session(identity, policy, not args.remember))
        print("Disconnected. Worker-owned temporary session state removed.", flush=True)
    except KeyboardInterrupt:
        print("Disconnected. Worker-owned temporary session state removed.", flush=True)
    except Exception:
        parser.exit(
            1, "Portable session unavailable; check pairing, policy and server connectivity.\n"
        )


if __name__ == "__main__":
    main()

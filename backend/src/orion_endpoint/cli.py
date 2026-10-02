"""Interactive lightweight worker operations; secrets never appear in status/logs."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import logging
import os
import subprocess
import sys
import uuid
from pathlib import Path

import httpx
from pydantic import Field

from orion_endpoint.executor import Executor
from orion_endpoint.policy import Policy
from orion_endpoint.protocol import Strict, validate_url
from orion_endpoint.worker import run


class PairIdentity(Strict):
    endpoint_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    credential: str = Field(min_length=32, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


class Identity(PairIdentity):
    server: str = Field(max_length=2048)


def data_path() -> Path:
    override = os.getenv("ORION_WORKER_DATA")
    if override:
        return Path(override)
    return Path.home() / ".orion-worker"


def private_write(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        path.parent.chmod(0o700)
    # Explicit Windows DACL inherited by all state; checked before storing the secret.
    else:
        account = getpass.getuser()
        result = subprocess.run(
            ["icacls", str(path.parent), "/inheritance:r", "/grant:r", f"{account}:(OI)(CI)F"],
            capture_output=True,
            check=False,
        )
        if result.returncode:
            raise OSError("private_storage_unavailable")
    if path.is_symlink():
        raise OSError("private_storage_unavailable")
    temporary = path.with_name(f".identity-{uuid.uuid4().hex}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream)
            stream.write("\n")
        os.replace(temporary, path)
        if os.name != "nt":
            path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(prog="orion-worker")
    parser.add_argument("--data", type=Path, default=data_path())
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("configure")
    pairing = commands.add_parser("pair")
    pairing.add_argument("--server", required=True)
    pairing.add_argument("--name", default="My endpoint")
    pairing.add_argument("--token", help="Tests only; normally prompt or ORION_PAIRING_TOKEN")
    commands.add_parser("run")
    commands.add_parser("status")
    commands.add_parser("revoke-local")
    browser = commands.add_parser("browser")
    browser.add_argument("action", choices=["install"])
    args = parser.parse_args()
    state_path = args.data / "identity.json"
    try:
        if args.command == "configure":
            path = args.data / "policy.json"
            if path.exists():
                parser.exit(1, "Policy already exists; edit it explicitly.\n")
            private_write(path, Policy().model_dump())
        elif args.command == "pair":
            if state_path.exists():
                parser.exit(1, "Already paired; revoke on the server and revoke-local first.\n")
            server = validate_url(args.server)
            token = (
                args.token or os.getenv("ORION_PAIRING_TOKEN") or getpass.getpass("Pairing token: ")
            )
            with httpx.Client(timeout=15, follow_redirects=False) as client:
                with client.stream(
                    "POST",
                    f"{server}/api/endpoints/pair",
                    json={"token": token, "name": args.name},
                ) as response:
                    if response.status_code != 200:
                        parser.exit(1, "Pairing rejected.\n")
                    payload = bytearray()
                    for chunk in response.iter_bytes():
                        if len(payload) + len(chunk) > 2048:
                            raise ValueError("identity_size")
                        payload.extend(chunk)
                    identity = json.loads(payload)
            identity = PairIdentity.model_validate(identity).model_dump()
            private_write(state_path, {"server": server, **identity})
        elif args.command == "status":
            if state_path.exists():
                identity = json.loads(state_path.read_text(encoding="utf-8"))
                print(json.dumps({"paired": True, "endpoint_id": identity["endpoint_id"]}))
            else:
                print('{"paired": false}')
        elif args.command == "revoke-local":
            state_path.unlink(missing_ok=True)
            print(
                "Local identity removed. Revoke the endpoint on Orion to invalidate the credential."
            )
        elif args.command == "browser":
            subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        else:
            if state_path.stat().st_size > 4096:
                raise ValueError("identity_size")
            identity = Identity.model_validate_json(
                state_path.read_text(encoding="utf-8")
            ).model_dump()
            policy = Policy.load(args.data / "policy.json")
            logging.basicConfig(level=logging.INFO, format="%(name)s %(message)s")
            asyncio.run(
                run(
                    identity["server"],
                    identity["endpoint_id"],
                    identity["credential"],
                    Executor(policy),
                )
            )
    except KeyboardInterrupt:
        pass
    except Exception:
        parser.exit(1, "Worker configuration, storage or runtime unavailable.\n")


if __name__ == "__main__":
    main()
